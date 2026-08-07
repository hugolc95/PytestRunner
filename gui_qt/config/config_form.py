"""Formulaire construit dynamiquement a partir du contenu d'un config.yml.

Editer du YAML brut expose a la faute de frappe qui casse tout le fichier :
une indentation de travers, un deux-points oublie, et la configuration devient
illisible. Le formulaire propose un champ par reglage, adapte au type de la
valeur, et reecrit le YAML lui-meme.

Le fichier reste editable en YAML dans un second onglet : c'est le filet de
securite pour tout ce que le formulaire ne saurait pas representer, et il permet
d'ajouter une cle absente du fichier.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_qt.config.config_loader import LOG_PATH_KEYS, normalize_key
from gui_qt.styles import styles
from gui_qt.styles.styles import toolbar_button

# Reglages dont la valeur est un chemin : ils recoivent un bouton "Parcourir".
DIRECTORY_HINTS = LOG_PATH_KEYS + ("output_dir", "report_path", "workspace", "root")
FILE_HINTS = ("python_executable", "python", "interpreter", "config_file")

# Explications affichees sous les reglages connus, pour eviter d'avoir a deviner.
DESCRIPTIONS = {
    "log_path": "Dossier ou sont ecrits les fichiers .log, un par test execute.",
    "log_directory": "Dossier ou sont ecrits les fichiers .log, un par test execute.",
    "python_executable": "Python utilisé pour collecter et exécuter les tests "
                         "(il lui faut pytest). Laisser vide pour le réglage global.",
    "import_mode": "Mode d'import pytest. importlib accepte des fichiers de test "
                   "de meme nom dans des dossiers differents.",
    "pythonpath": "Chemins ajoutes au PYTHONPATH des tests, un par ligne.",
}


def humanize(key: str) -> str:
    """`log_path` devient `Log path` : lisible sans perdre le nom reel."""
    return str(key).replace("_", " ").replace("-", " ").strip().capitalize()


def looks_like_directory(key: str) -> bool:
    normal = normalize_key(key)
    return normal in DIRECTORY_HINTS or normal.endswith(("_dir", "_path", "_directory"))


def looks_like_file(key: str) -> bool:
    return normalize_key(key) in FILE_HINTS


class _Field:
    """Un reglage : sait construire son widget et relire sa valeur."""

    def __init__(self, key: str, value):
        self.key = key
        self.original = value
        self.widget = None

    def value(self):
        raise NotImplementedError


class _BoolField(_Field):
    def build(self, parent) -> QWidget:
        self.widget = QCheckBox()
        self.widget.setChecked(bool(self.original))
        return self.widget

    def value(self):
        return self.widget.isChecked()


class _IntField(_Field):
    def build(self, parent) -> QWidget:
        self.widget = QSpinBox()
        self.widget.setRange(-1_000_000, 1_000_000)
        self.widget.setValue(int(self.original))
        return self.widget

    def value(self):
        return self.widget.value()


class _FloatField(_Field):
    def build(self, parent) -> QWidget:
        self.widget = QDoubleSpinBox()
        self.widget.setRange(-1_000_000, 1_000_000)
        self.widget.setDecimals(3)
        self.widget.setValue(float(self.original))
        return self.widget

    def value(self):
        return self.widget.value()


class _ListField(_Field):
    """Liste de valeurs simples : une par ligne, ce qui se saisit et se relit
    plus facilement qu'une syntaxe YAML a puces."""

    def build(self, parent) -> QWidget:
        self.widget = QPlainTextEdit()
        self.widget.setPlainText("\n".join(str(v) for v in self.original))
        self.widget.setMaximumHeight(72)
        self.widget.setPlaceholderText("Une valeur par ligne")
        return self.widget

    def value(self):
        lignes = [ligne.strip() for ligne in self.widget.toPlainText().splitlines()]
        return [ligne for ligne in lignes if ligne]


class _TextField(_Field):
    def __init__(self, key, value, browse: str | None = None):
        super().__init__(key, value)
        self.browse = browse  # "dir", "file" ou None

    def build(self, parent) -> QWidget:
        conteneur = QWidget()
        ligne = QHBoxLayout(conteneur)
        ligne.setContentsMargins(0, 0, 0, 0)

        self.widget = QLineEdit("" if self.original is None else str(self.original))
        self.widget.setClearButtonEnabled(True)
        ligne.addWidget(self.widget)

        if self.browse:
            bouton = QPushButton("Parcourir...")
            bouton.setStyleSheet(toolbar_button())
            bouton.clicked.connect(lambda: self._choisir(parent))
            ligne.addWidget(bouton)

        return conteneur

    def _choisir(self, parent):
        depart = self.widget.text().strip() or str(Path.home())
        if self.browse == "dir":
            chemin = QFileDialog.getExistingDirectory(parent, f"Choisir : {self.key}", depart)
        else:
            chemin, _ = QFileDialog.getOpenFileName(parent, f"Choisir : {self.key}", depart)
        if chemin:
            self.widget.setText(chemin)

    def value(self):
        texte = self.widget.text().strip()
        if texte == "" and self.original is None:
            return None
        return texte


