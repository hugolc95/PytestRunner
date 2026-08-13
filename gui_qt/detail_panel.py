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
        return "", f"Lecture impossible : {exc}"

    warning = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > MAX_DISPLAY_BYTES:
                content = f.read(MAX_DISPLAY_BYTES)
                warning = (
                    f"Fichier tronque a {MAX_DISPLAY_BYTES // 1_000_000} Mo "
                    f"(taille reelle : {size / 1_000_000:.1f} Mo)."
                )
            else:
                content = f.read()
    except OSError as exc:
        return "", f"Lecture impossible : {exc}"

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
        return "", f"Lecture impossible : {exc}", "\n", False

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
            f"Fichier tronque a {MAX_DISPLAY_BYTES // 1_000_000} Mo : lecture seule."
        )
    elif not modifiable:
        avertissement = "Fichier non decodable en UTF-8 : lecture seule."

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
        return f"Enregistrement impossible : {exc}"

    return None


class DetailPanel(QWidget):
    """Onglets Console / Source / Log affiches a droite de l'arbre."""

    # Emis quand l'utilisateur demande a detacher (True) ou rattacher (False) le
    # panneau. La fenetre principale s'en charge : elle seule connait le
    # splitter d'ou le panneau sort et ou il revient.
    detach_requested = pyqtSignal(bool)

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

        # Une console par lecteur. `self.console` reste la premiere : tout le
        # code d'affichage existant continue d'ecrire dedans sans changement.
        self.consoles: list[QTextEdit] = [self._new_console()]
        self.console = self.consoles[0]
        self.console_headers: list[QLabel] = [QLabel()]
        self.console_headers[0].setVisible(False)

        # Un onglet par lecteur au-dessus, les consoles en dessous. En mode
        # onglets une seule est visible, ce qui tient a n'importe quel nombre de
        # lecteurs ; le bouton "Comparer" les montre toutes a la fois.
        self.console_tabs = QTabBar()
        self.console_tabs.setDrawBase(False)
        self.console_tabs.setExpanding(False)
        # Fenetre etroite + plusieurs lecteurs : les onglets peuvent quand meme
        # manquer de place. Une ellipse et des fleches de defilement valent
        # mieux qu'un texte tronque sans le dire ; le nom complet reste de
        # toute facon dans l'infobulle.
        self.console_tabs.setElideMode(Qt.ElideRight)
        self.console_tabs.setUsesScrollButtons(True)
        self.console_tabs.setVisible(False)
        self.console_tabs.currentChanged.connect(self._on_console_tab_changed)

        self.compare_button = QToolButton()
        self.compare_button.setText("⊞")
        self.compare_button.setCheckable(True)
        self.compare_button.setAutoRaise(True)
        self.compare_button.setCursor(Qt.PointingHandCursor)
        self.compare_button.setToolTip("Afficher toutes les consoles cote a cote")
        self.compare_button.setVisible(False)
        self.compare_button.toggled.connect(self._on_compare_toggled)

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(4)
        barre.addWidget(self.console_tabs, 1)
        barre.addWidget(self.compare_button)

        self.console_area = QWidget()
        self._console_layout = QVBoxLayout(self.console_area)
        self._console_layout.setContentsMargins(0, 0, 0, 0)
        self._console_layout.setSpacing(2)
        self._console_layout.addLayout(barre)
        self.console_split = QSplitter(Qt.Vertical)
        self._console_layout.addWidget(self.console_split)
        self.console_split.addWidget(
            self._console_box(self.console_headers[0], self.console))

        self.source_view = CodeView()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Coloration a l'affichage : la sortie brute reste intacte pour
        # l'historique, les traces d'echec et la detection des statuts.
        self.console_highlighters = [PytestOutputHighlighter(self.console.document())]
        self.console_highlighter = self.console_highlighters[0]
        self.source_highlighter = PythonHighlighter(self.source_view.document())
        self.log_highlighter = LogHighlighter(self.log_view.document())

        self.source_header = QLabel("Cliquez un test dans l'arbre pour voir son code source.")
        self.log_header = QLabel("Cliquez un test dans l'arbre pour voir son log.")
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
            "Detacher ce panneau dans sa propre fenetre (second ecran, plein ecran...)")
        self.detach_button.toggled.connect(self._on_detach_toggled)

        self.tabs = QTabWidget()
        self.tabs.setCornerWidget(self.detach_button, Qt.TopRightCorner)
        self.tabs.addTab(self.console_area, "Console")
        self.tabs.addTab(
            self._wrap(self.source_header, self.source_view,
                       self.source_status, self.edit_button),
            "Source",
        )
        self.tabs.addTab(self._wrap(self.log_header, self.log_view), "Log")

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
    def _console_box(header: QLabel, vue: QTextEdit) -> QWidget:
        boite = QWidget()
        col = QVBoxLayout(boite)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(header)
        col.addWidget(vue)
        return boite

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
            entete = QLabel()
            self.consoles.append(vue)
            self.console_headers.append(entete)
            self.console_highlighters.append(PytestOutputHighlighter(vue.document()))
            self.console_split.addWidget(self._console_box(entete, vue))

        self._reader_labels = labels

        self.console_tabs.blockSignals(True)
        while self.console_tabs.count():
            self.console_tabs.removeTab(0)
        for index, nom in enumerate(labels if multi else []):
            self.console_tabs.addTab(short_reader_label(nom))
            self.console_tabs.setTabToolTip(index, nom)
            self.console_tabs.setTabTextColor(index, QColor(styles.reader_color(index)))
        self.console_tabs.blockSignals(False)

        self.console_tabs.setVisible(multi)
        self.compare_button.setVisible(multi)

        for index, entete in enumerate(self.console_headers):
            if multi and index < len(labels):
                entete.setText(labels[index])
                entete.setVisible(True)
            else:
                entete.setVisible(False)

        self._apply_console_layout()
        self.restyle()

    def _apply_console_layout(self):
        """Montre la console de l'onglet courant, ou toutes en mode comparaison."""
        nombre = max(1, len(getattr(self, "_reader_labels", [])))
        comparer = self.compare_button.isChecked()
        courant = max(0, self.console_tabs.currentIndex())

        for index, vue in enumerate(self.consoles):
            boite = vue.parentWidget()
            if index >= nombre:
                boite.setVisible(False)
            else:
                boite.setVisible(comparer or nombre == 1 or index == courant)

    def _on_console_tab_changed(self, _index: int):
        self._apply_console_layout()

    def _on_compare_toggled(self, actif: bool):
        self.compare_button.setToolTip(
            "Revenir a une console a la fois" if actif
            else "Afficher toutes les consoles cote a cote")
        self._apply_console_layout()

    def _on_detach_toggled(self, detache: bool):
        self.detach_button.setToolTip(
            "Remettre ce panneau dans la fenetre principale" if detache
            else "Detacher ce panneau dans sa propre fenetre (second ecran, plein ecran...)")
        self.detach_requested.emit(detache)

    def show_reader(self, reader_index: int):
        """Amene la console de ce lecteur au premier plan."""
        if 0 <= reader_index < self.console_tabs.count():
            self.console_tabs.setCurrentIndex(reader_index)

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
        self.compare_button.setStyleSheet(theme_toggle_button())
        self.detach_button.setStyleSheet(theme_toggle_button())
        for index in range(self.console_tabs.count()):
            self.console_tabs.setTabTextColor(index, QColor(styles.reader_color(index)))
        self.source_view.setStyleSheet(console_style())
        self.log_view.setStyleSheet(console_style())
        self.source_header.setStyleSheet(styles.muted_label())
        self.log_header.setStyleSheet(styles.muted_label())
        self.source_status.setStyleSheet(styles.muted_label())
        self.edit_button.setStyleSheet(theme_toggle_button())

        # Les couleurs de coloration viennent de la palette : elles doivent etre
        # reconstruites, pas seulement reappliquees.
        for highlighter in [*self.console_highlighters, self.source_highlighter,
                            self.log_highlighter]:
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
                "Ce fichier n'est pas modifiable ici." if self._current_source
                else "Choisissez un fichier de test pour le modifier."
            )
        elif self.edit_button.isChecked():
            self.edit_button.setToolTip("Revenir en lecture seule (enregistre)")
        else:
            self.edit_button.setToolTip("Modifier ce fichier (enregistrement automatique)")

    def set_source_editable(self, editable: bool):
        """Bascule l'onglet Source entre lecture seule et edition."""
        if editable and not (self._source_editable and self._current_source):
            self.edit_button.setChecked(False)
            return

        self.source_view.setReadOnly(not editable)
        if editable:
            self.source_view.setFocus()
            self.source_status.setText("Modification activee")
        else:
            self.save_source()

        self._refresh_edit_button()

    def _on_source_edited(self):
        if self._loading or self.source_view.isReadOnly():
            return
        self._dirty = True
        self.source_status.setText("Modifie...")
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
        self.source_status.setText("Enregistre")
        return True

    def set_workspace(self, workspace: str | None, config_path: str | None = None):
        """`config_path` est le fichier de configuration retenu pour ce
        workspace : c'est lui qui porte LOG_PATH quand il ne s'appelle pas
        config.yml."""
        self.workspace = workspace
        self.config_path = config_path

    def clear_details(self):
        self.save_source()
        self._show_no_source("Cliquez un test dans l'arbre pour voir son code source.")
        self.log_view.clear()
        self.log_header.setText("Cliquez un test dans l'arbre pour voir son log.")

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
            self._show_no_source("Aucun workspace charge.")
            return

        relative = target.split("::", 1)[0]
        if not relative.endswith(".py"):
            self._show_no_source(
                f"{relative} est un dossier : choisissez un fichier ou un test."
            )
            return

        path = Path(self.workspace) / relative
        if not path.is_file():
            self._show_no_source(f"Fichier source introuvable : {path}")
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

        lignes = ["Aucun log pour ce test.", f"Cherche dans : {racine}"]
        if declarant is not None:
            lignes.append(f"Chemin lu dans : {declarant.name}")
        else:
            lignes.append(
                "Aucun fichier de configuration du workspace ne declare de "
                "LOG_PATH : dossier par defaut."
            )
        if not racine.is_dir():
            lignes.append("Ce dossier n'existe pas encore.")
        else:
            runs = run_directories(racine)
            lignes.append(
                f"{len(runs)} dossier(s) de run examine(s), du plus recent au plus ancien."
                if runs else "Ce dossier ne contient aucun sous-dossier de run."
            )
        lignes.append("Lancez le test, ou verifiez la cle LOG_PATH de la configuration.")
        return "\n".join(lignes)

    def _load_log(self, nodeid: str | None):
        if not self.workspace:
            self.log_header.setText("Aucun workspace charge.")
            self.log_view.clear()
            return

        if not nodeid:
            self.log_header.setText(
                "Selectionnez un test precis (une feuille de l'arbre) pour voir son log."
            )
            self.log_view.clear()
            return

        path = find_test_log(self.workspace, nodeid, self.config_path)
        if path is None:
            self.log_header.setText(self._explain_missing_log())
            self.log_view.clear()
            return

        content, warning = read_text_file(Path(path))
        self.log_view.setPlainText(content)
        header = str(path)
        if warning:
            header += f"    ({warning})"
        self.log_header.setText(header)
        self.log_view.moveCursor(QTextCursor.End)

    # ------------------------------------------------------------------
    # Confort
    # ------------------------------------------------------------------

    def show_console(self):
        self.tabs.setCurrentIndex(CONSOLE_TAB)

    def show_source(self):
        self.tabs.setCurrentIndex(SOURCE_TAB)

    def show_log(self):
        self.tabs.setCurrentIndex(LOG_TAB)
