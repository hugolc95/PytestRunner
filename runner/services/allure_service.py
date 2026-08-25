"""Pont entre le domaine et Qt pour la generation du rapport Allure.

`allure generate` est un sous-processus qui peut prendre plusieurs secondes.
Il tourne desormais automatiquement apres chaque run (pas seulement au clic
sur le bouton) : le lancer depuis le fil de l'interface figerait la fenetre a
chaque fin de run, sans que l'utilisateur n'ait rien demande.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from runner.domain import interpreter


class AllureReportWorker(QThread):
    """Genere un rapport Allure hors du fil de l'interface."""

    done = pyqtSignal(bool, str)  # succes, detail (vide si succes)

    def __init__(self, allure_bin: str, resultats: Path, rapport: Path,
                env: dict, parent=None):
        super().__init__(parent)
        self._allure_bin = allure_bin
        self._resultats = resultats
        self._rapport = rapport
        self._env = env

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        try:
            resultat = subprocess.run(
                [self._allure_bin, "generate", "--clean", "-o", str(self._rapport),
                 str(self._resultats)],
                capture_output=True, text=True, timeout=120,
                creationflags=interpreter.subprocess_flags(),
                env=self._env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.done.emit(False, str(exc))
            return
        if resultat.returncode != 0:
            self.done.emit(False, (resultat.stderr or resultat.stdout or "").strip())
            return
        self.done.emit(True, "")
