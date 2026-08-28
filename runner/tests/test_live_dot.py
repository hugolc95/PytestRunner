"""Le point qui respire a cote du texte de statut, pendant un run."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QAbstractAnimation

from runner.ui.widgets import LiveDot


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_hidden_and_still_until_started(qapp):
    point = LiveDot()

    assert point.isHidden()
    assert point._anim.state() == QAbstractAnimation.Stopped


def test_starting_shows_it_and_runs_the_pulse(qapp):
    point = LiveDot()

    point.start()

    assert not point.isHidden()
    assert point._anim.state() == QAbstractAnimation.Running


def test_stopping_hides_it_and_resets_opacity(qapp):
    point = LiveDot()
    point.start()

    point.stop()

    assert point.isHidden()
    assert point._anim.state() == QAbstractAnimation.Stopped
    assert point._effet.opacity() == 1.0
