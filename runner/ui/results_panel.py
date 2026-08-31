"""Panneau de droite : la fiche d'un test, la sortie brute, les logs.

L'ordre des onglets est un choix, pas un hasard. Mesure faite sur un run reel
de 160 tests dont 44 en echec, la console produit 292 lignes :

    160  verdicts       -> deja dans l'arbre, une colonne par lecteur
      9  bannieres      -> jamais lues
      2  vides
    121  traces d'echec <- la SEULE chose qu'on ne trouve nulle part ailleurs

Le seul apport propre de la console represente 41 % de ses lignes, et c'est
justement ce qu'elle rend le plus difficile a trouver : il faut passer neuf
lignes avant la premiere trace, puis chercher la bonne parmi quarante-quatre.

D'ou la disposition : `Detail` d'abord, qui repond a la question posee (ce test
la, pourquoi), et la console juste derriere, entiere et copiable, pour tout ce
que la fiche ne peut pas deviner.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain import failures as failures_mod
from runner.domain import log_compare, logs
from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.source import path_of as source_path
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.console_view import ConsoleView
from runner.ui.detail_panel import DetailPanel
from runner.ui.source_panel import SourcePanel
from runner.ui.external_log import open_in_notepad_plus_plus

ONGLET_DETAIL = 0
ONGLET_SOURCE = 1
ONGLET_OUTPUT = 2
ONGLET_LOGS = 3


class ReaderViews(QWidget):
    """Une console par lecteur : une seule visible, ou toutes.

    Sert deux fois -- la sortie pytest et les logs -- avec un sens de
    comparaison different. Les sorties defilent, on les empile pour garder la
    largeur ; les logs se comparent ligne a ligne, on les met cote a cote.
    """

    reader_selected = Signal(int)
    open_file_requested = Signal(int)

    def __init__(self, orientation=Qt.Vertical, sync_scroll: bool = False,
                 show_lens: bool = True, highlight_differences: bool = False,
                 external_open: bool = False,
                 parent=None):
        super().__init__(parent)
        self._sync = sync_scroll
        self._show_lens = show_lens
        self._highlight_differences = highlight_differences
        self._external_open = external_open
        self._defile = False
        self._readers: tuple[Reader, ...] = ()
        self._difference_groups: list[tuple[frozenset[int], ...]] = []
        self._difference_index = -1

        self.views: list[ConsoleView] = []
        self.headers: list[QLabel] = []
        self._tab_labels: list[QLabel] = []
        self._paths: list[Path | None] = []

        self.tabs = QTabBar()
        self.tabs.setObjectName("ReaderTabs")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)

        self.compare = QPushButton()
        self.compare.setObjectName("IconSm")
        self.compare.setIcon(icons.icon("mdi.view-split-vertical", t.TEXT_MUTED))
        self.compare.setCheckable(True)
        self.compare.setToolTip(
            "Compare reader logs and highlight meaningful differences"
            if highlight_differences else
            "Compare every reader  (Ctrl+Shift+D)")
        self.compare.setVisible(False)
        self.compare.toggled.connect(self._on_compare_toggled)

        self.open_buttons: list[QPushButton] = []

        self.previous_difference = QPushButton()
        self.previous_difference.setObjectName("IconSm")
        self.previous_difference.setIcon(
            icons.icon("mdi.chevron-up", t.TEXT_MUTED))
        self.previous_difference.setToolTip(
            "Previous meaningful difference  (Shift+F7)")
        self.previous_difference.clicked.connect(
            lambda: self.navigate_difference(-1))

        self.difference_counter = QLabel("0 / 0")
        self.difference_counter.setObjectName("Faint")
        self.difference_counter.setAlignment(Qt.AlignCenter)
        self.difference_counter.setMinimumWidth(48)

        self.next_difference = QPushButton()
        self.next_difference.setObjectName("IconSm")
        self.next_difference.setIcon(
            icons.icon("mdi.chevron-down", t.TEXT_MUTED))
        self.next_difference.setToolTip("Next meaningful difference  (F7)")
        self.next_difference.clicked.connect(
            lambda: self.navigate_difference(1))

        self.difference_navigation = QWidget()
        navigation = QHBoxLayout(self.difference_navigation)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(t.SPACE_1)
        navigation.addWidget(self.previous_difference)
        navigation.addWidget(self.difference_counter)
        navigation.addWidget(self.next_difference)
        self.difference_navigation.setVisible(False)

        self._next_shortcut = QShortcut(QKeySequence("F7"), self)
        self._next_shortcut.activated.connect(
            lambda: self.navigate_difference(1))
        self._previous_shortcut = QShortcut(QKeySequence("Shift+F7"), self)
        self._previous_shortcut.activated.connect(
            lambda: self.navigate_difference(-1))

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(t.SPACE_1)
        barre.addWidget(self.tabs, 1)
        barre.addWidget(self.difference_navigation)
        barre.addWidget(self.compare)

        self.split = QSplitter(orientation)
        self.split.setChildrenCollapsible(False)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addLayout(barre)
        colonne.addWidget(self.split, 1)

        self._add_view()

    def _add_view(self) -> ConsoleView:
        vue = ConsoleView(show_lens=self._show_lens)
        entete = QLabel()
        entete.setVisible(False)
        entete.setObjectName("Faint")
        boite = QWidget()
        col = QVBoxLayout(boite)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_1)
        col.addWidget(entete)
        col.addWidget(vue, 1)
        self.views.append(vue)
        self.headers.append(entete)
        self._paths.append(None)
        self.split.addWidget(boite)
        if self._external_open:
            index = len(self.views) - 1
            vue.add_tool(self._make_open_button(index))
            vue.view.setContextMenuPolicy(Qt.CustomContextMenu)
            vue.view.customContextMenuRequested.connect(
                lambda position, i=index, v=vue.view:
                self._show_external_context_menu(i, v, position))
        if self._sync:
            for sens in ("verticalScrollBar", "horizontalScrollBar"):
                getattr(vue, sens)().valueChanged.connect(
                    lambda valeur, s=sens, v=vue: self._propager(s, v, valeur))
        return vue

    def _make_open_button(self, index: int) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("IconSm")
        bouton.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        bouton.setToolTip("Open this log")
        bouton.setEnabled(False)
        bouton.clicked.connect(lambda: self._request_external_open(index))
        self.open_buttons.append(bouton)
        return bouton

    def _propager(self, sens: str, source, valeur: int) -> None:
        if self._defile:
            return
        self._defile = True
        try:
            for vue in self.views:
                if vue is not source:
                    barre = getattr(vue, sens)()
                    if barre.value() != valeur:
                        barre.setValue(valeur)
        finally:
            self._defile = False

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        self._readers = tuple(readers)
        multi = len(self._readers) > 1
        while len(self.views) < max(1, len(self._readers)):
            self._add_view()
        if self._external_open:
            self._paths = [None] * len(self.views)
            self._update_external_buttons()
        self.tabs.blockSignals(True)
        for libelle in self._tab_labels:
            libelle.deleteLater()
        self._tab_labels.clear()
        while self.tabs.count():
            self.tabs.removeTab(0)
        for lecteur in (self._readers if multi else ()):
            position = self.tabs.addTab("")
            libelle = QLabel(f"●  {lecteur.short_name}")
            libelle.setAlignment(Qt.AlignCenter)
            libelle.setAttribute(Qt.WA_TransparentForMouseEvents)
            libelle.setProperty("readerIndex", lecteur.index)
            self.tabs.setTabButton(position, QTabBar.LeftSide, libelle)
            self._tab_labels.append(libelle)
            self.tabs.setTabToolTip(position, lecteur.name)
        self.tabs.blockSignals(False)
        for position, entete in enumerate(self.headers):
            if position < len(self._readers):
                lecteur = self._readers[position]
                entete.setText(lecteur.short_name)
                entete.setToolTip(lecteur.name)
            else:
                entete.clear()
        self.tabs.setVisible(multi)
        self.compare.setVisible(multi)
        self.difference_navigation.setVisible(
            multi and self.compare.isChecked() and self._highlight_differences)
        self._restyle_reader_names()
        self._apply_layout()

    def _apply_layout(self) -> None:
        nombre = max(1, len(self._readers))
        comparer = self.compare.isChecked()
        courant = max(0, self.tabs.currentIndex())
        for position, vue in enumerate(self.views):
            boite = vue.parentWidget()
            visible = position < nombre and (comparer or nombre == 1 or position == courant)
            boite.setVisible(visible)
            self.headers[position].setVisible(visible and comparer and nombre > 1)

    def _on_compare_toggled(self, checked: bool) -> None:
        self.difference_navigation.setVisible(checked and self._highlight_differences)
        self._apply_layout()
        self._update_difference_highlights(reveal=checked)

    def _on_tab(self, index: int) -> None:
        self._apply_layout()
        self._restyle_reader_names()
        self.reader_selected.emit(index)

    def select_silently(self, index: int) -> None:
        if 0 <= index < self.tabs.count() and index != self.tabs.currentIndex():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
            self._apply_layout()
            self._restyle_reader_names()

    def path_at(self, index: int) -> Path | None:
        if not 0 <= index < len(self._paths):
            return None
        path = self._paths[index]
        return path if path is not None and path.is_file() else None

    def _update_external_buttons(self) -> None:
        for index, bouton in enumerate(self.open_buttons):
            bouton.setEnabled(self.path_at(index) is not None)

    def _request_external_open(self, index: int) -> None:
        if self.path_at(index) is not None:
            self.open_file_requested.emit(index)

    def _show_external_context_menu(self, index: int, view, position) -> None:
        menu = view.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Open log")
        action.setEnabled(self.path_at(index) is not None)
        action.triggered.connect(lambda: self._request_external_open(index))
        menu.exec(view.mapToGlobal(position))

    def toggle_compare(self) -> None:
        if self.compare.isVisible():
            self.compare.setChecked(not self.compare.isChecked())

    def navigate_difference(self, direction: int) -> None:
        if not self.compare.isChecked() or not self._difference_groups:
            return
        courant = self._difference_index
        if courant < 0:
            courant = 0 if direction < 0 else -1
        self._show_difference((courant + direction) % len(self._difference_groups))

    def append(self, index: int, texte: str) -> None:
        if 0 <= index < len(self.views):
            self.views[index].append(texte)

    def set_text(self, index: int, texte: str, entete: str = "", chemin: str = "") -> None:
        if 0 <= index < len(self.views):
            self.views[index].set_text(texte)
            self.headers[index].setText(entete)
            self._paths[index] = Path(chemin) if chemin else None
            self.headers[index].setToolTip(chemin)
            self._update_external_buttons()
            self._update_difference_highlights()

    def _update_difference_highlights(self, reveal: bool = False) -> None:
        active = (self._highlight_differences and self.compare.isChecked()
                  and len(self._readers) > 1)
        if not active:
            self._difference_groups.clear()
            self._difference_index = -1
            self._refresh_difference_navigation()
            for view in self.views:
                view.highlight_lines()
            return
        count = len(self._readers)
        texts = [self.views[index].toPlainText() for index in range(count)]
        groups = log_compare.semantic_difference_groups(texts)
        self._difference_groups = list(groups)
        for index, view in enumerate(self.views):
            line_numbers = {
                line
                for group in self._difference_groups
                for line in group[index]
            }
            view.highlight_lines(line_numbers)
        if not self._difference_groups:
            self._difference_index = -1
        elif self._difference_index >= len(self._difference_groups):
            self._difference_index = len(self._difference_groups) - 1
        self._refresh_difference_navigation()
        if reveal and self._difference_groups:
            self._show_difference(0)

    def _show_difference(self, index: int) -> None:
        if not self._difference_groups:
            return
        self._difference_index = index % len(self._difference_groups)
        group = self._difference_groups[self._difference_index]
        for view_index, lines in enumerate(group):
            if view_index < len(self.views) and lines:
                self.views[view_index].scroll_to_line(min(lines))
        self._refresh_difference_navigation()

    def _refresh_difference_navigation(self) -> None:
        total = len(self._difference_groups)
        current = self._difference_index + 1 if self._difference_index >= 0 else 0
        self.difference_counter.setText(f"{current} / {total}")
        enabled = total > 0
        self.previous_difference.setEnabled(enabled)
        self.next_difference.setEnabled(enabled)

    def _restyle_reader_names(self) -> None:
        for position, libelle in enumerate(self._tab_labels):
            reader_index = self.tabs.tabData(position)
            if reader_index is None and position < len(self._readers):
                reader_index = self._readers[position].index
            colour = theme.reader_color(int(reader_index or 0))
            libelle.setStyleSheet(f"color: {colour};")
        for position, entete in enumerate(self.headers):
            if position < len(self._readers):
                colour = theme.reader_color(self._readers[position].index)
                entete.setStyleSheet(f"color: {colour};")

    def clear(self) -> None:
        for view in self.views:
            view.clear()
        self._paths = [None] * len(self.views)
        self._update_external_buttons()
        self._difference_groups.clear()
        self._difference_index = -1
        self._refresh_difference_navigation()

    def open_external(self, index: int) -> bool:
        path = self.path_at(index)
        return bool(path and open_in_notepad_plus_plus(path))


class ResultsPanel(QWidget):
    """Panneau central de resultats."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.detail = DetailPanel()
        self.source = SourcePanel()
        self.outputs = ReaderViews()
        self.logs = ReaderViews(orientation=Qt.Horizontal, sync_scroll=True,
                                highlight_differences=True, external_open=True)
        self.tabs.addTab(self.detail, "Detail")
        self.tabs.addTab(self.source, "Source")
        self.tabs.addTab(self.outputs, "Output")
        self.tabs.addTab(self.logs, "Logs")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        self.outputs.set_readers(readers)
        self.logs.set_readers(readers)

    def select_reader(self, index: int) -> None:
        self.outputs.select_silently(index)
        self.logs.select_silently(index)

    def clear(self) -> None:
        self.detail.clear()
        self.source.clear()
        self.outputs.clear()
        self.logs.clear()
