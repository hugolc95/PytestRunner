"""Ouverture d'un log avec Notepad++ depuis l'interface courante.

Ce module reste volontairement dans ``runner`` : l'executable courant exclut
l'ancienne interface ``gui_qt`` de son bundle PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from runner.ui.widgets import ErrorDialog


def open_log_folder(path: Path) -> None:
    """Open the exact folder, using Explorer's native API on Windows."""
    path = Path(path).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Log folder no longer exists: {path}")
    native_error = ""
    if sys.platform == "win32":
        try:
            os.startfile(str(path), "explore")
            return
        except OSError as exc:
            native_error = str(exc)
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        detail = f" ({native_error})" if native_error else ""
        raise OSError(f"The system file explorer could not open {path}{detail}")


def find_notepad_plus_plus() -> Path | None:
    """Retrouve Notepad++ dans le PATH ou ses emplacements Windows usuels."""
    for command in ("notepad++", "notepad++.exe"):
        found = shutil.which(command)
        if found:
            return Path(found)

    roots: list[str] = []
    for variable in ("PROGRAMW6432", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        value = os.environ.get(variable, "").strip()
        if value and value not in roots:
            roots.append(value)

    candidates = [Path(root) / "Notepad++" / "notepad++.exe" for root in roots]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(
            Path(local_app_data) / "Programs" / "Notepad++" / "notepad++.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


def open_in_notepad_plus_plus(parent, path: Path) -> bool:
    """Ouvre le fichier complet dans Notepad++, avec une erreur explicite."""
    path = Path(path)
    if not path.is_file():
        ErrorDialog.show_error(
            parent, "Log not found", f"This log no longer exists:\n{path}")
        return False

    executable = find_notepad_plus_plus()
    if executable is None:
        ErrorDialog.show_error(
            parent, "Notepad++ not found",
            "Notepad++ was not found in PATH or in its usual Windows folders.",
            f"Log file:\n{path}")
        return False

    try:
        subprocess.Popen([str(executable), str(path)])
    except OSError as exc:
        ErrorDialog.show_error(
            parent, "Could not open Notepad++", f"Could not open:\n{path}", str(exc))
        return False
    return True
