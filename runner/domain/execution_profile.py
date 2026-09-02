"""Portable execution profiles.

A profile is deliberately small: one ordered test sequence, one YAML
configuration and a few execution/report options.  External files are parsed
as untrusted input and are never written to the workspace while being checked.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

import yaml


FORMAT = "pytest-runner-execution-profile"
FORMAT_VERSION = 1
EXTENSION = ".pytest-profile"
MAX_PROFILE_BYTES = 10 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_STEPS = 10_000
MAX_REPETITIONS = 10_000
MAX_RERUN_FAILURES = 100
MAX_TOTAL_EXECUTIONS = 1_000_000
_NODEID = re.compile(r"^[^\x00\r\n]+::[^\x00\r\n]+$")


class ProfileValidationError(ValueError):
    """Raised when an imported profile is invalid, unsafe or unsupported."""


@dataclass
class ExecutionOptions:
    repetitions: int = 1
    rerun_failures: int = 0
    stop_after_failure: bool = False


@dataclass
class ReportOptions:
    generate_allure: bool = True
    save_complete_logs: bool = True


@dataclass
class ExecutionProfile:
    name: str
    sequence: list[str]
    configuration_name: str
    configuration_text: str
    description: str = ""
    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    reports: ReportOptions = field(default_factory=ReportOptions)
    source: str = "local"

    @property
    def total_executions(self) -> int:
        return len(self.sequence) * self.execution.repetitions


@dataclass(frozen=True)
class ProfileValidation:
    profile: ExecutionProfile
    matched_steps: tuple[str, ...]
    missing_steps: tuple[str, ...]

    @property
    def has_warnings(self) -> bool:
        return bool(self.missing_steps)


def _safe_name(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ProfileValidationError(f"{label} must be text.")
    clean = value.strip()
    if not clean or len(clean) > maximum or "\x00" in clean:
        raise ProfileValidationError(f"{label} is empty or too long.")
    return clean


def _optional_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ProfileValidationError(f"{label} is invalid or too long.")
    return value.strip()


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileValidationError(f"{label} must be an integer.")
    if not minimum <= value <= maximum:
        raise ProfileValidationError(
            f"{label} must be between {minimum} and {maximum}.")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileValidationError(f"{label} must be true or false.")
    return value


def _configuration_filename(value: object) -> str:
    name = _safe_name(value, "Configuration filename", 180)
    pure = PurePosixPath(name)
    if (pure.is_absolute() or len(pure.parts) != 1 or name in (".", "..")
            or pure.suffix.lower() not in (".yml", ".yaml")):
        raise ProfileValidationError("The configuration filename is unsafe.")
    return name


def _manifest(profile: ExecutionProfile, checksum: str) -> dict:
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "profile": {
            "id": profile.profile_id,
            "name": profile.name,
            "description": profile.description,
        },
        "configuration": {
            "file": profile.configuration_name,
            "sha256": checksum,
        },
        "sequence": [
            {"step_id": f"step-{index:05d}", "test": nodeid}
            for index, nodeid in enumerate(profile.sequence, 1)
        ],
        "execution": asdict(profile.execution),
        "reports": asdict(profile.reports),
    }


def validate_profile(profile: ExecutionProfile) -> None:
    _safe_name(profile.name, "Profile name", 120)
    _safe_name(profile.profile_id, "Profile identifier", 120)
    _configuration_filename(profile.configuration_name)
    if len(profile.configuration_text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ProfileValidationError("The YAML configuration is too large.")
    try:
        parsed_config = yaml.safe_load(profile.configuration_text)
    except yaml.YAMLError as exc:
        raise ProfileValidationError(f"The YAML configuration is invalid: {exc}") from exc
    if not isinstance(parsed_config, dict):
        raise ProfileValidationError("The YAML configuration must contain a mapping.")
    if not profile.sequence or len(profile.sequence) > MAX_STEPS:
        raise ProfileValidationError(
            f"A profile must contain between 1 and {MAX_STEPS} steps.")
    for nodeid in profile.sequence:
        if not isinstance(nodeid, str) or not _NODEID.match(nodeid):
            raise ProfileValidationError(f"Invalid pytest test identifier: {nodeid!r}")
        path = nodeid.split("::", 1)[0].replace("\\", "/")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ":" in path or ".." in pure.parts:
            raise ProfileValidationError(f"Unsafe test path: {nodeid}")
    _integer(profile.execution.repetitions, "Repetitions", 1, MAX_REPETITIONS)
    _integer(profile.execution.rerun_failures, "Re-run failures", 0, MAX_RERUN_FAILURES)
    _boolean(profile.execution.stop_after_failure, "Stop after failure")
    _boolean(profile.reports.generate_allure, "Generate Allure")
    _boolean(profile.reports.save_complete_logs, "Save complete logs")
    if profile.total_executions > MAX_TOTAL_EXECUTIONS:
        raise ProfileValidationError(
            f"The profile exceeds {MAX_TOTAL_EXECUTIONS:,} total executions.")


def export_profile(profile: ExecutionProfile, destination: str | Path) -> Path:
    validate_profile(profile)
    target = Path(destination)
    if target.suffix.lower() != EXTENSION:
        target = target.with_name(target.name + EXTENSION)
    config = profile.configuration_text.encode("utf-8")
    checksum = hashlib.sha256(config).hexdigest()
    manifest = json.dumps(
        _manifest(profile, checksum), ensure_ascii=False, indent=2).encode("utf-8")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest)
        archive.writestr(f"configuration/{profile.configuration_name}", config)
    return target


def _read_member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise ProfileValidationError(f"Required file is missing: {name}") from exc
    if info.file_size > limit:
        raise ProfileValidationError(f"{name} is too large.")
    with archive.open(info, "r") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ProfileValidationError(f"{name} is too large.")
    return data


def inspect_profile(path: str | Path, available_nodeids=()) -> ProfileValidation:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_PROFILE_BYTES:
        raise ProfileValidationError("The profile file is missing or too large.")
    if source.suffix.lower() != EXTENSION:
        raise ProfileValidationError(f"Expected a {EXTENSION} file.")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            if len(infos) != 2:
                raise ProfileValidationError("The archive contains unexpected files.")
            for info in infos:
                pure = PurePosixPath(info.filename)
                if pure.is_absolute() or ".." in pure.parts or info.is_dir():
                    raise ProfileValidationError("The archive contains an unsafe path.")
                # Unix symlinks carry 0120000 in the upper mode bits.
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ProfileValidationError("Symbolic links are not allowed.")
            raw_manifest = _read_member(archive, "manifest.json", MAX_MANIFEST_BYTES)
            try:
                manifest = json.loads(raw_manifest.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProfileValidationError("The manifest is not valid JSON.") from exc
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
                raise ProfileValidationError("This is not a Pytest Runner profile.")
            if manifest.get("format_version") != FORMAT_VERSION:
                raise ProfileValidationError(
                    f"Unsupported profile version: {manifest.get('format_version')!r}.")
            allowed = {"format", "format_version", "profile", "configuration",
                       "sequence", "execution", "reports"}
            if set(manifest) != allowed:
                raise ProfileValidationError("The manifest contains unknown fields.")
            meta, config_meta = manifest.get("profile"), manifest.get("configuration")
            execution, reports = manifest.get("execution"), manifest.get("reports")
            steps = manifest.get("sequence")
            if not all(isinstance(value, dict) for value in
                       (meta, config_meta, execution, reports)) or not isinstance(steps, list):
                raise ProfileValidationError("The manifest structure is invalid.")
            config_name = _configuration_filename(config_meta.get("file"))
            config = _read_member(
                archive, f"configuration/{config_name}", MAX_CONFIG_BYTES)
            if hashlib.sha256(config).hexdigest() != config_meta.get("sha256"):
                raise ProfileValidationError("The configuration checksum does not match.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ProfileValidationError("The profile archive is unreadable.") from exc

    if set(meta) != {"id", "name", "description"}:
        raise ProfileValidationError("The profile metadata contains unknown fields.")
    if set(config_meta) != {"file", "sha256"}:
        raise ProfileValidationError("The configuration metadata is invalid.")
    if set(execution) != {"repetitions", "rerun_failures", "stop_after_failure"}:
        raise ProfileValidationError("The execution settings are invalid.")
    if set(reports) != {"generate_allure", "save_complete_logs"}:
        raise ProfileValidationError("The report settings are invalid.")
    nodeids: list[str] = []
    step_ids: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"step_id", "test"}:
            raise ProfileValidationError("A sequence step is invalid.")
        step_id = _safe_name(step["step_id"], "Step identifier", 120)
        if step_id in step_ids:
            raise ProfileValidationError("Sequence step identifiers must be unique.")
        step_ids.add(step_id)
        nodeids.append(step["test"])
    try:
        config_text = config.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileValidationError("The YAML configuration must use UTF-8.") from exc
    profile = ExecutionProfile(
        profile_id=_safe_name(meta.get("id"), "Profile identifier", 120),
        name=_safe_name(meta.get("name"), "Profile name", 120),
        description=_optional_text(
            meta.get("description", ""), "Profile description", 1000),
        sequence=nodeids,
        configuration_name=config_name,
        configuration_text=config_text,
        execution=ExecutionOptions(
            repetitions=_integer(execution.get("repetitions"), "Repetitions", 1, MAX_REPETITIONS),
            rerun_failures=_integer(execution.get("rerun_failures"), "Re-run failures", 0, MAX_RERUN_FAILURES),
            stop_after_failure=_boolean(execution.get("stop_after_failure"), "Stop after failure"),
        ),
        reports=ReportOptions(
            generate_allure=_boolean(reports.get("generate_allure"), "Generate Allure"),
            save_complete_logs=_boolean(reports.get("save_complete_logs"), "Save complete logs"),
        ),
        source="imported",
    )
    validate_profile(profile)
    available = set(available_nodeids)
    matched = tuple(nodeid for nodeid in nodeids if nodeid in available)
    missing = tuple(nodeid for nodeid in nodeids if available and nodeid not in available)
    return ProfileValidation(profile, matched, missing)


class ProfileStore:
    """Local profile library backed by the same validated portable format."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, profile_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", profile_id)
        return self.root / f"{safe_id}{EXTENSION}"

    def save(self, profile: ExecutionProfile) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return export_profile(profile, self._path(profile.profile_id))

    def delete(self, profile_id: str) -> None:
        path = self._path(profile_id)
        if path.exists():
            path.unlink()

    def list(self) -> list[ExecutionProfile]:
        if not self.root.exists():
            return []
        profiles: list[ExecutionProfile] = []
        for path in self.root.glob(f"*{EXTENSION}"):
            try:
                profiles.append(inspect_profile(path).profile)
            except ProfileValidationError:
                continue
        return sorted(profiles, key=lambda profile: profile.name.casefold())

    def import_copy(self, source: str | Path, available_nodeids=()) -> ProfileValidation:
        validation = inspect_profile(source, available_nodeids)
        profile = validation.profile
        # Never overwrite an existing local profile merely because an external
        # file reused its identifier.
        if self._path(profile.profile_id).exists():
            profile.profile_id = str(uuid.uuid4())
        self.save(profile)
        return validation
