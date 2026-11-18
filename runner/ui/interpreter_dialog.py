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

from PySide6.QtCore import Qt, Signal, QTimer
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
from runner.ui.timeouts import seconds as timeout_seconds
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
        self._status_is_valid = False
        self._generation = 0
        self._probe_generation = -1
        self._probe_key = None
        self._validated_key = None
        self._pending_check = None
        self._save_requested = False
        self._close_result = None
        self._auto_check = QTimer(self)
        self._auto_check.setSingleShot(True)
        self._auto_check.setInterval(350)
        self._auto_check.timeout.connect(self.test_now)

        self.explanation = QLabel(
            "Choose the Python environment used to collect and run tests."
            "<br>It must have <b>pytest</b> installed.")
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
        self.test_button = test_button
        test_button.setObjectName("Ghost")
        test_button.clicked.connect(self.test_now)

        ligne_chemin = QHBoxLayout()
        ligne_chemin.setSpacing(t.SPACE_2)
        ligne_chemin.addWidget(self.path_field, 1)
        ligne_chemin.addWidget(browse_button)
        ligne_chemin.addWidget(test_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
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
        self.save_button.setEnabled(False)
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
        self.path_field.textChanged.connect(self._path_changed)

        if not embedded:
            self.test_now()

    def restyle(self) -> None:
        """Repaint labels whose inline colors otherwise survive a theme switch."""
        from runner.domain.models import Status
        self.explanation.setStyleSheet(f"color:{t.TEXT};background:transparent;")
        self.status_label.setStyleSheet(
            f"color:{t.status_color(Status.FAILED)};background:transparent;"
            if self._status_is_error else
            f"color:{t.status_color(Status.PASSED)};background:transparent;"
            if self._status_is_valid else theme.muted())
        self.override_label.setStyleSheet(
            f"color:{t.status_color(Status.SKIPPED)};background:transparent;")

    def _save(self) -> None:
        if self._validated_key != self._choice_key() or not self.save_button.isEnabled():
            return
        # Verifier encore en fond au moment de sauver : pytest peut avoir
        # ete retire ou l'executable supprime depuis le dernier Test.
        self._begin_check(save=True)

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
        self._begin_check()

    def _choice_key(self):
        text = self.interpreter_path()
        return text, text or default()

    def _path_changed(self) -> None:
        self._generation += 1
        self._validated_key = None
        self._save_requested = False
        self._pending_check = None
        self.save_button.setEnabled(False)
        self.save_button.setToolTip('Checking this environment before saving')
        self._say('Checking interpreter…')
        self._auto_check.start()

    def _begin_check(self, *, save=False):
        self._auto_check.stop()
        self._generation += 1
        self._validated_key = None
        self._save_requested = save
        self.save_button.setEnabled(False)
        self._pending_check = self._choice_key()
        chemin = self._pending_check[1]
        if not chemin:
            self._pending_check = None
            self._save_requested = False
            self._say("No Python found automatically: specify the path to "
                      "python.exe.", erreur=True)
            return
        self._say(f"Checking {chemin}…")
        self._start_pending_check()

    def _start_pending_check(self):
        # Le resultat et la fin du QThread sont deux signaux distincts :
        # attendre finished avant de remplacer son objet ou lancer le suivant.
        if self._probe is not None or self._pending_check is None:
            return
        self._probe_key, self._pending_check = self._pending_check, None
        self._probe_generation = self._generation
        self._probe = ProbeWorker(
            self._probe_key[1], self, timeout=timeout_seconds(self, "interpreter_timeout"))
        worker = self._probe
        self._probe.done.connect(self._on_probed)
        worker.finished.connect(self._probe_finished)
        self._probe.start()

    def _on_probed(self, info: InterpreterInfo) -> None:
        if (self._probe_generation != self._generation or self._probe_key != self._choice_key()
                or info.path != self._probe_key[1]):
            return
        self._validated_key = self._probe_key if info.usable else None
        self.save_button.setEnabled(info.usable)
        self.save_button.setToolTip('Save this verified environment' if info.usable else
                                    'Choose a working Python environment with pytest installed')
        self.status_label.setToolTip(info.path)
        self._say(('Ready · ' if info.usable else 'Python interpreter not usable\n') + info.summary(),
                  erreur=not info.usable, valid=info.usable)
        if self._save_requested and info.usable:
            self._save_requested = False
            self._say('Configuration saved.\n' + info.summary(), valid=True)
            self.saved.emit(self.interpreter_path())
            if not self._embedded:
                self.accept()
        elif not info.usable:
            self._save_requested = False

    def _probe_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if self._probe is worker:
            self._probe = None
        worker.deleteLater()
        if self._close_result is not None:
            result, self._close_result = self._close_result, None
            super().done(result)
            return
        self._start_pending_check()

    def wait_for_probe(self, timeout_ms: int = 3000) -> bool:
        self._auto_check.stop()
        self._pending_check = None
        self._save_requested = False
        if self._probe is not None:
            return self._probe.wait(timeout_ms)
        return True

    def done(self, result: int) -> None:
        self._auto_check.stop()
        self._pending_check = None
        if self._probe is not None:
            # Ne pas detruire un QThread encore actif ni bloquer Qt en
            # attendant un Python lent. finished achevera la fermeture.
            self._close_result = result
            self._generation += 1
            self._save_requested = False
            self.save_button.setEnabled(False)
            self.path_field.setEnabled(False)
            self.test_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self._say('Finishing interpreter check…')
            return
        super().done(result)

    def _say(self, texte: str, erreur: bool = False, *, valid: bool = False) -> None:
        self._status_is_error = erreur
        self._status_is_valid = valid
        self.status_label.setText(texte)
        self.restyle()
