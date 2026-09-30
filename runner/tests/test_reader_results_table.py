"""Verdict d'un test dans Detail : une ligne par lecteur.

Avant, une rangee unique alignait une case par lecteur, une case duree et une
case d'historique par lecteur : a 4 lecteurs aux noms longs, le panneau
exigeait plus de 3000 px et la fenetre ne se reduisait plus.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from runner.domain.models import Reader, Status
from runner.ui.detail_panel import DetailPanel, ReaderResultsTable

NODEID = "testSuite1/test_api.py::test_login[user]"
READERS = tuple(Reader(f"OnmikeyCardman 3x21 Reader {i}", i) for i in range(4))
STATUTS = {0: Status.FAILED, 1: Status.FAILED, 2: Status.PASSED, 3: Status.FAILED}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _panneau(qapp, durations=None, recent_runs=None):
    panneau = DetailPanel()
    panneau.show_test(NODEID, READERS, STATUTS, {}, durations=durations,
                      recent_runs=recent_runs)
    panneau.show()
    qapp.processEvents()
    return panneau


def _entetes(panneau):
    table = panneau.results_row
    return [l.text() for l in table.findChildren(QLabel, "StatCellLabel")
            if l.isVisibleTo(table)]


def _largeur_min(qapp, readers):
    panneau = DetailPanel()
    panneau.show_test(NODEID, readers, {r.index: Status.FAILED for r in readers}, {},
                      durations={r.index: 0.1 for r in readers},
                      recent_runs={r.index: [True, False] * 3 for r in readers})
    # Le tableau lui-meme : un panneau jamais affiche ne recalcule pas le
    # minimum de ses pages.
    return panneau.results_row.minimumSizeHint().width()


def test_more_readers_do_not_make_the_panel_wider(qapp):
    quatre = _largeur_min(qapp, READERS)
    huit = _largeur_min(qapp, tuple(Reader(f"OnmikeyCardman 3x21 Reader {i}", i) for i in range(8)))
    assert huit == quatre
    assert quatre < 400


def test_a_very_long_reader_name_does_not_widen_the_panel(qapp):
    long_nom = (Reader("HubReader " + "Very Long Secure Element Reader Name " * 4, 0),)
    assert _largeur_min(qapp, long_nom) == _largeur_min(qapp, (Reader("R", 0),))


def test_one_row_per_reader_with_its_full_name(qapp):
    panneau = _panneau(qapp)
    noms = [l.toolTip() for l in panneau.results_row.findChildren(QLabel)
            if l.toolTip().startswith("OnmikeyCardman")]
    assert noms == [r.name for r in READERS]
    verdicts = panneau.results_row.findChildren(QLabel, "ReaderVerdict_failed")
    assert len(verdicts) == 3
    assert len(panneau.results_row.findChildren(QLabel, "ReaderVerdict_passed")) == 1


def test_columns_only_appear_when_there_is_something_to_show(qapp):
    assert _entetes(_panneau(qapp)) == ["READER", "RESULT"]
    complet = _panneau(qapp, durations={0: 0.12}, recent_runs={1: [True, False]})
    complet.resize(900, 500)
    qapp.processEvents()
    assert _entetes(complet) == ["READER", "RESULT", "DURATION", "LAST RUNS"]


def test_a_narrow_panel_drops_the_duration_column(qapp):
    panneau = _panneau(qapp, durations={i: 0.1 for i in range(4)})
    table = panneau.results_row
    panneau.resize(ReaderResultsTable.ETROIT + 150, 500)
    qapp.processEvents()
    assert "DURATION" in _entetes(panneau)
    panneau.resize(ReaderResultsTable.ETROIT - 100, 500)
    qapp.processEvents()
    assert table.width() < ReaderResultsTable.ETROIT
    assert "DURATION" not in _entetes(panneau)


def test_a_reader_without_name_still_gets_a_row(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})
    assert any(l.toolTip() == "Test interpreter"
               for l in panneau.results_row.findChildren(QLabel))


def test_showing_another_test_replaces_the_rows(qapp):
    panneau = _panneau(qapp)
    panneau.show_test("t.py::other", READERS[:1], {0: Status.PASSED}, {})
    qapp.processEvents()
    visibles = [l for l in panneau.results_row.findChildren(QLabel)
                if l.toolTip().startswith("OnmikeyCardman")
                and l.isVisibleTo(panneau.results_row)]
    assert len(visibles) == 1


def test_each_reader_name_is_painted_in_its_reader_colour(qapp):
    """Meme couleur que la pastille devant le nom : on relie la ligne a son
    lecteur d'un coup d'oeil, comme dans le panneau Execution."""
    from PySide6.QtGui import QColor

    from runner.ui import tokens as t

    panneau = _panneau(qapp)
    panneau.resize(900, 500)
    qapp.processEvents()
    for lecteur in READERS[:2]:
        [label] = [l for l in panneau.results_row.findChildren(QLabel)
                   if l.toolTip() == lecteur.name]
        image = label.grab().toImage()
        attendu = QColor(t.reader_color(lecteur.index))
        proches = sum(
            max(abs(image.pixelColor(x, y).red() - attendu.red()),
                abs(image.pixelColor(x, y).green() - attendu.green()),
                abs(image.pixelColor(x, y).blue() - attendu.blue())) <= 30
            for x in range(image.width()) for y in range(image.height()))
        assert proches >= 10, f"{lecteur.name} n'est pas peint en {attendu.name()}"
