"""Small visual refinements for the main runner interface.

Keep the result summary and live run status flat: both already sit inside a
larger panel/status bar, so drawing another box around them creates a nested
"box in a box" effect on Windows.

This module also adds a lightweight live-run indicator to the test tree.  A
small loading icon follows the branch that currently contains the executing
test, so a collapsed folder/module/class still makes it obvious where pytest
is working.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t


_START_PREFIX = "PYTESTRUNNER_START\t"


def install() -> None:
    """Install the visual refinements before the main window is created."""
    from runner.domain import execution, reader_isolation
    from runner.services.run_service import RunService
    from runner.ui.detail_panel import DetailPanel
    from runner.ui.main_window import MainWindow
    from runner.ui.tree_model import TestTreeModel

    def flat_stat_cell(self, legende: str, valeur: QWidget) -> QWidget:
        cellule = QWidget()
        colonne = QVBoxLayout(cellule)
        colonne.setContentsMargins(t.SPACE_2, t.SPACE_1, t.SPACE_2, t.SPACE_1)
        colonne.setSpacing(2)

        from PyQt5.QtWidgets import QLabel
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
        # No extra background/border here: the status bar already provides
        # the visual container and the live dot + blue text carry the state.
        self.live_chip.setStyleSheet("")

    DetailPanel._stat_cell = flat_stat_cell
    MainWindow._set_status_live = flat_status_live

    # ------------------------------------------------------------------
    # Live branch indicator
    # ------------------------------------------------------------------
    # pytest's normal -v terminal output does not reliably expose a test start
    # as a complete line: for a long-running test the line can stay buffered
    # until the verdict arrives.  The internal reader plugin already owns a
    # stable machine-readable channel for verdicts, so append the matching
    # start hook there as well.  It is generated into the temporary pytest
    # process and never touches the user's test sources.
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

    # ReaderRun keeps every ordinary stdout line in the report.  The start
    # marker deliberately travels through on_line() so the UI sees it live,
    # then is removed from the stored output before history/log views receive
    # the finished report.
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

    def _running_groups(self) -> set:
        groupes = set()
        for nodeid in getattr(self, "_running_by_reader", {}).values():
            ligne = self._by_nodeid.get(nodeid)
            if ligne is None:
                continue
            parent = ligne.parent
            while parent is not None:
                # Mark every grouping level, not only Kind.FOLDER.  This means
                # the indicator remains visible whether the user collapsed a
                # folder, a module or a class.
                if parent.children:
                    groupes.add(parent)
                parent = parent.parent
        return groupes

    def _repaint_running_rows(self, rows) -> None:
        for ligne in rows:
            index = self.createIndex(ligne.row, 0, ligne)
            self.dataChanged.emit(
                index, index,
                [Qt.DecorationRole, Qt.ForegroundRole, Qt.ToolTipRole],
            )

    def set_running_test(self, reader_index: int, nodeid: str) -> None:
        avant = _running_groups(self)
        mapping = getattr(self, "_running_by_reader", None)
        if mapping is None:
            mapping = {}
            self._running_by_reader = mapping
        mapping[int(reader_index)] = nodeid
        apres = _running_groups(self)
        _repaint_running_rows(self, avant | apres)

    def clear_running_reader(self, reader_index: int) -> None:
        mapping = getattr(self, "_running_by_reader", None)
        if not mapping or int(reader_index) not in mapping:
            return
        avant = _running_groups(self)
        mapping.pop(int(reader_index), None)
        apres = _running_groups(self)
        _repaint_running_rows(self, avant | apres)

    def clear_running_tests(self) -> None:
        mapping = getattr(self, "_running_by_reader", None)
        if not mapping:
            return
        avant = _running_groups(self)
        mapping.clear()
        _repaint_running_rows(self, avant)

    def name_data_with_running_branch(self, ligne, role):
        active = ligne in _running_groups(self)
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

    # Replace the normal service wiring only to intercept the private start
    # marker.  Every normal console line and every existing signal keeps the
    # same destination as before.
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

        # Keep Python references to the local slots for as long as the window
        # lives.  PyQt usually retains connected callables, but explicit refs
        # make their lifetime unambiguous and avoid hard-to-reproduce Windows
        # disconnects during long runs.
        self._live_branch_line_slot = live_line
        self._live_branch_reader_finished_slot = reader_finished
        self._live_branch_run_finished_slot = run_finished

        self.service.line.connect(live_line)
        self.service.outcome.connect(self._on_outcome)
        self.service.progress.connect(self._on_progress)
        self.service.reader_finished.connect(reader_finished)
        self.service.finished.connect(run_finished)

    MainWindow._connect_service = connect_service_with_running_branch
