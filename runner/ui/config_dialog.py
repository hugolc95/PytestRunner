"""Editer la configuration du workspace : un formulaire, et le YAML en secours.

Ouvrir le fichier dans un editeur externe pour changer un lecteur ou un chemin
de logs oblige a connaitre la syntaxe YAML, et une indentation de travers rend
tout le workspace incollectable. Le formulaire propose un champ par reglage,
adapte a son type, et ne touche qu'aux lignes dont la valeur a change.

L'onglet YAML reste la pour ce que le formulaire ne represente pas : ajouter
une cle absente, ecrire une structure imbriquee, ou simplement relire le
fichier tel qu'il est. Ce qu'on y tape fait alors foi, commentaires compris.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain import config_file
from runner.domain.workspace import CLES_LOGS, CLES_PYTHON, CLES_READER, CLES_READERS
from runner.ui import tokens as t

ONGLET_FORMULAIRE = 0
ONGLET_YAML = 1

# Reglages dont la valeur est un dossier, ou un fichier : ils recoivent un
# bouton « Parcourir ». Taper un chemin a la main est la source d'erreur la
# plus courante de ce fichier.
CLES_DOSSIER = CLES_LOGS + ("output_dir", "report_path", "workspace", "root")
CLES_FICHIER = CLES_PYTHON + ("config_file",)

# Ce que fait un reglage, quand ce n'est pas evident depuis son nom.
EXPLICATIONS = {
    "log_path": "Folder where the conftest writes one .log per test.",
    "log_directory": "Folder where the conftest writes one .log per test.",
    "incremental_log": "Keep repeated executions in the same test folder and "
                       "number each log file instead of creating a Run folder.",
    "incrementallog": "Keep repeated executions in the same test folder and "
                      "number each log file instead of creating a Run folder.",
    "python_executable": "Python used to collect and run the tests. It needs "
                         "pytest. Empty means the application's own setting.",
    "reader": "The reader the tests read today.",
    "readers": "Extra readers to test with. The one above stays first — "
           "use + and − to change this list.",
    "reader_mode": "sequential runs the readers one after the other. Leave "
                   "empty for the default, which runs them together.",
    "import_mode": "pytest import mode. importlib accepts test files sharing "
                   "a name across folders.",
    "pythonpath": "Paths added to the tests' PYTHONPATH, one per line.",
}


def _joli(nom: str) -> str:
    """`log_path` devient `Log path` : un libelle, pas un identifiant."""
    return str(nom).replace("_", " ").replace("-", " ").strip().capitalize()


class ReaderList(QWidget):
    """La liste des lecteurs supplementaires, avec de quoi en ajouter.

    Une zone de texte libre marchait, mais demandait de savoir qu'un lecteur
    par ligne etait la regle -- et une ligne vide ou une faute de frappe y
    passaient inapercues. Ici chaque lecteur est une entree qu'on ajoute,
    renomme ou retire.

    Ne touche jamais a la cle `Reader` : celle-la est le lecteur que les tests
    lisent aujourd'hui, et se change dans son propre champ.
    """

    def __init__(self, valeurs, connus=(), parent=None):
        super().__init__(parent)
        self._connus = tuple(connus)

        self.list = QListWidget()
        self.list.setObjectName("Readers")
        # Trois lignes visibles : au-dela la fenetre se remplit d'une liste
        # qui, la plupart du temps, en compte une ou deux.
        self.list.setFixedHeight(t.CONTROL_MD * 3)
        for valeur in valeurs:
            self._ajouter_entree(str(valeur))

        self.add_button = QPushButton("+")
        self.add_button.setObjectName("IconSm")
        self.add_button.setToolTip("Add a reader")
        self.add_button.clicked.connect(self.ajouter)

        self.remove_button = QPushButton("−")
        self.remove_button.setObjectName("IconSm")
        self.remove_button.setToolTip("Remove the selected reader")
        self.remove_button.clicked.connect(self.retirer)

        boutons = QVBoxLayout()
        boutons.setContentsMargins(0, 0, 0, 0)
        boutons.setSpacing(t.SPACE_1)
        boutons.addWidget(self.add_button)
        boutons.addWidget(self.remove_button)
        boutons.addStretch(1)

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)
        ligne.addWidget(self.list, 1)
        ligne.addLayout(boutons)

        self.list.itemSelectionChanged.connect(self._maj)
        self._maj()

    def _ajouter_entree(self, texte: str) -> QListWidgetItem:
        item = QListWidgetItem(texte)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.list.addItem(item)
        return item

    def ajouter(self) -> None:
        """Ajoute un lecteur et ouvre son edition tout de suite.

        Pre-rempli avec un lecteur connu pas encore liste, quand il y en a :
        c'est presque toujours celui qu'on voulait, et cela evite de retaper
        un nom long ou la moindre faute rend le run muet.
        """
        deja = set(self.valeurs())
        propose = next((r for r in self._connus if r not in deja), "")
        item = self._ajouter_entree(propose)
        self.list.setCurrentItem(item)
        self.list.editItem(item)
        self._maj()

    def retirer(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._maj()

    def valeurs(self) -> list:
        """Les lecteurs, sans les vides : une entree laissee blanche donnerait
        une ligne `- ""` dans le fichier, et un run sur un lecteur sans nom."""
        return [self.list.item(i).text().strip()
                for i in range(self.list.count())
                if self.list.item(i).text().strip()]

    def _maj(self) -> None:
        self.remove_button.setEnabled(bool(self.list.selectedItems()))


class _Champ:
    """Un reglage a l'ecran : son chemin, son widget, et sa valeur de depart."""

    def __init__(self, chemin: tuple, widget, lire, depart):
        self.chemin = chemin
        self.widget = widget
        self._lire = lire
        self.depart = depart

    def valeur(self):
        return self._lire()

    def a_change(self) -> bool:
        return self.valeur() != self.depart


