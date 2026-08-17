"""Filtrer l'arbre par statut, et compter ce qui reste a passer.

Deux choses que l'ancienne interface avait et que la refonte avait perdues :
cliquer « 44 failed » pour ne voir que ces 44, et savoir combien de tests
restent pendant qu'un run avance.
"""

from __future__ import annotations

import textwrap

import pytest
from PyQt5.QtCore import QModelIndex

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
    "suite/perso/test_cert.py::test_chr",
    "suite/perso/test_cert.py::test_slot",
]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    w = MainWindow()
    w.workspace = Workspace.load(str(tmp_path))
    w.model.set_tree(build_tree(NODEIDS))
    w.model.set_readers((Reader("Reader A", 0),))
    w.left_stack.setCurrentWidget(w.tree)
    w.tree.expandAll()
    return w


def _feuilles_visibles(w) -> list[str]:
    """Noms des tests que l'arbre montre encore."""
    trouves: list[str] = []

    def descendre(parent):
        for ligne in range(w.model.rowCount(parent)):
            if w.tree.isRowHidden(ligne, parent):
                continue
            index = w.model.index(ligne, 0, parent)
            if index.internalPointer().is_leaf:
                trouves.append(w.model.data(index))
            descendre(index)

    descendre(QModelIndex())
    return trouves


@pytest.fixture
def joue(fenetre):
    """Un run fictif : deux verts, un rouge, un saute."""
    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    fenetre.model.apply_outcome(NODEIDS[1], Status.FAILED, 0)
    fenetre.model.apply_outcome(NODEIDS[2], Status.PASSED, 0)
    fenetre.model.apply_outcome(NODEIDS[3], Status.SKIPPED, 0)
    for statut, pastille in fenetre.pills.items():
        pastille.set_value(sum(
            1 for n in NODEIDS
            if fenetre.model.statuses_for_nodeid(n).get(0) is statut))
    return fenetre


# =========================================================================
# Le filtre
# =========================================================================


def test_everything_shows_before_any_filter(joue):
    assert len(_feuilles_visibles(joue)) == 4


def test_clicking_a_pill_keeps_only_that_status(joue):
    joue.filter_by_status(Status.FAILED)
    assert _feuilles_visibles(joue) == ["test_aid"]


def test_the_parents_of_a_kept_test_stay_visible(joue):
    """Masquer le dossier couperait le chemin vers le test : l'arbre n'aurait
    plus de racine a montrer."""
    joue.filter_by_status(Status.FAILED)

    noms = []

    def descendre(parent):
        for ligne in range(joue.model.rowCount(parent)):
            if joue.tree.isRowHidden(ligne, parent):
                continue
            index = joue.model.index(ligne, 0, parent)
            noms.append(joue.model.data(index))
            descendre(index)

    descendre(QModelIndex())
    assert "suite" in noms and "apdu" in noms and "test_select.py" in noms


def test_a_branch_without_a_match_is_hidden(joue):
    """`perso` n'a aucun echec : il n'a rien a faire a l'ecran."""
    joue.filter_by_status(Status.FAILED)

    noms = []

    def descendre(parent):
        for ligne in range(joue.model.rowCount(parent)):
            if joue.tree.isRowHidden(ligne, parent):
                continue
            index = joue.model.index(ligne, 0, parent)
            noms.append(joue.model.data(index))
            descendre(index)

    descendre(QModelIndex())
    assert "perso" not in noms


def test_clicking_the_same_pill_again_shows_everything(joue):
    """Le filtre est une bascule : le meme geste le pose et le retire."""
    joue.filter_by_status(Status.FAILED)
    joue.filter_by_status(Status.FAILED)

    assert len(_feuilles_visibles(joue)) == 4
    assert joue._status_filter is None


def test_switching_to_another_pill_replaces_the_filter(joue):
    joue.filter_by_status(Status.FAILED)
    joue.filter_by_status(Status.SKIPPED)

    assert _feuilles_visibles(joue) == ["test_slot"]
    assert not joue.pills[Status.FAILED].is_active()
    assert joue.pills[Status.SKIPPED].is_active()


def test_the_active_pill_says_which_filter_is_on(joue):
    joue.filter_by_status(Status.PASSED)
    assert joue.pills[Status.PASSED].is_active()
    assert "passed" in joue.status_label.text().lower()


def test_a_pill_at_zero_cannot_be_clicked(fenetre):
    """Filtrer sur un statut qu'aucun test ne porte viderait l'arbre sans
    rien apprendre."""
    recus = []
    pastille = fenetre.pills[Status.ERROR]
    pastille.clicked.connect(recus.append)
    pastille.set_value(0)

    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtGui import QMouseEvent

    event = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(2, 2),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pastille.mousePressEvent(event)
    assert recus == []


def test_a_pill_with_results_emits_its_status(joue):
    recus = []
    pastille = joue.pills[Status.FAILED]
    pastille.clicked.connect(recus.append)

    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtGui import QMouseEvent

    event = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(2, 2),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    pastille.mousePressEvent(event)
    assert recus == [Status.FAILED]


# =========================================================================
# Le filtre ne doit pas survivre a un changement de contexte
# =========================================================================


def test_a_new_run_drops_the_filter(joue):
    """Un filtre pose sur le run precedent masquerait les resultats du
    nouveau au fur et a mesure qu'ils arrivent."""
    from runner.domain.models import RunRequest

    joue.filter_by_status(Status.FAILED)
    assert len(_feuilles_visibles(joue)) == 1

    joue._on_run_started(RunRequest(workspace="/w", interpreter="python",
                                    nodeids=tuple(NODEIDS), readers=()))

    assert joue._status_filter is None
    assert len(_feuilles_visibles(joue)) == 4


def test_a_new_collection_drops_the_filter(joue):
    from runner.domain.execution import Collection

    joue.filter_by_status(Status.FAILED)
    joue._on_collected(Collection(tuple(NODEIDS)))

    assert joue._status_filter is None
    assert not any(p.is_active() for p in joue.pills.values())


# =========================================================================
# Le compteur des tests restants
# =========================================================================


def test_the_remaining_counter_starts_at_the_total(fenetre):
    from runner.domain.models import RunRequest

    requete = RunRequest(workspace="/w", interpreter="python",
                         nodeids=tuple(NODEIDS),
                         readers=(Reader("A", 0), Reader("B", 1)))
    fenetre._on_run_started(requete)

    # Quatre tests sur deux lecteurs : huit passages a faire.
    assert fenetre.remaining_pill.value() == 8
    assert not fenetre.remaining_pill.isHidden()


def test_the_remaining_counter_goes_down(fenetre):
    fenetre._on_progress(3, 10)
    assert fenetre.remaining_pill.value() == 7
    fenetre._on_progress(9, 10)
    assert fenetre.remaining_pill.value() == 1


def test_the_remaining_counter_never_goes_negative(fenetre):
    fenetre._on_progress(12, 10)
    assert fenetre.remaining_pill.value() == 0


def test_the_remaining_counter_disappears_when_the_run_ends(fenetre):
    from runner.domain.models import RunRequest

    fenetre._on_run_started(RunRequest(workspace="/w", interpreter="python",
                                       nodeids=tuple(NODEIDS), readers=()))
    assert not fenetre.remaining_pill.isHidden()

    fenetre._on_run_finished([])
    assert fenetre.remaining_pill.isHidden()


def test_the_remaining_counter_is_hidden_before_any_run(fenetre):
    """Un « 0 left » affiche en permanence sur une fenetre qui n'a rien lance
    ne veut rien dire."""
    assert fenetre.remaining_pill.isHidden()
