"""Le modele de l'arbre, teste sans instancier la fenetre principale."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QColor

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel

NODEIDS = [
    "suite/test_a.py::test_one[x]",
    "suite/test_a.py::test_one[y]",
    "suite/test_b.py::test_two",
]
READERS = (Reader("Reader A", 0), Reader("Reader B", 1))


@pytest.fixture
def model(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree(NODEIDS))
    m.set_readers(READERS)
    return m


@pytest.fixture(scope="session")
def qapp():
    """QApplication partagee : le modele n'a pas besoin de plus."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


def _racine(model) -> QModelIndex:
    return model.index(0, 0, QModelIndex())


# ------------------------------------------------------------------ structure

def test_one_status_column_per_reader(model):
    assert model.columnCount() == 1 + len(READERS)
    assert model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "Reader A"
    assert model.headerData(2, Qt.Horizontal, Qt.DisplayRole) == "Reader B"


def test_the_full_reader_name_stays_in_the_tooltip(model):
    assert model.headerData(1, Qt.Horizontal, Qt.ToolTipRole) == "Reader A"


def test_each_reader_header_carries_its_own_colour(model):
    from runner.ui import tokens as t

    assert model.headerData(1, Qt.Horizontal, Qt.ForegroundRole) == QColor(
        t.reader_color(READERS[0].index))
    assert model.headerData(2, Qt.Horizontal, Qt.ForegroundRole) == QColor(
        t.reader_color(READERS[1].index))


def test_search_is_case_insensitive_and_keeps_tree_order(model):
    assert model.matching_nodeids("TEST_ONE") == NODEIDS[:2]
    assert model.matching_nodeids("[Y]") == [NODEIDS[1]]
    assert model.matching_nodeids("absent") == []


def test_without_readers_a_single_status_column_remains(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree(NODEIDS))
    assert m.columnCount() == 2


def test_the_leaves_carry_the_nodeids(model):
    assert sorted(model.checked_nodeids()) == sorted(NODEIDS)
    assert model.counts() == (3, 3)


# ------------------------------------------------------------------ selection

def test_everything_starts_selected(model):
    assert model.data(_racine(model), Qt.CheckStateRole) == Qt.Checked


def test_unchecking_a_folder_unchecks_what_it_holds(model):
    """L'utilisateur pense en blocs, pas en feuilles."""
    model.setData(_racine(model), Qt.Unchecked, Qt.CheckStateRole)
    assert model.checked_nodeids() == []


def test_a_partly_checked_folder_says_so(model):
    """Ni coche ni decoche : l'etat intermediaire evite de croire que tout le
    dossier part au run."""
    feuille = model.index_for_nodeid(NODEIDS[0])
    model.setData(feuille, Qt.Unchecked, Qt.CheckStateRole)
    assert model.data(_racine(model), Qt.CheckStateRole) == Qt.PartiallyChecked


def test_selection_changes_are_announced(model, qapp):
    recu = []
    model.selection_changed.connect(lambda c, t: recu.append((c, t)))
    model.set_all_checked(False)
    assert recu[-1] == (0, 3)


# -------------------------------------------------------------------- statuts

def test_a_result_lands_on_its_leaf(model):
    assert model.apply_outcome(NODEIDS[0], Status.FAILED, 0) is True
    ligne = model.index_for_nodeid(NODEIDS[0]).internalPointer()
    assert model.status_for(ligne, 0) is Status.FAILED


def test_an_unknown_nodeid_is_reported_not_swallowed(model):
    """Collecte non reproductible : mieux vaut le signaler que le perdre."""
    assert model.apply_outcome("jamais/vu.py::test_x", Status.PASSED, 0) is False


def test_a_group_shows_the_worst_of_its_children(model):
    model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    model.apply_outcome(NODEIDS[1], Status.FAILED, 0)
    ligne = _racine(model).internalPointer()
    assert model.status_for(ligne, 0) is Status.FAILED


def test_each_reader_keeps_its_own_result(model):
    model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    model.apply_outcome(NODEIDS[0], Status.FAILED, 1)
    ligne = model.index_for_nodeid(NODEIDS[0]).internalPointer()
    assert model.status_for(ligne, 0) is Status.PASSED
    assert model.status_for(ligne, 1) is Status.FAILED


def test_clearing_statuses_keeps_the_selection(model):
    """Un reset complet du modele replierait l'arbre et perdrait la branche que
    l'utilisateur venait d'ouvrir pour choisir ses tests."""
    model.setData(model.index_for_nodeid(NODEIDS[0]), Qt.Unchecked, Qt.CheckStateRole)
    model.apply_outcome(NODEIDS[1], Status.FAILED, 0)

    model.clear_statuses()

    ligne = model.index_for_nodeid(NODEIDS[1]).internalPointer()
    assert model.status_for(ligne, 0) is Status.PENDING
    assert NODEIDS[0] not in model.checked_nodeids(), "la selection doit survivre"


def test_clearing_statuses_emits_no_model_reset(model):
    """La vue perdrait son depliage : c'est ce que le reset provoquait."""
    resets = []
    model.modelReset.connect(lambda: resets.append(1))
    model.clear_statuses()
    assert resets == []


# ---------------------------------------------------------------- divergences

def test_divergent_tests_are_listed(model):
    """La question centrale d'un run multi-lecteur."""
    model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    model.apply_outcome(NODEIDS[0], Status.FAILED, 1)
    model.apply_outcome(NODEIDS[1], Status.PASSED, 0)
    model.apply_outcome(NODEIDS[1], Status.PASSED, 1)

    assert model.divergent_nodeids() == [NODEIDS[0]]


def test_agreement_is_not_a_divergence(model):
    model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    model.apply_outcome(NODEIDS[0], Status.FAILED, 1)
    assert model.divergent_nodeids() == []


def test_a_single_reader_can_never_disagree(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree(NODEIDS))
    m.set_readers((Reader("Only", 0),))
    m.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    assert m.divergent_nodeids() == []


def test_failed_tests_are_listed_across_readers(model):
    model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    model.apply_outcome(NODEIDS[0], Status.ERROR, 1)
    assert model.failed_nodeids() == [NODEIDS[0]]


# -------------------------------------------------------------------- lecture

def test_the_nodeid_is_readable_from_the_index(model):
    index = model.index_for_nodeid(NODEIDS[2])
    assert model.data(index, NODEID_ROLE) == NODEIDS[2]


def test_an_unknown_nodeid_gives_an_invalid_index(model):
    assert not model.index_for_nodeid("absent").isValid()
