"""Boite de dialogue de choix de l'interpreteur Python utilise pour les tests.

Ce reglage est global (QSettings persistees par la fenetre). Un workspace peut
le surcharger via la cle `python_executable` de sa configuration, auquel cas
la boite le signale : le champ ci-dessous resterait sans effet pour ce
workspace tant qu'il est charge.

Le champ n'est pas juste un chemin qu'on tape : un "Test" verifie qu'il s'agit
bien d'un Python, avec pytest installe. Decouvrir apres coup, au premier
lancement de tests, qu'on a fait une faute de frappe dans le chemin est une
mauvaise surprise qu'un bouton suffit a eviter.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from runner.domain.interpreter import InterpreterInfo, default
from runner.services.interpreter_service import ProbeWorker
from runner.ui import theme
from runner.ui import tokens as t


class InterpreterDialog(QDialog):
    saved = Signal(str)

    def __init__(self, current: str, declared_by_workspace: str = "", parent=None,
                 embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Test Python interpreter")
        self.resize(640, 260)
        self._probe: ProbeWorker | None = None
        self._status_is_error = False

        self.explanation = QLabel(
            "The interface and the tests run in two separate processes: pytest "
            "is started as a subprocess. You can therefore use a different "
            "Python here than the interface's — for example a 64-bit Python "
            "for tests that load native DLLs."
            "<br><br>"
            "This interpreter must have <b>pytest</b> installed.")
        self.explanation.setWordWrap(True)
        self.explanation.setTextFormat(Qt.RichText)

        self.path_field = QLineEdit(current)
        self.path_field.setPlaceholderText(
            "Path to python.exe — leave empty to use the default Python")
        self.path_field.setClearButtonEnabled(True)

        browse_button = QPushButton("Browse…")
        browse_button.setObjectName("Ghost")
        browse_button.clicked.connect(self._browse)

        test_button = QPushButton("Test")
        test_button.setObjectName("Ghost")
        test_button.clicked.connect(self.test_now)

        ligne_chemin = QHBoxLayout()
        ligne_chemin.setSpacing(t.SPACE_2)
        ligne_chemin.addWidget(self.path_field, 1)
        ligne_chemin.addWidget(browse_button)
        ligne_chemin.addWidget(test_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.override_label = QLabel("")
        self.override_label.setWordWrap(True)
        self.override_label.setVisible(False)
        if declared_by_workspace:
            self.override_label.setText(
                f"This workspace's configuration already forces an interpreter "
                f"({declared_by_workspace}). It takes priority over the setting "
                f"above while this workspace is loaded.")
            self.override_label.setVisible(True)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self._save)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setVisible(not embedded)

        ligne_boutons = QHBoxLayout()
        ligne_boutons.addStretch(1)
        ligne_boutons.addWidget(self.cancel_button)
        ligne_boutons.addWidget(self.save_button)

        colonne = QVBoxLayout(self)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(self.explanation)
        colonne.addLayout(ligne_chemin)
        colonne.addWidget(self.status_label)
        colonne.addWidget(self.override_label)
        colonne.addStretch(1)
        colonne.addLayout(ligne_boutons)
        self.restyle()

        if not embedded:
            self.test_now()

    def restyle(self) -> None:
        """Repaint labels whose inline colors otherwise survive a theme switch."""
        from runner.domain.models import Status
        self.explanation.setStyleSheet(f"color:{t.TEXT};background:transparent;")
        self.status_label.setStyleSheet(
            f"color:{t.status_color(Status.FAILED)};background:transparent;"
            if self._status_is_error else theme.muted())
        self.override_label.setStyleSheet(
            f"color:{t.status_color(Status.SKIPPED)};background:transparent;")

    def _save(self) -> None:
        self.saved.emit(self.interpreter_path())
        if not self._embedded:
            self.accept()

    def interpreter_path(self) -> str:
        return self.path_field.text().strip()

    def _browse(self) -> None:
        depart = os.path.dirname(self.interpreter_path()) or os.path.expanduser("~")
        filtre = "Python (python.exe python3.exe)" if os.name == "nt" else "All files (*)"
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choose the test Python interpreter", depart, filtre)
        if chemin:
            self.path_field.setText(chemin)
            self.test_now()

    def test_now(self) -> None:
        chemin = self.interpreter_path() or default()

        if not chemin:
            self._say("No Python found automatically: specify the path to "
                      "python.exe.", erreur=True)
            return

        self._say(f"Checking {chemin}…")

        if self._probe is not None and self._probe.isRunning():
            return
        self._probe = ProbeWorker(chemin, self)
        self._probe.done.connect(self._on_probed)
        self._probe.start()

    def _on_probed(self, info: InterpreterInfo) -> None:
        self._say(f"{info.path}\n{info.summary()}",
                  erreur=not info.ok or not info.pytest_version)

    def wait_for_probe(self, timeout_ms: int = 3000) -> None:
        if self._probe is not None:
            self._probe.wait(timeout_ms)

    def done(self, result: int) -> None:
        self.wait_for_probe()
        super().done(result)

    def _say(self, texte: str, erreur: bool = False) -> None:
        self._status_is_error = erreur
        self.status_label.setText(texte)
        self.restyle()
