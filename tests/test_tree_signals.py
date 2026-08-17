"""Les mises a jour d'apparence de l'arbre ne doivent pas reveiller la
propagation des cases a cocher.

Sans blocage des signaux, chaque setData/setIcon emet itemChanged, donc
_on_item_changed reparcourt tout l'arbre pour repropager les cases et recompter
la selection. Sur un workspace de 6000 tests, reset_result_colors passait ainsi
de 46 ms a 45 secondes de gel de l'interface, a chaque lancement de tests.
"""

import pytest

from core.test_tree import build_test_tree
from gui_qt.test_tree_view import TestTreeView, STATUS_ROLE


NODEIDS = [
    f"paquet_{d}/test_fichier_{f}.py::test_fonction_{t}[{p}]"
    for d in range(3)
    for f in range(4)
    for t in range(5)
    for p in range(4)
]


@pytest.fixture
def tree(qtbot, tmp_path):
    view = TestTreeView()
    qtbot.addWidget(view)
    view.load_tree(build_test_tree(NODEIDS, str(tmp_path)))
    return view


def count_item_changed(tree) -> list:
    emissions = []
    tree.model.itemChanged.connect(lambda item: emissions.append(item))
    return emissions


def test_the_fixture_tree_is_big_enough_to_matter(tree):
    assert len(tree.get_selected_nodeids()) == len(NODEIDS) == 240


def test_reset_result_colors_emits_no_item_changed(tree):
    emissions = count_item_changed(tree)
    tree.reset_result_colors()
    assert emissions == []


def test_applying_a_result_emits_no_item_changed(tree):
    emissions = count_item_changed(tree)
    tree.update_single_test(NODEIDS[0], "FAILED")
    assert emissions == []


def test_applying_every_result_emits_no_item_changed(tree):
    emissions = count_item_changed(tree)
    for nodeid in NODEIDS:
        tree.update_single_test(nodeid, "PASSED")
    assert emissions == []


def test_status_is_still_applied_and_propagated(tree):
    """Bloquer les signaux ne doit rien casser fonctionnellement."""
    tree.update_single_test(NODEIDS[0], "FAILED")

    leaf = tree._find_item_for_nodeid(NODEIDS[0])
    assert leaf.data(STATUS_ROLE) == "FAILED"
    assert tree.model.item(0).data(STATUS_ROLE) == "FAILED"


def test_reset_clears_previous_statuses(tree):
    tree.update_single_test(NODEIDS[0], "FAILED")
    tree.reset_result_colors()

    leaf = tree._find_item_for_nodeid(NODEIDS[0])
    assert leaf.data(STATUS_ROLE) is None
    assert tree.model.item(0).data(STATUS_ROLE) is None


def test_selection_is_untouched_by_status_updates(tree):
    before = tree.get_selected_nodeids()
    for nodeid in NODEIDS:
        tree.update_single_test(nodeid, "PASSED")
    tree.reset_result_colors()

    assert tree.get_selected_nodeids() == before


def test_checkbox_propagation_still_works(tree):
    """Le blocage doit rester circonscrit aux mises a jour d'apparence :
    cocher/decocher doit toujours declencher la propagation."""
    emissions = count_item_changed(tree)
    tree.set_all_checked(False)

    assert tree.get_selected_nodeids() == []

    root = tree.model.item(0)
    root.setCheckState(2)  # Qt.Checked
    assert emissions, "cocher un noeud doit toujours emettre itemChanged"
    assert len(tree.get_selected_nodeids()) > 0
