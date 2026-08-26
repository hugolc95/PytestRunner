"""Le label de statut passe en "vivant" (couleur pleine, gras) pendant un
run -- normal ou stress-test -- et revient au gris attenue une fois fini.

Meme mecanique pour les deux : avant, seul le stress-test avait un widget
dedie pour ca (un bandeau a part, mal place). Desormais le meme label sert
les deux, qu'on lance une selection classique, un filtre par marker, ou
"Run until it fails" / "Run N times".
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader, RunRequest

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _requete(**kwargs) -> RunRequest:
    base = dict(workspace="/w", interpreter="python",
               nodeids=tuple(NODEIDS), readers=(Reader("", 0),))
    base.update(kwargs)
    return RunRequest(**base)


def test_a_classic_run_turns_the_status_label_live(fenetre):
    """Qu'on lance une selection de tests cochee a la main, ou un sous-
    ensemble filtre par marker, le chemin est le meme : `_on_run_started`."""
    fenetre._on_run_started(_requete())

    assert fenetre.status_label.styleSheet()
    assert "running" in fenetre.status_label.text().lower()


def test_finishing_a_classic_run_returns_to_the_idle_style(fenetre):
    fenetre._on_run_started(_requete())
    assert fenetre.status_label.styleSheet()

    fenetre._on_run_finished([])

    assert fenetre.status_label.styleSheet() == ""


def test_progress_ticks_stay_in_the_live_style(fenetre):
    fenetre._on_run_started(_requete())
    style_au_depart = fenetre.status_label.styleSheet()

    fenetre._on_progress(1, 2)

    assert fenetre.status_label.styleSheet() == style_au_depart
    assert "running" in fenetre.status_label.text().lower()
