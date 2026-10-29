"""Heritage YAML, sous-groupes independants et confirmation avant tout drop."""
import copy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from runner.domain.execution_profile import (
    ExecutionProfile, ProfileStore, ProfileValidationError, effective_step_overrides,
    export_profile, group_entry, group_path, inspect_profile, validate_profile,
)
from runner.domain.history_profile import capture_profile, profile_from_entry
from runner.domain.models import Reader, RunRequest, Status
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.profile_dialogs import ConfirmGroupMoveDialog, ProfileGroupDialog, StepParametersDialog

ROOT = dict(id='t0', name='Qualification T0', color='#448aff', description='Complete suite using protocol T0.',
            configuration_overrides={'card': {'protocol': 'T0'}})
CHILD = dict(id='prepare', name='Card preparation', color='#00a99d', description='Connect and read the card.')
NODES = [f'Card/Setup/test_prepare.py::test_{name}' for name in ('connect', 'read_atr', 'select')]


@pytest.fixture
def page(qtbot, tmp_path):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    profile = ExecutionProfile('Protocols', NODES.copy(), 'config.yaml', 'card:\n  protocol: AUTO\n  timeout: 15\n',
                               profile_id=page.current_profile().profile_id,
                               step_groups=[ROOT.copy() for _ in NODES])
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    return page


def test_nested_groups_duplicate_with_independent_ids_and_group_yaml(page, tmp_path):
    page._apply_group([0, 1], CHILD)
    original = page._profile_from_editor()
    assert [g['id'] for g in group_path(original.step_groups[0])] == ['t0', 'prepare']
    root = page.sequence_list.topLevelItem(0)
    assert root.child(0).data(0, _GROUP_ROLE)['id'] == 'prepare'
    page.sequence_list.setCurrentItem(root)
    page.duplicate_steps()
    assert page._flatten_sequence() == NODES * 2
    groups = page._step_groups()
    assert [g['id'] for g in group_path(groups[0])] == ['t0', 'prepare']
    copied = group_path(groups[3])
    assert copied[0]['id'] != 't0' and copied[1]['id'] != 'prepare'
    page._apply_group_yaml(copied[0]['id'], {'card': {'protocol': 'T1'}})
    profile = page._profile_from_editor()
    assert [p['card']['protocol'] for p in effective_step_overrides(profile)] == ['T0'] * 3 + ['T1'] * 3
    assert len({g['id'] for entry in profile.step_groups for g in group_path(entry)}) == 4
    restored = inspect_profile(export_profile(profile, tmp_path / 'nested')).profile
    assert restored.step_groups == profile.step_groups
    entry = SimpleNamespace(replay_profile=capture_profile(RunRequest('', 'python', tuple(NODES), ()), profile))
    assert profile_from_entry(entry).step_groups == profile.step_groups


def test_inheritance_and_replace_only_changes_chosen_parameters(page):
    child = dict(CHILD, configuration_overrides={'card': {'protocol': 'T1', 'timeout': 20}})
    page._apply_group([0, 1], child)
    steps = page._step_items()
    from runner.ui.execution_profiles_page import _OVERRIDES_ROLE
    steps[0].setData(0, _OVERRIDES_ROLE, {'card': {'protocol': 'T0', 'timeout': 50}})
    before = effective_step_overrides(page._profile_from_editor())
    assert before == [{'card': {'protocol': 'T0', 'timeout': 50}},
                      {'card': {'protocol': 'T1', 'timeout': 20}}, {'card': {'protocol': 'T0'}}]
    page._apply_group_yaml('t0', {'card': {'protocol': 'T1'}}, replace=True)
    after = effective_step_overrides(page._profile_from_editor())
    assert after == [{'card': {'protocol': 'T1', 'timeout': 50}},
                     {'card': {'protocol': 'T1', 'timeout': 20}}, {'card': {'protocol': 'T1'}}]


def test_group_yaml_dialog_cancel_apply_and_inherited_test_value(page, monkeypatch):
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    def edit(dialog):
        assert dialog.windowTitle() == 'Group YAML parameters'
        mode, value = dialog.controls[('card', 'protocol')]
        assert value.currentText() == 'T0'
        value.setText('T1') if hasattr(value, 'setText') else value.setCurrentText('T1')
        return QDialog.Rejected
    monkeypatch.setattr(StepParametersDialog, 'exec', edit)
    page.parameters_button.click()
    assert effective_step_overrides(page._profile_from_editor())[0]['card']['protocol'] == 'T0'
    def apply(dialog):
        mode, value = dialog.controls[('card', 'protocol')]
        value.setText('T1') if hasattr(value, 'setText') else value.setCurrentText('T1')
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', apply)
    page.parameters_button.click()
    assert all(p['card']['protocol'] == 'T1' for p in effective_step_overrides(page._profile_from_editor()))
    page.sequence_list.setCurrentItem(page._step_items()[0])
    def inherited(dialog):
        mode, value = dialog.controls[('card', 'protocol')]
        assert mode.currentText() == 'Inherited value'
        assert not value.isEnabled()
        assert value.currentText() == 'T1'
        return QDialog.Rejected
    monkeypatch.setattr(StepParametersDialog, 'exec', inherited)
    page.parameters_button.click()


