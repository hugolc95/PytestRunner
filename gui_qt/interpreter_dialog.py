"""Boite de dialogue de choix de l'interpreteur Python utilise pour les tests.

Ce reglage est global (QSettings) ; un workspace peut le surcharger via la cle
`python_executable` de son config.yml, auquel cas la boite l'indique et le champ
global reste sans effet pour ce workspace.
"""

from __future__ import annotations

import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.python_interpreter import (
    InterpreterInfo,
    default_interpreter,
    interpreter_from_config,
    probe_interpreter,
)

from gui_qt.styles.styles import primary_button, toolbar_button


class _ProbeWorker(QThread):
    """Interroge l'interpreteur hors du thread UI : un python.exe injoignable
    (chemin reseau, antivirus) peut mettre plusieurs secondes a repondre."""

    done_signal = pyqtSignal(object)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        # use_cache=False : "Tester" doit refleter l'etat reel maintenant (pytest
        # vient peut-etre d'etre installe). Le resultat alimente quand meme le
        # cache partage, donc le prochain lancement de tests reste instantane.
        self.done_signal.emit(probe_interpreter(self.path, use_cache=False))


class InterpreterDialog(QDialog):
    def __init__(self, current: str, workspace: str | None = None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Interpreteur Python des tests")
        self.resize(680, 260)
        self._probe: _ProbeWorker | None = None
        self._workspace = workspace

        explanation = QLabel(
            "L'interface et les tests tournent dans deux processus separes : pytest est "
            "lance en sous-processus. Vous pouvez donc utiliser ici un Python different "
            "de celui de l'interface, par exemple un Python 64 bits pour des tests qui "
            "chargent des DLL natives."
            "<br><br>"
            "Cet interpreteur doit avoir <b>pytest</b> installe "
            "(et <b>pytest-xdist</b> pour l'option Parallel)."
        )
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.RichText)

        self.path_edit = QLineEdit(current)
        self.path_edit.setPlaceholderText(
            "Chemin de python.exe (laisser vide pour utiliser le Python par defaut)"
        )
        self.path_edit.setClearButtonEnabled(True)

        browse_button = QPushButton("Parcourir...")
        browse_button.setStyleSheet(toolbar_button())
        browse_button.clicked.connect(self._browse)

        test_button = QPushButton("Tester")
        test_button.setStyleSheet(toolbar_button())
        test_button.clicked.connect(self._test)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_button)
        path_row.addWidget(test_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.override_label = QLabel("")
        self.override_label.setWordWrap(True)
        self.override_label.setStyleSheet("color: #b26a00;")

        override = interpreter_from_config(workspace)
        if override:
            self.override_label.setText(
                f"Note : le config.yml de ce workspace impose deja un interpreteur "
                f"({override}). Il a priorite sur le reglage ci-dessus tant que ce "
                f"workspace est charge."
            )

        ok_button = QPushButton("Enregistrer")
        ok_button.setStyleSheet(primary_button())
        ok_button.clicked.connect(self.accept)

        cancel_button = QPushButton("Annuler")
        cancel_button.setStyleSheet(toolbar_button())
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(ok_button)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(path_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.override_label)
        layout.addStretch(1)
        layout.addLayout(button_row)

        self._test()

    def interpreter_path(self) -> str:
        return self.path_edit.text().strip()

    def _browse(self):
        start_dir = os.path.dirname(self.interpreter_path()) or os.path.expanduser("~")
        filter_ = "Python (python.exe python3.exe)" if os.name == "nt" else "Tous les fichiers (*)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir l'interpreteur Python des tests", start_dir, filter_
        )
        if path:
            self.path_edit.setText(path)
            self._test()

    def _test(self):
        path = self.interpreter_path() or default_interpreter()

        if not path:
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText(
                "Aucun Python trouve automatiquement : indiquez le chemin de python.exe."
            )
            return

        self.status_label.setStyleSheet("color: #555;")
        self.status_label.setText(f"Verification de {path} ...")

        if self._probe is not None and self._probe.isRunning():
            return

        self._probe = _ProbeWorker(path)
        self._probe.done_signal.connect(self._on_probe_done)
        self._probe.start()

    def _on_probe_done(self, info: InterpreterInfo):
        if info.ok:
            color = "#1b7a34" if info.pytest_version else "#b26a00"
        else:
            color = "#b00020"

        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(f"{info.path}\n{info.summary()}")
