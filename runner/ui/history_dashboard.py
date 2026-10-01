"""Historique moderne : un lancement groupe ses lecteurs et reste explorable.

La liste repond a « quel run ? », le panneau de droite a « qu'est-ce qui
s'est passe ? ». Les informations secondaires vivent dans des onglets afin
que l'ecran initial ne montre que le verdict et les problemes utiles.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QActionGroup, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner.domain import logs, report
from runner.domain.history import History, RunEntry, compare
from runner.domain.models import Reader, Status
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.history_window import FlakyDialog
from runner.ui.history_execution_tree import HistoryExecutionModel
from runner.ui.detail_panel import DetailPanel
from runner.ui.tree_model import NODEID_ROLE
from runner.domain.failures import index_failures, failure_for
from runner.ui.results_panel import ReaderViews
from runner.ui.widgets import EmptyState, StatusRibbon


def _when(timestamp: float, with_date: bool = True) -> str:
    pattern = "%Y-%m-%d %H:%M:%S" if with_date else "%H:%M"
    return time.strftime(pattern, time.localtime(timestamp))


def _short_reader(name: str) -> str:
    words = str(name or "").split()
    while len(words) > 1 and words[-1].lower() in ("reader", "lecteur"):
        words.pop()
    return " ".join(words) or "No reader"


@dataclass(frozen=True)
class RunGroup:
    """Toutes les entrees Reader qui appartiennent au meme lancement."""

    id: str
    entries: tuple[RunEntry, ...]

    @property
    def timestamp(self) -> float:
        return max((entry.timestamp for entry in self.entries), default=0.0)

    @property
    def workspace(self) -> str:
        return self.entries[0].workspace if self.entries else ""

    @property
    def build_number(self) -> int | None:
        return self.entries[0].build_number if self.entries else None

    @property
    def log_root(self) -> str:
        return next((entry.log_root for entry in self.entries if entry.log_root), "")

    @property
    def reader_names(self) -> tuple[str, ...]:
        return tuple(entry.reader for entry in self.entries if entry.reader)

    @property
    def origin_label(self) -> str:
        entry = self.entries[0] if self.entries else None
        if entry and entry.run_kind == "profile":
            return f"Profile: {entry.profile_name}" if entry.profile_name else "Profile"
        if entry and entry.run_kind == "classic":
            return "Selected run"
        return "Origin unknown (older run)"

    @property
    def display_name(self) -> str:
        entry = self.entries[0] if self.entries else None
        if entry and entry.run_name:
            return entry.run_name
        if entry and entry.run_kind == "profile":
            return entry.profile_name or "Execution profile"
        return f"Run #{self.build_number:04d}" if self.build_number is not None else f"Run {self.id}"

    @property
    def nodeids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            nodeid for entry in self.entries for nodeid in entry.nodeids))

    @property
    def failed_nodeids(self) -> tuple[str, ...]:
        return tuple(sorted({
            nodeid for entry in self.entries for nodeid in entry.failed_nodeids
        }))

    @property
    def duration(self) -> float:
        # Les lecteurs tournent normalement en parallele. Sans information de
        # mode dans les anciens fichiers, le maximum est le meilleur temps de
        # mur disponible et evite de doubler artificiellement la duree.
        return max((entry.duration for entry in self.entries), default=0.0)

    def count(self, status: Status) -> int:
        return sum(entry.count(status) for entry in self.entries)

    @property
    def total(self) -> int:
        return sum(entry.total for entry in self.entries)

    @property
    def issues(self) -> int:
        return self.count(Status.FAILED) + self.count(Status.ERROR)

    @property
    def ok(self) -> bool:
        return self.issues == 0

    @property
    def locked(self) -> bool:
        # `History.set_locked()` verrouille toujours TOUTES les entrees d'un
        # meme run d'un coup ; `all()` reste correct meme dans le cas
        # (normalement impossible) ou elles divergeraient.
        return bool(self.entries) and all(entry.locked for entry in self.entries)

    def entry_for_reader(self, reader: str) -> RunEntry | None:
        return next((entry for entry in self.entries
                     if entry.reader == reader), None)


def group_entries(entries) -> list[RunGroup]:
    grouped: dict[tuple[str, str], list[RunEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.id, entry.workspace), []).append(entry)
    result = [RunGroup(key[0], tuple(sorted(values,
                                           key=lambda e: e.reader.lower())))
              for key, values in grouped.items()]
    return sorted(result, key=lambda group: group.timestamp, reverse=True)


class HistoryTabBar(QTabBar):
    """Onglets volontairement egaux, quels que soient leurs libelles."""

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802 (API Qt)
        hint = super().tabSizeHint(index)
        return QSize(112, max(36, hint.height()))

    def minimumTabSizeHint(self, index: int) -> QSize:  # noqa: N802
        return self.tabSizeHint(index)


def _history_tabs() -> QTabWidget:
    tabs = QTabWidget()
    bar = HistoryTabBar()
    bar.setObjectName("HistoryTabs")
    tabs.setTabBar(bar)
    return tabs


class DeleteRunButton(QPushButton):
    """An icon's pixels must change explicitly; QSS color cannot tint it."""

    def restyle(self, hovered=False):
        color = t.status_color(Status.FAILED) if hovered else t.TEXT_MUTED
        self.setIcon(icons.icon("mdi.trash-can-outline", color))
        self.setStyleSheet(
            f"QPushButton {{background:transparent;border:1px solid transparent;}}"
            f"QPushButton:hover {{background:{t.rgba(t.status_color(Status.FAILED), 0.12)};"
            f"border-color:{t.status_color(Status.FAILED)};}}")

    def enterEvent(self, event):
        self.restyle(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.restyle(False)
        super().leaveEvent(event)


class RunCard(QFrame):
    """Resume compact place dans la liste de gauche.

    Un historique bien rempli peut afficher jusqu'a 300 cartes en meme temps
    (`History.MAX_ENTREES`), chacune posant sa propre couleur par-widget --
    necessaire, une carte melange plusieurs teintes (statut, lecteur) qu'une
    seule regle QSS partagee ne peut pas exprimer. Tout reconstruire a chaque
    bascule de theme coute bien plus cher que repeindre les memes widgets en
    place. `_repeints` retient donc comment recalculer chaque couleur depuis
    les jetons courants, et `restyle()` la rejoue sans rien reconstruire.
    """

    lock_toggled = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, group: RunGroup, parent=None):
        super().__init__(parent)
        self.group = group
        self.setObjectName("HistoryCard")
        self.setFixedHeight(142)
        self._selected = False
        self._repeints: list[callable] = []

        top = QHBoxLayout()
        top.setSpacing(t.SPACE_2)
        self.dot = QLabel("●")
        self._paint(self.dot,
                    lambda: f"color:{t.status_color(Status.PASSED if group.ok else Status.FAILED)};"
                            "background:transparent;")
        self.dot.hide()
        entry = group.entries[0] if group.entries else None
        is_profile = bool(entry and entry.run_kind == "profile")
        is_selected = bool(entry and entry.run_kind == "classic")

        def origin_color():
            light = t.current_theme() == "light"
            if is_profile:
                return "#6d35cf" if light else "#bd9aff"
            if is_selected:
                return "#2463b8" if light else "#91bfff"
            return t.TEXT_MUTED

        def origin_background():
            light = t.current_theme() == "light"
            if is_profile:
                return "#f0e9ff" if light else "#302343"
            if is_selected:
                return "#e8f0ff" if light else "#203249"
            return t.BG_RAISED
        kind = "PROFILE" if is_profile else (
            "SELECTED RUN" if entry and entry.run_kind == "classic" else "ORIGIN UNKNOWN")
        self.origin_label = self._label(kind, t.TEXT_XS, 700, origin_color)
        self.origin_label.setToolTip(group.origin_label)
        top.addWidget(self.origin_label)
        top.addStretch(1)
        if group.build_number is not None:
            top.addWidget(self._label(f"#{group.build_number:04d}", t.TEXT_XS, 700,
                                      lambda: t.TEXT_MUTED))
        top.addWidget(self._label(_when(group.timestamp, False), t.TEXT_XS, 500,
                                  lambda: t.TEXT_MUTED))
        self.origin_banner = QFrame()
        self.origin_banner.setObjectName("HistoryOriginBanner")
        self.origin_banner.setFixedHeight(34)
        top.setContentsMargins(14, 0, 14, 0)
        self.origin_banner.setLayout(top)
        self._paint(self.origin_banner, lambda:
                    f"QFrame#HistoryOriginBanner {{background:{origin_background()};"
                    f"border:none;border-top-left-radius:{t.RADIUS_MD}px;"
                    f"border-top-right-radius:{t.RADIUS_MD}px;}}")
        title_row = QHBoxLayout()
        title = group.display_name
        self.run_title = self._label(title, 17, 600)
        self.run_title.setToolTip(title)
        self.run_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        title_row.addWidget(self.run_title, 1)
        self.protected_badge = self._label(
            "PROTECTED", t.TEXT_XS, 700, lambda: t.ACCENT)
        self.protected_badge.setVisible(group.locked)
        self.protected_badge.setToolTip(
            "This run is kept when clearing history")
        title_row.addWidget(self.protected_badge)
        title_row.addWidget(self._lock_button(group))
        title_row.addSpacing(t.SPACE_1)
        title_row.addWidget(self._delete_button())

        counts = QHBoxLayout()
        counts.setSpacing(t.SPACE_3)
        counts.addWidget(self._label(f"{group.count(Status.PASSED)} passed",
                                     t.TEXT_XS, 600,
                                     lambda: t.status_color(Status.PASSED)))
        if group.count(Status.FAILED):
            counts.addWidget(self._label(f"{group.count(Status.FAILED)} failed",
                                         t.TEXT_XS, 600,
                                         lambda: t.status_color(Status.FAILED)))
        if group.count(Status.ERROR):
            counts.addWidget(self._label(f"{group.count(Status.ERROR)} error",
                                         t.TEXT_XS, 600,
                                         lambda: t.status_color(Status.ERROR)))
        if group.count(Status.SKIPPED):
            counts.addWidget(self._label(f"{group.count(Status.SKIPPED)} skipped",
                                         t.TEXT_XS, 600,
                                         lambda: t.status_color(Status.SKIPPED)))
        counts.addStretch(1)
        counts.addWidget(self._label(f"{group.duration:.1f}s", t.TEXT_XS, 500,
                                    lambda: t.TEXT_MUTED))

        readers = QHBoxLayout()
        readers.setSpacing(t.SPACE_1)
        for index, entry in enumerate(group.entries[:2]):
            readers.addWidget(self._reader_chip(entry.reader, index))
        if len(group.entries) > 2:
            readers.addWidget(self._label(f"+{len(group.entries) - 2}",
                                          t.TEXT_XS, 600, lambda: t.TEXT_MUTED))
        readers.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self.origin_banner)
        body = QVBoxLayout()
        body.setContentsMargins(15, 8, 15, 12)
        body.setSpacing(5)
        body.addLayout(title_row)
        workspace_label = self._label(Path(group.workspace).name or group.workspace,
                                     t.TEXT_XS, 400, lambda: t.TEXT_MUTED)
        workspace_label.setToolTip(group.workspace)
        workspace_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        body.addWidget(workspace_label)
        body.addLayout(counts)
        # Reader details remain in the detail pane; the compact card matches
        # the approved mockup's title / metadata / results hierarchy.
        reader_container = QWidget(self)
        reader_container.setLayout(readers)
        reader_container.hide()
        layout.addLayout(body)
        self.set_selected(False)

    def _paint(self, widget: QWidget, style_of) -> None:
        """Enregistre `widget` pour rejouer sa feuille a chaque `restyle()`."""
        self._repeints.append(lambda: widget.setStyleSheet(style_of()))
        widget.setStyleSheet(style_of())

    def _label(self, text, size, weight, color=None) -> QLabel:
        label = QLabel(str(text))
        base = (f"font-family:'Segoe UI';font-size:{size}px;font-weight:{weight};"
                "background:transparent;border:none;")
        if color is None:
            # Pas de couleur a soi : elle vient de `QWidget{{color:...}}`, deja
            # dans la feuille globale et deja rejouee a chaque bascule -- rien
            # a refigurer ici, un `restyle()` de plus par carte pour rien.
            label.setStyleSheet(base)
            return label
        self._paint(label, lambda: base + f"color:{color()};")
        return label

    def _reader_chip(self, name: str, index: int) -> QLabel:
        label = QLabel(f"●  {_short_reader(name)}")

        def style() -> str:
            couleur = t.reader_color(index)
            return (f"color:{couleur};background:{t.rgba(couleur, 0.10)};"
                    f"border:1px solid {t.rgba(couleur, 0.28)};border-radius:9px;"
                    f"padding:2px {t.SPACE_2}px;font-size:{t.TEXT_XS}px;font-weight:600;")

        self._paint(label, style)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return label

    def _lock_button(self, group: RunGroup) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("IconSm")
        bouton.setCheckable(True)
        bouton.setChecked(group.locked)
        bouton.setCursor(Qt.PointingHandCursor)
        bouton.setAccessibleName(
            "Unprotect this run" if group.locked else "Protect this run")
        bouton.setAccessibleDescription(
            "Protected runs are kept when clearing history.")
        bouton.clicked.connect(lambda: self.lock_toggled.emit(self.group))
        self.lock_button = bouton

        def style() -> None:
            verrouille = bouton.isChecked()
            bouton.setToolTip(
                "Unprotect this run"
                if verrouille else "Protect this run from Clear history")
            bouton.setAccessibleName(
                "Unprotect this run" if verrouille else "Protect this run")
            couleur = t.ACCENT if verrouille else t.TEXT_MUTED
            glyphe = "mdi.lock" if verrouille else "mdi.lock-open-variant-outline"
            bouton.setIcon(icons.icon(glyphe, couleur))

        self._repeints.append(style)
        style()
        return bouton

    def _delete_button(self) -> QPushButton:
        bouton = DeleteRunButton()
        bouton.setObjectName("IconDanger")
        bouton.setCursor(Qt.PointingHandCursor)
        bouton.setToolTip("Delete this run")
        bouton.setAccessibleName("Delete this run")
        bouton.setAccessibleDescription(
            "Delete this run and the saved output for every reader.")
        bouton.clicked.connect(lambda: self.delete_requested.emit(self.group))
        self.delete_button = bouton

        def style() -> None:
            bouton.restyle(bouton.underMouse())

        self._repeints.append(style)
        style()
        return bouton

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        border = ("#6d35cf" if t.current_theme() == "light" else "#bd9aff") if selected else t.BORDER
        background = t.BG_SURFACE
        # Une regle qualifiee par selecteur (`QFrame#HistoryCard{...}`) force
        # Qt a faire correspondre le selecteur avant d'appliquer quoi que ce
        # soit ; en forme directe (sans selecteur), les proprietes visent
        # `self` sans ce detour -- mesure a l'appui, plus de trois fois moins
        # cher a l'echelle d'une liste bien remplie.
        self.setStyleSheet(
            f"QFrame#HistoryCard {{background:{background};border:1px solid {border};"
            f"border-radius:10px;}}")

    def restyle(self) -> None:
        for repeindre in self._repeints:
            repeindre()
        self.set_selected(self._selected)


