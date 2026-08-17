"""Pont entre le domaine et Qt pour l'interrogation d'un interpreteur.

Un probe lance un vrai processus Python et y importe pytest : plusieurs
centaines de millisecondes, parfois davantage sous Windows avec un antivirus.
Le faire depuis le fil de l'interface gele la fenetre.
"""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from runner.domain import interpreter


class ProbeWorker(QThread):
    """Interroge un interpreteur hors du fil de l'interface."""

    done = pyqtSignal(object)  # InterpreterInfo

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        # use_cache=False : un "Test" demande par l'utilisateur doit refleter
        # l'etat reel maintenant (pytest vient peut-etre d'etre installe). Le
        # resultat alimente quand meme le cache partage, donc le prochain
        # lancement de tests reste instantane.
        self.done.emit(interpreter.probe(self._path, use_cache=False))
