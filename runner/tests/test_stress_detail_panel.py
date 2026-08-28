"""La fiche du panneau Detail pendant et apres un "Run until it fails" /
"Run N times" : un ruban unique (une seule tentative a la fois, pas un lot),
et -- une fois termine -- une trace qu'on peut choisir parmi les tentatives
en echec.
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.stress import (
    MODE_N_TIMES,
    MODE_UNTIL_FAIL,
    StressAttempt,
    StressReaderResult,
    StressSummary,
)
from runner.ui.detail_panel import DetailPanel

NODEID = "tests/test_authentication.py::test_login_timeout_retries"


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def panneau(qapp):
    # `isVisible()` ne compose qu'avec un ancetre reellement affiche : sans ce
    # `show()`, la liste des tentatives ratees resterait "invisible" aux yeux
    # de Qt meme quand le code l'affiche explicitement.
    p = DetailPanel()
    p.show()
    yield p
    p.close()
    p.deleteLater()


def _sortie_en_echec(message: str = "AssertionError") -> str:
    return (
        "=================================== FAILURES ===================================\n"
        "_________________________ test_login_timeout_retries _________________________\n"
        "    def test_login_timeout_retries():\n"
        ">       assert False\n"
        f"E       {message}\n"
    )


def _tentative_en_echec(number: int, message: str = "AssertionError") -> StressAttempt:
    rapport = ReaderReport(reader=Reader("", 0), output=_sortie_en_echec(message))
    resultat = StressReaderResult(Reader("", 0), rapport, Status.FAILED)
    return StressAttempt(number, Status.FAILED, (resultat,))


def test_running_shows_the_attempt_and_live_counts(panneau):
    panneau.show_stress_running(NODEID, MODE_UNTIL_FAIL, cap=50,
                                ran=6, passed=6, failed_attempts=0)

    assert panneau.stack.currentIndex() == DetailPanel.PAGE_STRESS
    assert "attempt 7 of 50" in panneau.stress_sub.text()
    assert "6" in panneau.stress_counters.text()
    assert not panneau.stress_failures.isVisible()


def test_n_times_running_shows_both_passed_and_failed_live(panneau):
    panneau.show_stress_running(NODEID, MODE_N_TIMES, cap=20,
                                ran=11, passed=9, failed_attempts=2)

    assert "run 12 of 20" in panneau.stress_sub.text()
    assert "9" in panneau.stress_counters.text()
    assert "2" in panneau.stress_counters.text()


def test_until_fail_done_with_a_failure_points_at_the_breaking_attempt(panneau):
    tentative = _tentative_en_echec(8, "TimeoutError")
    resume = StressSummary(mode=MODE_UNTIL_FAIL, cap=50, ran=8, passed=7,
                           failed_attempts=[tentative])

    panneau.show_stress_done(NODEID, resume)

    assert "Attempt 8 of 8" in panneau.stress_sub.text()
    assert panneau.stress_failures.isVisible()
    assert panneau.stress_failures.count() == 1
    assert "TimeoutError" in panneau.stress_body.toPlainText()


def test_until_fail_done_without_ever_failing_hides_the_failed_list(panneau):
    resume = StressSummary(mode=MODE_UNTIL_FAIL, cap=50, ran=50, passed=50)

    panneau.show_stress_done(NODEID, resume)

    assert "Never failed in 50 attempts" in panneau.stress_sub.text()
    assert not panneau.stress_failures.isVisible()


def test_n_times_done_shows_the_pass_rate_and_lets_you_pick_a_failure(panneau):
    premiere = _tentative_en_echec(4, "AssertionError: boom")
    seconde = _tentative_en_echec(9, "TimeoutError: slow")
    resume = StressSummary(mode=MODE_N_TIMES, cap=20, ran=20, passed=18,
                           failed_attempts=[premiere, seconde])

    panneau.show_stress_done(NODEID, resume)

    assert "90%" in panneau.stress_sub.text()
    assert panneau.stress_failures.count() == 2
    # La plus recente (attempt 9) est montree par defaut.
    assert "TimeoutError" in panneau.stress_body.toPlainText()

    panneau._sur_tentative_ratee(panneau.stress_failures.item(0))
    assert "AssertionError" in panneau.stress_body.toPlainText()


def test_a_cancelled_series_says_so(panneau):
    resume = StressSummary(mode=MODE_N_TIMES, cap=20, ran=6, passed=6, cancelled=True)

    panneau.show_stress_done(NODEID, resume)

    assert "Stopped by you" in panneau.stress_sub.text()
    assert "6" in panneau.stress_sub.text()
