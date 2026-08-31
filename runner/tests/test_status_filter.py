"""Filtrer l'arbre par statut, et compter ce qui reste a passer.

Deux choses que l'ancienne interface avait et que la refonte avait perdues :
cliquer « 44 failed » pour ne voir que ces 44, et savoir combien de tests
restent pendant qu'un run avance.
"""

from __future__ import annotations

import textwrap

import pytest
from PySide6.QtCore import QModelIndex, Qt

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
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PySide6.QtCore import QSettings

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
    fenetre._rafraichir_compteurs()
    return fenetre


# =========================================================================
# Emplacement des compteurs
# =========================================================================


def test_the_pills_live_in_the_workspace_bar_not_the_status_bar(fenetre):
    """Les verdicts vivent desormais, plus grands, dans l'espace vide de la
    barre du workspace -- plus question de les repeter en plus petit tout en
    bas, ce qui affichait deux fois le meme chiffre."""
    barre_workspace = fenetre.workspace_combo.parentWidget().layout()
    for pastille in fenetre.pills.values():
        assert barre_workspace.indexOf(pastille) >= 0

    for pastille in fenetre.pills.values():
        assert pastille.parentWidget() is not fenetre.statusBar()


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


def test_the_active_pill_actually_looks_different(joue):
    """Le badge, pas seulement le drapeau : sinon rien a l'ecran ne dit quel
    filtre est en cours."""
    pastille = joue.pills[Status.PASSED]
    repos = pastille.styleSheet()

    joue.filter_by_status(Status.PASSED)

    assert pastille.styleSheet() != repos


def test_a_pill_defines_its_own_hover_style(joue):
    """Sans une regle `:hover` explicite, le style natif de Windows dessine
    son propre relief au survol -- un rectangle sombre par-dessus le fond
    clair du badge, illisible en theme clair."""
    pastille = joue.pills[Status.FAILED]

    assert "QPushButton:hover" in pastille.styleSheet()


def test_a_pill_at_zero_cannot_be_clicked(fenetre):
    """Filtrer sur un statut qu'aucun test ne porte viderait l'arbre sans
    rien apprendre."""
    recus = []
    pastille = fenetre.pills[Status.ERROR]
    pastille.filter_clicked.connect(recus.append)
    pastille.set_value(0)

    pastille.click()

    assert recus == []


def test_the_compass_ring_reflects_the_same_counts_as_the_pills(joue):
    """L'anneau et les pastilles lisent le meme etat -- pas question qu'ils
    divergent apres un run."""
    for statut, pastille in joue.pills.items():
        assert f"{pastille.value()} {statut.label.lower()}" in joue.compass_ring.toolTip()


def test_the_compass_percentage_matches_the_passed_share(joue):
    total = sum(p.value() for p in joue.pills.values())
    attendu = round(100 * joue.pills[Status.PASSED].value() / total)
    assert joue.compass_pct.text() == f"{attendu}%"


def test_a_pill_with_results_emits_its_status(joue):
    recus = []
    pastille = joue.pills[Status.FAILED]
    pastille.filter_clicked.connect(recus.append)

    pastille.click()

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


def _lancer(fenetre, *readers):
    from runner.domain.models import RunRequest

    fenetre._on_run_started(RunRequest(
        workspace="/w", interpreter="python", nodeids=tuple(NODEIDS),
        readers=readers))


def test_the_remaining_counter_goes_down(fenetre):
    """Il suit l'ARBRE, pas le nombre de signaux recus.

    Il se deduisait de l'argument du signal d'avancement, lui-meme une somme
    de resultats recus. Deux verdicts pour un meme test -- un rejeu, une
    erreur de setup suivie d'un verdict -- et le compteur avancait deux fois.
    """
    # Un run precedent a laisse ses resultats : le nouveau doit repartir du
    # total. Sur un arbre deja vierge, oublier de remettre le decompte a zero
    # ne se serait pas vu.
    for nodeid in NODEIDS:
        fenetre.model.apply_outcome(nodeid, Status.PASSED, 0)

    _lancer(fenetre, Reader("A", 0))
    assert fenetre.remaining_pill.value() == 4
    assert fenetre.pills[Status.PASSED].value() == 0

    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    fenetre._on_progress(1, 4)
    assert fenetre.remaining_pill.value() == 3

    fenetre.model.apply_outcome(NODEIDS[1], Status.FAILED, 0)
    fenetre._on_progress(2, 4)
    assert fenetre.remaining_pill.value() == 2


def test_the_same_test_reported_twice_counts_once(fenetre):
    """Le cas qui faisait deriver les compteurs."""
    _lancer(fenetre, Reader("A", 0))

    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    fenetre._on_progress(1, 4)
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    fenetre._on_progress(2, 4)

    assert fenetre.remaining_pill.value() == 3
    assert fenetre.pills[Status.FAILED].value() == 1


def test_a_verdict_that_changes_moves_from_one_pill_to_the_other(fenetre):
    """Une erreur de setup suivie d'un verdict : la case change de statut, elle
    ne s'ajoute pas."""
    _lancer(fenetre, Reader("A", 0))

    fenetre.model.apply_outcome(NODEIDS[0], Status.ERROR, 0)
    fenetre._on_progress(1, 4)
    assert fenetre.pills[Status.ERROR].value() == 1

    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    fenetre._on_progress(2, 4)

    assert fenetre.pills[Status.ERROR].value() == 0
    assert fenetre.pills[Status.PASSED].value() == 1
    assert fenetre.remaining_pill.value() == 3


def test_the_remaining_counter_never_goes_negative(fenetre):
    """Plus de resultats que de passages prevus : le run declare un lecteur,
    la suite en rapporte deux. Un « -4 left » se lirait comme un bug."""
    _lancer(fenetre, Reader("A", 0))
    for nodeid in NODEIDS:
        for index in (0, 1):
            fenetre.model.apply_outcome(nodeid, Status.PASSED, index)
    fenetre._on_progress(8, 4)

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
