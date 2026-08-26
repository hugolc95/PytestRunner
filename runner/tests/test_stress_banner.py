"""Le bandeau de stress-test : cache au repos, une couleur par etat."""

from __future__ import annotations

import pytest

from runner.ui.widgets import StressBanner


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_hidden_until_something_is_shown(qapp):
    bandeau = StressBanner()
    assert not bandeau.isVisible()


def test_running_shows_a_stop_button_not_a_dismiss(qapp):
    bandeau = StressBanner()
    bandeau.show_running("Stress-testing test_x", "attempt 3 of 50")

    assert bandeau.isVisible()
    assert bandeau.stop_button.isVisible()
    assert not bandeau.dismiss_button.isVisible()


def test_failed_shows_a_dismiss_button_not_stop(qapp):
    bandeau = StressBanner()
    bandeau.show_failed("Stopped — test_x failed", "attempt 8 of 50")

    assert not bandeau.stop_button.isVisible()
    assert bandeau.dismiss_button.isVisible()


def test_clicking_dismiss_hides_the_banner_and_emits(qapp):
    bandeau = StressBanner()
    bandeau.show_done("20 of 20 runs complete", "18 passed · 2 failed")

    emis = []
    bandeau.dismissed.connect(lambda: emis.append(True))
    bandeau.dismiss_button.click()

    assert not bandeau.isVisible()
    assert emis == [True]


def test_clicking_stop_emits_without_hiding(qapp):
    bandeau = StressBanner()
    bandeau.show_running("Stress-testing test_x", "attempt 3 of 50")

    emis = []
    bandeau.stop_clicked.connect(lambda: emis.append(True))
    bandeau.stop_button.click()

    assert emis == [True]
