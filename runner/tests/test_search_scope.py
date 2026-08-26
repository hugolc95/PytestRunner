"""Le champ de recherche a deux portees : par nom de test, ou dans les
traces d'echec. Un seul champ, un seul compteur -- seule la portee change.
"""

from __future__ import annotations

import pytest

from runner.ui.widgets import SCOPE_FAILURES, SCOPE_TESTS, SearchBar


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_starts_in_the_tests_scope(qapp):
    barre = SearchBar()
    assert barre.scope == SCOPE_TESTS
    assert barre.tests_button.isChecked()
    assert not barre.failures_button.isChecked()


def test_clicking_in_failures_switches_the_scope_and_placeholder(qapp):
    barre = SearchBar()
    barre.failures_button.click()

    assert barre.scope == SCOPE_FAILURES
    assert "failure" in barre.field.placeholderText().lower()


def test_switching_scope_emits_the_new_scope(qapp):
    barre = SearchBar()
    vus = []
    barre.scope_changed.connect(vus.append)

    barre.failures_button.click()

    assert vus == [SCOPE_FAILURES]


def test_switching_scope_clears_whatever_was_typed(qapp):
    barre = SearchBar()
    barre.field.setText("test_login")

    barre.failures_button.click()

    assert barre.field.text() == ""


def test_switching_back_to_tests_restores_the_original_placeholder(qapp):
    barre = SearchBar()
    barre.failures_button.click()
    barre.tests_button.click()

    assert barre.scope == SCOPE_TESTS
    assert barre.field.placeholderText() == "Find a test…"


def test_clicking_the_already_active_scope_does_nothing(qapp):
    barre = SearchBar()
    barre.field.setText("keep me")
    vus = []
    barre.scope_changed.connect(vus.append)

    barre.tests_button.click()

    assert barre.field.text() == "keep me"
    assert vus == []
