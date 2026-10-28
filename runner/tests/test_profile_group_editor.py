"""Les groupes sont un rendu : l'ordre et le YAML restent par occurrence."""

import copy

import pytest
from PySide6.QtCore import Qt

from runner.domain.execution_profile import ExecutionProfile, ProfileStore, export_profile, inspect_profile
from runner.ui.execution_profiles_page import (
    AddTestsDialog, ExecutionProfilesPage, _EDITOR_ROLE, _OVERRIDES_ROLE,
)
from runner.ui.tree_model import NODEID_ROLE


NODES = ['perso/test_card.py::TestCard::test_init',
         'perso/test_card.py::TestCard::test_write',
         'security/test_auth.py::test_pin[valid]',
         'security/test_auth.py::test_pin[invalid]',
         'health/test_reader.py::test_connect']
PATCHES = [{}, {'timeout': 20}, {'protocol': 'T1'}, {}, {}]


@pytest.fixture
def page(qtbot, tmp_path):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    profile = ExecutionProfile('Card checks', list(NODES), 'config.yaml',
                               'timeout: 15\nprotocol: T0\n',
                               profile_id=page.current_profile().profile_id,
                               step_overrides=copy.deepcopy(PATCHES))
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    return page


def test_group_duplicate_move_save_and_export_keep_occurrence_parameters(page, tmp_path):
    tree = page.sequence_list
    assert tree.topLevelItemCount() == 3
    assert not tree.topLevelItem(0).isExpanded()
    tree.topLevelItem(0).setSelected(True)
    page.duplicate_steps()
    expected_ids = NODES[:2] + NODES[:2] + NODES[2:]
    expected_patches = PATCHES[:2] + PATCHES[:2] + PATCHES[2:]
    assert page._flatten_sequence() == expected_ids
    assert page._step_patches() == expected_patches
    # Le groupe duplique devient la selection et se deplace en bloc.
    page._move_step(1)
    expected_ids = NODES[:2] + NODES[2:4] + NODES[:2] + NODES[4:]
    expected_patches = PATCHES[:2] + PATCHES[2:4] + PATCHES[:2] + PATCHES[4:]
    assert page._flatten_sequence() == expected_ids
    assert page._step_patches() == expected_patches
    assert page.save_current()
    saved = page.store.list()[0]
    restored = inspect_profile(export_profile(saved, tmp_path / 'campaign')).profile
    assert restored.sequence == expected_ids
    assert restored.step_overrides == expected_patches


def test_duplicate_parent_and_member_does_not_duplicate_member_twice(page):
    group = page.sequence_list.topLevelItem(0)
    group.setSelected(True)
    group.child(1).setSelected(True)
    page.duplicate_steps()
    assert page._flatten_sequence() == NODES[:2] + NODES[:2] + NODES[2:]
    assert page._step_patches() == PATCHES[:2] + PATCHES[:2] + PATCHES[2:]


def test_group_expansion_does_not_open_every_yaml_editor(page):
    page._expand_groups()
    assert page.sequence_list.topLevelItem(0).isExpanded()
    assert page.sequence_list.topLevelItem(1).isExpanded()
    assert all(not step.isExpanded() for step in page._step_items())
    assert all(page.sequence_list.itemWidget(step.child(0), 0) is None for step in page._step_items())
    step = page._step_items()[1]
    page.sequence_list.setCurrentItem(step)
    toggle, editor = page._parameter_controls[('timeout',)]
    assert toggle.isChecked() and editor.text() == '20'
    assert page.sequence_list.itemWidget(step.child(0), 0) is not None
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(1))
    assert not step.isExpanded()
    assert page._step_patches() == PATCHES


def test_moving_member_keeps_other_open_groups_and_yaml_with_the_right_test(page):
    page._expand_groups()
    page.sequence_list.setCurrentItem(page._step_items()[1])
    page._move_step(-1)
    assert page._flatten_sequence() == [NODES[1], NODES[0], *NODES[2:]]
    assert page._step_patches() == [PATCHES[1], PATCHES[0], *PATCHES[2:]]
    assert page.sequence_list.topLevelItem(1).isExpanded()
    assert page._parameter_controls[('timeout',)][1].text() == '20'


def test_repeated_additions_remain_separate_groups_and_repeat_button_reuses_selection(qtbot, tmp_path):
    picker = AddTestsDialog(NODES)
    qtbot.addWidget(picker)
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    picker.tests_added.connect(page._append_tests)
    group = picker.model.index(0, 0)
    picker.model.setData(group, Qt.Checked, Qt.CheckStateRole)
    picker.add_button.click()
    assert picker._selection_order == []
    assert picker.add_again_button.isEnabled()
    picker.add_again_button.click()
    assert page._flatten_sequence() == NODES[:2] + NODES[:2]
    assert page.sequence_list.topLevelItemCount() == 2
    assert all(picker.tree.isColumnHidden(i) for i in range(1, picker.model.columnCount()))


def test_drop_between_groups_keeps_parameters_and_does_not_save_editor_rows(page):
    tree = page.sequence_list
    first, second = tree.topLevelItem(0), tree.topLevelItem(1)
    # Meme deplacement d'items Qt qu'un drop entre deux groupes ; le rendu
    # est reconstruit apres la fin du geste, jamais au milieu du drop natif.
    moved = first.takeChild(1)
    second.insertChild(1, moved)
    tree.setCurrentItem(moved)
    page._settle_sequence_order()
    assert page._flatten_sequence() == [NODES[0], NODES[2], NODES[1], NODES[3], NODES[4]]
    assert page._step_patches() == [PATCHES[0], PATCHES[2], PATCHES[1], PATCHES[3], PATCHES[4]]
    assert all(item.data(0, NODEID_ROLE) for item in page._step_items())
    assert all(item.child(0).data(0, _EDITOR_ROLE) for item in page._step_items())


def test_duplicate_group_patches_are_independent(page):
    page.sequence_list.topLevelItem(0).setSelected(True)
    page.duplicate_steps()
    copied = page._step_items()[3]
    copied.setData(0, _OVERRIDES_ROLE, {'timeout': 42})
    assert page._step_patches()[1] == {'timeout': 20}
    assert page._step_patches()[3] == {'timeout': 42}
