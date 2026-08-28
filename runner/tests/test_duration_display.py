"""Duree affichee dans le panneau Detail : par test, et agregee par groupe.

La mesure elle-meme est testee dans test_durations.py (parsing) et
test_stress_service.py / test_allure_report.py (le flag sur la commande
reelle) -- ici on verifie seulement que le panneau l'affiche correctement
une fois qu'elle lui est passee.
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader, Status
from runner.ui.detail_panel import DetailPanel

NODEID = "tests/test_x.py::test_slow"


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------- test

def test_a_single_readers_duration_is_shown(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      {0: 0.45})

    assert "0.45s" in panneau._duree_visible


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
