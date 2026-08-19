"""Ouverture d'un log avec Notepad++ depuis l'interface courante.

Ce module reste volontairement dans ``runner`` : l'executable courant exclut
l'ancienne interface ``gui_qt`` de son bundle PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import QMessageBox


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
        QMessageBox.warning(
            parent,
            "Log not found",
            f"This log no longer exists:\n{path}",
        )
        return False

    executable = find_notepad_plus_plus()
    if executable is None:
        QMessageBox.warning(
            parent,
            "Notepad++ not found",
            "Notepad++ was not found in PATH or in its usual Windows folders.\n\n"
            f"Log file:\n{path}",
        )
        return False

    try:
        subprocess.Popen([str(executable), str(path)])
    except OSError as exc:
        QMessageBox.critical(
            parent,
            "Could not open Notepad++",
            f"Could not open:\n{path}\n\n{exc}",
        )
        return False
    return True
