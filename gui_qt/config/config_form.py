"""Formulaire construit dynamiquement a partir du contenu d'un config.yml.

Editer du YAML brut expose a la faute de frappe qui casse tout le fichier : une
indentation de travers, un deux-points oublie, et la configuration devient
illisible. Le formulaire propose un champ par reglage, adapte au type de la
valeur, et reecrit le YAML lui-meme.

Les configurations profondement imbriquees (une section par mode, chacune avec
ses reglages) sont presentees comme une fenetre de preferences : la liste des
sections a gauche, les reglages de la section choisie a droite. Empiler des
cadres les uns dans les autres produisait des zones de defilement imbriquees et
un empilement vertical illisible.
"""

from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_qt.config.config_loader import LOG_PATH_KEYS, normalize_key
from gui_qt.styles import styles
from gui_qt.styles.styles import toolbar_button

# Reglages dont la valeur est un chemin : ils recoivent un bouton "Parcourir".
DIRECTORY_HINTS = LOG_PATH_KEYS + ("output_dir", "report_path", "workspace", "root")
FILE_HINTS = ("python_executable", "python", "interpreter", "config_file")

# Largeur maximale d'un champ. Sans plafond, un champ occupe toute la largeur
# d'une fenetre agrandie et son bouton "Parcourir" se retrouve a un metre de
# son libelle.
MAX_FIELD_WIDTH = 560

# Nom de la section regroupant les reglages qui ne sont pas dans un sous-groupe.
GENERAL_SECTION = "General"

