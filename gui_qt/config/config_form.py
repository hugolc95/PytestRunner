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

from PyQt5.QtCore import QEvent, Qt
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
    QSizePolicy,
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

# Bornes de largeur d'un champ. Le minimum evite un champ riquiqui pour une
# valeur courte ; le maximum evite qu'un champ traverse un ecran large et
# renvoie son bouton "Parcourir" a un metre de son libelle.
MIN_FIELD_WIDTH = 240
MAX_FIELD_WIDTH = 900


def width_for_content(widget: QWidget, textes, marge: int = 36) -> int:
    """Largeur permettant d'afficher ces textes en entier, dans les bornes.

    Le sizeHint d'un QLineEdit ne depend pas de son contenu : il vaut toujours
    une vingtaine de caracteres. Combine a une politique de croissance qui s'y
    tient, un chemin comme `C:/Projets/CryptoWrapper/cryptolib_ifx_wrapper/Test`
    apparaissait tronque a `_ifx_wrapper\\Test` alors que la fenetre agrandie
    etait aux trois quarts vide. On dimensionne donc sur le contenu reel.
    """
    metrics = widget.fontMetrics()
    besoin = max((metrics.horizontalAdvance(str(t)) for t in textes), default=0)
    return max(MIN_FIELD_WIDTH, min(besoin + marge, MAX_FIELD_WIDTH))

# Bornes de largeur du navigateur de sections, ajuste a ses titres.
NAV_MIN_WIDTH = 170
NAV_MAX_WIDTH = 380

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


class _ValueList(QPlainTextEdit):
    """Zone de saisie qui se donne la hauteur d'un nombre de lignes fixe.

    La hauteur suit la police, au lieu d'etre figee a la construction : la
    feuille de style de l'application n'est appliquee au widget qu'une fois
    celui-ci integre a la fenetre, et elle change l'interligne (21 px avant,
    17 apres). Mesuree trop tot, la boite faisait trois lignes de trop.
    """

    def __init__(self, lignes: int):
        super().__init__()
        self._lignes = lignes

    def line_height(self) -> float:
        """Interligne reel du document.

        fontMetrics().lineSpacing() le sous-estime (15 px contre 17 ici) et la
        derniere valeur se retrouvait coupee en deux, avec une barre de
        defilement pour quatre elements.
        """
        document = self.document()
        bloc = document.documentLayout().blockBoundingRect(document.firstBlock())
        return bloc.height() or self.fontMetrics().lineSpacing()

    def adjust_height(self):
        marges = 2 * self.document().documentMargin() + 2 * self.frameWidth()
        self.setFixedHeight(int(self._lignes * self.line_height() + marges) + 2)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjust_height()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self.adjust_height()


class _ListField(_Field):
    """Liste de valeurs simples : une par ligne, plus simple a saisir et a relire
    qu'une syntaxe YAML a puces."""

    # Hauteur adaptee au contenu, entre ces bornes : une liste de quatre modes
    # ne doit pas etre tronquee a deux lignes, une de cent ne doit pas remplir
    # l'ecran.
    MIN_LINES = 3
    MAX_LINES = 10

    def build(self, parent) -> QWidget:
        lignes = min(max(len(self.original), self.MIN_LINES), self.MAX_LINES)
        self.widget = _ValueList(lignes)
        self.widget.setPlainText("\n".join(str(v) for v in self.original))
        self.widget.setPlaceholderText("Une valeur par ligne")
        self.widget.setLineWrapMode(QPlainTextEdit.NoWrap)
        # Largeur de la plus longue valeur : sans cela, une liste de modes
        # s'affichait tronquee alors qu'il restait de la place. Une liste plus
        # longue que MAX_LINES defile, sa barre prend de la place a son tour.
        marge = 24 if len(self.original) > self.MAX_LINES else 8
        self.widget.setMaximumWidth(width_for_content(self.widget, self.original, marge))
        self.widget.adjust_height()
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
        # Le champ s'etire jusqu'a montrer sa valeur entiere, puis s'arrete : le
        # bouton reste a portee du libelle sur une fenetre large.
        self.widget.setMaximumWidth(
            width_for_content(self.widget, [self.original], marge=48)
        )
        ligne.addWidget(self.widget, 1)

        if self.browse:
            bouton = QPushButton("Parcourir...")
            bouton.setStyleSheet(toolbar_button())
            bouton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            bouton.clicked.connect(lambda: self._choisir(parent))
            ligne.addWidget(bouton)

        # Absorbe ce qui depasse une fois le champ a sa largeur utile, pour que
        # le champ et son bouton restent groupes a gauche.
        ligne.addStretch(0)
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
        # Les champs prennent la largeur disponible, chacun jusqu'a son propre
        # plafond calcule sur son contenu. Rester au sizeHint donnait des champs
        # de vingt caracteres, identiques pour un mot et pour un chemin complet.
        formulaire.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
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
                aide.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        """Un seul nom affiche, le nom lisible.

        Montrer aussi la cle brute a cote doublait l'information sans rien
        apprendre : humanize() ne fait qu'ajouter des espaces et ajuster la
        casse. L'orthographe exacte, celle qu'on cherche dans le fichier, reste
        disponible dans l'infobulle.
        """
        libelle = QLabel(f"<b>{humanize(key)}</b>")
        libelle.setTextFormat(Qt.RichText)
        libelle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        infobulle = str(key)
        description = DESCRIPTIONS.get(normalize_key(key))
        if description:
            infobulle += f"\n\n{description}"
        libelle.setToolTip(infobulle)
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
        self.sections.setMaximumWidth(NAV_MAX_WIDTH)
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
        self._adjust_navigator_width()

    def _adjust_navigator_width(self):
        """Ajuste le navigateur au plus long titre, sans le laisser deborder.

        Une largeur fixe tronquait les noms de sections imbriquees, alors qu'un
        fichier a deux sections en gaspillait la moitie.
        """
        metrics = self.sections.fontMetrics()
        plus_large = 0

        def parcourir(item, profondeur: int):
            nonlocal plus_large
            largeur = metrics.horizontalAdvance(item.text(0))
            largeur += profondeur * self.sections.indentation()
            plus_large = max(plus_large, largeur)
            for i in range(item.childCount()):
                parcourir(item.child(i), profondeur + 1)

        for i in range(self.sections.topLevelItemCount()):
            parcourir(self.sections.topLevelItem(i), 1)

        largeur = max(NAV_MIN_WIDTH, min(plus_large + 24, NAV_MAX_WIDTH))
        self.sections.setMaximumWidth(largeur)
        self.splitter.setSizes([largeur, max(largeur, self.width() - largeur)])

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
