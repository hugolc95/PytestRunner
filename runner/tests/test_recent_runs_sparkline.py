"""Mini-tendance d'un test sur ses derniers runs, dans le panneau Detail."""

from __future__ import annotations

import pytest

from runner.ui.widgets import RecentRunsSparkline


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_empty_history_shows_no_bar_and_says_so(qapp):
    sparkline = RecentRunsSparkline()
    sparkline.set_runs([])

    assert sparkline._ligne.count() == 0
    assert "no recorded history" in sparkline.toolTip().lower()


def test_one_bar_per_run_oldest_first(qapp):
    sparkline = RecentRunsSparkline()
    sparkline.set_runs([True, True, False])

    assert sparkline._ligne.count() == 3


def test_the_tooltip_counts_the_failures(qapp):
    sparkline = RecentRunsSparkline()
    sparkline.set_runs([True, False, True, False, True])

    assert "failed 2 of the last 5 runs" in sparkline.toolTip().lower()


def test_a_clean_streak_says_so_without_counting_failures(qapp):
    sparkline = RecentRunsSparkline()
    sparkline.set_runs([True, True, True])

    assert "passed every one of the last 3 runs" in sparkline.toolTip().lower()


def test_setting_runs_again_replaces_the_previous_bars(qapp):
    sparkline = RecentRunsSparkline()
    sparkline.set_runs([True, True, True, True])
    sparkline.set_runs([False])

    assert sparkline._ligne.count() == 1
