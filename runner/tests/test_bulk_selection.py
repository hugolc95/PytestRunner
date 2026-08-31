"""Cocher beaucoup de tests d'un coup : marker filter et « divergents ».

Les deux gestes cochaient un par un via `setData()`, qui rappelle
`_emit_selection()` -- un recomptage de TOUT l'arbre -- a CHAQUE nodeid. Sur
une suite de plusieurs milliers de tests et un marker qui en retient des
centaines, ca gele l'interface. `set_checked_nodeids()` (voir
`test_tree_model.py`) fait le meme recomptage une seule fois ; ce qui suit
verifie que les deux appelants s'en servent bien, avec le meme resultat
qu'avant.
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree

NODEIDS = [
    "suite/test_a.py::test_slow_one",
    "suite/test_a.py::test_fast",
    "suite/test_b.py::test_slow_two",
]
LECTEURS = (Reader("Reader A", 0), Reader("Reader B", 1))


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
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


# ------------------------------------------------------- le filtre par marker

def test_the_marker_filter_checks_exactly_the_matches(fenetre, monkeypatch):
    fenetre._markers_by_nodeid = {
        NODEIDS[0]: ("slow",),
        NODEIDS[1]: (),
        NODEIDS[2]: ("slow",),
    }
    monkeypatch.setattr(fenetre.markers, "matcher",
                        lambda: (lambda noms: "slow" in noms))
    monkeypatch.setattr(fenetre.markers, "expression", lambda: "slow")

    fenetre._on_marker_filter()

    assert set(fenetre.model.checked_nodeids()) == {NODEIDS[0], NODEIDS[2]}


def test_the_marker_filter_announces_the_selection_only_once(fenetre, monkeypatch):
    fenetre._markers_by_nodeid = {n: ("slow",) for n in NODEIDS}
    monkeypatch.setattr(fenetre.markers, "matcher", lambda: (lambda noms: True))
    monkeypatch.setattr(fenetre.markers, "expression", lambda: "slow")

    recu = []
    fenetre.model.selection_changed.connect(lambda c, t: recu.append((c, t)))
    fenetre._on_marker_filter()

    assert len(recu) == 2  # `set_all_checked(False)` puis le recomptage final
    assert recu[-1] == (3, 3)


# --------------------------------------------------------- les divergents

@pytest.fixture
def avec_lecteurs(fenetre):
    fenetre.model.set_readers(LECTEURS)
    fenetre.results.set_readers(LECTEURS)
    for nodeid in NODEIDS:
        for lecteur in LECTEURS:
            fenetre.model.apply_outcome(nodeid, Status.PASSED, lecteur.index)
    # Un seul nodeid divergent : les deux lecteurs ne s'accordent que sur lui.
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    return fenetre


def test_select_divergent_checks_exactly_the_disagreements(avec_lecteurs):
    avec_lecteurs.select_divergent()

    assert avec_lecteurs.model.checked_nodeids() == [NODEIDS[0]]


def test_select_divergent_announces_the_selection_only_once(avec_lecteurs):
    recu = []
    avec_lecteurs.model.selection_changed.connect(lambda c, t: recu.append((c, t)))
    avec_lecteurs.select_divergent()

    assert len(recu) == 2
    assert recu[-1] == (1, 3)