class ConfigDialog(QDialog):
    """Le fichier de configuration du workspace, editable sans quitter l'outil."""

    saved = Signal(str)

    def __init__(self, config_path: str, readers_connus=(), parent=None,
                 candidats=(), workspace_path: str = "", embedded: bool = False):
        super().__init__(parent)
        self.path = Path(config_path)
        self._embedded = embedded
        self._workspace_path = (Path(workspace_path) if workspace_path
                                else self.path.parent)
        self._readers_connus = tuple(readers_connus)
        self._candidats = [Path(c) for c in candidats]
        if self.path not in self._candidats:
            self._candidats.insert(0, self.path)
        self._champs: list[_Champ] = []
        self._groupes: list[tuple[QWidget, str]] = []
        self._tracking_changes = False
        self._loaded_raw = ""

        self.setWindowTitle(f"Configuration — {self.path.name}")
        # Une QDialog n'a par defaut ni agrandissement ni reduction : sur une
        # configuration fournie, on veut pouvoir la mettre en plein ecran.
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint)
        self.setSizeGripEnabled(True)
        self.resize(760, 620)

        self.chemin_label = QLabel(str(self.path))
        self.chemin_label.setObjectName("Faint")
        self.chemin_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # Le selecteur reste accessible meme si un seul fichier a ete detecte :
        # le YAML voulu peut etre plus loin dans l'arborescence ou en dehors
        # des candidats automatiques. Un projet qui en a plusieurs voyait
        # auparavant l'outil en prendre un sans permettre d'en choisir un autre.
        self.file_row = QFrame()
        self.file_row.setObjectName("ConfigFileHeader")
        rangee = QHBoxLayout(self.file_row)
        rangee.setContentsMargins(t.SPACE_3, t.SPACE_2,
                                  t.SPACE_3, t.SPACE_2)
        rangee.setSpacing(t.SPACE_2)

        etiquette = QLabel("Fichier actif")
        etiquette.setObjectName("ConfigFileLabel")
        self.file_combo = QComboBox()
        for candidat in self._candidats:
            self._ajouter_candidat(candidat)
        position = self.file_combo.findData(str(self.path))
        if position >= 0:
            self.file_combo.setCurrentIndex(position)
        self.file_combo.currentIndexChanged.connect(self._changer_de_fichier)

        self.choose_file_button = QPushButton("Browse…")
        self.choose_file_button.setObjectName("Ghost")
        self.choose_file_button.setToolTip(
            "Choose another .yml or .yaml file, including in a subfolder")
        self.choose_file_button.clicked.connect(self._choisir_fichier)

        rangee.addWidget(etiquette)
        rangee.addWidget(self.file_combo, 1)
        rangee.addWidget(self.choose_file_button)

        self.state_badge = QLabel("Enregistré")
        self.state_badge.setObjectName("ConfigStateSaved")
        self.state_badge.setAlignment(Qt.AlignCenter)
        rangee.addWidget(self.state_badge)

        self.form_host = QWidget()
        self._form = QVBoxLayout(self.form_host)
        self._form.setContentsMargins(t.SPACE_2, t.SPACE_2, t.SPACE_2, t.SPACE_2)
        self._form.setSpacing(t.SPACE_4)

        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setWidget(self.form_host)

        self.raw = QPlainTextEdit()
        self.raw.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.raw.setPlaceholderText("key: value")
        self.raw.textChanged.connect(self._refresh_dirty_state)

        self.settings_search = QLineEdit()
        self.settings_search.setPlaceholderText("Rechercher un paramètre…")
        self.settings_search.setClearButtonEnabled(True)
        self.settings_search.textChanged.connect(self._filter_settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(defilement, "Settings")
        self.tabs.addTab(self.raw, "YAML")
        self.tabs.currentChanged.connect(self._on_tab)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.reload_button = QPushButton("Recharger")
        self.reload_button.setObjectName("Ghost")
        self.reload_button.clicked.connect(self.reload)

        self.discard_button = QPushButton("Annuler les modifications")
        self.discard_button.setObjectName("Ghost")
        self.discard_button.clicked.connect(self.reload)
        self.discard_button.setEnabled(False)

        self.save_button = QPushButton("Enregistrer")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.save)

        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("Ghost")
        self.close_button.clicked.connect(self.reject)
        self.close_button.setVisible(not embedded)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        actions.addWidget(self.status, 1)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.discard_button)
        actions.addWidget(self.close_button)
        actions.addWidget(self.save_button)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(self.file_row)
        colonne.addWidget(self.chemin_label)
        colonne.addWidget(self.settings_search)
        colonne.addWidget(self.tabs, 1)
        colonne.addLayout(actions)

        # Pas de feuille posee sur l'editeur : la feuille globale habille deja
        # les QPlainTextEdit, en police a chasse fixe et aux couleurs du theme.
        # Une feuille locale ne suivrait pas la bascule clair / sombre.
        self.reload()

    # ------------------------------------------------------------- chargement

    def _libelle_candidat(self, chemin: Path) -> str:
        try:
            return chemin.relative_to(self._workspace_path).as_posix()
        except ValueError:
            return str(chemin)

    def _ajouter_candidat(self, chemin: Path) -> int:
        position = self.file_combo.count()
        self.file_combo.addItem(self._libelle_candidat(chemin), str(chemin))
        self.file_combo.setItemData(position, str(chemin), Qt.ToolTipRole)
        return position

    def _choisir_fichier(self) -> None:
        choisi, _ = QFileDialog.getOpenFileName(
            self, "Choose the workspace configuration", str(self.path.parent),
            "YAML files (*.yml *.yaml)")
        if not choisi:
            return
        position = self.file_combo.findData(choisi)
        if position < 0:
            chemin = Path(choisi)
            self._candidats.append(chemin)
            position = self._ajouter_candidat(chemin)
        self.file_combo.setCurrentIndex(position)

    def _changer_de_fichier(self, _index: int) -> None:
        """Bascule sur un autre YAML du workspace.

        Les modifications non enregistrees du fichier courant sont perdues :
        on le dit, plutot que de les emporter silencieusement vers un fichier
        auquel elles n'appartiennent pas.
        """
        choisi = self.file_combo.currentData()
        if not choisi or Path(choisi) == self.path:
            return

        perdues = len(self._modifications())
        self.path = Path(choisi)
        self.setWindowTitle(f"Configuration — {self.path.name}")
        self.chemin_label.setText(str(self.path))
        self.reload()
        if perdues:
            quoi = ("1 unsaved change was" if perdues == 1
                    else f"{perdues} unsaved changes were")
            self._dire(f"Switched file — {quoi} dropped.", alerte=True)

    def reload(self) -> None:
        """Relit le fichier et rebatit les deux vues."""
        self._tracking_changes = False
        donnees = config_file.charger(self.path)
        texte = config_file.lire_texte(self.path)
        self._loaded_raw = texte if texte is not None else ""
        self.raw.setPlainText(self._loaded_raw)
        self._batir(donnees)
        self._dire("")
        self._tracking_changes = True
        self._set_state("saved")

    def _batir(self, donnees: dict) -> None:
        while self._form.count():
            element = self._form.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._champs = []
        self._groupes = []

        simples = {c: v for c, v in donnees.items() if not isinstance(v, dict)}
        sections = {c: v for c, v in donnees.items() if isinstance(v, dict)}

        if simples:
            self._form.addWidget(self._groupe("Settings", (), simples))
        for nom, contenu in sections.items():
            self._form.addWidget(self._groupe(_joli(nom), (nom,), contenu))

        if not simples and not sections:
            vide = QLabel("This file has no setting yet. Add one in the YAML tab.")
            vide.setObjectName("Muted")
            vide.setWordWrap(True)
            self._form.addWidget(vide)

        self._form.addStretch(1)
        self._connect_change_tracking()
        self._filter_settings(self.settings_search.text())

    def _groupe(self, titre: str, prefixe: tuple, contenu: dict) -> QWidget:
        boite = QFrame()
        boite.setObjectName("ConfigGroup")
        colonne = QVBoxLayout(boite)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_3,
                                   t.SPACE_3, t.SPACE_3)
        colonne.setSpacing(t.SPACE_2)

        etiquette = QLabel(titre)
        etiquette.setObjectName("Title")
        colonne.addWidget(etiquette)

        formulaire = QFormLayout()
        formulaire.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        formulaire.setSpacing(t.SPACE_2)

        for nom, valeur in contenu.items():
            if isinstance(valeur, dict):
                # Une section dans une section : le formulaire s'arrete la, et
                # le dit plutot que de faire disparaitre le reglage.
                imbriquee = QLabel("nested section — edit it in the YAML tab")
                imbriquee.setObjectName("Faint")
                formulaire.addRow(_joli(nom), imbriquee)
                continue
            formulaire.addRow(_joli(nom),
                              self._widget(prefixe + (nom,), nom, valeur))

        colonne.addLayout(formulaire)
        recherche = " ".join((titre, *(_joli(nom) for nom in contenu))).lower()
        self._groupes.append((boite, recherche))
        return boite

    # ------------------------------------------------------------------ champs

    def _widget(self, chemin: tuple, nom: str, valeur) -> QWidget:
        cle = config_file.normaliser(nom)
        boite = QWidget()
        ligne = QVBoxLayout(boite)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(2)

        saisie, lire = self._saisie(cle, valeur)
        ligne.addWidget(saisie)

        explication = EXPLICATIONS.get(cle)
        if explication:
            aide = QLabel(explication)
            aide.setObjectName("Faint")
            aide.setWordWrap(True)
            ligne.addWidget(aide)

        self._champs.append(_Champ(chemin, saisie, lire, lire()))
        return boite

    def _saisie(self, cle: str, valeur):
        """Le widget adapte au type de la valeur, et de quoi la relire."""
        # `cle:` sans rien derriere se lit None. Rendu par `str()`, il
        # remplissait le champ du mot « None » -- que rien ne distingue d'une
        # valeur voulue, et qui serait ecrit tel quel a l'enregistrement.
        if valeur is None:
            valeur = ""

        if isinstance(valeur, bool):
            case = QCheckBox()
            case.setChecked(valeur)
            return case, case.isChecked

        if isinstance(valeur, int):
            champ = QSpinBox()
            champ.setRange(-1_000_000, 1_000_000)
            champ.setValue(valeur)
            return champ, champ.value

        if isinstance(valeur, float):
            champ = QDoubleSpinBox()
            champ.setRange(-1_000_000, 1_000_000)
            champ.setDecimals(3)
            champ.setValue(valeur)
            return champ, champ.value

        if isinstance(valeur, (list, tuple)):
            if cle in CLES_READERS:
                champ = ReaderList(valeur, self._readers_connus)
                return champ, champ.valeurs
            champ = QPlainTextEdit("\n".join(str(v) for v in valeur))
            champ.setFixedHeight(t.CONTROL_MD * 3)
            return champ, lambda: [l.strip() for l in
                                   champ.toPlainText().splitlines() if l.strip()]

        if cle in CLES_READER or cle in CLES_READERS:
            champ = QComboBox()
            champ.setEditable(True)
            # Le lecteur en cours reste choisissable meme debranche : sans
            # cela, rouvrir la configuration ferait disparaitre le reglage.
            propositions = list(dict.fromkeys(
                [str(valeur)] + [str(r) for r in self._readers_connus]))
            champ.addItems([p for p in propositions if p])
            champ.setCurrentText(str(valeur))
            return champ, champ.currentText

        champ = QLineEdit(str(valeur))
        if cle in CLES_DOSSIER or cle in CLES_FICHIER:
            return self._avec_parcourir(champ, cle in CLES_FICHIER), champ.text
        return champ, champ.text

    def _avec_parcourir(self, champ: QLineEdit, fichier: bool) -> QWidget:
        boite = QWidget()
        ligne = QHBoxLayout(boite)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)

        bouton = QPushButton("Browse…")
        bouton.setObjectName("Ghost")
        bouton.clicked.connect(lambda: self._parcourir(champ, fichier))

        ligne.addWidget(champ, 1)
        ligne.addWidget(bouton)
        return boite

    def _parcourir(self, champ: QLineEdit, fichier: bool) -> None:
        depart = champ.text() or str(self.path.parent)
        if fichier:
            choisi, _ = QFileDialog.getOpenFileName(self, "Choose a file", depart)
        else:
            choisi = QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                      depart)
        if choisi:
            champ.setText(choisi)

    # ------------------------------------------------------------- onglets

    def _connect_change_tracking(self) -> None:
        """Observe les widgets du formulaire sans connaitre leur type métier."""
        for field in self.form_host.findChildren(QLineEdit):
            field.textChanged.connect(self._refresh_dirty_state)
        for field in self.form_host.findChildren(QComboBox):
            field.currentTextChanged.connect(self._refresh_dirty_state)
        for field in self.form_host.findChildren(QCheckBox):
            field.toggled.connect(self._refresh_dirty_state)
        for field in self.form_host.findChildren(QSpinBox):
            field.valueChanged.connect(self._refresh_dirty_state)
        for field in self.form_host.findChildren(QDoubleSpinBox):
            field.valueChanged.connect(self._refresh_dirty_state)
        for field in self.form_host.findChildren(QPlainTextEdit):
            field.textChanged.connect(self._refresh_dirty_state)
        for readers in self.form_host.findChildren(ReaderList):
            readers.list.itemChanged.connect(self._refresh_dirty_state)
            readers.list.model().rowsInserted.connect(self._refresh_dirty_state)
            readers.list.model().rowsRemoved.connect(self._refresh_dirty_state)

    def _filter_settings(self, text: str) -> None:
        query = text.strip().lower()
        for group, haystack in self._groupes:
            group.setVisible(not query or query in haystack)

    def _has_raw_changes(self) -> bool:
        return self.raw.toPlainText() != self._loaded_raw

    def _refresh_dirty_state(self, *_args) -> None:
        if not self._tracking_changes:
            return
        dirty = (self._has_raw_changes() if self.tabs.currentIndex() == ONGLET_YAML
                 else bool(self._modifications()))
        self._set_state("modified" if dirty else "saved")

    def _set_state(self, state: str) -> None:
        labels = {
            "saved": ("Enregistré", "ConfigStateSaved"),
            "modified": ("Modifié", "ConfigStateModified"),
            "error": ("Erreur YAML", "ConfigStateError"),
        }
        text, object_name = labels[state]
        self.state_badge.setText(text)
        self.state_badge.setObjectName(object_name)
        self.state_badge.style().unpolish(self.state_badge)
        self.state_badge.style().polish(self.state_badge)
        self.discard_button.setEnabled(state != "saved")

    def _on_tab(self, index: int) -> None:
        """Passer a l'onglet YAML relit le FICHIER, pas le formulaire.

        Y afficher ce que le formulaire a en memoire donnerait un texte
        reserialise, commentaires effaces -- exactement ce qu'on cherche a
        eviter. Les modifications non enregistrees sont signalees plutot que
        recopiees.
        """
        self.settings_search.setVisible(index == ONGLET_FORMULAIRE)
        self._refresh_dirty_state()
        if index != ONGLET_YAML:
            return
        if self._modifications():
            self._dire("Unsaved changes in the form are not shown here. "
                       "Save first, or edit the file below directly.", alerte=True)
        else:
            self._dire("")

    # --------------------------------------------------------- enregistrement

    def _modifications(self) -> dict:
        """Uniquement ce qui a change : le reste du fichier n'est pas touche."""
        return {champ.chemin: champ.valeur()
                for champ in self._champs if champ.a_change()}

    def save(self) -> None:
        if self.tabs.currentIndex() == ONGLET_YAML:
            self._enregistrer_texte()
        else:
            self._enregistrer_formulaire()

    def _enregistrer_formulaire(self) -> None:
        changements = self._modifications()
        if not changements:
            self._dire("Nothing to save.")
            return

        ok, message = config_file.ecrire(self.path, changements)
        if not ok:
            self._dire(f"Could not write: {message}", alerte=True)
            return

        self.reload()
        combien = len(changements)
        self._dire(f"Saved {combien} setting{'s' if combien > 1 else ''}.")
        self.saved.emit(str(self.path))

    def _enregistrer_texte(self) -> None:
        texte = self.raw.toPlainText()
        valide, probleme = config_file.valider(texte)
        if not valide:
            # Rien n'est ecrit : un YAML invalide rendrait le workspace
            # incollectable, et l'erreur ressortirait bien plus tard sous la
            # forme d'une collecte qui echoue sans raison apparente.
            self._dire(f"Not saved — {probleme}", alerte=True)
            self._set_state("error")
            match = re.search(r"line\s+(\d+)", str(probleme), re.IGNORECASE)
            if match:
                line = max(1, int(match.group(1)))
                cursor = self.raw.textCursor()
                cursor.movePosition(QTextCursor.Start)
                cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor,
                                    line - 1)
                cursor.select(QTextCursor.LineUnderCursor)
                self.raw.setTextCursor(cursor)
                self.raw.centerCursor()
                self.raw.setFocus()
            return

        ok, message = config_file.ecrire_texte(self.path, texte)
        if not ok:
            self._dire(f"Could not write: {message}", alerte=True)
            return

        self.reload()
        self.tabs.setCurrentIndex(ONGLET_YAML)
        self._dire("Saved.")
        self.saved.emit(str(self.path))

    def _dire(self, message: str, alerte: bool = False) -> None:
        from runner.domain.models import Status

        self.status.setText(message)
        couleur = t.status_color(Status.FAILED) if alerte else t.TEXT_MUTED
        self.status.setStyleSheet(
            f"color: {couleur}; font-size: {t.TEXT_SM}px; background: transparent;")
