"""Panneau de droite : Console, Source et Log.

Cliquer sur un test dans l'arbre affiche son code source et son fichier de log
sans quitter l'application. La console reste l'onglet par defaut et conserve
exactement son comportement : `panel.console` est le QTextEdit historique.

Le log est retrouve par le meme chemin que le mode "Ouvrir le log" : le conftest
du workspace ecrit un fichier par test dans le dossier indique par la cle
`log_directory` de son config.yml, et un manifeste fait le lien nodeid -> fichier.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QTextCursor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QTabBar,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.pytest_executor import compact_path
from gui_qt.code_view import CodeView
from gui_qt.config.config_loader import (
    find_config_declaring_log_path,
    find_test_log,
    resolve_log_root,
    run_directories,
)
from gui_qt.highlighters import LogHighlighter, PythonHighlighter, PytestOutputHighlighter
from gui_qt.styles import styles
from gui_qt.styles.styles import console_style, theme_toggle_button
from gui_qt.test_tree_view import short_reader_label

CONSOLE_TAB = 0
SOURCE_TAB = 1
LOG_TAB = 2

# Taille au-dela de laquelle on n'affiche que le debut du fichier : ouvrir un log
# de plusieurs dizaines de Mo figerait l'interface.
MAX_DISPLAY_BYTES = 2_000_000

# Delai apres la derniere frappe avant enregistrement. Assez court pour qu'un
# lancement de tests juste apres une correction parte du bon fichier, assez long
# pour ne pas ecrire a chaque caractere.
AUTOSAVE_DELAY_MS = 700


def function_name_from_nodeid(nodeid: str) -> str | None:
    """Nom de la fonction de test, sans la classe ni le parametre.

    'a/test_x.py::TestC::test_f[cas]' -> 'test_f'
    """
    if "::" not in nodeid:
        return None
    last = nodeid.split("::")[-1]
    return last.split("[", 1)[0].strip() or None


def read_text_file(path: Path) -> tuple[str, str | None]:
    """Contenu du fichier et message d'avertissement eventuel.

    Les logs de test peuvent contenir des octets non decodables (traces APDU
    brutes) : on remplace plutot que d'echouer.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "", f"Could not read: {exc}"

    warning = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > MAX_DISPLAY_BYTES:
                content = f.read(MAX_DISPLAY_BYTES)
                warning = (
                    f"File truncated to {MAX_DISPLAY_BYTES // 1_000_000} MB "
                    f"(actual size: {size / 1_000_000:.1f} MB)."
                )
            else:
                content = f.read()
    except OSError as exc:
        return "", f"Could not read: {exc}"

    return content, warning


def read_source_file(path: Path) -> tuple[str, str | None, str, bool]:
    """Contenu d'un fichier source, avec de quoi le reecrire fidelement.

    Retourne (contenu, avertissement, fin_de_ligne, modifiable). Un fichier
    tronque ou qui ne se decode pas en UTF-8 n'est pas modifiable : le
    reecrire depuis ce qui est affiche detruirait ce qui n'a pas ete lu.

    La fin de ligne d'origine est retenue pour ne pas convertir tout un
    fichier CRLF en LF (ou l'inverse) a la premiere frappe, ce qui ferait un
    diff de plusieurs milliers de lignes.
    """
    try:
        brut = path.read_bytes()
    except OSError as exc:
        return "", f"Could not read: {exc}", "\n", False

    tronque = len(brut) > MAX_DISPLAY_BYTES
    if tronque:
        brut = brut[:MAX_DISPLAY_BYTES]

    try:
        texte = brut.decode("utf-8")
        modifiable = not tronque
    except UnicodeDecodeError:
        texte = brut.decode("utf-8", errors="replace")
        modifiable = False

    crlf = texte.count("\r\n")
    fin_de_ligne = "\r\n" if crlf > texte.count("\n") - crlf else "\n"
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")

    avertissement = None
    if tronque:
        avertissement = (
            f"File truncated to {MAX_DISPLAY_BYTES // 1_000_000} MB: read-only."
        )
    elif not modifiable:
        avertissement = "File not decodable as UTF-8: read-only."

    return texte, avertissement, fin_de_ligne, modifiable


