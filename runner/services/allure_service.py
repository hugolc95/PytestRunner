"""Pont entre le domaine et Qt pour la generation du rapport Allure.

`allure generate` est un sous-processus qui peut prendre plusieurs secondes.
Il tourne desormais automatiquement apres chaque run (pas seulement au clic
sur le bouton) : le lancer depuis le fil de l'interface figerait la fenetre a
chaque fin de run, sans que l'utilisateur n'ait rien demande.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from runner.domain import interpreter


class AllureReportWorker(QThread):
    """Genere un rapport Allure hors du fil de l'interface.

    Important : le signal public ``done`` n'est emis qu'APRES le signal Qt
    ``finished``. L'ancienne version emettait ``done`` directement depuis
    ``run()``. La fenetre principale libere sa reference au worker dans le
    slot de ``done`` ; sous Windows, Qt pouvait alors detruire le QThread
    quelques instructions avant le vrai retour de ``run()``, ce qui termine
    brutalement le processus avec ``QThread: Destroyed while thread is still
    running``. C'etait visible comme un freeze puis une fermeture de
    l'interface juste apres la fin des tests.
    """

    done = Signal(bool, str)  # succes, detail (vide si succes)

    def __init__(self, allure_bin: str, resultats: Path, rapport: Path,
                 env: dict, parent=None):
        super().__init__(parent)
        self._allure_bin = allure_bin
        self._resultats = resultats
        self._rapport = rapport
        self._env = env
        self._resultat: tuple[bool, str] = (False, "Allure generation did not run")

        # ``finished`` est emis par QThread seulement une fois ``run()``
        # entierement sorti. Comme l'objet worker appartient au thread GUI,
        # ce slot est ensuite execute dans le thread GUI et peut emettre
        # ``done`` sans risque que la fenetre detruise un thread encore actif.
        self.finished.connect(self._emit_done_after_finished)

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
            self._resultat = (False, str(exc))
            return

        if resultat.returncode != 0:
            self._resultat = (
                False,
                (resultat.stderr or resultat.stdout or "").strip(),
            )
            return

        self._resultat = (True, "")

    def _emit_done_after_finished(self) -> None:
        """Transmet le resultat uniquement lorsque QThread est bien termine."""
        self.done.emit(*self._resultat)