DESCRIPTIONS = {
    "log_path": "Dossier ou sont ecrits les fichiers .log, un par test execute.",
    "log_directory": "Dossier ou sont ecrits les fichiers .log, un par test execute.",
    "python_executable": "Python utilise pour collecter et executer les tests "
                         "(il lui faut pytest). Vide = reglage global de l'application.",
    "import_mode": "Mode d'import pytest. importlib accepte des fichiers de test "
                   "de meme nom dans des dossiers differents.",
    "pythonpath": "Chemins ajoutes au PYTHONPATH des tests, un par ligne.",
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def humanize(key: str) -> str:
    """Nom lisible d'une cle, sans en detruire la casse.

    `ChecksumObjConfigAlgo` devient `Checksum obj config algo` et non
    `Checksumobjconfigalgo` : str.capitalize() met en minuscules tout ce qui
    suit la premiere lettre.
    """
    texte = _CAMEL.sub(" ", str(key))
    texte = texte.replace("_", " ").replace("-", " ")
    texte = " ".join(texte.split())
    if not texte:
        return ""
    if texte.isupper():
        texte = texte.lower()
    return texte[0].upper() + texte[1:]


def key_worth_showing(key: str) -> bool:
    """Vrai si la cle reelle apporte quelque chose a cote du nom lisible.

    Afficher `LOG_PATH` a cote de `Log path` n'informe personne et allonge le
    libelle. En revanche `ChecksumObjConfigAlgo`, rendu `Checksum obj config
    algo`, devient difficile a relier a ce qu'on lit dans le fichier : la cle
    est alors montree.

    La comparaison se fait a separateurs pres, et non sur les seuls caracteres
    alphanumeriques : humanize() ne modifiant que les espaces et la casse, une
    comparaison trop permissive masquerait toujours la cle.
    """
    return humanize(key).lower().replace(" ", "_") != str(key).lower()


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
        self.widget.setMaximumWidth(160)
        return self.widget

    def value(self):
        return self.widget.value()


class _FloatField(_Field):
    def build(self, parent) -> QWidget:
        self.widget = QDoubleSpinBox()
        self.widget.setRange(-1_000_000, 1_000_000)
        self.widget.setDecimals(3)
        self.widget.setValue(float(self.original))
        self.widget.setMaximumWidth(160)
        return self.widget

    def value(self):
        return self.widget.value()


class _ListField(_Field):
    """Liste de valeurs simples : une par ligne, plus simple a saisir et a relire
    qu'une syntaxe YAML a puces."""

    # Hauteur adaptee au contenu, entre ces bornes : une liste de quatre modes
    # ne doit pas etre tronquee a deux lignes, une de cent ne doit pas remplir
    # l'ecran.
    MIN_LINES = 3
    MAX_LINES = 10

    def build(self, parent) -> QWidget:
        self.widget = QPlainTextEdit()
        self.widget.setPlainText("\n".join(str(v) for v in self.original))
        self.widget.setPlaceholderText("Une valeur par ligne")
        self.widget.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.widget.setMaximumWidth(MAX_FIELD_WIDTH)

        lignes = min(max(len(self.original), self.MIN_LINES), self.MAX_LINES)
        hauteur_ligne = self.widget.fontMetrics().lineSpacing()
        self.widget.setFixedHeight(lignes * hauteur_ligne + 12)
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
        ligne.setSpacing(6)

        self.widget = QLineEdit("" if self.original is None else str(self.original))
        self.widget.setClearButtonEnabled(True)
        self.widget.setMaximumWidth(MAX_FIELD_WIDTH)
        ligne.addWidget(self.widget)

        if self.browse:
            bouton = QPushButton("Parcourir...")
            bouton.setStyleSheet(toolbar_button())
            bouton.clicked.connect(lambda: self._choisir(parent))
            ligne.addWidget(bouton)

        # Occupe la place restante, pour que le champ et son bouton restent
        # groupes a gauche au lieu de s'etirer sur toute la fenetre.
        ligne.addStretch(1)
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


class _SectionForm(QScrollArea):
    """Les reglages simples d'un niveau : une page du navigateur."""

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.fields: dict[str, _Field] = {}

        contenu = QWidget()
        layout = QVBoxLayout(contenu)
        layout.setContentsMargins(12, 10, 12, 10)

        formulaire = QFormLayout()
        formulaire.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        formulaire.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        formulaire.setHorizontalSpacing(14)
        formulaire.setVerticalSpacing(6)

        for key, value in data.items():
            if isinstance(value, dict):
                continue  # c'est une sous-section, elle a sa propre page
            champ = build_field(key, value)
            self.fields[key] = champ
            formulaire.addRow(self._label_for(key), champ.build(self))

            description = DESCRIPTIONS.get(normalize_key(key))
            if description:
                aide = QLabel(description)
                aide.setWordWrap(True)
                aide.setStyleSheet(styles.muted_label())
                aide.setContentsMargins(0, 0, 0, 4)
                formulaire.addRow("", aide)

        if not self.fields:
            vide = QLabel("Cette section ne contient que des sous-sections.")
            vide.setStyleSheet(styles.muted_label())
            layout.addWidget(vide)

        layout.addLayout(formulaire)
        layout.addStretch(1)
        self.setWidget(contenu)

    def _label_for(self, key: str) -> QWidget:
        if key_worth_showing(key):
            texte = (
                f"<b>{humanize(key)}</b>"
                f"&nbsp;<span style='font-size:10px; "
                f"color:{styles.palette()['text_muted']}'>{key}</span>"
            )
        else:
            texte = f"<b>{humanize(key)}</b>"

        libelle = QLabel(texte)
        libelle.setTextFormat(Qt.RichText)
        libelle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        description = DESCRIPTIONS.get(normalize_key(key))
        if description:
            libelle.setToolTip(description)
        return libelle

    def values(self) -> dict:
        return {key: champ.value() for key, champ in self.fields.items()}


class ConfigForm(QWidget):
    """Navigateur de sections a gauche, reglages de la section a droite."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data: dict = {}
        # Chemin de section (tuple de cles) -> page de reglages.
        self._pages: dict[tuple, _SectionForm] = {}

        self.sections = QTreeWidget()
        self.sections.setHeaderHidden(True)
        self.sections.setMaximumWidth(260)
        self.sections.currentItemChanged.connect(self._on_section_changed)

        self.pages = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.sections)
        self.splitter.addWidget(self.pages)
        self.splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

    # ------------------------------------------------------------------ chargement

    def load(self, data: dict):
        self._data = data if isinstance(data, dict) else {}
        self._pages.clear()
        self.sections.clear()
        while self.pages.count():
            self.pages.removeWidget(self.pages.widget(0))

        racine = self._add_section((), GENERAL_SECTION, self._data, None)
        self._add_children((), self._data, racine)

        self.sections.expandAll()
        # La liste des sections ne sert a rien quand il n'y en a qu'une.
        self.sections.setVisible(self.sections.topLevelItem(0).childCount() > 0)
        self.sections.setCurrentItem(racine)

    def _add_section(self, chemin: tuple, titre: str, data: dict, parent) -> QTreeWidgetItem:
        page = _SectionForm(data)
        self._pages[chemin] = page
        self.pages.addWidget(page)

        item = QTreeWidgetItem([titre])
        item.setData(0, Qt.UserRole, chemin)
        if parent is None:
            self.sections.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _add_children(self, chemin: tuple, data: dict, parent: QTreeWidgetItem):
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            sous_chemin = chemin + (key,)
            item = self._add_section(sous_chemin, humanize(key), value, parent)
            self._add_children(sous_chemin, value, item)

    def _on_section_changed(self, item, _precedent):
        if item is None:
            return
        chemin = item.data(0, Qt.UserRole)
        page = self._pages.get(chemin)
        if page is not None:
            self.pages.setCurrentWidget(page)

    # ------------------------------------------------------------------- relecture

    def field(self, key: str, section: tuple = ()):
        """Champ d'un reglage, eventuellement dans une sous-section.

        `form.field("format", ("rapport",))` designe le reglage `format` de la
        section `rapport`.
        """
        page = self._pages.get(tuple(section))
        return page.fields.get(key) if page is not None else None

    def section_titles(self) -> list[str]:
        """Titres des sections, dans l'ordre d'affichage du navigateur."""
        titres = []

        def parcourir(item):
            titres.append(item.text(0))
            for i in range(item.childCount()):
                parcourir(item.child(i))

        for i in range(self.sections.topLevelItemCount()):
            parcourir(self.sections.topLevelItem(i))
        return titres

    def values(self) -> dict:
        return self._values_for((), self._data)

    def _values_for(self, chemin: tuple, data: dict) -> dict:
        page = self._pages.get(chemin)
        edites = page.values() if page is not None else {}

        resultat = {}
        for key, value in data.items():
            if isinstance(value, dict):
                resultat[key] = self._values_for(chemin + (key,), value)
            elif key in edites:
                resultat[key] = edites[key]
            else:
                # Valeur que le formulaire ne sait pas editer : conservee telle
                # quelle plutot que perdue.
                resultat[key] = value
        return resultat
