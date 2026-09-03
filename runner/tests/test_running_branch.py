"""L'indicateur "en cours" (icone + texte bleu) pendant un run en direct.

`clean_ui.install()` etend `TestTreeModel` pour teindre en bleu la branche
active pendant l'execution -- installe une seule fois ici, comme au demarrage
reel de l'application (`runner/__main__.py`).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from runner.domain.tree import build_tree
from runner.ui import clean_ui
from runner.ui import tokens as t
from runner.ui.tree_model import TestTreeModel

clean_ui.install()

NODEIDS = [
    "suite/test_math.py::test_compute[case_1-2]",
    "suite/test_math.py::test_compute[case_2-4]",
]


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def model(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree(NODEIDS))
    return m


def _index_for(model, nodeid: str):
    ligne = model._by_nodeid[nodeid]
    return model.createIndex(ligne.row, 0, ligne)


def test_the_running_case_itself_turns_blue_not_just_its_function(model):
    """Avant le correctif, seule la fonction parametree (le groupe) passait
    en bleu : le cas precis qui tourne vraiment restait dans sa couleur
    normale, impossible a distinguer de ses freres pas encore lances."""
    running = NODEIDS[0]
    other = NODEIDS[1]
    model.set_running_test(0, running)

    running_index = _index_for(model, running)
    other_index = _index_for(model, other)

    assert model.data(running_index, Qt.ForegroundRole) == QColor(t.ACCENT)
    assert model.data(other_index, Qt.ForegroundRole) != QColor(t.ACCENT)


def test_the_parametrized_function_still_turns_blue_too(model):
    """La fonction qui regroupe les cas doit rester active : un dossier
    replie doit encore montrer ou pytest travaille."""
    model.set_running_test(0, NODEIDS[0])

    fonction = model._by_nodeid[NODEIDS[0]].parent
    fonction_index = model.createIndex(fonction.row, 0, fonction)

    assert model.data(fonction_index, Qt.ForegroundRole) == QColor(t.ACCENT)


def test_finishing_the_reader_clears_the_case_and_its_function(model):
    model.set_running_test(0, NODEIDS[0])
    model.clear_running_reader(0)

    running_index = _index_for(model, NODEIDS[0])
    fonction = model._by_nodeid[NODEIDS[0]].parent
    fonction_index = model.createIndex(fonction.row, 0, fonction)

    assert model.data(running_index, Qt.ForegroundRole) != QColor(t.ACCENT)
    assert model.data(fonction_index, Qt.ForegroundRole) != QColor(t.ACCENT)


def test_moving_to_the_next_case_clears_the_previous_one(model):
    model.set_running_test(0, NODEIDS[0])
    model.set_running_test(0, NODEIDS[1])

    premier_index = _index_for(model, NODEIDS[0])
    second_index = _index_for(model, NODEIDS[1])

    assert model.data(premier_index, Qt.ForegroundRole) != QColor(t.ACCENT)
    assert model.data(second_index, Qt.ForegroundRole) == QColor(t.ACCENT)
