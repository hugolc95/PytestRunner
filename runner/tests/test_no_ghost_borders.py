"""Un `setStyleSheet()` pose directement sur un label assez imbrique dans la
mise en page (une carte, dans une rangee, dans un panneau, dans la fenetre)
fait dessiner a Qt un contour fantome autour de la ligne de mise en page qui
le contient -- meme avec une seule regle de couleur, sans rapport avec ce
qu'elle dit. READER A, PASSED, la duree et le "Running…" du bas en portaient
chacun un, en plus de la carte qui les entoure deja.

Reproduit et confirme (sous Fusion ET sous le style Windows) via des scripts
autonomes hors pytest -- voir la discussion pour le detail. A l'interieur du
harnais pytest, la reproduction au pixel s'est averee peu fiable (marges,
voisins d'une autre couleur, arrondi d'un badge trop court, et le
declenchement lui-meme sensible a l'ordre d'execution des tests). Le test
precis et stable est donc celui du MECANISME du correctif : ces labels ne
posent plus jamais leur propre feuille de style, ils s'appuient sur une
regle globale posee par nom d'objet (voir `QLabel#StatCellLabel`,
`#ReaderVerdict_*`, `#StatusLive` dans theme.py).
"""

from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QApplication, QLabel

from runner.domain.models import Reader, RunRequest, Status
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace

NODEIDS = ["suite/test_a.py::test_un"]


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
    f.model.set_readers((Reader("Reader A", 0),))
    f.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    f.left_stack.setCurrentWidget(f.tree)
    index = f.model.index_for_nodeid(NODEIDS[0])
    f._select_test(index)
    f.resize(1200, 800)
    f.show()
    qapp.processEvents()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def test_the_reader_label_never_gets_its_own_stylesheet(fenetre):
    label = fenetre.results.detail.findChild(QLabel, "StatCellLabel")
    assert label is not None
    assert label.styleSheet() == ""


def test_the_verdict_text_never_gets_its_own_stylesheet(fenetre):
    label = fenetre.results.detail.findChild(QLabel, "ReaderVerdict_passed")
    assert label is not None
    assert label.styleSheet() == ""


def test_the_live_status_label_never_gets_its_own_stylesheet(fenetre, qapp):
    fenetre._on_run_started(RunRequest(
        workspace="/w", interpreter="python", nodeids=tuple(NODEIDS),
        readers=(Reader("Reader A", 0),)))
    qapp.processEvents()

    assert fenetre.status_label.objectName() == "StatusLive"
    assert fenetre.status_label.styleSheet() == ""

    fenetre._on_run_finished([])

    assert fenetre.status_label.objectName() == "Muted"
    assert fenetre.status_label.styleSheet() == ""
