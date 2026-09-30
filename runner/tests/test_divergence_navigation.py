"""Run multi-lecteur : les desaccords se voient et se parcourent.

Une ligne dont les lecteurs rendent des verdicts differents est teintee dans
l'arbre ; « View differences », a cote de « View failures », y mene. Chaque
clic sur l'un ou l'autre va au cas suivant, et reboucle apres le dernier.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree

NODEIDS = [f"suite/test_{c}.py::test_{c}" for c in "abcde"]
LECTEURS = (Reader("Reader A", 0), Reader("Reader B", 1))
# a : d'accord (passed)   b : diverge (failed/passed)   c : d'accord (failed)
# d : diverge (passed/skipped)   e : d'accord (passed)
VERDICTS = {
    "a": (Status.PASSED, Status.PASSED),
    "b": (Status.FAILED, Status.PASSED),
    "c": (Status.FAILED, Status.FAILED),
    "d": (Status.PASSED, Status.SKIPPED),
    "e": (Status.PASSED, Status.PASSED),
}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from runner.domain.workspace import Workspace
    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace(path=str(tmp_path), config_path="", settings={})
    f.model.set_tree(build_tree(NODEIDS))
    f.model.set_readers(LECTEURS)
    f.results.set_readers(LECTEURS)
    f._set_profile_tree_visible(False)
    for nodeid in NODEIDS:
        lettre = nodeid[-1]
        for lecteur, statut in zip(LECTEURS, VERDICTS[lettre]):
            f.model.apply_outcome(nodeid, statut, lecteur.index)
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _courant(fenetre):
    return fenetre.model.data(fenetre.tree.currentIndex().siblingAtColumn(0),
                              Qt.DisplayRole)


def _fond(fenetre, nodeid, colonne=0):
    index = fenetre.model.index_for_nodeid(nodeid).siblingAtColumn(colonne)
    return fenetre.model.data(index, Qt.BackgroundRole)


# ----------------------------------------------------------------- surlignage

def test_only_rows_where_readers_disagree_are_tinted(fenetre):
    teintes = [n[-1] for n in NODEIDS if _fond(fenetre, n) is not None]
    assert teintes == ["b", "d"]


def test_the_whole_row_is_tinted(fenetre):
    for colonne in range(fenetre.model.columnCount()):
        assert _fond(fenetre, NODEIDS[1], colonne) is not None


def test_a_reader_still_running_is_not_a_disagreement(fenetre):
    fenetre.model.clear_statuses()
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    fenetre.model.apply_outcome(NODEIDS[0], Status.RUNNING, 1)
    assert _fond(fenetre, NODEIDS[0]) is None
    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 1)
    assert _fond(fenetre, NODEIDS[0]) is not None


def test_the_row_repaints_when_it_starts_to_diverge(fenetre):
    fenetre.model.clear_statuses()
    recu = []
    fenetre.model.dataChanged.connect(
        lambda a, b, roles: recu.append((a.column(), b.column(), list(roles))))
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    assert (0, 2, [Qt.BackgroundRole]) in recu


def test_a_single_reader_never_diverges(fenetre):
    fenetre.model.set_readers(LECTEURS[:1])
    assert all(_fond(fenetre, n) is None for n in NODEIDS)


def test_profile_rows_are_tinted_too(qapp):
    from runner.ui.live_profile_model import LiveProfileModel

    modele = LiveProfileModel()
    modele.set_tree(build_tree(NODEIDS[:1]))
    modele.set_readers(LECTEURS)
    [feuille] = modele.ordered_leaves()
    feuille.statuses.update({0: Status.PASSED, 1: Status.FAILED})
    index = modele.createIndex(feuille.row, 2, feuille)
    assert modele.data(index, Qt.BackgroundRole) is not None


# ----------------------------------------------------------------- boutons

def test_the_differences_button_appears_only_when_readers_disagree(fenetre):
    fenetre._show_failure_actions([])
    assert not fenetre.view_differences_button.isHidden()

    fenetre.model.clear_statuses()
    for nodeid in NODEIDS:
        for lecteur in LECTEURS:
            fenetre.model.apply_outcome(nodeid, Status.PASSED, lecteur.index)
    fenetre._show_failure_actions([])
    assert fenetre.view_differences_button.isHidden()


def test_each_click_goes_to_the_next_difference_and_wraps(fenetre):
    vus = []
    for _ in range(3):
        fenetre.view_differences_button.click()
        vus.append(_courant(fenetre))
    assert vus == ["test_b", "test_d", "test_b"]


def test_each_click_goes_to_the_next_failure_and_wraps(fenetre):
    vus = []
    for _ in range(3):
        fenetre.view_failures_button.click()
        vus.append(_courant(fenetre))
    assert vus == ["test_b", "test_c", "test_b"]


def test_navigation_starts_after_the_selected_test(fenetre):
    fenetre.tree.setCurrentIndex(fenetre.model.index_for_nodeid(NODEIDS[2]))
    fenetre.view_differences_button.click()
    assert _courant(fenetre) == "test_d"
    fenetre.tree.setCurrentIndex(fenetre.model.index_for_nodeid(NODEIDS[2]))
    fenetre.view_failures_button.click()
    assert _courant(fenetre) == "test_b"


def test_the_tint_is_really_painted_despite_the_stylesheet(fenetre, qapp):
    """La regle `QTreeView::item` de la feuille de style fait ignorer le
    BackgroundRole : sans le delegate, la teinte n'apparait jamais."""
    fenetre.resize(1200, 700)
    fenetre.show()
    fenetre.tree.expandAll()
    qapp.processEvents()
    image = fenetre.tree.viewport().grab().toImage()

    def pixel(nodeid):
        rect = fenetre.tree.visualRect(fenetre.model.index_for_nodeid(nodeid))
        return image.pixelColor(rect.right() - 20, rect.center().y())

    assert pixel(NODEIDS[1]) != pixel(NODEIDS[0])  # b diverge, a non
