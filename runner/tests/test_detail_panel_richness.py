"""Le panneau Detail d'un test, enrichi : le nodeid complet et copiable, les
markers, et -- pour un test qui passe -- au moins la derniere execution et sa
mini-tendance, plutot qu'une seule phrase grise perdue dans un grand vide.
"""

from __future__ import annotations

import time

import pytest

from runner.domain.models import Reader, Status
from runner.ui.detail_panel import DetailPanel

NODEID = "tests/test_authentication.py::test_login_valid_credentials"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------- nodeid

def test_the_full_nodeid_is_shown(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})

    assert panneau.nodeid_label.text() == NODEID


def test_the_copy_button_puts_the_nodeid_on_the_clipboard(qapp):
    from PySide6.QtWidgets import QApplication

    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})

    panneau.copy_nodeid_button.click()

    assert QApplication.clipboard().text() == NODEID


# ------------------------------------------------------------------ markers

def test_markers_show_as_chips(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      markers=("smoke", "auth"))

    assert not panneau.markers_row.isHidden()
    textes = [panneau._markers_layout.itemAt(i).widget().text()
             for i in range(panneau._markers_layout.count())
             if panneau._markers_layout.itemAt(i).widget() is not None]
    assert textes == ["smoke", "auth"]


def test_no_markers_hides_the_row(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})

    assert panneau.markers_row.isHidden()


# --------------------------------------------------------------- sparklines

def test_a_reader_with_history_gets_a_sparkline(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      recent_runs={0: [True, True, False]})

    assert 0 in panneau._sparklines
    assert panneau._sparklines[0]._runs == (True, True, False)


def test_a_reader_without_history_gets_no_sparkline(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})

    assert panneau._sparklines == {}


# --------------------------------------------------------- carte "ca passe"

def test_a_pass_shows_when_it_last_ran(qapp):
    quand = time.time()
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      last_seen=quand)

    attendu = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(quand))
    assert attendu in panneau.body.toPlainText()


def test_a_pass_with_a_clean_history_does_not_mention_flaky(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      recent_runs={0: [True, True, True]})

    assert "flaky" not in panneau.body.toPlainText().lower()


def test_a_pass_with_a_failure_in_its_history_is_flagged_flaky(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      recent_runs={0: [True, False, True]})

    corps = panneau.body.toPlainText().lower()
    assert "flaky 1 time in the last 3 runs" in corps


def test_a_pass_without_any_history_shows_no_sub_line(qapp):
    """Ni date ni tendance connues : la carte reste simple, sans rien inventer."""
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None})

    assert "Passed on the last run." in panneau.body.toPlainText()
    assert "Last run:" not in panneau.body.toPlainText()


# --------------------------------------------------------------------- restyle

def test_restyle_keeps_the_nodeid_markers_and_sparkline(qapp):
    panneau = DetailPanel()
    panneau.show_test(NODEID, (Reader("", 0),), {0: Status.PASSED}, {0: None},
                      markers=("smoke",), recent_runs={0: [True, False]})

    panneau.restyle()

    assert panneau.nodeid_label.text() == NODEID
    assert not panneau.markers_row.isHidden()
    assert 0 in panneau._sparklines
