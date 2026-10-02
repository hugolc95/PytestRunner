"""Duree affichee dans le panneau Detail : par test, et agregee par groupe.

La mesure elle-meme est testee dans test_durations.py (parsing) et
test_stress_service.py / test_run_service.py (le flag sur la commande
reelle) -- ici on verifie seulement que le panneau l'affiche correctement
une fois qu'elle lui est passee.
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader, Status
from runner.domain.duration import format_duration
from runner.ui.detail_panel import DetailPanel

NODEID = "tests/test_x.py::test_slow"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------- test

@pytest.mark.parametrize("seconds, expected", [
    (0.45, "0.45s"), (65.25, "1 min 5.25s"),
    (3661.5, "1 h 1 min 1.5s"),
])
def test_a_single_readers_duration_is_shown(qapp, seconds, expected):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      {0: seconds})

    assert expected in panneau._duree_visible
    from PySide6.QtWidgets import QLabel
    assert expected in [label.text() for label in panneau.findChildren(QLabel)]


@pytest.mark.parametrize("seconds, precision, expected", [
    (0, 0, "0s"), (0.45, 2, "0.45s"), (59.94, 1, "59.9s"),
    (59.99, 1, "1 min 0s"), (60, 0, "1 min 0s"),
    (3599.99, 1, "1 h 0 min 0s"), (3665, 0, "1 h 1 min 5s"),
    (90061, 1, "25 h 1 min 1s"), (None, 1, "—"),
    (float("nan"), 1, "—"),
])
def test_duration_units_and_rounding(seconds, precision, expected):
    assert format_duration(seconds, precision) == expected


def test_long_run_duration_in_history_and_html(qapp, tmp_path):
    from runner.domain.history import History, RunEntry
    from runner.domain import report
    from runner.ui.history_dashboard import HistoryWindow
    from PySide6.QtWidgets import QLabel

    history = History(tmp_path)
    entry = history.add(RunEntry(id="long", timestamp=1, workspace="/w",
                                 duration=3665, counts={"PASSED": 1}))
    window = HistoryWindow(history)
    expected = "1 h 1 min 5s"
    assert expected in window.detail_meta.text()
    assert expected in [label.text() for _, card in window._cards
                        for label in card.findChildren(QLabel)]
    assert window.details_table.item(0, 5).text() == expected
    target = tmp_path / "report.html"
    ok, message = report.write_html(entry, target, "")
    assert ok, message
    assert expected in target.read_text()


def test_each_readers_duration_is_labelled_when_there_are_several(qapp):
    lecteurs = (Reader("Reader A", 0), Reader("Reader B", 1))
    panneau = DetailPanel()
    panneau.show_test(NODEID, lecteurs,
                      {0: Status.PASSED, 1: Status.PASSED}, {0: None, 1: None},
                      {0: 0.45, 1: 1.2})

    assert "Reader A: 0.45s" in panneau._duree_visible
    assert "Reader B: 1.20s" in panneau._duree_visible


def test_an_unknown_duration_shows_nothing_not_a_fake_zero(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None}, {0: None})

    assert panneau._duree_visible == ""


def test_missing_durations_argument_does_not_crash(qapp):
    """L'appelant historique ne passait rien -- doit rester valide."""
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})


# -------------------------------------------------------------------- groupe

def test_group_total_duration_is_appended_to_the_count(qapp):
    panneau = DetailPanel()
    panneau.show_group("suite/apdu", "test_select.py", (Reader("", 0),),
                       {0: {Status.PASSED: 3}}, [], {0: 4.2})

    assert "4.20s" in panneau.group_total.text()


def test_group_without_any_known_duration_shows_only_the_count(qapp):
    panneau = DetailPanel()
    panneau.show_group("suite/apdu", "test_select.py", (Reader("", 0),),
                       {0: {Status.PASSED: 3}}, [], {0: None})

    assert "·" not in panneau.group_total.text()
    assert "3 test" in panneau.group_total.text()


def test_restyle_keeps_the_duration_after_a_theme_change(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None}, {0: 0.45})

    panneau.restyle()

    assert "0.45s" in panneau._duree_visible
