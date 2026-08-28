"""Le menu contextuel (clic droit) de l'arbre.

`menu.exec_()` ouvre une vraie boucle d'evenements modale : les tests
construisent le menu (`_construire_menu_test` / `_construire_menu_groupe`)
sans jamais l'executer, et declenchent les actions directement.
"""

from __future__ import annotations

import sys

import pytest
from PyQt5.QtWidgets import QApplication, QMenu

from runner.domain import execution
from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.results_panel import ONGLET_SOURCE
from runner.ui.run_n_times_dialog import RunNTimesDialog
from runner.services.run_service import RunService

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
    "suite/perso/test_cert.py::test_chr",
]


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

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


def _action(menu: QMenu, texte: str):
    for action in menu.actions():
        if action.text() == texte:
            return action
    return None


def _menu_pour(fenetre, nodeid: str) -> QMenu:
    index = fenetre.model.index_for_nodeid(nodeid)
    menu = QMenu(fenetre)
    fenetre._construire_menu_test(menu, nodeid)
    return menu


# ------------------------------------------------------------- un test seul

def test_a_test_node_offers_the_six_actions(fenetre):
    menu = _menu_pour(fenetre, NODEIDS[0])
    libelles = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert libelles == ["Run only this test", "Run until it fails…",
                        "Run N times…", "Copy nodeid",
                        "Copy failure trace", "Open file"]


def test_run_only_this_test_starts_a_normal_run(fenetre, monkeypatch):
    appels = []
    monkeypatch.setattr(fenetre, "_start", lambda nodeids: appels.append(nodeids))
    menu = _menu_pour(fenetre, NODEIDS[0])

    _action(menu, "Run only this test").trigger()

    assert appels == [[NODEIDS[0]]]


def test_copy_nodeid_puts_it_on_the_clipboard(fenetre):
    menu = _menu_pour(fenetre, NODEIDS[0])

    _action(menu, "Copy nodeid").trigger()

    assert QApplication.clipboard().text() == NODEIDS[0]


def test_copy_failure_trace_is_disabled_without_a_known_failure(fenetre):
    menu = _menu_pour(fenetre, NODEIDS[0])
    assert not _action(menu, "Copy failure trace").isEnabled()


def test_copy_failure_trace_is_enabled_and_copies_the_real_trace(fenetre):
    sortie = (
        "=================================== FAILURES ===================================\n"
        "_________________________ test_atr _________________________\n"
        "    def test_atr():\n"
        ">       assert False\n"
        "E       AssertionError: boom\n"
    )
    fenetre.results.set_report(_rapport_avec_sortie(sortie))

    menu = _menu_pour(fenetre, NODEIDS[0])
    action = _action(menu, "Copy failure trace")
    assert action.isEnabled()

    action.trigger()
    assert "AssertionError: boom" in QApplication.clipboard().text()


def test_open_file_switches_to_the_source_tab(fenetre):
    menu = _menu_pour(fenetre, NODEIDS[0])
    _action(menu, "Open file").trigger()
    assert fenetre.results.tabs.currentIndex() == ONGLET_SOURCE


def test_actions_are_disabled_while_a_run_is_busy(fenetre, monkeypatch):
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    menu = _menu_pour(fenetre, NODEIDS[0])

    assert not _action(menu, "Run only this test").isEnabled()
    assert not _action(menu, "Run until it fails…").isEnabled()
    assert not _action(menu, "Run N times…").isEnabled()


# --------------------------------------------------------- dossier / fichier

def _menu_groupe_pour(fenetre, nodeid_temoin: str) -> QMenu:
    index = fenetre.model.index_for_nodeid(nodeid_temoin).parent()
    menu = QMenu(fenetre)
    fenetre._construire_menu_groupe(menu, index)
    return menu, index


def test_a_module_file_offers_run_only_this_and_open_file(fenetre):
    menu, _ = _menu_groupe_pour(fenetre, NODEIDS[0])
    libelles = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert libelles == ["Run only this", "Open file"]


def test_a_folder_does_not_offer_open_file(fenetre):
    # Le dossier "suite" est le parent du module -- deux niveaux au-dessus
    # de test_atr.
    index_module = fenetre.model.index_for_nodeid(NODEIDS[0]).parent()
    index_dossier = index_module.parent()
    menu = QMenu(fenetre)
    fenetre._construire_menu_groupe(menu, index_dossier)

    libelles = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert libelles == ["Run only this"]


def test_run_only_this_on_a_module_runs_every_test_beneath_it(fenetre, monkeypatch):
    appels = []
    monkeypatch.setattr(fenetre, "_start", lambda nodeids: appels.append(nodeids))
    menu, _ = _menu_groupe_pour(fenetre, NODEIDS[0])

    _action(menu, "Run only this").trigger()

    assert sorted(appels[0]) == sorted(NODEIDS[:2])


def _rapport_avec_sortie(sortie: str):
    from runner.domain.execution import ReaderReport

    return ReaderReport(reader=Reader("", 0), output=sortie)
