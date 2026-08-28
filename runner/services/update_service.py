"""Network-share update discovery and staging for the packaged application.

The application is built by PyInstaller in *onedir* mode, so an update is a
complete PytestRunner directory, not just PytestRunner.exe.  The shared folder
therefore publishes a ZIP containing that directory plus a small latest.json
manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


UPDATE_DIR_ENV = "PYTESTRUNNER_UPDATE_DIR"
SOURCE_FILE = "update_source.txt"
MANIFEST_FILE = "latest.json"
APP_EXE = "PytestRunner.exe"


class UpdateError(RuntimeError):
    """Raised when a published update is invalid or cannot be prepared."""


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    package: str
    sha256: str


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    staged_app_dir: Path
    install_dir: Path
    executable: Path
    temp_dir: Path


def application_dir() -> Path:
    """Directory that contains the running packaged application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def configured_update_dir() -> Path | None:
    """Resolve the corporate update share without hard-coding it in source.

    Deployment can either set PYTESTRUNNER_UPDATE_DIR or place an
    ``update_source.txt`` beside PytestRunner.exe.  The latter is convenient for
    a copied portable installation and deliberately survives future updates.
    """
    env = os.environ.get(UPDATE_DIR_ENV, "").strip()
    if env:
        return Path(env)

    source_file = application_dir() / SOURCE_FILE
    try:
        value = source_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(value) if value else None


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.strip().split("."))
    except ValueError as exc:
        raise UpdateError(f"Invalid version: {value!r}") from exc


def is_newer(candidate: str, current: str) -> bool:
    """Return True when candidate is a strictly newer dotted numeric version."""
    a = _version_tuple(candidate)
    b = _version_tuple(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def read_manifest(update_dir: Path) -> UpdateManifest:
    path = Path(update_dir) / MANIFEST_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UpdateError(f"Cannot read update manifest: {path}") from exc
    except ValueError as exc:
        raise UpdateError(f"Invalid JSON in update manifest: {path}") from exc

    try:
        version = str(data["version"]).strip()
        package = str(data["package"]).strip()
        sha256 = str(data["sha256"]).strip().lower()
    except (KeyError, TypeError) as exc:
        raise UpdateError("latest.json must contain version, package and sha256") from exc

    _version_tuple(version)
    if not package or Path(package).name != package:
        raise UpdateError("Update package must be a simple file name")
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise UpdateError("Invalid SHA-256 in latest.json")
    return UpdateManifest(version, package, sha256)


def check_for_update(current_version: str) -> tuple[Path, UpdateManifest] | None:
    update_dir = configured_update_dir()
    if update_dir is None:
        return None
    manifest = read_manifest(update_dir)
    if not is_newer(manifest.version, current_version):
        return None
    return update_dir, manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(zip_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise UpdateError(f"Unsafe path in update archive: {member.filename}") from exc
        archive.extractall(destination)


def prepare_update(update_dir: Path, manifest: UpdateManifest) -> PreparedUpdate:
    """Copy, verify and unpack an update while the current UI stays usable."""
    package = Path(update_dir) / manifest.package
    if not package.is_file():
        raise UpdateError(f"Update package not found: {package}")

    temp_dir = Path(tempfile.mkdtemp(prefix="PytestRunner-update-"))
    copied = temp_dir / manifest.package
    extracted = temp_dir / "staged"
    extracted.mkdir()

    try:
        shutil.copy2(package, copied)
        actual = _sha256(copied)
        if actual != manifest.sha256:
            raise UpdateError(
                "Update package checksum mismatch. "
                f"Expected {manifest.sha256}, got {actual}."
            )
        _safe_extract(copied, extracted)

        direct = extracted / APP_EXE
        nested = extracted / "PytestRunner" / APP_EXE
        if direct.is_file():
            staged_app_dir = extracted
        elif nested.is_file():
            staged_app_dir = nested.parent
        else:
            raise UpdateError(
                f"Update archive does not contain {APP_EXE} at its root "
                "or inside a PytestRunner directory."
            )

        install_dir = application_dir()
        executable = install_dir / APP_EXE
        if not executable.is_file():
            raise UpdateError("Automatic install is only available from PytestRunner.exe")

        return PreparedUpdate(
            version=manifest.version,
            staged_app_dir=staged_app_dir,
            install_dir=install_dir,
            executable=executable,
            temp_dir=temp_dir,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def make_restart_script(prepared: PreparedUpdate, pid: int) -> Path:
    """Create a temporary cmd script that waits, replaces files, and restarts.

    The script lives outside the install directory so it can keep running while
    every file in the PyInstaller directory is replaced.  ``robocopy /E`` is
    intentional rather than ``/MIR``: deployment-local files such as
    update_source.txt must not be deleted by an application update.
    """
    script = prepared.temp_dir / "apply_update.cmd"
    staged = str(prepared.staged_app_dir)
    install = str(prepared.install_dir)
    executable = str(prepared.executable)
    temp_dir = str(prepared.temp_dir)

    content = f'''@echo off\r\nsetlocal\r\nset "TARGET_PID={int(pid)}"\r\nfor /L %%I in (1,1,30) do (\r\n  tasklist /FI "PID eq %TARGET_PID%" 2>nul | findstr /R /C:"[ ]%TARGET_PID%[ ]" >nul\r\n  if errorlevel 1 goto :process_stopped\r\n  timeout /T 1 /NOBREAK >nul\r\n)\r\nexit /b 10\r\n\r\n:process_stopped\r\nrobocopy "{staged}" "{install}" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\nset "RC=%ERRORLEVEL%"\r\nif %RC% GEQ 8 exit /b %RC%\r\nstart "" "{executable}"\r\ntimeout /T 2 /NOBREAK >nul\r\nrmdir /S /Q "{temp_dir}" 2>nul\r\nexit /b 0\r\n'''
    script.write_text(content, encoding="utf-8", newline="")
    return script
