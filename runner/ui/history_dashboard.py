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

from PySide6.QtCore import QPoint, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QActionGroup, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from runner.domain import logs, report
from runner.domain.history import History, RunEntry, compare
from runner.domain.models import Reader, Status
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.history_window import FlakyDialog
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
        self.setFixedHeight(102)
        self._selected = False
        self._repeints: list[callable] = []

        top = QHBoxLayout()
        top.setSpacing(t.SPACE_2)
        self.dot = QLabel("●")
        self._paint(self.dot,
                    lambda: f"color:{t.status_color(Status.PASSED if group.ok else Status.FAILED)};"
                            "background:transparent;")
        top.addWidget(self.dot)
        top.addWidget(self._label(_when(group.timestamp, False), 13, 700))
        if group.build_number is not None:
            top.addWidget(self._label(f"#{group.build_number:04d}", t.TEXT_XS, 700,
                                      lambda: t.ACCENT))
        top.addWidget(self._label(Path(group.workspace).name or group.workspace,
                                  t.TEXT_SM, 600))
        top.addStretch(1)
        top.addWidget(self._label(f"{group.duration:.1f}s", t.TEXT_XS, 500,
                                  lambda: t.TEXT_MUTED))
        top.addWidget(self._lock_button(group))
        top.addWidget(self._delete_button())

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
        if group.ok:
            counts.addWidget(self._label("No issues", t.TEXT_XS, 500,
                                         lambda: t.TEXT_MUTED))
        counts.addStretch(1)

        readers = QHBoxLayout()
        readers.setSpacing(t.SPACE_1)
        for index, entry in enumerate(group.entries[:2]):
            readers.addWidget(self._reader_chip(entry.reader, index))
        if len(group.entries) > 2:
            readers.addWidget(self._label(f"+{len(group.entries) - 2}",
                                          t.TEXT_XS, 600, lambda: t.TEXT_MUTED))
        readers.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        layout.setSpacing(t.SPACE_1)
        layout.addLayout(top)
        layout.addLayout(counts)
        layout.addLayout(readers)
        self.set_selected(False)

    def _paint(self, widget: QWidget, style_of) -> None:
        """Enregistre `widget` pour rejouer sa feuille a chaque `restyle()`."""
        self._repeints.append(lambda: widget.setStyleSheet(style_of()))
        widget.setStyleSheet(style_of())

    def _label(self, text, size, weight, color=None) -> QLabel:
        label = QLabel(str(text))
        base = f"font-size:{size}px;font-weight:{weight};background:transparent;border:none;"
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
        bouton.clicked.connect(lambda: self.lock_toggled.emit(self.group))
        self.lock_button = bouton

        def style() -> None:
            verrouille = bouton.isChecked()
            bouton.setToolTip(
                "Unprotect this run (Clear history will remove it)"
                if verrouille else "Protect this run from Clear history")
            couleur = t.ACCENT if verrouille else t.TEXT_MUTED
            glyphe = "mdi.lock" if verrouille else "mdi.lock-open-variant-outline"
            bouton.setIcon(icons.icon(glyphe, couleur))

        self._repeints.append(style)
        style()
        return bouton

    def _delete_button(self) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("IconSm")
        bouton.setCursor(Qt.PointingHandCursor)
        bouton.setToolTip("Delete this run")
        bouton.clicked.connect(lambda: self.delete_requested.emit(self.group))
        self.delete_button = bouton

        def style() -> None:
            bouton.setIcon(icons.icon("mdi.trash-can-outline", t.TEXT_MUTED))

        self._repeints.append(style)
        style()
        return bouton

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        border = t.ACCENT if selected else t.BORDER
        background = t.rgba(t.ACCENT, 0.08) if selected else t.BG_SURFACE
        # Une regle qualifiee par selecteur (`QFrame#HistoryCard{...}`) force
        # Qt a faire correspondre le selecteur avant d'appliquer quoi que ce
        # soit ; en forme directe (sans selecteur), les proprietes visent
        # `self` sans ce detour -- mesure a l'appui, plus de trois fois moins
        # cher a l'echelle d'une liste bien remplie.
        self.setStyleSheet(
            f"background:{background};border:1px solid {border};"
            f"border-radius:{t.RADIUS_MD}px;")

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
        self.search.setMinimumWidth(240)
        self.search.setMaximumWidth(360)
        self.search.textChanged.connect(self._apply_filters)

        self.workspace_filter = QComboBox()
        self.workspace_filter.setFixedWidth(190)
        self.workspace_filter.currentIndexChanged.connect(self._apply_filters)

        self.filter_button = QToolButton()
        self.filter_button.setText("Readers")
        self.filter_button.setObjectName("HistoryAction")
        self.filter_button.setPopupMode(QToolButton.InstantPopup)
        self.filter_menu = QMenu(self.filter_button)
        self.filter_button.setMenu(self.filter_menu)

        self.compare_button = QPushButton("Compare")
        self.compare_button.setObjectName("Primary")
        self.compare_button.setFixedWidth(108)
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
        self.run_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.run_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.run_list.itemDoubleClicked.connect(lambda _item: self.view_output())
        self.run_list.verticalScrollBar().valueChanged.connect(
            lambda _value: self._materialize_cards())

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
        left.setMinimumWidth(360)
        left.setMaximumWidth(520)
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

        self.passed_value = QLabel()
        self.passed_value.setStyleSheet(
            f"font-size:22px;font-weight:700;color:{t.status_color(Status.PASSED)};"
            "background:transparent;")
        self.failed_value = QLabel()
        self.failed_value.setObjectName("Muted")
        self.error_value = QLabel()
        self.error_value.setObjectName("Muted")
        self.success_value = QLabel()
        self.success_value.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{t.status_color(Status.PASSED)};"
            "background:transparent;")
        summary_top = QHBoxLayout()
        summary_top.setSpacing(t.SPACE_2)
        summary_top.addWidget(self.passed_value)
        summary_top.addWidget(self.failed_value)
        summary_top.addWidget(self.error_value)
        summary_top.addStretch(1)
        summary_top.addWidget(self.success_value)

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
        summary_layout.addWidget(self.detail_meta)

        self.tabs = _history_tabs()
        self.overview = self._build_overview()
        self.issues_table = self._issue_table()
        self.output = ReaderViews(Qt.Vertical)
        self.details_table = QTableWidget(0, 8)
        self.details_table.setHorizontalHeaderLabels(
            ["Reader", "Passed", "Failed", "Skipped", "Error",
             "Duration", "Exit", "JUnit"])
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.issues_table, "Issues (0)")
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
        layout.addWidget(summary)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)
        return panel

    def _build_overview(self) -> QWidget:
        widget = QWidget()
        self.issue_preview = self._issue_table()
        self.issue_preview.setMaximumHeight(190)

        issues_title = QLabel("Issues requiring attention")
        issues_title.setStyleSheet(
            f"font-size:{t.TEXT_MD}px;font-weight:700;background:transparent;")
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(issues_title)
        left.addWidget(self.issue_preview)
        left.addStretch(1)

        self.reader_box = QFrame()
        self.reader_box.setObjectName("HistoryAside")
        self.reader_box.setFixedWidth(290)
        self.reader_layout = QVBoxLayout(self.reader_box)
        self.reader_layout.setContentsMargins(t.SPACE_3, t.SPACE_3,
                                              t.SPACE_3, t.SPACE_3)
        title = QLabel("Readers")
        title.setStyleSheet(
            f"font-size:{t.TEXT_MD}px;font-weight:700;background:transparent;")
        self.reader_layout.addWidget(title)
        self.reader_layout.addStretch(1)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, t.SPACE_2, 0, 0)
        layout.setSpacing(t.SPACE_3)
        layout.addLayout(left, 1)
        layout.addWidget(self.reader_box)
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

    def restyle(self) -> None:
        """Rejoue les couleurs figees a la construction de chaque carte.

        Rester sur la page PENDANT une bascule de theme laissait les cartes
        deja construites dans l'ancienne teinte, cote a cote avec un fond deja
        repeint. Chaque `RunCard` sait desormais se repeindre en place ; un
        historique bien rempli peut en compter jusqu'a 300 (`MAX_ENTREES`), et
        les reconstruire toutes -- l'ancienne approche -- couterait bien plus
        cher qu'un simple repeint.
        """
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
                item.setSizeHint(QSize(0, 106))
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
        viewport = self.run_list.viewport()
        first = self.run_list.indexAt(QPoint(1, 1)).row()
        last = self.run_list.indexAt(
            QPoint(1, max(1, viewport.height() - 2))).row()
        if first < 0:
            first = 0
        if last < first:
            last = min(count - 1, first + 12)
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
        if self._compare_mode and len(selected) > 2:
            current = self.run_list.currentItem()
            self._adjusting_selection = True
            try:
                for item in selected:
                    if item is not current:
                        item.setSelected(False)
                        break
            finally:
                self._adjusting_selection = False

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
        self.detail_title.setText(Path(group.workspace).name or group.workspace)
        self.detail_subtitle.setText(
            f"{_when(group.timestamp)}  ·  {group.workspace}")
        self.passed_value.setText(str(group.count(Status.PASSED)))
        self.failed_value.setText(f"{group.count(Status.FAILED)} failed")
        self.error_value.setText(f"{group.count(Status.ERROR)} error")
        success = 100 * group.count(Status.PASSED) / group.total if group.total else 0
        self.success_value.setText(f"{success:.0f}% success")
        counts = {status: group.count(status) for status in Status}
        self.ribbon.set_counts(counts)
        self.detail_meta.setText(
            f"{len(group.nodeids)} tests    {group.total} results    "
            f"{group.duration:.1f}s    "
            f"{len(group.entries)} reader{'s' if len(group.entries) != 1 else ''}    "
            + (f"Build #{group.build_number:04d}    "
               if group.build_number is not None else "")
            + f"Run ID {group.id}")
        self.tabs.setTabText(1, f"Issues ({len(group.failed_nodeids)})")
        self._fill_issues(self.issue_preview, group)
        self._fill_issues(self.issues_table, group)
        self._fill_readers(group)
        self._fill_output(group)
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
        table.setVisible(bool(nodeids))
        if table is self.issue_preview:
            table.setMaximumHeight(min(190, 42 + 34 * max(1, len(nodeids))))

    def _fill_readers(self, group: RunGroup) -> None:
        # Le titre et le stretch restent ; seules les cartes intermediaires
        # sont recreees pour le run courant.
        while self.reader_layout.count() > 2:
            item = self.reader_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, entry in reversed(list(enumerate(group.entries))):
            card = QFrame()
            card.setObjectName("HistoryReaderCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(t.SPACE_2, t.SPACE_2,
                                      t.SPACE_2, t.SPACE_2)
            name = QLabel(f"●  {_short_reader(entry.reader)}")
            name.setStyleSheet(
                f"color:{t.reader_color(index)};font-weight:700;"
                "background:transparent;")
            result = QLabel(
                f"{entry.count(Status.PASSED)} passed    "
                f"{entry.count(Status.FAILED) + entry.count(Status.ERROR)} issues")
            result.setObjectName("Muted")
            layout.addWidget(name)
            layout.addWidget(result)
            self.reader_layout.insertWidget(1, card)

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
        if not self._compare_mode:
            self._enter_compare_mode()
            return
        groups = self._selected_groups()
        if len(groups) != 2:
            return
        if not self._compatible(groups[0], groups[1]):
            self._say("Choose two runs from the same workspace with a common reader.",
                      alert=True)
            return
        GroupComparisonDialog(groups[0], groups[1], self).exec()

    def _enter_compare_mode(self) -> None:
        if len(self._visible_groups) < 2:
            return
        self._compare_mode = True
        self.run_list.clearSelection()
        self.run_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.cancel_compare.setVisible(True)
        self._say("Select two compatible runs.")
        self._update_compare_action()

    def _leave_compare_mode(self) -> None:
        self._compare_mode = False
        self.run_list.setSelectionMode(QAbstractItemView.SingleSelection)
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
        left = set(first.reader_names)
        right = set(second.reader_names)
        return bool(left & right) or (not left and not right)

    def _update_compare_action(self) -> None:
        if not self._compare_mode:
            self.compare_button.setText("Compare")
            self.compare_button.setEnabled(len(self._visible_groups) >= 2)
            return
        count = len(self._selected_groups())
        self.compare_button.setText("Compare selected" if count == 2
                                    else f"Compare {count} / 2")
        self.compare_button.setEnabled(count == 2)
