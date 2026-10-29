"""Les groupes colores restent lies aux occurrences, y compris apres export."""

import copy
import json
from types import SimpleNamespace
import zipfile

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from runner.domain.execution_profile import (
    ExecutionProfile, ExecutionOptions, ProfileStore, ProfileValidationError,
    export_profile, inspect_profile, validate_profile,
)
from runner.domain.history_profile import capture_profile, profile_from_entry
from runner.domain.models import Reader, RunRequest, Status
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.profile_dialogs import ProfileGroupDialog, StepParametersDialog

NODES = ['a/test_card.py::test_connect', 'b/test_pin.py::test_pin[valid]',
         'a/test_card.py::test_connect', 'c/test_close.py::test_close']
GROUP = {'id': 'preparation', 'name': 'Card preparation', 'color': '#448aff',
         'description': 'Connect the reader and check the card.'}


@pytest.fixture
def page(qtbot, tmp_path):
    result = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(result)
    profile = ExecutionProfile('Qualification', NODES.copy(), 'config.yaml', 'timeout: 15\n',
                               profile_id=result.current_profile().profile_id,
                               step_overrides=[{}, {'timeout': 20}, {'timeout': 30}, {}])
    result._profiles[result.profile_list.currentRow()] = profile
    result._populate(profile)
    return result


def test_group_button_collects_nonadjacent_occurrences_without_losing_yaml(page):
    steps = page._step_items()
    steps[0].setSelected(True)
    steps[2].setSelected(True)
    def fill():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProfileGroupDialog)
        assert not dialog.save_button.isEnabled()
        dialog.name_edit.setText(GROUP['name'])
        dialog.description_edit.setText(GROUP['description'])
        dialog.save_button.click()
    QTimer.singleShot(0, fill)
    page.group_button.click()
    assert page._flatten_sequence() == [NODES[0], NODES[2], NODES[1], NODES[3]]
    assert page._step_patches() == [{}, {'timeout': 30}, {'timeout': 20}, {}]
    groups = page._step_groups()
    assert groups[0] == groups[1]
    assert groups[0]['name'] == GROUP['name']
    assert groups[2:] == [{}, {}]
    group = page.sequence_list.topLevelItem(0)
    assert GROUP['description'] in group.text(0)
    assert not group.icon(0).isNull()
    assert page.group_button.text() == 'Edit group…'


def test_cancel_group_keeps_order_and_metadata(page):
    page._step_items()[0].setSelected(True)
    original = page._profile_from_editor()
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    page.group_button.click()
    assert page._profile_from_editor() == original


def test_group_duplicate_move_remove_and_ungroup_preserve_parameters(page, tmp_path):
    page._apply_group([0, 1], GROUP)
    page.duplicate_steps()
    assert page._flatten_sequence() == NODES[:2] + NODES[:2] + NODES[2:]
    groups = page._step_groups()
    assert groups[0] == groups[1] == GROUP
    assert groups[2] == groups[3]
    assert groups[2]['id'] != GROUP['id']
    page._move_step(1)
    assert page._step_groups()[-2]['name'] == GROUP['name']
    assert page.save_current()
    restored = inspect_profile(export_profile(page.store.list()[0], tmp_path / 'groups')).profile
    assert restored.step_groups == page._step_groups()
    assert restored.step_overrides == page._step_patches()
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    patches = page._step_patches()
    page.ungroup_steps()
    assert page._step_groups()[:2] == [{}, {}]
    assert page._step_patches() == patches
    page._step_items()[0].setSelected(True)
    page.remove_steps()
    assert len(page._step_groups()) == len(page._flatten_sequence())
    assert page._step_patches() == patches[1:]


def test_duplicate_member_stays_inside_group_and_drop_changes_membership(page):
    page._apply_group([0, 1], GROUP)
    group = page.sequence_list.topLevelItem(0)
    group.setExpanded(True)
    # Un Ctrl synthetique d'un autre test peut conserver le groupe selectionne.
    page.sequence_list.clearSelection()
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.duplicate_steps()
    assert page._step_groups()[:3] == [GROUP] * 3
    group = page.sequence_list.topLevelItem(0)
    step = page._step_items()[1]
    parent = step.parent()
    parent.takeChild(parent.indexOfChild(step))
    page.sequence_list.addTopLevelItem(step)
    page._settle_sequence_order()
    assert page._step_groups()[-1] == {}
    assert page._flatten_sequence()[-1] == NODES[0]


def test_edit_metadata_updates_split_group_occurrences(page):
    page._apply_group([0, 1], GROUP)
    groups = page._step_groups()
    groups[-1] = copy.deepcopy(GROUP)
    page._rebuild_sequence(NODES, page._step_patches(), groups)
    changed = dict(GROUP, color='#00a99d', description='Updated description')
    page._apply_group([0, 1], changed, editing=True)
    assert page._step_groups() == [changed, changed, {}, changed]


