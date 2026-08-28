"""Les markers et l'historique par test, de la fenetre jusqu'au panneau
Detail -- les tests de detail_panel.py verifient l'affichage une fois les
donnees recues, ceux-ci verifient qu'elles lui arrivent bien.
"""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSettings

from runner.domain.history import History, RunEntry
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow

NODEID = "suite/apdu/test_select.py::test_atr"


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace.load(str(tmp_path))
    f.model.set_tree(build_tree([NODEID]))
    f.model.set_readers((Reader("", 0),))
    f.results.set_readers((Reader("", 0),))
    f.history = History(tmp_path / "history")
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _selectionner(fenetre) -> None:
    fenetre._select_test(fenetre.model.index_for_nodeid(NODEID))


def test_markers_reach_the_detail_panel(fenetre):
    fenetre._markers_by_nodeid = {NODEID: ("smoke", "auth")}

    _selectionner(fenetre)

    assert not fenetre.results.detail.markers_row.isHidden()
    textes = [fenetre.results.detail._markers_layout.itemAt(i).widget().text()
             for i in range(fenetre.results.detail._markers_layout.count())
             if fenetre.results.detail._markers_layout.itemAt(i).widget() is not None]
    assert textes == ["smoke", "auth"]


def test_a_test_never_seen_before_has_no_sparkline(fenetre):
    _selectionner(fenetre)

    assert fenetre.results.detail._sparklines == {}


def test_past_runs_of_this_test_feed_the_sparkline(fenetre):
    fenetre.history.add(RunEntry(
        id="r1", timestamp=1.0, workspace=str(fenetre.workspace.path),
        nodeids=(NODEID,), failed_nodeids=(NODEID,)))
    fenetre.history.add(RunEntry(
        id="r2", timestamp=2.0, workspace=str(fenetre.workspace.path),
        nodeids=(NODEID,), failed_nodeids=()))

    _selectionner(fenetre)

    assert fenetre.results.detail._sparklines[0]._runs == (False, True)


def test_the_last_seen_timestamp_reaches_the_panel(fenetre):
    from runner.domain.models import Status

    fenetre.history.add(RunEntry(
        id="r1", timestamp=42.0, workspace=str(fenetre.workspace.path),
        nodeids=(NODEID,), failed_nodeids=()))
    fenetre.model.apply_outcome(NODEID, Status.PASSED, 0)

    _selectionner(fenetre)

    import time
    attendu = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(42.0))
    assert attendu in fenetre.results.detail.body.toPlainText()
