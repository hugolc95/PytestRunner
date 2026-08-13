"""Le champ de recherche amene au test, il ne masque pas le reste.

Filtrer faisait perdre l'endroit ou l'on etait : le test trouve apparaissait
seul, sans son fichier ni sa classe autour, et il fallait vider le champ pour
revoir le contexte. La recherche laisse l'arbre entier visible et s'y deplace.
"""

import textwrap

import pytest
from PyQt5.QtCore import QSettings

from core.test_tree import build_test_tree

NODEIDS = [
    "a/test_alpha.py::test_login",
    "a/test_alpha.py::test_logout",
    "b/test_beta.py::TestGroup::test_login_again",
    "b/test_beta.py::TestGroup::test_other",
]


@pytest.fixture
def window(qtbot, tmp_path):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.tree.load_tree(build_test_tree(NODEIDS))
    return fenetre


def _lignes_masquees(tree) -> list[str]:
    """Noms de toutes les lignes masquees, a n'importe quelle profondeur."""
    masquees: list[str] = []

    def parcourir(item):
        for row in range(item.rowCount()):
            enfant = item.child(row)
            if enfant is None:
                continue
            if tree.isRowHidden(row, item.index()):
                masquees.append(enfant.text())
            parcourir(enfant)

    parcourir(tree.model.invisibleRootItem())
    return masquees


def test_finding_hides_nothing_not_even_the_non_matching_tests(window):
    """Le point central. Regarder les seules lignes racine ne suffit pas : avec
    un filtre, elles restent visibles puisqu'elles CONTIENNENT une
    correspondance. C'est `test_other`, qui n'en est pas une, qui disparait."""
    window.filter_edit.setText("test_login")

    assert _lignes_masquees(window.tree) == []


def test_the_first_match_is_selected_right_away(window):
    window.filter_edit.setText("logout")

    courant = window.tree.model.itemFromIndex(window.tree.currentIndex())
    assert courant is not None
    assert "logout" in courant.text()


def test_matches_are_counted(window):
    window.filter_edit.setText("test_log")
    # test_login, test_logout, test_login_again
    assert window.find_label.text() == "1/3"


def test_enter_cycles_through_the_matches(window):
    window.filter_edit.setText("test_log")
    noms = []
    for _ in range(4):
        courant = window.tree.model.itemFromIndex(window.tree.currentIndex())
        noms.append(courant.text())
        window.find_next()

    assert len(set(noms[:3])) == 3, "chaque correspondance doit etre atteinte"
    assert noms[3] == noms[0], "la recherche doit boucler"


def test_going_backwards_wraps_around(window):
    window.filter_edit.setText("test_log")
    window.find_previous()
    assert window.find_label.text() == "3/3"


def test_a_match_deep_in_the_tree_is_expanded_into_view(window):
    """Le test trouve peut etre sous un fichier et une classe replies : sans
    depliage, on selectionne une ligne que personne ne voit."""
    window.tree.collapseAll()
    window.filter_edit.setText("test_login_again")

    index = window.tree.currentIndex()
    assert index.isValid()
    parent = index.parent()
    while parent.isValid():
        assert window.tree.isExpanded(parent), "chaque parent doit etre deplie"
        parent = parent.parent()


def test_no_match_says_so(window):
    window.filter_edit.setText("nexiste_pas")
    assert window.find_label.text() == "no match"
    assert not window.btn_find_next.isEnabled()


def test_clearing_the_field_clears_the_indicator(window):
    window.filter_edit.setText("test_log")
    window.filter_edit.setText("")
    assert window.find_label.text() == ""