def test_groups_survive_archive_and_history_without_changing_execution(tmp_path):
    profile = ExecutionProfile('Groups', NODES.copy(), '', '',
                               step_groups=[GROUP, GROUP, {}, {}])
    archive = export_profile(profile, tmp_path / 'groups')
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read('manifest.json'))
        assert manifest['format_version'] == 3
    restored = inspect_profile(archive).profile
    assert restored.sequence == profile.sequence
    assert restored.step_groups == profile.step_groups
    request = RunRequest('', 'python', tuple(NODES), ())
    entry = SimpleNamespace(replay_profile=capture_profile(request, profile))
    assert profile_from_entry(entry).step_groups == profile.step_groups


@pytest.mark.parametrize('groups', [
    [GROUP], [None] * 4, [{'name': 'Missing fields'}] * 4,
    [dict(GROUP, color='invalid')] * 4,
    [dict(GROUP, name=' ')] * 4,
    [GROUP, dict(GROUP, name='Conflicting group'), {}, {}],
    [dict(GROUP, description='x' * 301)] * 4,
])
def test_invalid_groups_are_rejected(groups):
    profile = ExecutionProfile('Invalid', NODES, '', '', step_groups=groups)
    with pytest.raises(ProfileValidationError):
        validate_profile(profile)


def test_live_tree_keeps_group_colors_descriptions_repeats_and_retry_statuses(qapp):
    profile = ExecutionProfile('Groups', NODES.copy(), '', '',
                               step_groups=[GROUP, GROUP, {}, {}],
                               execution=ExecutionOptions(repetitions=2))
    model = LiveProfileModel()
    model.prepare(profile, [Reader('A', 0), Reader('C', 2)])
    for repetition in range(2):
        root = model.index(repetition, 0)
        group = model.index(0, 0, root)
        assert GROUP['name'] in group.data()
        assert GROUP['description'] in group.data(Qt.ToolTipRole)
        assert group.data(Qt.BackgroundRole).name() == GROUP['color']
        assert not group.data(Qt.DecorationRole).isNull()
    assert [model.locations[f'{i}:0'][2] for i in range(8)] == NODES * 2
    model.apply_execution(0, 1, 2, NODES[0], Status.ERROR)
    leaf = model.index_for_nodeid('0:1')
    parent = leaf.parent()
    while parent.isValid() and GROUP['name'] not in parent.data():
        parent = parent.parent()
    assert parent.isValid()
    assert model.status_for(parent.internalPointer(), 2) == Status.ERROR


def test_yaml_dialog_cancel_and_apply_are_transactional(page, monkeypatch):
    def cancel(dialog):
        mode, editor = dialog.controls[('timeout',)]
        mode.setCurrentText('Custom value')
        editor.setText('99')
        return QDialog.Rejected
    page.sequence_list.setCurrentItem(page._step_items()[0])
    monkeypatch.setattr(StepParametersDialog, 'exec', cancel)
    page.parameters_button.click()
    assert page._step_patches()[0] == {}
    def apply(dialog):
        mode, editor = dialog.controls[('timeout',)]
        mode.setCurrentText('Custom value')
        editor.setText('99')
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', apply)
    page.parameters_button.click()
    assert page._step_patches()[0] == {'timeout': 99}
    assert page._step_patches()[2] == {'timeout': 30}


def test_boolean_value_and_override_mode_are_distinct_and_reader_is_managed(qtbot):
    dialog = StepParametersDialog('test_x.py::test_a', {'enabled': True, 'Reader': 'local'}, {})
    qtbot.addWidget(dialog)
    mode, editor = dialog.controls[('enabled',)]
    assert mode.currentText() == 'Profile value'
    assert editor.currentText() == 'true' and not editor.isEnabled()
    mode.setCurrentText('Custom value')
    editor.setCurrentText('false')
    assert dialog.patch == {'enabled': False}
    assert not dialog.controls[('Reader',)][0].isEnabled()
    dialog.reset()
    assert dialog.patch == {}
    assert editor.currentText() == 'true'


def test_dropping_ungrouped_test_into_named_group_assigns_color_and_preserves_yaml(page):
    page._apply_group([0, 1], GROUP)
    group = page.sequence_list.topLevelItem(0)
    step = page._step_items()[-1]
    index = page.sequence_list.indexOfTopLevelItem(step)
    assert index >= 0
    page.sequence_list.takeTopLevelItem(index)
    group.addChild(step)
    page._settle_sequence_order()
    assert page._flatten_sequence() == [NODES[0], NODES[1], NODES[3], NODES[2]]
    assert page._step_groups() == [GROUP, GROUP, GROUP, {}]
    assert page._step_patches() == [{}, {'timeout': 20}, {}, {'timeout': 30}]


def test_removed_profile_parameter_is_explicit_and_reset_does_not_reintroduce_it(qtbot):
    dialog = StepParametersDialog('test_x.py::test_a', {}, {'old_timeout': 30})
    qtbot.addWidget(dialog)
    mode, editor = dialog.controls[('old_timeout',)]
    assert mode.currentText() == 'Custom value'
    dialog.reset()
    assert dialog.patch == {}
    assert editor.text() == ''
    assert editor.placeholderText() == 'Not set in profile'