def write_source_file(path: Path, texte: str, fin_de_ligne: str) -> str | None:
    """Ecrit le fichier source. Retourne un message d'erreur, ou None.

    L'ecriture passe par un fichier temporaire du meme dossier, remplace
    ensuite d'un seul coup : un disque plein ou un verrou en cours de route
    laisserait sinon le fichier de test a moitie ecrit.
    """
    contenu = texte.replace("\n", fin_de_ligne) if fin_de_ligne != "\n" else texte
    temporaire = path.with_name(path.name + ".pytestrunner.tmp")

    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as f:
            f.write(contenu)
        os.replace(temporaire, path)
    except OSError as exc:
        try:
            temporaire.unlink()
        except OSError:
            pass
        return f"Could not save: {exc}"

    return None


def _reader_box(header: QLabel, vue: QWidget) -> QWidget:
    """Une vue de lecteur : son en-tete au-dessus, la vue en dessous."""
    boite = QWidget()
    col = QVBoxLayout(boite)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(2)
    col.addWidget(header)
    col.addWidget(vue)
    return boite


class ReaderStack(QWidget):
    """Une vue par lecteur, avec onglets pour choisir et bouton pour comparer.

    Console et Log ont exactement le meme besoin : montrer une vue a la fois
    quand on suit un lecteur, les montrer toutes quand on veut les comparer.
    Le seul reglage qui change est le sens de la comparaison -- les consoles
    l'une sous l'autre (leurs lignes defilent), les logs cote a cote (on
    compare la meme ligne d'un lecteur a l'autre).
    """

    reader_selected = pyqtSignal(int)

    def __init__(self, orientation, texte_comparer: str, texte_revenir: str,
                 synchroniser_defilement: bool = False, parent=None):
        super().__init__(parent)

        self.views: list[QWidget] = []
        self.headers: list[QLabel] = []
        self._labels: list[str] = []
        self._texte_comparer = texte_comparer
        self._texte_revenir = texte_revenir
        self._synchroniser = synchroniser_defilement
        # Garde contre la reaction en chaine : deplacer une barre en deplace une
        # autre, qui redeplacerait la premiere.
        self._en_defilement = False

        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        # Fenetre etroite + plusieurs lecteurs : les onglets peuvent quand meme
        # manquer de place. Une ellipse et des fleches de defilement valent
        # mieux qu'un texte tronque sans le dire ; le nom complet reste de
        # toute facon dans l'infobulle.
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.compare_button = QToolButton()
        self.compare_button.setText("⊞")
        self.compare_button.setCheckable(True)
        self.compare_button.setAutoRaise(True)
        self.compare_button.setCursor(Qt.PointingHandCursor)
        self.compare_button.setToolTip(texte_comparer)
        self.compare_button.setVisible(False)
        self.compare_button.toggled.connect(self._on_compare_toggled)

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(4)
        barre.addWidget(self.tabs, 1)
        barre.addWidget(self.compare_button)

        self.split = QSplitter(orientation)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(2)
        colonne.addLayout(barre)
        colonne.addWidget(self.split)

    def add_view(self, vue: QWidget, header: QLabel):
        self.views.append(vue)
        self.headers.append(header)
        self.split.addWidget(_reader_box(header, vue))

        if self._synchroniser:
            for sens in ("verticalScrollBar", "horizontalScrollBar"):
                barre = getattr(vue, sens)()
                barre.valueChanged.connect(
                    lambda valeur, s=sens, v=vue: self._propager_defilement(s, v, valeur))

    def _propager_defilement(self, sens: str, source: QWidget, valeur: int):
        """Fait suivre les autres vues, pour comparer la meme ligne partout.

        Cote a cote, chaque vue ne montre que la moitie de la largeur : sans
        cela, amener la valeur d'un lecteur sous les yeux laissait celle de
        l'autre hors champ, et il n'y avait plus rien a comparer.
        """
        if self._en_defilement:
            return

        self._en_defilement = True
        try:
            for vue in self.views:
                if vue is source:
                    continue
                barre = getattr(vue, sens)()
                if barre.value() != valeur:
                    barre.setValue(valeur)
        finally:
            self._en_defilement = False

    def set_readers(self, labels: list[str]):
        """Un onglet par lecteur, ou aucun quand il n'y en a qu'un."""
        self._labels = list(labels)
        multi = len(self._labels) > 1

        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for index, nom in enumerate(self._labels if multi else []):
            self.tabs.addTab(short_reader_label(nom))
            self.tabs.setTabToolTip(index, nom)
            self.tabs.setTabTextColor(index, QColor(styles.reader_color(index)))
        self.tabs.blockSignals(False)

        self.tabs.setVisible(multi)
        self.compare_button.setVisible(multi)
        self.apply_layout()

    def apply_layout(self):
        """Montre la vue de l'onglet courant, ou toutes en mode comparaison."""
        nombre = max(1, len(self._labels))
        comparer = self.compare_button.isChecked()
        courant = max(0, self.tabs.currentIndex())

        for index, vue in enumerate(self.views):
            boite = vue.parentWidget()
            if boite is None:
                continue
            if index >= nombre:
                boite.setVisible(False)
            else:
                boite.setVisible(comparer or nombre == 1 or index == courant)

    def show_reader(self, index: int):
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def select_silently(self, index: int):
        """Change l'onglet courant sans reemettre reader_selected.

        Sert a garder Console et Log sur le meme lecteur : sans cela, chacun
        renverrait son choix a l'autre, indefiniment.
        """
        if not 0 <= index < self.tabs.count() or index == self.tabs.currentIndex():
            return
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self.apply_layout()

    def _on_tab_changed(self, index: int):
        self.apply_layout()
        self.reader_selected.emit(index)

    def _on_compare_toggled(self, actif: bool):
        self.compare_button.setToolTip(
            self._texte_revenir if actif else self._texte_comparer)
        self.apply_layout()


