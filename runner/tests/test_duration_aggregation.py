"""La duree d'un dossier ou d'un fichier est la SOMME de ses tests -- pas
juste celle du dernier lecteur qui a fini, et pas faussee par un test dont
pytest n'a pas garde la mesure.
"""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSettings

from runner.domain.execution import ReaderReport
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
    "suite/perso/test_cert.py::test_chr",
]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace.load(str(tmp_path))
    f.model.set_tree(build_tree(NODEIDS))
    f.model.set_readers((Reader("", 0),))
    f.results.set_readers((Reader("", 0),))
    f.left_stack.setCurrentWidget(f.tree)
    f.tree.expandAll()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def test_a_single_tests_duration_reaches_the_detail_panel(fenetre):
    fenetre.results.set_report(ReaderReport(
        reader=Reader("", 0), durations={NODEIDS[0]: 0.75}))

    index = fenetre.model.index_for_nodeid(NODEIDS[0])
    fenetre._select_test(index)

    assert fenetre.results.detail.stack.currentIndex() == fenetre.results.detail.PAGE_TEST
    dernier = fenetre.results.detail._results_layout.itemAt(
        fenetre.results.detail._results_layout.count() - 1).widget()
    assert "0.75s" in dernier.text()


def test_a_module_shows_the_sum_of_its_tests(fenetre):
    fenetre.results.set_report(ReaderReport(
        reader=Reader("", 0),
        durations={NODEIDS[0]: 0.30, NODEIDS[1]: 0.45}))

    index_module = fenetre.model.index_for_nodeid(NODEIDS[0]).parent()
    fenetre._select_test(index_module)

    assert "0.75s" in fenetre.results.detail.group_total.text()


def test_a_test_with_no_known_duration_does_not_break_the_sum(fenetre):
    # test_aid n'a pas de duree connue (trop rapide pour le releve de pytest,
    # ou jamais joue) : la somme du module ne compte que ce qui EST connu.
    fenetre.results.set_report(ReaderReport(
        reader=Reader("", 0), durations={NODEIDS[0]: 0.30}))

    index_module = fenetre.model.index_for_nodeid(NODEIDS[0]).parent()
    fenetre._select_test(index_module)

    assert "0.30s" in fenetre.results.detail.group_total.text()


def test_the_root_folder_sums_every_module_beneath_it(fenetre):
    fenetre.results.set_report(ReaderReport(
        reader=Reader("", 0),
        durations={NODEIDS[0]: 0.30, NODEIDS[1]: 0.45, NODEIDS[2]: 1.00}))

    # test_atr -> test_select.py -> apdu -> suite (la racine commune aux deux
    # dossiers "apdu" et "perso").
    index_racine = fenetre.model.index_for_nodeid(NODEIDS[0]).parent().parent().parent()
    fenetre._select_test(index_racine)

    assert "1.75s" in fenetre.results.detail.group_total.text()


def test_no_durations_at_all_shows_only_the_count(fenetre):
    index_module = fenetre.model.index_for_nodeid(NODEIDS[0]).parent()
    fenetre._select_test(index_module)

    assert "·" not in fenetre.results.detail.group_total.text()