class ComparisonPane(QWidget):
    """Comparaison incorporable dans un onglet Reader."""

    def __init__(self, comparison, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, t.SPACE_2, 0, 0)
        layout.setSpacing(t.SPACE_3)
        if comparison.unchanged:
            unchanged = QLabel("No verdict changed between these runs.")
            unchanged.setObjectName("Muted")
            layout.addWidget(unchanged)
        layout.addWidget(self._section("New failures", comparison.newly_failed,
                                       Status.FAILED))
        layout.addWidget(self._section("Fixed", comparison.newly_fixed,
                                       Status.PASSED))
        layout.addWidget(self._section("Still failing", comparison.still_failing,
                                       Status.SKIPPED))
        layout.addStretch(1)

    @staticmethod
    def _section(title: str, nodeids, status: Status) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_1)
        label = QLabel(f"{title} ({len(nodeids)})")
        label.setStyleSheet(
            f"color:{t.status_color(status)};font-size:{t.TEXT_MD}px;"
            "font-weight:700;background:transparent;")
        layout.addWidget(label)
        if not nodeids:
            empty = QLabel("None")
            empty.setObjectName("Faint")
            layout.addWidget(empty)
            return box
        listing = QListWidget()
        listing.setEditTriggers(QAbstractItemView.NoEditTriggers)
        listing.addItems(nodeids)
        listing.setMaximumHeight(min(150, 34 * len(nodeids) + 8))
        layout.addWidget(listing)
        return box