class DetailPanel(QWidget):
    """Onglets Console / Source / Log affiches a droite de l'arbre."""

    # Emis quand l'utilisateur demande a detacher (True) ou rattacher (False) le
    # panneau. La fenetre principale s'en charge : elle seule connait le
    # splitter d'ou le panneau sort et ou il revient.
    detach_requested = pyqtSignal(bool)

    # Emis avec l'index du lecteur dont la console vient d'etre amenee au
    # premier plan. Les compteurs de bas de fenetre s'y accrochent pour montrer
    # le resultat de CE lecteur plutot que le total de tous.
    reader_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.workspace: str | None = None
        # Fichier de configuration retenu pour ce workspace : il porte le
        # LOG_PATH quand il ne s'appelle pas config.yml.
        self.config_path: str | None = None
        self._current_source: Path | None = None
        self._source_newline = "\n"
        self._source_editable = False
        self._dirty = False
        # Vrai pendant le remplissage de la vue : le textChanged provoque par
        # setPlainText ne doit pas passer pour une modification de l'utilisateur.
        self._loading = False

        # Une console par lecteur, l'une SOUS l'autre en comparaison : leurs
        # lignes defilent, on suit chacune sur toute la largeur.
        self.console_stack = ReaderStack(
            Qt.Vertical,
            "Show all consoles at once",
            "Back to one console at a time")
        self.console_stack.reader_selected.connect(
            lambda i: self._on_reader_chosen(i, self.log_stack))

        # Noms historiques, conserves : tout le code d'affichage existant
        # continue d'ecrire dans `self.console` sans changement.
        self.console_area = self.console_stack
        self.console_tabs = self.console_stack.tabs
        self.compare_button = self.console_stack.compare_button
        self.console_split = self.console_stack.split
        self.consoles: list[QTextEdit] = self.console_stack.views
        self.console_headers: list[QLabel] = self.console_stack.headers

        entete_console = QLabel()
        entete_console.setVisible(False)
        self.console_stack.add_view(self._new_console(), entete_console)
        self.console = self.consoles[0]

        self.source_view = CodeView()

        # Un log par lecteur, cote a cote en comparaison : le meme test ecrit
        # son propre .log sur chaque lecteur, et c'est en les mettant l'un a
        # cote de l'autre qu'on voit a quelle ligne ils divergent.
        self.log_stack = ReaderStack(
            Qt.Horizontal,
            "Show every reader's log side by side",
            "Back to one log at a time",
            synchroniser_defilement=True)
        self.log_stack.reader_selected.connect(
            lambda i: self._on_reader_chosen(i, self.console_stack))

        self.log_area = self.log_stack
        self.log_tabs = self.log_stack.tabs
        self.log_compare_button = self.log_stack.compare_button
        self.log_split = self.log_stack.split
        self.log_views: list[QPlainTextEdit] = self.log_stack.views
        self.log_headers: list[QLabel] = self.log_stack.headers

        self.log_header = QLabel("Click a test in the tree to see its log.")
        self.log_header.setWordWrap(True)
        self.log_stack.add_view(self._new_log_view(), self.log_header)
        self.log_view = self.log_views[0]

        # Coloration a l'affichage : la sortie brute reste intacte pour
        # l'historique, les traces d'echec et la detection des statuts.
        self.console_highlighters = [PytestOutputHighlighter(self.console.document())]
        self.console_highlighter = self.console_highlighters[0]
        self.source_highlighter = PythonHighlighter(self.source_view.document())
        self.log_highlighters = [LogHighlighter(self.log_view.document())]
        self.log_highlighter = self.log_highlighters[0]

        self.source_header = QLabel("Click a test in the tree to see its source code.")
        for header in (self.source_header, self.log_header):
            header.setWordWrap(True)

        # Bouton discret : la modification est un geste volontaire, on ne tape
        # pas par megarde dans un fichier de test en le consultant.
        self.edit_button = QToolButton()
        self.edit_button.setText("✎")
        self.edit_button.setCheckable(True)
        self.edit_button.setAutoRaise(True)
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setEnabled(False)
        self.edit_button.toggled.connect(self.set_source_editable)

        self.source_status = QLabel("")

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTOSAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_source)
        self.source_view.textChanged.connect(self._on_source_edited)

        # Bouton de detachement, loge dans le coin des onglets : il doit rester
        # atteignable depuis Console, Source et Log.
        self.detach_button = QToolButton()
        self.detach_button.setText("⧉")
        self.detach_button.setCheckable(True)
        self.detach_button.setAutoRaise(True)
        self.detach_button.setCursor(Qt.PointingHandCursor)
        self.detach_button.setToolTip(
            "Detach this panel into its own window (second screen, full screen...)")
        self.detach_button.toggled.connect(self._on_detach_toggled)

        self.tabs = QTabWidget()
        self.tabs.setCornerWidget(self.detach_button, Qt.TopRightCorner)
        self.tabs.addTab(self.console_area, "Console")
        self.tabs.addTab(
            self._wrap(self.source_header, self.source_view,
                       self.source_status, self.edit_button),
            "Source",
        )
        self.tabs.addTab(self.log_area, "Log")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        self._refresh_edit_button()
        self.restyle()

    @staticmethod
    def _new_console() -> QTextEdit:
        vue = QTextEdit()
        vue.setReadOnly(True)
        vue.document().setMaximumBlockCount(12000)
        vue.setLineWrapMode(QTextEdit.NoWrap)
        return vue

    @staticmethod
    def _new_log_view() -> QPlainTextEdit:
        vue = QPlainTextEdit()
        vue.setReadOnly(True)
        vue.setLineWrapMode(QPlainTextEdit.NoWrap)
        return vue

    def set_readers(self, labels: list[str]):
        """Une console par lecteur, atteignable par onglet.

        Une console unique melangeant des runs simultanes serait illisible : les
        lignes s'y entrelaceraient au rythme des cartes. Les empiler toutes ne
        tient qu'a deux lecteurs, d'ou les onglets, et le bouton "Comparer" pour
        les remettre cote a cote quand on veut les lire ensemble.
        """
        labels = list(labels)
        multi = len(labels) > 1

        while len(self.consoles) < len(labels):
            vue = self._new_console()
            self.console_highlighters.append(PytestOutputHighlighter(vue.document()))
            self.console_stack.add_view(vue, QLabel())

        while len(self.log_views) < len(labels):
            vue = self._new_log_view()
            entete = QLabel()
            entete.setWordWrap(True)
            self.log_highlighters.append(LogHighlighter(vue.document()))
            self.log_stack.add_view(vue, entete)

        self._reader_labels = labels
        self.console_stack.set_readers(labels)
        self.log_stack.set_readers(labels)

        # L'en-tete d'une console nomme son lecteur ; celui d'un log porte le
        # chemin du fichier, pose par _load_log_into().
        for index, entete in enumerate(self.console_headers):
            if multi and index < len(labels):
                entete.setText(labels[index])
                entete.setVisible(True)
            else:
                entete.setVisible(False)

        self.restyle()

    def _on_reader_chosen(self, index: int, autre: "ReaderStack"):
        """Console et Log restent sur le meme lecteur, quel que soit l'onglet
        par lequel on l'a choisi."""
        autre.select_silently(index)
        self.reader_selected.emit(index)

    def _on_detach_toggled(self, detache: bool):
        self.detach_button.setToolTip(
            "Put this panel back in the main window" if detache
            else "Detach this panel into its own window (second screen, full screen...)")
        self.detach_requested.emit(detache)

    def show_reader(self, reader_index: int):
        """Amene la console ET le log de ce lecteur au premier plan."""
        self.console_stack.show_reader(reader_index)

    def console_for(self, reader_index: int) -> QTextEdit:
        """Console de ce lecteur, la premiere a defaut."""
        if 0 <= reader_index < len(self.consoles):
            return self.consoles[reader_index]
        return self.console

    @staticmethod
    def _wrap(header: QLabel, view: QPlainTextEdit, *extras: QWidget) -> QWidget:
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(6, 6, 6, 6)
        box.setSpacing(4)

        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(6)
        ligne.addWidget(header, 1)
        for extra in extras:
            ligne.addWidget(extra)

        box.addLayout(ligne)
        box.addWidget(view)
        return container

    def restyle(self):
        for index, vue in enumerate(self.consoles):
            vue.setStyleSheet(console_style())
            entete = self.console_headers[index]
            couleur = styles.reader_color(index)
            # Ni gras ni gros : l'en-tete nomme la console, il ne doit pas
            # peser plus que ce qu'elle contient.
            entete.setStyleSheet(
                f"color:{couleur}; font-weight:500; font-size:11px; padding:2px 6px;"
                f"border-left:3px solid {couleur};"
                f"background:{styles.mix(styles.palette()['surface'], couleur, 0.07)};"
            )
        for barre in (self.console_tabs, self.log_tabs):
            barre.setStyleSheet(styles.reader_tab_style())
            for index in range(barre.count()):
                barre.setTabTextColor(index, QColor(styles.reader_color(index)))
        for bouton in (self.compare_button, self.log_compare_button,
                       self.detach_button):
            bouton.setStyleSheet(theme_toggle_button())
        self.source_view.setStyleSheet(console_style())
        # Les logs par lecteur portent la meme pastille de couleur que leur
        # console, pour qu'on sache d'un coup d'oeil lequel on lit.
        multi = len(getattr(self, "_reader_labels", [])) > 1
        for index, vue in enumerate(self.log_views):
            vue.setStyleSheet(console_style())
            entete = self.log_headers[index]
            if multi:
                couleur = styles.reader_color(index)
                entete.setStyleSheet(
                    f"color:{couleur}; font-weight:500; font-size:10px; padding:1px 5px;"
                    f"border-left:2px solid {couleur};"
                    f"background:{styles.mix(styles.palette()['surface'], couleur, 0.06)};"
                )
            else:
                entete.setStyleSheet(
                    f"color:{styles.palette()['text_muted']}; font-size:10px; padding:1px 2px;")
        self.source_header.setStyleSheet(styles.muted_label())
        self.source_status.setStyleSheet(styles.muted_label())
        self.edit_button.setStyleSheet(theme_toggle_button())

        # Les couleurs de coloration viennent de la palette : elles doivent etre
        # reconstruites, pas seulement reappliquees.
        for highlighter in [*self.console_highlighters, self.source_highlighter,
                            *self.log_highlighters]:
            highlighter.refresh()
        self.source_view.restyle()

    # ------------------------------------------------------------------
    # Modification du fichier source
    # ------------------------------------------------------------------

    def _refresh_edit_button(self):
        modifiable = self._source_editable and self._current_source is not None
        self.edit_button.setEnabled(modifiable)
        if not modifiable:
            self.edit_button.setToolTip(
                "This file cannot be edited here." if self._current_source
                else "Choose a test file to edit it."
            )
        elif self.edit_button.isChecked():
            self.edit_button.setToolTip("Back to read-only (saved)")
        else:
            self.edit_button.setToolTip("Edit this file (auto-saved)")

    def set_source_editable(self, editable: bool):
        """Bascule l'onglet Source entre lecture seule et edition."""
        if editable and not (self._source_editable and self._current_source):
            self.edit_button.setChecked(False)
            return

        self.source_view.setReadOnly(not editable)
        if editable:
            self.source_view.setFocus()
            self.source_status.setText("Editing enabled")
        else:
            self.save_source()

        self._refresh_edit_button()

    def _on_source_edited(self):
        if self._loading or self.source_view.isReadOnly():
            return
        self._dirty = True
        self.source_status.setText("Modified...")
        self._save_timer.start()

    def save_source(self) -> bool:
        """Ecrit les modifications en attente. Retourne True si un test relance
        maintenant partira bien du fichier affiche."""
        self._save_timer.stop()
        if not self._dirty or self._current_source is None:
            return True

        erreur = write_source_file(
            self._current_source, self.source_view.toPlainText(), self._source_newline
        )
        if erreur:
            self.source_status.setText(erreur)
            return False

        self._dirty = False
        self.source_status.setText("Saved")
        return True

    def set_workspace(self, workspace: str | None, config_path: str | None = None):
        """`config_path` est le fichier de configuration retenu pour ce
        workspace : c'est lui qui porte LOG_PATH quand il ne s'appelle pas
        config.yml."""
        self.workspace = workspace
        self.config_path = config_path

    def clear_details(self):
        self.save_source()
        self._show_no_source("Click a test in the tree to see its source code.")
        for vue in self.log_views:
            vue.clear()
        for entete in self.log_headers:
            entete.setText("Click a test in the tree to see its log.")

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def show_for(self, target: str | None, nodeid: str | None):
        """Charge la source et le log correspondant a l'element clique.

        `target` porte le chemin (fichier, classe ou fonction), `nodeid` n'existe
        que pour les feuilles executables.
        """
        self._load_source(target, nodeid)
        self._load_log(nodeid)

    def _load_source(self, target: str | None, nodeid: str | None):
        # Changer de fichier ne doit jamais perdre une frappe en attente.
        self.save_source()

        if not self.workspace or not target:
            self._show_no_source("No workspace loaded.")
            return

        relative = target.split("::", 1)[0]
        if not relative.endswith(".py"):
            self._show_no_source(
                f"{relative} is a folder: choose a file or a test."
            )
            return

        path = Path(self.workspace) / relative
        if not path.is_file():
            self._show_no_source(f"Source file not found: {path}")
            return

        content, warning, newline, editable = read_source_file(path)

        self._loading = True
        try:
            self.source_view.setPlainText(content)
        finally:
            self._loading = False

        self._current_source = path
        self._source_newline = newline
        self._source_editable = editable
        self._dirty = False
        self._set_editing(False)
        self.source_status.setText("")

        header = str(path)
        if warning:
            header += f"    ({warning})"
        self.source_header.setText(header)

        function = function_name_from_nodeid(nodeid or target or "")
        if function:
            self._scroll_to_function(content, function)

    def _show_no_source(self, message: str):
        self._current_source = None
        self._source_editable = False
        self._dirty = False
        self._set_editing(False)
        self._loading = True
        try:
            self.source_view.clear()
        finally:
            self._loading = False
        self.source_header.setText(message)
        self.source_status.setText("")

    def _set_editing(self, editing: bool):
        """Repositionne le bouton sans repasser par son gestionnaire."""
        self.edit_button.blockSignals(True)
        self.edit_button.setChecked(editing)
        self.edit_button.blockSignals(False)
        self.source_view.setReadOnly(not editing)
        self._refresh_edit_button()

    def _scroll_to_function(self, content: str, function: str):
        """Place le curseur sur la definition du test, pour ne pas atterrir en
        haut d'un fichier de plusieurs milliers de lignes."""
        # Espaces horizontaux uniquement : \s engloberait les sauts de ligne, et
        # le motif commencerait alors a matcher sur les lignes vides qui
        # precedent la definition, placant le curseur trop haut.
        pattern = re.compile(
            rf"^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(function)}[ \t]*\(",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if not match:
            return

        line = content.count("\n", 0, match.start())
        cursor = self.source_view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, line)
        # On place le curseur sans selectionner la ligne : une selection posee
        # son fond bleu par-dessus le texte, illisible en theme clair. La
        # surbrillance discrete de la ligne courante suffit a la reperer.
        self.source_view.setTextCursor(cursor)
        self.source_view.centerCursor()

    def _explain_missing_log(self) -> str:
        """Dit ou l'on a cherche et d'ou vient ce chemin.

        Sans cela, un LOG_PATH non lu (fichier de configuration au nom
        inhabituel) donnait un onglet vide, sans aucun moyen de comprendre que
        le GUI regardait dans `<workspace>/logs`.
        """
        racine = resolve_log_root(self.workspace, self.config_path)
        declarant = find_config_declaring_log_path(self.workspace, self.config_path)

        lignes = ["No log for this test.", f"Searched in: {racine}"]
        if declarant is not None:
            lignes.append(f"Path read from: {declarant.name}")
        else:
            lignes.append(
                "No workspace configuration file declares a "
                "LOG_PATH: using the default folder."
            )
        if not racine.is_dir():
            lignes.append("This folder does not exist yet.")
        else:
            runs = run_directories(racine)
            lignes.append(
                f"{len(runs)} run folder(s) examined, most recent first."
                if runs else "This folder has no run subfolder."
            )
        lignes.append("Run the test, or check the configuration's LOG_PATH key.")
        return "\n".join(lignes)

    def _load_log(self, nodeid: str | None):
        """Charge le log du test, un par lecteur quand il y en a plusieurs."""
        lecteurs = list(getattr(self, "_reader_labels", []))
        if len(lecteurs) > 1:
            for index, lecteur in enumerate(lecteurs[:len(self.log_views)]):
                self._load_log_into(index, nodeid, lecteur)
            return

        self._load_log_into(0, nodeid, "")

    def _load_log_into(self, index: int, nodeid: str | None, reader: str):
        if index >= len(self.log_views):
            return

        vue = self.log_views[index]
        entete = self.log_headers[index]
        # Le nom du lecteur suffit a nommer sa colonne : cote a cote, elle est
        # etroite, et le chemin ne differe d'un lecteur a l'autre que par le
        # dossier du lecteur -- justement ce que l'en-tete dit deja. Chemin
        # complet en infobulle.
        prefixe = f"{reader}  —  " if reader else ""

        if not self.workspace:
            entete.setText(prefixe + "No workspace loaded.")
            vue.clear()
            return

        if not nodeid:
            entete.setText(
                prefixe + "Select a specific test (a leaf of the tree) to see its log."
            )
            vue.clear()
            return

        path = find_test_log(self.workspace, nodeid, self.config_path, reader)
        if path is None:
            entete.setText(prefixe + self._explain_missing_log())
            vue.clear()
            return

        content, warning = read_text_file(Path(path))
        vue.setPlainText(content)
        # Le nom du lecteur, ou a defaut le seul nom du fichier : un chemin de
        # log reel fait plusieurs lignes de gros texte au-dessus du log, pour
        # une information qu'on ne lit pas. Chemin complet en infobulle.
        header = reader if reader else compact_path(str(path), levels=0)
        if warning:
            header += f"    ({warning})"
        entete.setText(header)
        entete.setToolTip(str(path))
        vue.moveCursor(QTextCursor.End)

    # ------------------------------------------------------------------
    # Confort
    # ------------------------------------------------------------------

    def show_console(self):
        self.tabs.setCurrentIndex(CONSOLE_TAB)

    def show_source(self):
        self.tabs.setCurrentIndex(SOURCE_TAB)

    def show_log(self):
        self.tabs.setCurrentIndex(LOG_TAB)
