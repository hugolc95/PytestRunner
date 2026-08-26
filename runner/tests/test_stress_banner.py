"""Le bandeau de stress-test : cache au repos, une couleur par etat."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt

from runner.ui.widgets import StressBanner


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_hidden_until_something_is_shown(qapp):
    bandeau = StressBanner()
    assert not bandeau.isVisible()


def test_the_background_color_is_forced_to_paint_from_the_stylesheet(qapp):
    """Le bug reel rapporte : un QWidget nu ignore `background-color` sous le
    style natif Windows tant que cet attribut n'est pas pose -- ca passait
    par chance ailleurs, pas la. Sans lui, la pastille reste transparente
    quel que soit l'etat."""
    bandeau = StressBanner()
    assert bandeau.testAttribute(Qt.WA_StyledBackground)


def test_running_and_failed_and_done_each_set_a_real_stylesheet(qapp):
    """Les trois etats doivent vraiment poser un style -- pas juste changer
    le texte pendant qu'une pastille grise reste affichee partout."""
    bandeau = StressBanner()

    bandeau.show_running("Stress 1/50")
    style_running = bandeau.styleSheet()
    assert style_running

    bandeau.show_failed("Failed 8/50")
    style_failed = bandeau.styleSheet()
    assert style_failed and style_failed != style_running

    bandeau.show_done("50/50 · 100%")
    style_done = bandeau.styleSheet()
    assert style_done and style_done != style_failed


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


def test_the_visible_label_stays_short_the_detail_goes_in_the_tooltip(qapp):
    """La pastille vit dans l'espace vide a droite de la barre Run -- le nom
    complet du test n'y tiendrait pas. Il doit rester accessible, mais dans
    l'infobulle, pas dans le texte visible."""
    bandeau = StressBanner()
    bandeau.show_running("Stress 3/50",
                         "Stress-testing test_login_timeout_retries — attempt 3 of 50")

    assert bandeau._texte.text() == "Stress 3/50"
    assert "test_login_timeout_retries" in bandeau.toolTip()
    assert "test_login_timeout_retries" not in bandeau._texte.text()


def test_the_tooltip_falls_back_to_the_visible_text_without_a_detail(qapp):
    bandeau = StressBanner()
    bandeau.show_done("50/50 · 100%")

    assert bandeau.toolTip() == "50/50 · 100%"
