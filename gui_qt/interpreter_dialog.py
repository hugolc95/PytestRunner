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

        self.setWindowTitle("Test Python interpreter")
        self.resize(680, 260)
        self._probe: _ProbeWorker | None = None
        self._workspace = workspace

        explanation = QLabel(
            "The interface and the tests run in two separate processes: pytest is "
            "started as a subprocess. You can therefore use a different Python here "
            "than the interface's, for example a 64-bit Python for tests that load "
            "native DLLs."
            "<br><br>"
            "This interpreter must have <b>pytest</b> installed "
            "(and <b>pytest-xdist</b> for the Parallel option)."
        )
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.RichText)

        self.path_edit = QLineEdit(current)
        self.path_edit.setPlaceholderText(
            "Path to python.exe (leave empty to use the default Python)"
        )
        self.path_edit.setClearButtonEnabled(True)

        browse_button = QPushButton("Browse...")
        browse_button.setStyleSheet(toolbar_button())
        browse_button.clicked.connect(self._browse)

        test_button = QPushButton("Test")
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
                f"Note: this workspace's config.yml already forces an interpreter "
                f"({override}). It takes priority over the setting above while this "
                f"workspace is loaded."
            )

        ok_button = QPushButton("Save")
        ok_button.setStyleSheet(primary_button())
        ok_button.clicked.connect(self.accept)

        cancel_button = QPushButton("Cancel")
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
        filter_ = "Python (python.exe python3.exe)" if os.name == "nt" else "All files (*)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the test Python interpreter", start_dir, filter_
        )
        if path:
            self.path_edit.setText(path)
            self._test()

    def _test(self):
        path = self.interpreter_path() or default_interpreter()

        if not path:
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText(
                "No Python found automatically: specify the path to python.exe."
            )
            return

        self.status_label.setStyleSheet("color: #555;")
        self.status_label.setText(f"Checking {path} ...")

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
