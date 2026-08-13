"""Editeur de configuration : formulaire par defaut, YAML brut en secours.

Le formulaire evite la faute de frappe qui casse tout le fichier. L'onglet YAML
reste disponible pour ajouter une cle absente ou pour les structures que le
formulaire ne represente pas, et les deux vues restent synchronisees.
"""

from pathlib import Path

import yaml
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui_qt.config.config_form import ConfigForm
from gui_qt.config.config_loader import load_yaml, save_yaml
from gui_qt.styles import styles
from gui_qt.styles.styles import console_style, primary_button, toolbar_button

FORM_TAB = 0
YAML_TAB = 1


class ConfigEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.path: Path | None = None

        self.title = QLabel("Project configuration")
        self.title.setStyleSheet("font-weight: 600;")

        self.form = ConfigForm()

        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setPlaceholderText("key: value")

        self.tabs = QTabWidget()
        self.tabs.addTab(self.form, "Settings")
        self.tabs.addTab(self.raw_editor, "YAML")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.save_button = QPushButton("Save")
        self.save_button.setStyleSheet(primary_button())
        self.save_button.clicked.connect(self.save)

        self.reload_button = QPushButton("Reload")
        self.reload_button.setStyleSheet(toolbar_button())
        self.reload_button.clicked.connect(self.reload)

        barre = QHBoxLayout()
        barre.addWidget(self.status, 1)
        barre.addWidget(self.reload_button)
        barre.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.tabs)
        layout.addLayout(barre)

        self.restyle()

    def restyle(self):
        self.raw_editor.setStyleSheet(console_style())
        self.status.setStyleSheet(styles.muted_label())

    # ------------------------------------------------------------------ chargement

    def load(self, path: Path):
        self.path = Path(path)
        self.title.setText(str(self.path))
        self.reload()

    def reload(self):
        if not self.path:
            return
        try:
            data = load_yaml(self.path)
        except Exception as exc:
            self._report(f"Could not read: {exc}", erreur=True)
            return

        self.form.load(data)
        self.raw_editor.setPlainText(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        self._report("")

    # --------------------------------------------------------------- synchronisation

    def _on_tab_changed(self, index: int):
        """Chaque vue est alimentee par l'autre au moment de l'afficher, pour
        qu'une saisie ne soit jamais perdue en changeant d'onglet."""
        if index == YAML_TAB:
            self.raw_editor.setPlainText(
                yaml.safe_dump(self.form.values(), sort_keys=False, allow_unicode=True)
            )
            self._report("")
            return

        data = self._parse_raw()
        if data is not None:
            self.form.load(data)

    def _parse_raw(self) -> dict | None:
        try:
            data = yaml.safe_load(self.raw_editor.toPlainText()) or {}
        except yaml.YAMLError as exc:
            self._report(f"Invalid YAML: {exc}", erreur=True)
            return None

        if not isinstance(data, dict):
            self._report("The file must contain a list of keys.", erreur=True)
            return None

        self._report("")
        return data

    # ---------------------------------------------------------------- enregistrement

    def current_values(self) -> dict | None:
        """Configuration telle qu'affichee, depuis l'onglet actif."""
        if self.tabs.currentIndex() == YAML_TAB:
            return self._parse_raw()
        return self.form.values()

    def save(self):
        if not self.path:
            return

        data = self.current_values()
        if data is None:
            # Le message d'erreur est deja affiche, et rien n'est ecrit : un
            # YAML invalide ne doit pas remplacer un fichier valide.
            QMessageBox.warning(
                self, "Save cancelled",
                "The configuration was not saved: fix the reported error.",
            )
            return

        try:
            save_yaml(self.path, data)
        except Exception as exc:
            self._report(f"Could not write: {exc}", erreur=True)
            return

        # Les deux vues sont remises en phase avec ce qui vient d'etre ecrit.
        self.form.load(data)
        self.raw_editor.setPlainText(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        self._report(f"Saved to {self.path}")

    def _report(self, message: str, erreur: bool = False):
        self.status.setText(message)
        if erreur:
            self.status.setStyleSheet(f"color: {styles.palette()['danger']};")
        else:
            self.status.setStyleSheet(styles.muted_label())