class GroupComparisonDialog(QDialog):
    """Compare deux lancements, Reader par Reader."""

    def __init__(self, older: RunGroup, newer: RunGroup, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare runs")
        self.resize(860, 680)

        first, second = sorted((older, newer), key=lambda group: group.timestamp)
        header = QLabel(
            f"<b>Reference</b>  {_when(first.timestamp)}<br>"
            f"<b>Compared to</b>  {_when(second.timestamp)}")
        header.setTextFormat(Qt.RichText)

        tabs = _history_tabs()
        common = [name for name in first.reader_names
                  if second.entry_for_reader(name) is not None]
        if not common and len(first.entries) == len(second.entries) == 1:
            common = [first.entries[0].reader]
        for reader in common:
            before = first.entry_for_reader(reader) or first.entries[0]
            after = second.entry_for_reader(reader) or second.entries[0]
            tabs.addTab(ComparisonPane(compare(before, after)),
                        _short_reader(reader))

        close = QPushButton("Close")
        close.setObjectName("Ghost")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        layout.setSpacing(t.SPACE_3)
        layout.addWidget(header)
        layout.addWidget(tabs, 1)
        layout.addLayout(bottom)


class HistoryWindow(QDialog):
    """Tableau de bord des lancements enregistres."""

    rerun_requested = Signal(object)
    compare_requested = Signal(object)

    def __init__(self, history: History, parent=None):
        super().__init__(parent)
        self.history = history
        self._groups: list[RunGroup] = []
        self._visible_groups: list[RunGroup] = []
        self._cards: list[tuple[QListWidgetItem, RunCard]] = []
        self._listed_groups: list[RunGroup] = []
        self._listed_visible_groups: list[RunGroup] = []
        self._items_by_id: dict[str, QListWidgetItem] = {}
        self._day_headers: dict[str, QListWidgetItem] = {}
        # `run_list.blockSignals()` ne fait taire QUE `run_list` lui-meme, pas
        # sa scrollbar verticale : ajouter/retirer des lignes dans
        # `_populate_list()` peut faire bouger sa plage ou sa valeur, ce qui
        # rappelle `_materialize_cards()` EN PLEIN MILIEU du remplissage --
        # une carte fraichement `deleteLater()`-ee par cet appel reentrant
        # pouvait ensuite etre reutilisee par la boucle exterieure, encore en
        # cours, via son propre instantane (perime) de `self._cards`.
        self._populating = False
        self._filter_reader = ""
        self._compare_mode = False
        self._adjusting_selection = False
        self._export_submenus: list[QMenu] = []

        self.setWindowTitle("Run history")
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint)
        self.setSizeGripEnabled(True)
        self.resize(1380, 790)

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------ construction

    def _build_ui(self) -> None:
        self.history_title = QLabel("History")
        self.history_title.setObjectName("HistoryPageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("Muted")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.history_title)
        titles.addWidget(self.subtitle)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search runs, tests, or readers…")
        self.search.setMinimumWidth(180)
        self.search.setMaximumWidth(360)
        self.search.textChanged.connect(self._apply_filters)

        self.workspace_filter = QComboBox()
        self.workspace_filter.setMinimumWidth(140)
        self.workspace_filter.setMaximumWidth(190)
        self.workspace_filter.currentIndexChanged.connect(self._apply_filters)

        self.filter_button = QToolButton()
        self.filter_button.setText("Readers")
        self.filter_button.setObjectName("HistoryAction")
        self.filter_button.setPopupMode(QToolButton.InstantPopup)
        self.filter_menu = QMenu(self.filter_button)
        self.filter_button.setMenu(self.filter_menu)

        self.compare_button = QPushButton("Compare")
        self.compare_button.setObjectName("Primary")
        # Let Qt include the text, stylesheet padding and display scaling.
        self.compare_button.setMinimumWidth(108)
        self.compare_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.compare_button.clicked.connect(self._compare_clicked)
        self.cancel_compare = QPushButton("Cancel")
        self.cancel_compare.setObjectName("Ghost")
        self.cancel_compare.setVisible(False)
        self.cancel_compare.clicked.connect(self._leave_compare_mode)

        header = QHBoxLayout()
        header.setSpacing(t.SPACE_2)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(self.search)
        header.addWidget(self.workspace_filter)
        header.addWidget(self.filter_button)
        header.addWidget(self.cancel_compare)
        header.addWidget(self.compare_button)

        self.list_all = QPushButton("All")
        self.list_all.setCheckable(True)
        self.list_all.setChecked(True)
        self.list_issues = QPushButton("With issues")
        self.list_issues.setObjectName("Ghost")
        self.list_issues.setCheckable(True)
        self.list_all.clicked.connect(lambda: self._set_issue_filter(False))
        self.list_issues.clicked.connect(lambda: self._set_issue_filter(True))

        self.list_count = QLabel()
        self.list_count.setObjectName("Muted")
        self.clear_filters_button = QPushButton("Clear filters")
        self.clear_filters_button.setObjectName("Ghost")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        self.clear_filters_button.setVisible(False)

        list_tools = QHBoxLayout()
        list_tools.setContentsMargins(t.SPACE_3, t.SPACE_2,
                                      t.SPACE_3, t.SPACE_2)
        list_tools.addWidget(self.list_all)
        list_tools.addWidget(self.list_issues)
        list_tools.addStretch(1)
        list_tools.addWidget(self.clear_filters_button)
        list_tools.addWidget(self.list_count)

        self.run_list = QListWidget()
        self.run_list.setFrameShape(QFrame.NoFrame)
        self.run_list.setSpacing(t.SPACE_1)
        self.run_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.run_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.run_list.itemDoubleClicked.connect(lambda _item: self.view_output())
        self.run_list.verticalScrollBar().valueChanged.connect(
            lambda _value: self._materialize_cards())
        self._cards_timer = QTimer(self)
        self._cards_timer.setSingleShot(True)
        self._cards_timer.timeout.connect(self._materialize_cards)
        self.run_list.viewport().installEventFilter(self)
        self.run_list.verticalScrollBar().rangeChanged.connect(
            lambda _minimum, _maximum: self._cards_timer.start(0))

        self.empty = EmptyState(
            "mdi.history", "No run recorded yet",
            "Every completed run is kept here with its output and reader results.")
        self.filtered_empty = EmptyState(
            "mdi.filter-remove-outline", "No matching runs",
            "Change your search or clear the filters to show recorded runs.")
        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self.run_list)
        self.left_stack.addWidget(self.empty)
        self.left_stack.addWidget(self.filtered_empty)

        left = QFrame()
        self.history_list_panel = left
        left.setObjectName("Surface")
        left.setMinimumWidth(300)
        left.setMaximumWidth(500)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(list_tools)
        left_layout.addWidget(self.left_stack, 1)

        self.detail_empty = EmptyState(
            "mdi.history", "Choose a run",
            "Its issues, reader results and saved output will appear here.")
        self.detail = self._build_detail()
        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self.detail_empty)
        self.detail_stack.addWidget(self.detail)

        right = QFrame()
        right.setObjectName("Surface")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(t.SPACE_4, t.SPACE_3,
                                        t.SPACE_4, t.SPACE_3)
        right_layout.addWidget(self.detail_stack, 1)

        body = QHBoxLayout()
        body.setSpacing(t.SPACE_3)
        body.addWidget(left, 4)
        body.addWidget(right, 7)

        self.status = QLabel()
        self.status.setObjectName("Muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_4, t.SPACE_4,
                                  t.SPACE_4, t.SPACE_3)
        layout.setSpacing(t.SPACE_3)
        layout.addLayout(header)
        layout.addLayout(body, 1)
        layout.addWidget(self.status)

    def _build_detail(self) -> QWidget:
        panel = QWidget()
        self.detail_title = QLabel()
        self.detail_title.setObjectName("HistoryDetailTitle")
        self.detail_subtitle = QLabel()
        self.detail_subtitle.setObjectName("Muted")
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.detail_title)
        names.addWidget(self.detail_subtitle)
        self.rename_button = QPushButton("Rename")
        self.rename_button.setObjectName("Ghost")
        self.rename_button.clicked.connect(self._begin_rename)
        names.addWidget(self.rename_button)
        self.rename_edit = QLineEdit()
        self.rename_edit.setMaxLength(100)
        self.rename_edit.setPlaceholderText("Run name (optional)")
        self.rename_edit.setAccessibleName("Rename run")
        self.rename_edit.returnPressed.connect(self._save_rename)
        self.rename_edit.hide()
        names.addWidget(self.rename_edit)

        self.rerun_button = QPushButton("Re-run")
        self.rerun_button.setObjectName("Run")
        self.rerun_button.setFixedWidth(88)
        self.rerun_button.clicked.connect(self.rerun)
        self.logs_button = QPushButton("Logs")
        self.logs_button.setObjectName("Ghost")
        self.logs_button.setFixedWidth(76)
        self.logs_button.clicked.connect(self.open_logs)
        self.export_button = QToolButton()
        self.export_button.setText("Export")
        self.export_button.setObjectName("HistoryAction")
        self.export_button.setFixedWidth(96)
        self.export_button.setPopupMode(QToolButton.InstantPopup)
        self.export_menu = QMenu(self.export_button)
        self.export_button.setMenu(self.export_menu)

        top = QHBoxLayout()
        top.addLayout(names)
        top.addStretch(1)
        top.addWidget(self.logs_button)
        top.addWidget(self.rerun_button)
        top.addWidget(self.export_button)

        self.reader_selector = QComboBox()
        self.reader_selector.setAccessibleName("History reader")
        self.reader_selector.currentIndexChanged.connect(
            lambda _: self._select_execution_reader(self.reader_selector.currentData()))
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Reader"))
        selector_row.addWidget(self.reader_selector, 1)

        self._result_filter = None
        self.result_cards = {}
        self.result_values = {}
        self.result_icons = {}
        summary_top = QHBoxLayout()
        summary_top.setSpacing(t.SPACE_2)
        for status in (Status.PASSED, Status.FAILED, Status.ERROR, Status.SKIPPED):
            card = QPushButton()
            card.setCheckable(True)
            card.setMinimumWidth(0)
            card.setMinimumHeight(88)
            card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            card.setAccessibleName(f"Filter {status.label.lower()} results")
            card.clicked.connect(lambda checked=False, value=status: self._filter_results(value))
            box = QVBoxLayout(card)
            box.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
            value = QLabel("0")
            label = QLabel(status.value.capitalize())
            glyph = QLabel()
            glyph.setFixedSize(16, 16)
            caption = QHBoxLayout()
            caption.setSpacing(t.SPACE_1)
            caption.addWidget(glyph)
            caption.addWidget(label)
            caption.addStretch(1)
            for widget in (value, label, glyph):
                widget.setAttribute(Qt.WA_TransparentForMouseEvents)
            box.addWidget(value)
            box.addLayout(caption)
            self.result_cards[status] = card
            self.result_values[status] = value
            self.result_icons[status] = glyph
            summary_top.addWidget(card, 1)
        self.passed_value = self.result_values[Status.PASSED]
        self.failed_value = self.result_values[Status.FAILED]
        self.error_value = self.result_values[Status.ERROR]
        self.skipped_value = self.result_values[Status.SKIPPED]
        self.success_value = QLabel()
        self.success_value.setWordWrap(True)
        self._style_result_counts()

        self.ribbon = StatusRibbon()
        self.detail_meta = QLabel()
        self.detail_meta.setObjectName("Muted")
        summary = QFrame()
        summary.setObjectName("HistorySummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(t.SPACE_3, t.SPACE_2,
                                          t.SPACE_3, t.SPACE_2)
        summary_layout.addLayout(summary_top)
        summary_layout.addWidget(self.ribbon)
        summary_layout.addWidget(self.success_value)
        self.detail_meta.setWordWrap(True)
        summary_layout.addWidget(self.detail_meta)

        self.tabs = _history_tabs()
        self.issues_table = self._issue_table()
        self.issue_preview = self.issues_table
        self.overview = self._build_overview()
        self.output = ReaderViews(Qt.Vertical)
        self.details_table = QTableWidget(0, 8)
        self.details_table.setHorizontalHeaderLabels(
            ["Reader", "Passed", "Failed", "Skipped", "Error",
             "Duration", "Exit", "JUnit"])
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.issues_table, "Failed (0)")
        self.tabs.addTab(self.output, "Output")
        self.tabs.addTab(self.details_table, "Details")

        self.flaky_button = QPushButton("Unstable tests")
        self.flaky_button.setObjectName("Ghost")
        self.flaky_button.clicked.connect(self.show_flaky)
        self.delete_button = QPushButton("Delete run")
        self.delete_button.setObjectName("Danger")
        self.delete_button.clicked.connect(self.delete_run)
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.clicked.connect(self.clear_history)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.flaky_button)
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.delete_button)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_3)
        layout.addLayout(top)
        layout.addLayout(selector_row)
        layout.addWidget(summary)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)
        return panel

    def _build_overview(self) -> QWidget:
        widget = QWidget()
        # The issue table lives in Failed; Overview shows the actual sequence.
        self.execution_title = QLabel("Executed tests")
        self.execution_tree = QTreeView()
        self.execution_model = HistoryExecutionModel(self)
        self.execution_tree.setModel(self.execution_model)
        self.execution_tree.setUniformRowHeights(True)
        self.execution_tree.setAnimated(False)
        self.execution_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.execution_tree.header().setStretchLastSection(False)
        self.execution_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.execution_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.execution_tree.setColumnWidth(1, 110)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(self.execution_title)
        left.addWidget(self.execution_tree, 1)

        tree_panel = QWidget()
        tree_panel.setLayout(left)
        self.execution_detail = DetailPanel()
        self.execution_detail.body.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.execution_detail.open_output.connect(lambda: self.tabs.setCurrentIndex(2))
        self.execution_tree.selectionModel().currentChanged.connect(self._show_execution_detail)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(tree_panel)
        split.addWidget(self.execution_detail)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, t.SPACE_2, 0, 0)
        layout.addWidget(split)
        return widget

    @staticmethod
    def _issue_table() -> QTableWidget:
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Test", "Reader"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.setColumnWidth(1, 220)
        return table

    def _style_result_counts(self) -> None:
        for status, card in self.result_cards.items():
            color = t.status_color(status)
            self.result_icons[status].setPixmap(icons.status_icon(status).pixmap(16, 16))
            selected = self._result_filter is status
            card.setChecked(selected)
            card.setStyleSheet(
                f"QPushButton {{min-height:80px;padding:0;background:{t.BG_RAISED};border:1px solid "
                f"{color if selected else t.BORDER};border-radius:{t.RADIUS_MD}px;}}"
                f"QPushButton:hover {{background:{t.BG_HOVER};}}"
                f"QLabel {{color:{color};background:transparent;}}")
            self.result_values[status].setStyleSheet(
                f"color:{color};font-size:24px;font-weight:600;background:transparent;")
        self.success_value.setStyleSheet(f"color:{t.TEXT_MUTED};background:transparent;")

    def restyle(self) -> None:
        """Rejoue les couleurs figees a la construction de chaque carte.

        Rester sur la page PENDANT une bascule de theme laissait les cartes
        deja construites dans l'ancienne teinte, cote a cote avec un fond deja
        repeint. Chaque `RunCard` sait desormais se repeindre en place ; un
        historique bien rempli peut en compter jusqu'a 300 (`MAX_ENTREES`), et
        les reconstruire toutes -- l'ancienne approche -- couterait bien plus
        cher qu'un simple repeint.
        """
        self._style_result_counts()
        self.execution_detail.restyle()
        for _item, card in self._cards:
            card.restyle()

    # --------------------------------------------------------------- donnees

    def refresh(self) -> None:
        self._groups = group_entries(self.history.entries())
        flaky = self.history.flaky()
        self.subtitle.setText(
            f"{len(self._groups)} recorded runs  ·  {len(flaky)} unstable tests")
        self.flaky_button.setEnabled(bool(self._groups))
        self.clear_button.setEnabled(bool(self._groups))
        self._rebuild_workspace_filter()
        self._rebuild_reader_filter()
        self._apply_filters()

    def _rebuild_workspace_filter(self) -> None:
        current = self.workspace_filter.currentData()
        workspaces = sorted({group.workspace for group in self._groups},
                            key=lambda path: Path(path).name.lower())
        self.workspace_filter.blockSignals(True)
        self.workspace_filter.clear()
        self.workspace_filter.addItem("All workspaces", "")
        for workspace in workspaces:
            self.workspace_filter.addItem(Path(workspace).name or workspace,
                                          workspace)
        index = self.workspace_filter.findData(current)
        self.workspace_filter.setCurrentIndex(max(0, index))
        self.workspace_filter.blockSignals(False)

    def _rebuild_reader_filter(self) -> None:
        readers = sorted({name for group in self._groups
                          for name in group.reader_names}, key=str.lower)
        self.filter_menu.clear()
        actions = QActionGroup(self.filter_menu)
        actions.setExclusive(True)
        for name, label in [("", "All readers")] + [
                (reader, _short_reader(reader)) for reader in readers]:
            action = self.filter_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == self._filter_reader)
            action.triggered.connect(
                lambda checked, value=name: self._set_reader_filter(value))
            actions.addAction(action)
        self._reader_action_group = actions

    def _set_reader_filter(self, reader: str) -> None:
        self._filter_reader = reader
        self.filter_button.setText("Readers (1)" if reader else "Readers")
        self._apply_filters()

    def _set_issue_filter(self, issues_only: bool) -> None:
        self.list_all.setChecked(not issues_only)
        self.list_issues.setChecked(issues_only)
        self._apply_filters()

    def _clear_filters(self) -> None:
        self.search.clear()
        self.workspace_filter.setCurrentIndex(0)
        self._filter_reader = ""
        self.list_all.setChecked(True)
        self.list_issues.setChecked(False)
        self.filter_button.setText("Readers")
        self._rebuild_reader_filter()
        self._apply_filters()

    def _apply_filters(self) -> None:
        query = self.search.text().strip().lower()
        workspace = self.workspace_filter.currentData() or ""
        issues_only = self.list_issues.isChecked()

        def matches(group: RunGroup) -> bool:
            if workspace and group.workspace != workspace:
                return False
            if self._filter_reader and self._filter_reader not in group.reader_names:
                return False
            if issues_only and group.ok:
                return False
            if not query:
                return True
            haystack = "\n".join((group.id, group.workspace,
                                  *group.reader_names, *group.nodeids)).lower()
            return query in haystack

        self._visible_groups = [group for group in self._groups if matches(group)]
        active_filters = sum((bool(query), bool(workspace),
                              bool(self._filter_reader), issues_only))
        self.clear_filters_button.setVisible(bool(active_filters))
        shown = len(self._visible_groups)
        total = len(self._groups)
        self.list_count.setText(
            f"{shown}/{total} runs" if active_filters else f"{total} runs")
        self._populate_list()

    def _populate_list(self) -> None:
        self._populating = True
        self.run_list.blockSignals(True)
        if self._listed_groups != self._groups:
            # `removeItemWidget()` DOIT venir avant `clear()`/`deleteLater()` :
            # Qt suit les widgets d'index dans la meme structure interne que
            # les editeurs persistants, et `updateEditorGeometries()` la
            # reparcourt a chaque fois que la vue redevient visible. Sans ce
            # detachement explicite -- deja fait correctement dans
            # `_materialize_cards()` -- `clear()` peut laisser une reference
            # pendante vers une carte deja detruite, invisible tant qu'on
            # reste sur la page mais qui fait planter l'appli (segfault natif,
            # pas une exception Python) au prochain retour sur Historique.
            for item, card in self._cards:
                self.run_list.removeItemWidget(item)
                card.setParent(None)
                card.deleteLater()
            while self.run_list.count():
                self.run_list.takeItem(0)
            self._cards.clear()
            self._items_by_id.clear()
            self._day_headers.clear()
            previous_day = ""
            for group in self._groups:
                day = time.strftime("%Y-%m-%d", time.localtime(group.timestamp))
                if day != previous_day:
                    header = QListWidgetItem(day)
                    header.setFlags(Qt.NoItemFlags)
                    header.setSizeHint(QSize(0, 24))
                    self._day_headers[day] = header
                    previous_day = day
                item = QListWidgetItem()
                item.setData(Qt.UserRole, group)
                item.setSizeHint(QSize(0, 146))
                self._items_by_id[group.id] = item
            self._listed_groups = list(self._groups)

        # Les objets lourds sont conserves, seuls les items legers quittent et
        # rejoignent la liste. Les filtres ne reconstruisent donc plus aucune
        # carte, tout en gardant une liste ne contenant que les resultats (ce
        # qui simplifie clavier, selection et accessibilite).
        #
        # Rejouer ce remue-menage (tout retirer, tout rajouter) alors que la
        # liste VISIBLE n'a pas change est a la fois inutile et risque : fait
        # juste apres qu'une page redevienne visible (par exemple en
        # regardant l'Historique pendant qu'un run tourne encore), la vue
        # n'a pas fini de stabiliser sa mise en page, et ce retrait/rajout
        # d'items pouvait laisser une reference perimee dans le suivi interne
        # des "editeurs" de Qt -- invisible jusqu'au prochain retour sur la
        # page, qui plantait alors nativement (segfault, pas une exception
        # Python). Rien n'a besoin de bouger si la liste affichee est deja
        # la bonne.
        if self._visible_groups != self._listed_visible_groups:
            while self.run_list.count():
                item = self.run_list.item(0)
                if item.data(Qt.UserRole) is not None:
                    self.run_list.removeItemWidget(item)
                self.run_list.takeItem(0)
            cards = {id(item): card for item, card in self._cards}
            previous_day = ""
            for group in self._visible_groups:
                day = time.strftime("%Y-%m-%d", time.localtime(group.timestamp))
                if day != previous_day:
                    self.run_list.addItem(self._day_headers[day])
                    previous_day = day
                item = self._items_by_id[group.id]
                self.run_list.addItem(item)
                card = cards.get(id(item))
                if card is not None:
                    self.run_list.setItemWidget(item, card)
            self._listed_visible_groups = list(self._visible_groups)
        self.run_list.blockSignals(False)
        self._populating = False
        self._materialize_cards()

        if not self._groups:
            self.left_stack.setCurrentWidget(self.empty)
        elif not self._visible_groups:
            self.left_stack.setCurrentWidget(self.filtered_empty)
        else:
            self.left_stack.setCurrentWidget(self.run_list)
        if self._visible_groups:
            current = self.run_list.currentItem()
            first = (current if current is not None and not current.isHidden()
                     and current.data(Qt.UserRole) is not None
                     else self._first_run_item())
            if first is not None:
                first.setSelected(True)
                self.run_list.setCurrentItem(first)
                self._on_selection_changed()
        else:
            self.detail_stack.setCurrentWidget(self.detail_empty)
        self._update_compare_action()

    def eventFilter(self, watched, event):
        if (watched is self.run_list.viewport()
                and event.type() in (QEvent.Resize, QEvent.Show)):
            # Wait until Qt has laid out the newly visible viewport.
            self._cards_timer.start(0)
        return super().eventFilter(watched, event)

    def _materialize_cards(self) -> None:
        """Ne construit que les cartes proches de la zone visible.

        Une carte est un petit arbre de widgets et de styles. En creer 300 au
        chargement bloquait plusieurs secondes alors que l'ecran n'en montre
        qu'une dizaine. Les items restent tous presents pour le clavier et les
        filtres ; les widgets suivent simplement le viewport.
        """
        if self._populating:
            # `_populate_list()` a deja prevu son propre appel une fois les
            # lignes stabilisees ; un signal de sa scrollbar (que son
            # `blockSignals()` ne couvre pas) peut en rappeler un second en
            # PLEIN milieu de son remplissage, sur des lignes pas encore a
            # leur place -- source du crash natif corrige ici.
            return
        count = self.run_list.count()
        if not count:
            return
        viewport = self.run_list.viewport().rect()
        # Hit-testing a fixed point can land in the list's spacing, returning
        # no index even far down the history. Use actual row geometry instead.
        # Binary search keeps this cheap regardless of the history length.
        first, end = 0, count
        while first < end:
            middle = (first + end) // 2
            rect = self.run_list.visualItemRect(self.run_list.item(middle))
            if rect.bottom() < viewport.top():
                first = middle + 1
            else:
                end = middle
        last = first
        while last + 1 < count:
            rect = self.run_list.visualItemRect(self.run_list.item(last + 1))
            if rect.top() > viewport.bottom():
                break
            last += 1
        wanted = set(range(max(0, first - 3), min(count, last + 4)))

        kept: list[tuple[QListWidgetItem, RunCard]] = []
        for item, card in self._cards:
            row = self.run_list.row(item)
            if row in wanted:
                kept.append((item, card))
            else:
                if row >= 0:
                    self.run_list.removeItemWidget(item)
                card.setParent(None)
                card.deleteLater()
        self._cards = kept
        existing = {id(item) for item, _card in kept}
        selected = set(map(id, self.run_list.selectedItems()))
        for row in sorted(wanted):
            item = self.run_list.item(row)
            group = item.data(Qt.UserRole)
            if group is None or id(item) in existing:
                continue
            card = RunCard(group)
            card.set_selected(id(item) in selected)
            card.lock_toggled.connect(self._toggle_lock)
            card.delete_requested.connect(self.delete_run)
            self.run_list.setItemWidget(item, card)
            self._cards.append((item, card))

    def _first_run_item(self) -> QListWidgetItem | None:
        for row in range(self.run_list.count()):
            item = self.run_list.item(row)
            if not item.isHidden() and item.data(Qt.UserRole) is not None:
                return item
        return None

    def _selected_groups(self) -> list[RunGroup]:
        return [item.data(Qt.UserRole) for item in self.run_list.selectedItems()
                if item.data(Qt.UserRole) is not None]

    def _current_group(self) -> RunGroup | None:
        item = self.run_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _on_selection_changed(self) -> None:
        if self._adjusting_selection:
            return
        selected = self.run_list.selectedItems()
        selected_items = self.run_list.selectedItems()
        for item, card in self._cards:
            selected = any(item is candidate for candidate in selected_items)
            if card._selected != selected:
                card.set_selected(selected)

        group = self._current_group()
        if group is not None:
            self._show_group(group)
        self._update_compare_action()

    def _show_group(self, group: RunGroup) -> None:
        self.detail_stack.setCurrentWidget(self.detail)
        entry = group.entries[0] if group.entries else None
        self.detail_title.setText(group.display_name)
        self.rename_edit.hide()
        self.detail_subtitle.setText(
            f"{_when(group.timestamp)}  ·  {group.origin_label}  ·  {group.workspace}")
        self.tabs.setTabText(1, f"Failed ({len(group.failed_nodeids)})")
        self._fill_issues(self.issues_table, group)
        self._fill_readers(group)
        self._fill_output(group)
        self._select_execution_reader(-1)
        self._fill_details(group)
        self._fill_export_menu(group)
        self.rerun_button.setEnabled(bool(group.nodeids))
        self.logs_button.setEnabled(
            group.build_number is not None and bool(group.log_root))
        self.delete_button.setEnabled(True)

    @staticmethod
    def _issue_readers(group: RunGroup) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for entry in group.entries:
            for nodeid in entry.failed_nodeids:
                mapping.setdefault(nodeid, []).append(
                    _short_reader(entry.reader))
        return mapping

    def _fill_issues(self, table: QTableWidget, group: RunGroup) -> None:
        mapping = self._issue_readers(group)
        nodeids = list(mapping)
        table.setRowCount(len(nodeids))
        for row, nodeid in enumerate(nodeids):
            test = QTableWidgetItem(nodeid)
            test.setForeground(QColor(t.status_color(Status.FAILED)))
            table.setItem(row, 0, test)
            table.setItem(row, 1, QTableWidgetItem(", ".join(mapping[nodeid])))
        # Pas de `setVisible()` ici : ce tableau est une page d'onglet, dont Qt
        # gere lui-meme la visibilite. Le forcer l'affichait sous Overview.

    def _fill_readers(self, group: RunGroup) -> None:
        self._execution_group = group
        self._history_failure_indexes = {}
        self._result_filter = None
        self.reader_selector.blockSignals(True)
        self.reader_selector.clear()
        self.reader_selector.addItem("All readers — global results", -1)
        for index, entry in enumerate(group.entries):
            self.reader_selector.addItem(_short_reader(entry.reader), index)
        self.reader_selector.setCurrentIndex(0)
        self.reader_selector.blockSignals(False)

    def _select_execution_reader(self, index: int) -> None:
        group = getattr(self, '_execution_group', None)
        if group is None or index is None or not -1 <= index < len(group.entries):
            return
        self._selected_execution_reader = index
        self.reader_selector.blockSignals(True)
        self.reader_selector.setCurrentIndex(index + 1)
        self.reader_selector.blockSignals(False)
        self._result_filter = None
        self.execution_detail.clear()
        self.execution_tree.setUpdatesEnabled(False)
        try:
            if index == -1:
                self.execution_model.set_entries(group.entries)
                self.execution_tree.expandToDepth(1)
                # Test verdicts stay visible without opening their reader results.
                for key in self.execution_model._original_ids:
                    if ":" not in key:
                        self.execution_tree.collapse(self.execution_model.index_for_nodeid(key))
                self.execution_title.setText("All results · global verdict per test")
            else:
                entry = group.entries[index]
                self.execution_model.set_entry(entry)
                self.execution_tree.expandToDepth(1)
                self.execution_title.setText(f"Executed tests · {_short_reader(entry.reader)}")
                self.output.select_silently(index)
        finally:
            self.execution_tree.setUpdatesEnabled(True)
        entries = group.entries if index == -1 else (group.entries[index],)
        counts = {status: sum(entry.count(status) for entry in entries) for status in Status}
        for status, value in self.result_values.items():
            value.setText(str(counts[status]))
        self.ribbon.set_counts(counts)
        total = sum(counts.values())
        executed = counts[Status.PASSED] + counts[Status.FAILED] + counts[Status.ERROR]
        self.success_value.setText(
            f"{100 * counts[Status.PASSED] / executed:.0f}% success · "
            f"{counts[Status.PASSED]} / {executed} excluding skipped"
            if executed else "No executed results · skipped excluded")
        self.detail_meta.setText(
            f"{len(group.nodeids)} tests · {total} results · {group.duration:.1f}s · "
            f"{len(entries)} reader{'s' if len(entries) != 1 else ''} · "
            + (f"Build #{group.build_number:04d} · " if group.build_number is not None else "")
            + f"Run ID {group.id}")
        self._style_result_counts()

    def _filter_results(self, status):
        self._result_filter = None if self._result_filter is status else status
        selected = self._result_filter
        model = self.execution_model
        from PySide6.QtCore import QModelIndex
        def apply(parent=QModelIndex()):
            any_visible = False
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                if getattr(self, '_selected_execution_reader', -1) == -1 and index.data(NODEID_ROLE):
                    # Filter the global verdict, keeping all readers accessible underneath.
                    visible = selected is None or model.status_for(index.internalPointer(), 0) is selected
                else:
                    children_visible = apply(index) if model.rowCount(index) else False
                    visible = selected is None or children_visible or model.status_for(index.internalPointer(), 0) is selected
                self.execution_tree.setRowHidden(row, parent, not visible)
                any_visible |= visible
            return any_visible
        apply()
        self.tabs.setCurrentIndex(0)
        self._style_result_counts()

    def _show_execution_detail(self, index, previous=None):
        if not index.isValid():
            return
        nodeid = index.data(NODEID_ROLE)
        if not nodeid:
            self.execution_detail.clear()
            return
        group = self._execution_group
        reader_index = self._selected_execution_reader
        if reader_index == -1:
            reader_index = self.execution_model.reader_for_index(index)
        indexes = range(len(group.entries)) if reader_index is None else (reader_index,)
        statuses, failures, readers = {}, {}, []
        for i in indexes:
            entry = group.entries[i]
            readers.append(Reader(entry.reader or "No reader", i))
            if self._selected_execution_reader == -1 and reader_index is None:
                row = index.internalPointer()
                statuses[i] = self.execution_model.status_for(row.children[i], 0)
            else:
                statuses[i] = self.execution_model.status_for(index.internalPointer(), 0)
            if i not in self._history_failure_indexes:
                self._history_failure_indexes[i] = index_failures(entry.output())
            failures[i] = failure_for(self._history_failure_indexes[i], nodeid)
        self.execution_detail.show_test(nodeid, tuple(readers), statuses, failures)

    def _fill_output(self, group: RunGroup) -> None:
        readers = tuple(Reader(entry.reader or "No reader", index)
                        for index, entry in enumerate(group.entries))
        self.output.set_readers(readers)
        for index, entry in enumerate(group.entries):
            self.output.set_text(index, entry.output() or "This run kept no output.",
                                 _short_reader(entry.reader), entry.output_file)

    def _fill_details(self, group: RunGroup) -> None:
        self.details_table.setRowCount(len(group.entries))
        for row, entry in enumerate(group.entries):
            values = (
                _short_reader(entry.reader),
                str(entry.count(Status.PASSED)),
                str(entry.count(Status.FAILED)),
                str(entry.count(Status.SKIPPED)),
                str(entry.count(Status.ERROR)),
                f"{entry.duration:.1f}s",
                str(entry.exit_code),
                "Available" if entry.junit_path else "—",
            )
            for column, value in enumerate(values):
                self.details_table.setItem(row, column, QTableWidgetItem(value))
        self.details_table.resizeColumnsToContents()

    def _fill_export_menu(self, group: RunGroup) -> None:
        self.export_menu.clear()
        self._export_submenus.clear()
        profile_action = self.export_menu.addAction("Export as execution profile…")
        profile_action.setEnabled(bool(group.nodeids))
        profile_action.triggered.connect(lambda checked=False: self.export_execution_profile())
        self.export_menu.addSeparator()
        for entry in group.entries:
            if len(group.entries) > 1:
                # Un parent explicite est necessaire avec PySide 6.8 : les
                # sous-menus crees par ``addMenu(str)`` peuvent etre vus comme
                # des fenetres orphelines et detruits par le nettoyage Qt.
                menu = QMenu(_short_reader(entry.reader), self.export_menu)
                self.export_menu.addMenu(menu)
                self._export_submenus.append(menu)
            else:
                menu = self.export_menu
            html = menu.addAction("Export HTML…")
            html.triggered.connect(
                lambda checked=False, value=entry: self.export_html(value))
            junit = menu.addAction("Export JUnit XML…")
            junit.setEnabled(bool(entry.junit_path))
            junit.triggered.connect(
                lambda checked=False, value=entry: self.export_junit(value))

    # -------------------------------------------------------------- actions

    def export_execution_profile(self) -> None:
        from runner.domain.execution_profile import EXTENSION, ProfileValidationError, export_profile
        from runner.domain.history_profile import profile_from_entry

        group = self._current_group()
        if group is None or not group.entries:
            return
        entry = group.entries[0]
        configuration = None
        if entry.replay_profile is None:
            choice = QMessageBox.question(
                self, "Configuration not archived",
                "This older run has no saved configuration or execution options. "
                "The recorded sequence can still be exported.\n\n"
                "Choose a YAML configuration to include?\n"
                "Yes: choose a file. No: export the sequence only (local settings on import).",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Cancel)
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Yes:
                configuration, _ = QFileDialog.getOpenFileName(
                    self, "Choose configuration for the exported profile", entry.workspace,
                    "YAML (*.yaml *.yml)")
                if not configuration:
                    return
        try:
            profile = profile_from_entry(entry, group.display_name[:120], configuration)
            path, _ = QFileDialog.getSaveFileName(
                self, "Export run as execution profile", f"run_{entry.id}{EXTENSION}",
                f"Pytest Runner profiles (*{EXTENSION})")
            if not path:
                return
            target = export_profile(profile, path)
        except (OSError, UnicodeError, ProfileValidationError) as exc:
            self._say(f"Could not export profile: {exc}", True)
            return
        self._say(f"Profile exported to {target}. Import it from Execution Profiles on the other computer.")

    def view_output(self) -> None:
        if self._current_group() is not None:
            self.tabs.setCurrentIndex(2)

    def open_logs(self) -> None:
        group = self._current_group()
        if group is None or group.build_number is None or not group.log_root:
            return
        fichiers = logs.find_logs_for_build(
            Path(group.log_root), group.build_number,
            self._filter_reader,
        )
        if not fichiers:
            self._say(f"No logs found for build #{group.build_number:04d}.", True)
            return
        try:
            dossier = os.path.commonpath([str(path.parent) for path in fichiers])
        except ValueError:
            dossier = str(fichiers[0].parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dossier))

    def rerun(self) -> None:
        group = self._current_group()
        if group is None or not group.nodeids:
            return
        self.rerun_requested.emit(group)
        if self.isWindow():
            self.accept()

    def export_html(self, entry: RunEntry | None = None) -> None:
        entry = entry or self._first_entry()
        if entry is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the report", f"report_{entry.id}.html", "HTML (*.html)")
        if not path:
            return
        ok, message = report.write_html(entry, Path(path), entry.output())
        self._say(f"Report written to {path}" if ok else
                  f"Could not write the report: {message}", not ok)

    def export_junit(self, entry: RunEntry | None = None) -> None:
        entry = entry or self._first_entry()
        if entry is None or not entry.junit_path:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the JUnit report", f"junit_{entry.id}.xml", "XML (*.xml)")
        if not path:
            return
        ok, message = report.write_junit(entry, Path(path))
        self._say(f"JUnit XML written to {path}" if ok else message, not ok)

    def _first_entry(self) -> RunEntry | None:
        group = self._current_group()
        return group.entries[0] if group and group.entries else None

    def _begin_rename(self) -> None:
        group = self._current_group()
        if group is None:
            return
        self._renaming_run_id = group.id
        self.rename_edit.setText(group.display_name)
        self.rename_edit.show()
        self.rename_edit.setFocus()
        self.rename_edit.selectAll()
        self.rename_edit.setToolTip("Press Enter to save. Empty restores the automatic name.")

    def _save_rename(self) -> None:
        self.history.rename_run(self._renaming_run_id, self.rename_edit.text())
        self.rename_edit.hide()
        self.refresh()
        self._say("Run renamed.")

    def delete_run(self, group: RunGroup | None = None) -> None:
        # `group` peut arriver d'un signal Qt sans rapport (le bouton "Delete
        # run" du panneau emet un `bool` de coche) : ne garder que le cas ou
        # c'est vraiment un `RunGroup`, sinon retomber sur la selection
        # courante comme avant.
        group = group if isinstance(group, RunGroup) else self._current_group()
        if group is None:
            return
        answer = QMessageBox.question(
            self, "Delete run",
            f"Delete the run from {_when(group.timestamp)}, including the "
            "saved outputs for every reader?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        removed = self.history.remove_run(group.id)
        self.refresh()
        self._say(f"Run deleted ({removed} reader entries).")

    def _toggle_lock(self, group: RunGroup) -> None:
        if group is None:
            return
        verrouille = not group.locked
        self.history.set_locked(group.id, verrouille)
        self.refresh()
        self._say("Run protected from Clear history." if verrouille
                  else "Run no longer protected.")

    def clear_history(self) -> None:
        removable = [group for group in self._groups if not group.locked]
        if not removable:
            if self._groups:
                self._say("Every run is protected -- nothing to clear.")
            return
        locked_count = len(self._groups) - len(removable)
        message = (f"Delete {len(removable)} recorded run"
                  f"{'s' if len(removable) != 1 else ''} and their saved outputs?")
        if locked_count:
            message += (f" ({locked_count} protected run"
                        f"{'s' if locked_count != 1 else ''} will be kept.)")
        answer = QMessageBox.question(
            self, "Clear history", message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.history.clear()
        self.refresh()
        self._say("History cleared." if not locked_count else
                  f"History cleared ({locked_count} protected run"
                  f"{'s' if locked_count != 1 else ''} kept).")

    def show_flaky(self) -> None:
        FlakyDialog(self.history.flaky(), self).exec()

    def _say(self, message: str, alert: bool = False) -> None:
        self.status.setText(message)
        color = t.status_color(Status.FAILED) if alert else t.TEXT_MUTED
        self.status.setStyleSheet(
            f"color:{color};font-size:{t.TEXT_SM}px;background:transparent;")

    # ------------------------------------------------------------ comparaison

    def _compare_clicked(self) -> None:
        groups = self._selected_groups()
        if len(groups) < 2 and not self._compare_mode:
            self._enter_compare_mode()
            return
        if len(groups) < 2:
            return
        if any(not self._compatible(groups[0], group) for group in groups[1:]):
            self._say("Choose runs from the same workspace.",
                      alert=True)
            return
        self.compare_requested.emit(groups)

    def _enter_compare_mode(self) -> None:
        if len(self._visible_groups) < 2:
            return
        self._compare_mode = True
        self.run_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cancel_compare.setVisible(True)
        self._say("Ctrl+click to select runs, Shift+click to select a range. Choose the same workspace.")
        self._update_compare_action()

    def _leave_compare_mode(self) -> None:
        self._compare_mode = False
        self.run_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cancel_compare.setVisible(False)
        self.status.clear()
        first = self._first_run_item()
        if first is not None:
            self.run_list.clearSelection()
            first.setSelected(True)
            self.run_list.setCurrentItem(first)
        self._update_compare_action()

    @staticmethod
    def _compatible(first: RunGroup, second: RunGroup) -> bool:
        if first.workspace != second.workspace:
            return False
        return True

    def _update_compare_action(self) -> None:
        if not self._compare_mode:
            self.compare_button.setText("Compare")
            self.compare_button.setEnabled(len(self._visible_groups) >= 2)
            return
        count = len(self._selected_groups())
        self.compare_button.setText("Compare selected" if count >= 2
                                    else f"Compare {count} / 2+")
        self.compare_button.setEnabled(count >= 2)