def test_create_subgroup_button_opens_dialog_with_parent_context(page):
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    assert page.subgroup_button.isEnabled()
    def fill():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProfileGroupDialog)
        dialog.name_edit.setText('Setup folder')
        dialog.description_edit.setText('All setup tests')
        dialog.save_button.click()
    QTimer.singleShot(0, fill)
    page.subgroup_button.click()
    assert len(group_path(page._step_groups()[0])) == 2
    assert page.sequence_list.topLevelItem(0).child(0).data(0, _GROUP_ROLE)['name'] == 'Setup folder'


def test_group_change_confirmation_cancel_has_no_side_effect_then_move_changes_inheritance(page, monkeypatch):
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    page.duplicate_steps()
    destination = page.sequence_list.topLevelItem(1)
    destination_id = destination.data(0, _GROUP_ROLE)['id']
    page._apply_group_yaml(destination_id, {'card': {'protocol': 'T1'}})
    destination = page.sequence_list.topLevelItem(1)
    step = page._step_items()[0]
    page.sequence_list.setCurrentItem(step)
    before = page._profile_from_editor()
    seen = []
    def cancel(dialog):
        assert dialog.windowTitle() == 'Confirm group change'
        from PySide6.QtWidgets import QLabel
        text = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
        assert 'T0 → T1' in text
        seen.append(text)
        return QDialog.Rejected
    monkeypatch.setattr(ConfirmGroupMoveDialog, 'exec', cancel)
    assert not page._confirm_drop(destination)
    assert page._profile_from_editor() == before
    assert seen
    monkeypatch.setattr(ConfirmGroupMoveDialog, 'exec', lambda self: QDialog.Accepted)
    assert page._confirm_drop(destination)
    parent = step.parent()
    parent.takeChild(parent.indexOfChild(step))
    destination.addChild(step)
    page._settle_sequence_order()
    profile = page._profile_from_editor()
    assert len(profile.sequence) == 6
    assert effective_step_overrides(profile)[-1]['card']['protocol'] == 'T1'
    validate_profile(profile)


def test_same_group_reorder_needs_no_confirmation_and_cyclic_drop_is_rejected(page, monkeypatch):
    root = page.sequence_list.topLevelItem(0)
    page.sequence_list.setCurrentItem(page._step_items()[0])
    monkeypatch.setattr(ConfirmGroupMoveDialog, 'exec', lambda self: pytest.fail('Unexpected confirmation'))
    assert page._confirm_drop(root)
    page.sequence_list.setCurrentItem(root)
    assert not page._confirm_drop(page._step_items()[0])


def test_live_nested_group_tree_keeps_order_and_retry_statuses(page, qapp):
    page._apply_group([0, 1], CHILD)
    profile = page._profile_from_editor()
    model = LiveProfileModel()
    model.prepare(profile, [Reader('A', 0)])
    root = model.index(0, 0, model.index(0, 0))
    child = model.index(0, 0, root)
    assert ROOT['name'] in root.data() and CHILD['name'] in child.data()
    from runner.ui.profile_group_delegate import GROUP_ROLE
    assert root.data(GROUP_ROLE)['description'] == ROOT['description']
    assert child.data(GROUP_ROLE)['color'] == CHILD['color']
    assert [model.locations[f'{i}:0'][2] for i in range(3)] == NODES
    model.apply_execution(0, 1, 0, NODES[0], Status.ERROR)
    assert model.status_for(root.internalPointer(), 0) == Status.ERROR
    assert model.status_for(child.internalPointer(), 0) == Status.ERROR


@pytest.mark.parametrize('entry', [dict(ROOT, parents=[ROOT]), dict(ROOT, parents='invalid'),
                                  dict(ROOT, configuration_overrides=[]),
                                  dict(CHILD, parents=[ROOT] * 20)])
def test_invalid_group_hierarchy_is_rejected(entry):
    profile = ExecutionProfile('Invalid', NODES, '', '', step_groups=[entry] * 3)
    with pytest.raises(ProfileValidationError):
        validate_profile(profile)


def test_subgroup_button_uses_selected_parent_even_if_all_tests_share_a_deeper_group(page):
    page._apply_group([0, 1, 2], CHILD)
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    def fill():
        dialog = QApplication.activeModalWidget()
        dialog.name_edit.setText('New level')
        dialog.save_button.click()
    QTimer.singleShot(0, fill)
    page.subgroup_button.click()
    path = group_path(page._step_groups()[0])
    assert [group['name'] for group in path] == [ROOT['name'], 'New level', CHILD['name']]
    validate_profile(page._profile_from_editor())
