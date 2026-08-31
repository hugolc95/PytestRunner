"""Small visual refinements for the main runner interface.

Keep the result summary and live run status flat: both already sit inside a
larger panel/status bar, so drawing another box around them creates a nested
"box in a box" effect on Windows.

This module also adds a lightweight live-run indicator to the test tree. A
small loading icon follows the branch that currently contains the executing
test, so a collapsed folder/module/class still makes it obvious where pytest
is working.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t


_START_PREFIX = "PYTESTRUNNER_START\t"


def install() -> None:
    """Install the visual refinements before the main window is created."""
    from runner.domain import execution, reader_isolation
    from runner.ui.detail_panel import DetailPanel
    from runner.ui.main_window import MainWindow
    from runner.ui.tree_model import TestTreeModel
    from runner.ui.widgets import CompassRing

    def flat_stat_cell(self, legende: str, valeur: QWidget) -> QWidget:
        cellule = QWidget()
        colonne = QVBoxLayout(cellule)
        colonne.setContentsMargins(t.SPACE_2, t.SPACE_1, t.SPACE_2, t.SPACE_1)
        colonne.setSpacing(2)

        from PySide6.QtWidgets import QLabel
        libelle = QLabel(legende.upper())
        libelle.setObjectName("StatCellLabel")
        colonne.addWidget(libelle)
        colonne.addWidget(valeur)
        return cellule

    def flat_status_live(self, texte: str) -> None:
        couleur = t.status_color(Status.RUNNING)
        self.status_label.setObjectName("StatusLive")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(texte)
        self.live_dot.set_color(couleur)
        self.live_dot.start()
        self.live_chip.setStyleSheet("")

    DetailPanel._stat_cell = flat_stat_cell
    MainWindow._set_status_live = flat_status_live

    # ------------------------------------------------------------------
    # Compass: completed verdicts + tests still expected
    # ------------------------------------------------------------------
    # Keep unfinished tests as a real segment of the same ring. This makes an
    # incomplete/aborted run visible immediately: if pytest exits before every
    # selected (test, reader) pair produced a verdict, a grey PENDING segment
    # remains in the compass instead of the ring looking deceptively complete.
    CompassRing.ORDER = (
        Status.PASSED,
        Status.FAILED,
        Status.SKIPPED,
        Status.ERROR,
        Status.PENDING,
    )
    original_compass_set_counts = CompassRing.set_counts

    def compass_set_counts_with_remaining(self, counts) -> None:
        merged = dict(counts)
        merged[Status.PENDING] = max(0, int(getattr(self, "_remaining", 0)))
        original_compass_set_counts(self, merged)

    def compass_set_remaining(self, remaining: int) -> None:
        remaining = max(0, int(remaining))
        if remaining == getattr(self, "_remaining", None):
            return
        self._remaining = remaining
        # Reuse the already cached verdict counts. No tree/model scan is
        # involved: one tiny widget repaint per completed test only.
        merged = dict(getattr(self, "_counts", {}))
        merged[Status.PENDING] = remaining
        original_compass_set_counts(self, merged)

    CompassRing.set_counts = compass_set_counts_with_remaining
    CompassRing.set_remaining = compass_set_remaining

    original_run_started = MainWindow._on_run_started
    original_progress = MainWindow._on_progress

    def run_started_with_compass_remaining(self, request) -> None:
        self.compass_ring.set_remaining(request.total_tests)
        original_run_started(self, request)

    def progress_with_compass_remaining(self, done: int, total: int) -> None:
        original_progress(self, done, total)
        self.compass_ring.set_remaining(total - done)

    MainWindow._on_run_started = run_started_with_compass_remaining
    MainWindow._on_progress = progress_with_compass_remaining

    # ------------------------------------------------------------------
    # Live branch indicator
    # ------------------------------------------------------------------
    if _START_PREFIX not in reader_isolation._SOURCE:
        reader_isolation._SOURCE += '''\
\n
_START_PREFIX = "PYTESTRUNNER_START"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logstart(nodeid, location):
    """Tell Pytest Runner which test has just started."""
    if "PYTEST_XDIST_WORKER" not in os.environ:
        sys.__stdout__.write("\\n%s\\t%s\\n" % (_START_PREFIX, nodeid))
        sys.__stdout__.flush()
'''

    # The start marker travels through the live output channel, then is
    # stripped from the finished report so it never pollutes logs/history.
    original_reader_run = execution.ReaderRun.run

    def reader_run_without_start_marker(self, on_line, on_outcome):
        rapport = original_reader_run(self, on_line, on_outcome)
        if _START_PREFIX in rapport.output:
            rapport.output = "".join(
                ligne for ligne in rapport.output.splitlines(keepends=True)
                if not ligne.strip().startswith(_START_PREFIX)
            )
        return rapport

    execution.ReaderRun.run = reader_run_without_start_marker

    original_name_data = TestTreeModel._data_colonne_nom

    def _branch_for_nodeid(self, nodeid: str) -> tuple:
        """Return grouping ancestors once, in O(tree depth)."""
        ligne = self._by_nodeid.get(nodeid)
        if ligne is None:
            return ()
        groupes = []
        parent = ligne.parent
        while parent is not None:
            if parent.children:
                groupes.append(parent)
            parent = parent.parent
        return tuple(groupes)

    def _ensure_running_state(self) -> None:
        if not hasattr(self, "_running_branch_by_reader"):
            self._running_branch_by_reader = {}
            # Reference count instead of rebuilding the active set for every
            # paint. Multiple readers may legitimately share the same branch.
            self._running_group_refs = {}
            self._running_groups_cache = set()

    def _repaint_running_rows(self, rows) -> None:
        for ligne in rows:
            index = self.createIndex(ligne.row, 0, ligne)
            self.dataChanged.emit(
                index, index,
                [Qt.DecorationRole, Qt.ForegroundRole, Qt.ToolTipRole],
            )

    def _remove_branch(self, reader_index: int) -> set:
        _ensure_running_state(self)
        changed = set()
        ancien = self._running_branch_by_reader.pop(int(reader_index), ())
        for groupe in ancien:
            refs = self._running_group_refs.get(groupe, 0) - 1
            if refs <= 0:
                self._running_group_refs.pop(groupe, None)
                if groupe in self._running_groups_cache:
                    self._running_groups_cache.remove(groupe)
                    changed.add(groupe)
            else:
                self._running_group_refs[groupe] = refs
        return changed

    def set_running_test(self, reader_index: int, nodeid: str) -> None:
        """Move one reader's indicator without repainting an unchanged branch.

        The old implementation recomputed every active branch from scratch for
        every Qt data() call, then repainted all ancestors at every test. On a
        large visible tree that made scrolling and live updates noticeably
        slower. Here the active groups are cached, and only rows whose active
        state really toggles are repainted.
        """
        _ensure_running_state(self)
        reader_index = int(reader_index)
        nouveau = _branch_for_nodeid(self, nodeid)
        ancien = self._running_branch_by_reader.get(reader_index, ())
        if nouveau == ancien:
            return

        changed = _remove_branch(self, reader_index)
        self._running_branch_by_reader[reader_index] = nouveau
        for groupe in nouveau:
            refs = self._running_group_refs.get(groupe, 0)
            self._running_group_refs[groupe] = refs + 1
            if refs == 0:
                self._running_groups_cache.add(groupe)
                changed.add(groupe)
        _repaint_running_rows(self, changed)

    def clear_running_reader(self, reader_index: int) -> None:
        changed = _remove_branch(self, int(reader_index))
        if changed:
            _repaint_running_rows(self, changed)

    def clear_running_tests(self) -> None:
        _ensure_running_state(self)
        if not self._running_groups_cache:
            self._running_branch_by_reader.clear()
            self._running_group_refs.clear()
            return
        changed = set(self._running_groups_cache)
        self._running_branch_by_reader.clear()
        self._running_group_refs.clear()
        self._running_groups_cache.clear()
        _repaint_running_rows(self, changed)

    def name_data_with_running_branch(self, ligne, role):
        # Hot path: Qt calls data() repeatedly while painting/scrolling. This
        # must stay an O(1) set lookup; never walk the tree from here.
        active = ligne in getattr(self, "_running_groups_cache", ())
        if active and role == Qt.DecorationRole:
            return icons.status_icon(Status.RUNNING, group=True)
        if active and role == Qt.ForegroundRole:
            return QColor(t.ACCENT)
        if active and role == Qt.ToolTipRole:
            base = original_name_data(self, ligne, role) or ligne.node.name
            return f"{base}\nTests are running inside this branch."
        return original_name_data(self, ligne, role)

    TestTreeModel.set_running_test = set_running_test
    TestTreeModel.clear_running_reader = clear_running_reader
    TestTreeModel.clear_running_tests = clear_running_tests
    TestTreeModel._data_colonne_nom = name_data_with_running_branch

    def connect_service_with_running_branch(self) -> None:
        self.service.started.connect(self._on_run_started)

        def live_line(reader_index: int, texte: str) -> None:
            brut = texte.strip()
            if brut.startswith(_START_PREFIX):
                nodeid = brut[len(_START_PREFIX):].strip()
                if nodeid:
                    self.model.set_running_test(reader_index, nodeid)
                return
            self.results.append_output(reader_index, texte)

        def reader_finished(rapport) -> None:
            self.model.clear_running_reader(rapport.reader.index)
            self.results.set_report(rapport)

        def run_finished(rapports) -> None:
            self.model.clear_running_tests()
            self._on_run_finished(rapports)

        self._live_branch_line_slot = live_line
        self._live_branch_reader_finished_slot = reader_finished
        self._live_branch_run_finished_slot = run_finished

        self.service.line.connect(live_line)
        self.service.outcome.connect(self._on_outcome)
        self.service.progress.connect(self._on_progress)
        self.service.reader_finished.connect(reader_finished)
        self.service.finished.connect(run_finished)

    MainWindow._connect_service = connect_service_with_running_branch