def build_field(key: str, value) -> _Field:
    """Choisit le widget adapte au type de la valeur.

    Le booleen est teste avant l'entier : en Python, True est un int.
    """
    if isinstance(value, bool):
        return _BoolField(key, value)
    if isinstance(value, int):
        return _IntField(key, value)
    if isinstance(value, float):
        return _FloatField(key, value)
    if isinstance(value, (list, tuple)):
        return _ListField(key, list(value))

    if looks_like_directory(key):
        return _TextField(key, value, browse="dir")
    if looks_like_file(key):
        return _TextField(key, value, browse="file")
    return _TextField(key, value)


class ConfigForm(QScrollArea):
    """Formulaire genere a partir d'un dictionnaire de configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._fields: dict[str, _Field] = {}
        self._nested: dict[str, "ConfigForm"] = {}
        self._data: dict = {}
        self.setWidget(QWidget())

    def load(self, data: dict):
        self._data = data if isinstance(data, dict) else {}
        self._fields.clear()
        self._nested.clear()

        contenu = QWidget()
        layout = QVBoxLayout(contenu)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        simples = QFormLayout()
        simples.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        simples.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        simples.setHorizontalSpacing(12)
        simples.setVerticalSpacing(4)

        for key, value in self._data.items():
            if isinstance(value, dict):
                continue  # traite plus bas, dans son propre cadre
            field = build_field(key, value)
            self._fields[key] = field
            simples.addRow(self._label_for(key), field.build(self))

            # L'explication occupe toute la largeur sous le champ. Placee dans
            # la colonne des libelles, elle se repliait sur quatre lignes et
            # faisait tripler la hauteur de chaque reglage.
            description = DESCRIPTIONS.get(normalize_key(key))
            if description:
                aide = QLabel(description)
                aide.setWordWrap(True)
                aide.setStyleSheet(styles.muted_label())
                aide.setContentsMargins(0, 0, 0, 4)
                simples.addRow("", aide)

        if self._fields:
            layout.addLayout(simples)

        # Les sous-dictionnaires deviennent des cadres, pour garder la structure
        # du fichier visible plutot que de l'aplatir.
        for key, value in self._data.items():
            if not isinstance(value, dict):
                continue
            cadre = QGroupBox(humanize(key))
            interne = QVBoxLayout(cadre)
            interne.setContentsMargins(6, 4, 6, 6)
            sous_formulaire = ConfigForm()
            sous_formulaire.load(value)
            sous_formulaire.setFrameShape(QScrollArea.NoFrame)
            interne.addWidget(sous_formulaire)
            self._nested[key] = sous_formulaire
            layout.addWidget(cadre)

        if not self._data:
            vide = QLabel("Ce fichier de configuration est vide.\n"
                          "Utilisez l'onglet YAML pour y ajouter des reglages.")
            vide.setStyleSheet(styles.muted_label())
            layout.addWidget(vide)

        layout.addStretch(1)
        self.setWidget(contenu)

    def _label_for(self, key: str) -> QWidget:
        """Libelle sur UNE ligne : nom lisible, puis cle reelle en plus petit.

        Les empiler sur deux lignes doublait la hauteur de chaque reglage pour
        afficher deux fois la meme information. La cle reelle reste visible
        parce que c'est elle qu'on retrouve dans le fichier et dans la
        documentation du projet.
        """
        libelle = QLabel(
            f"<b>{humanize(key)}</b>"
            f"&nbsp;<span style=\'font-size:10px; color:{styles.palette()['text_muted']}\'>"
            f"{key}</span>"
        )
        libelle.setTextFormat(Qt.RichText)
        libelle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        description = DESCRIPTIONS.get(normalize_key(key))
        if description:
            libelle.setToolTip(description)

        return libelle

    def values(self) -> dict:
        """Configuration reconstruite, dans l'ordre d'origine des cles."""
        resultat = {}
        for key in self._data:
            if key in self._nested:
                resultat[key] = self._nested[key].values()
            elif key in self._fields:
                resultat[key] = self._fields[key].value()
            else:
                resultat[key] = self._data[key]
        return resultat
