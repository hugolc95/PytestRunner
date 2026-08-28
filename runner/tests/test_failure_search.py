"""Chercher un texte dans les traces d'echec du dernier run, et sauter au
test correspondant -- au lieu de chercher un test par son nom.
"""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSettings

from runner.domain.execution import ReaderReport
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.widgets import SCOPE_FAILURES

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


def _sortie(nom_test: str, message: str) -> str:
    return (
        "=================================== FAILURES ===================================\n"
        f"_________________________ {nom_test} _________________________\n"
        "    def f():\n"
        ">       assert False\n"
        f"E       {message}\n"
    )


@pytest.fixture
def deux_echecs(fenetre):
    """test_atr et test_chr echouent avec des messages differents ;
    test_aid passe."""
    sortie = "\n".join([
        _sortie("test_atr", "ConnectionError: gateway timed out"),
        _sortie("test_chr", "AssertionError: expected 200, got 503"),
    ])
    fenetre.results.set_report(ReaderReport(reader=Reader("", 0), output=sortie))
    return fenetre


def test_switching_to_failures_scope_searches_traces_not_names(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)

    fenetre._on_search("ConnectionError")

    assert fenetre._matches == [NODEIDS[0]]


def test_a_name_that_only_matches_by_coincidence_in_trace_text_is_found(fenetre, deux_echecs):
    """Le texte cherche peut n'avoir aucun rapport avec le nom du test --
    c'est justement ce que la recherche par nom ne sait pas faire."""
    fenetre.search._set_scope(SCOPE_FAILURES)

    fenetre._on_search("expected 200")

    assert fenetre._matches == [NODEIDS[2]]


def test_a_query_matching_both_failures_finds_both_in_tree_order(fenetre):
    sortie = "\n".join([
        _sortie("test_atr", "TimeoutError: slow"),
        _sortie("test_chr", "TimeoutError: also slow"),
    ])
    fenetre.results.set_report(ReaderReport(reader=Reader("", 0), output=sortie))
    fenetre.search._set_scope(SCOPE_FAILURES)

    fenetre._on_search("TimeoutError")

    assert fenetre._matches == [NODEIDS[0], NODEIDS[2]]


def test_the_results_list_shows_the_matching_line_as_a_snippet(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)

    fenetre._on_search("ConnectionError")

    assert fenetre.failure_results.count() == 1
    texte = fenetre.failure_results.item(0).text()
    assert "test_atr" in texte
    assert "ConnectionError" in texte


def test_no_match_says_so_instead_of_an_empty_list(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)

    fenetre._on_search("NoSuchExceptionAnywhere")

    assert fenetre.failure_results.count() == 1
    assert "no failure" in fenetre.failure_results.item(0).text().lower()


def test_clicking_a_result_jumps_to_that_test(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)
    fenetre._on_search("expected 200")

    fenetre._sur_resultat_echec_clique(fenetre.failure_results.item(0))

    assert fenetre.tree.currentIndex() == fenetre.model.index_for_nodeid(NODEIDS[2])


def test_next_and_previous_cycle_through_failure_matches(fenetre):
    sortie = "\n".join([
        _sortie("test_atr", "BoomError: one"),
        _sortie("test_chr", "BoomError: two"),
    ])
    fenetre.results.set_report(ReaderReport(reader=Reader("", 0), output=sortie))
    fenetre.search._set_scope(SCOPE_FAILURES)
    fenetre._on_search("BoomError")
    assert fenetre.tree.currentIndex() == fenetre.model.index_for_nodeid(NODEIDS[0])

    fenetre._goto_match(1)
    assert fenetre.tree.currentIndex() == fenetre.model.index_for_nodeid(NODEIDS[2])


def test_switching_scope_hides_stale_results(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)
    fenetre._on_search("ConnectionError")
    assert fenetre.failure_results.count() == 1

    fenetre.search._set_scope("tests")

    assert fenetre.failure_results.count() == 0
    assert fenetre._matches == []


def test_switching_back_to_tests_scope_uses_name_matching_again(fenetre, deux_echecs):
    fenetre.search._set_scope(SCOPE_FAILURES)
    fenetre.search._set_scope("tests")

    fenetre._on_search("test_atr")

    assert fenetre._matches == [NODEIDS[0]]
    assert not fenetre.failure_results.isVisible()
