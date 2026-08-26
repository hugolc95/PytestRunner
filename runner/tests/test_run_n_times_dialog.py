"""Choisir combien de fois rejouer un test."""

from __future__ import annotations

import pytest

from runner.ui.run_n_times_dialog import RunNTimesDialog


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_default_count_is_preselected(qapp):
    dialogue = RunNTimesDialog(defaut=20)
    assert dialogue.count() == 20
    assert dialogue._boutons_preset[2].isChecked()  # "20"


def test_clicking_a_preset_sets_the_count(qapp):
    dialogue = RunNTimesDialog(defaut=20)
    dialogue._boutons_preset[3].click()  # "50"
    assert dialogue.count() == 50


def test_typing_a_custom_value_unchecks_every_preset(qapp):
    dialogue = RunNTimesDialog(defaut=20)
    dialogue.compte.setValue(7)
    assert dialogue.count() == 7
    assert not any(b.isChecked() for b in dialogue._boutons_preset)
