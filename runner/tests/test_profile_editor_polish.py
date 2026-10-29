"""Annulation atomique, provenance effective et deplacements accessibles."""
import copy

import pytest
import yaml
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from runner.domain.execution_profile import ExecutionProfile, ProfileStore, group_path, effective_step_overrides
from runner.domain.profile_configuration import configuration_details
from runner.domain.models import Reader
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE
from runner.ui.profile_dialogs import EffectiveConfigurationDialog, MoveToGroupDialog, StepParametersDialog
from runner.ui.profile_group_delegate import EXCEPTION_ROLE
from runner.ui.live_profile_model import LiveProfileModel

NODES = [f'Card/test_card.py::test_{name}' for name in ('connect', 'read', 'select')]
ROOT = dict(id='t1', name='Qualification T1', color='#a675ed', description='The complete T1 suite.',
            configuration_overrides={'card': {'protocol': 'T1'}})
BASE = {'Reader': 'Reader A', 'card': {'protocol': 'T0', 'timeout': 15}}


@pytest.fixture
def page(qtbot, tmp_path):
    result = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(result)
    profile = ExecutionProfile('Protocols', NODES.copy(), 'config.yaml', yaml.safe_dump(BASE),
                               profile_id=result.current_profile().profile_id, step_groups=[ROOT] * 3)
    result._profiles[result.profile_list.currentRow()] = profile
    result._populate(profile)
    return result


def data(page):
    profile = page._profile_from_editor()
    return profile.sequence, profile.step_overrides, profile.step_groups


def test_duplicate_and_group_yaml_are_separate_atomic_undo_steps(page):
    original = data(page)
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    page.duplicate_steps()
    duplicate = data(page)
    identifier = page.sequence_list.topLevelItem(1).data(0, _GROUP_ROLE)['id']
    page._apply_group_yaml(identifier, {'card': {'protocol': 'T0'}})
    destination = page.sequence_list.topLevelItem(1)
    changed = data(page)
    assert page.undo_stack.count() == 2
    page.undo_stack.undo()
    assert data(page) == duplicate
    page.undo_stack.undo()
    assert data(page) == original
    page.undo_stack.redo()
    page.undo_stack.redo()
    assert data(page) == changed
    assert effective_step_overrides(page._profile_from_editor())[0]['card']['protocol'] == 'T1'
    assert effective_step_overrides(page._profile_from_editor())[-1]['card']['protocol'] == 'T0'


def test_undo_after_save_preserves_disk_and_redo_returns_to_clean_state(page):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.remove_steps()
    assert page.save_current()
    saved = page.store.list()[0]
    assert not page._dirty and page.undo_stack.canUndo()
    page.undo_stack.undo()
    assert page._flatten_sequence() == NODES
    assert page._dirty
    assert page.store.list()[0] == saved
    page.undo_stack.redo()
    assert not page._dirty
    assert page._flatten_sequence() == NODES[1:]


def test_redo_is_discarded_by_a_new_action_and_profile_switch_clears_history(page):
    page._append_tests([NODES[0]])
    page.undo_stack.undo()
    assert page.undo_stack.canRedo()
    page._append_tests([NODES[1]])
    assert not page.undo_stack.canRedo()
    page.new_profile()
    assert not page.undo_stack.canUndo()
    assert page._flatten_sequence() == []


def test_rejected_parameter_dialog_does_not_add_undo_and_text_options_restore(page, monkeypatch):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    monkeypatch.setattr(StepParametersDialog, 'exec', lambda self: QDialog.Rejected)
    page.parameters_button.click()
    assert page.undo_stack.count() == 0
    page.name_edit.setText('First edit')
    page.name_edit.setText('Second edit')
    assert page.undo_stack.count() == 1
    page.undo_stack.undo()
    assert page.name_edit.text() == 'Protocols'
    page.undo_stack.redo()
    assert page.name_edit.text() == 'Second edit'


def test_group_creation_remove_ungroup_and_restore_yaml_and_selection(page):
    group = dict(id='setup', name='Setup', color='#00a99d', description='Prepare the card')
    page._step_items()[0].setSelected(True)
    page._step_items()[1].setSelected(True)
    before = data(page)
    page._apply_group([0, 1], group)
    grouped = data(page)
    page.remove_steps()
    assert page._flatten_sequence() == [NODES[2]]
    page.undo_stack.undo()
    assert data(page) == grouped
    assert page.sequence_list.currentItem().data(0, _GROUP_ROLE)['id'] == 'setup'
    page.ungroup_steps()
    page.undo_stack.undo()
    assert data(page) == grouped
    page.undo_stack.undo()
    assert data(page) == before


def test_native_drop_is_one_undo_action(page):
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    page.duplicate_steps()
    original = data(page)
    root = page.sequence_list.topLevelItem(0)
    other = page.sequence_list.topLevelItem(1)
    step = page._step_items()[0]
    parent = step.parent()
    parent.takeChild(parent.indexOfChild(step))
    other.addChild(step)
    page.sequence_list.setCurrentItem(step)
    count = page.undo_stack.count()
    page._settle_sequence_order()
    moved = data(page)
    assert page.undo_stack.count() == count + 1
    page.undo_stack.undo()
    assert data(page) == original
    page.undo_stack.redo()
    assert data(page) == moved


def test_context_move_keeps_own_overrides_and_is_undoable(page):
    from runner.ui.execution_profiles_page import _OVERRIDES_ROLE
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    page.duplicate_steps()
    destination = page.sequence_list.topLevelItem(1)
    identifier = destination.data(0, _GROUP_ROLE)['id']
    page._apply_group_yaml(identifier, {'card': {'protocol': 'T0'}})
    destination = page.sequence_list.topLevelItem(1)
    page._step_items()[0].setData(0, _OVERRIDES_ROLE, {'card': {'timeout': 90}})
    page.sequence_list.setCurrentItem(page._step_items()[0])
    original = data(page)
    # Le meme dialogue que le menu clic droit, avec apercu avant son unique validation.
    def move():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, MoveToGroupDialog)
        index = next(i for i, (_, target) in enumerate(dialog.targets) if target is destination)
        dialog.target_combo.setCurrentIndex(index)
        assert 'T1 → T0' in dialog.preview.text()
        dialog.move_button.click()
    QTimer.singleShot(0, move)
    page.move_to_group()
    assert page._step_patches()[-1] == {'card': {'timeout': 90}}
    assert effective_step_overrides(page._profile_from_editor())[-1] == {'card': {'protocol': 'T0', 'timeout': 90}}
    page.undo_stack.undo()
    assert data(page) == original


def test_context_cancel_keeps_data_and_history_and_menu_handles_multiselection(page):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page._step_items()[1].setSelected(True)
    before = data(page)
    count = page.undo_stack.count()
    menu = page._context_menu()
    actions = {action.text(): action for action in menu.actions()}
    assert not actions['View effective YAML…'].isEnabled()
    assert actions['Move to…'].isEnabled()
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    page.move_to_group()
    assert data(page) == before and page.undo_stack.count() == count


def test_effective_values_have_precise_origins_and_flag_real_exceptions():
    child = dict(id='setup', name='Setup', color='#00a99d', description='',
                 configuration_overrides={'card': {'timeout': 25}})
    config, rows, exceptions = configuration_details(BASE, [ROOT, child], {'card': {'protocol': 'T0'}})
    values = {row['path']: row for row in rows}
    assert config == {'Reader': 'Reader A', 'card': {'protocol': 'T0', 'timeout': 25}}
    assert values[('Reader',)]['source'] == 'Profile'
    assert values[('card', 'protocol')]['source'] == 'This test'
    assert values[('card', 'timeout')]['source'] == 'Group: Qualification T1 / Setup'
    assert {exception['path'] for exception in exceptions} == {('card', 'protocol'), ('card', 'timeout')}
    assert values[('card', 'protocol')]['exception']['inherited'] == 'T1'
    # Le groupe racine T1 n'est pas une exception a sa propre politique.
    assert not configuration_details(BASE, [ROOT], {})[2]
    assert not configuration_details(BASE, [ROOT], {'card': {'protocol': 'T1'}})[2]


def test_origin_tracking_drops_fields_replaced_by_a_scalar():
    config, rows, _ = configuration_details(BASE, [], {'card': 'disabled'})
    assert config['card'] == 'disabled'
    assert {row['path'] for row in rows} == {('Reader',), ('card',)}
    assert next(row for row in rows if row['path'] == ('card',))['source'] == 'This test'


def test_effective_dialog_switches_reader_filters_copies_without_modifying_profile(qtbot):
    config, rows, _ = configuration_details(BASE, [ROOT], {'card': {'protocol': 'T0'}})
    original = copy.deepcopy(config)
    dialog = EffectiveConfigurationDialog(NODES[0], config, rows, ['Reader A', 'Reader B'])
    qtbot.addWidget(dialog)
    dialog.reader_combo.setCurrentIndex(1)
    assert yaml.safe_load(dialog.yaml_view.toPlainText())['Reader'] == 'Reader B'
    assert 'This test' in [dialog.table.item(i, 2).text() for i in range(dialog.table.rowCount())]
    dialog.search.setText('protocol')
    assert sum(not dialog.table.isRowHidden(i) for i in range(dialog.table.rowCount())) == 1
    dialog._copy()
    assert QApplication.clipboard().text() == dialog.yaml_view.toPlainText()
    assert config == original


def test_warning_indicators_agree_in_editor_preview_and_run_tree(page):
    from runner.ui.execution_profiles_page import _OVERRIDES_ROLE
    page._step_items()[0].setData(0, _OVERRIDES_ROLE, {'card': {'protocol': 'T0'}})
    page._mark_dirty()
    step = page._step_items()[0]
    assert step.data(0, EXCEPTION_ROLE)
    assert 'YAML exception' in step.text(0)
    assert 'inherited T1' in step.toolTip(0)
    assert '1 exception' in page.sequence_list.topLevelItem(0).text(0)
    model = LiveProfileModel()
    profile = page._profile_from_editor()
    model.prepare(profile, [Reader('A', 0)])
    index = model.index_for_nodeid('0:0')
    assert index.data(EXCEPTION_ROLE)
    assert 'YAML exception' in index.data()
    assert 'inherited T1' in index.data(Qt.ToolTipRole)
    assert index.parent().data(EXCEPTION_ROLE)


def test_undo_redo_shortcuts_work_from_the_sequence_tree(page, qtbot):
    page.resize(1300, 800)
    page.show()
    page.activateWindow()
    page.sequence_list.setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is page and page.sequence_list.hasFocus())
    page._append_tests([NODES[0]])
    before = page._flatten_sequence()
    qtbot.keyClick(page.sequence_list, Qt.Key_Z, Qt.ControlModifier)
    assert page._flatten_sequence() == NODES
    qtbot.keyClick(page.sequence_list, Qt.Key_Y, Qt.ControlModifier)
    assert page._flatten_sequence() == before


def test_undo_history_is_bounded_and_never_changes_persisted_files(page):
    for _ in range(55):
        page._append_tests([NODES[0]])
    assert page.undo_stack.count() == 50
    for _ in range(50):
        page.undo_stack.undo()
    assert len(page._flatten_sequence()) == len(NODES) + 5
    assert page.store.list() == []


def test_numeric_yaml_keys_are_kept_in_effective_preview(qtbot):
    config, rows, _ = configuration_details({'codes': {0: 'zero', 1: 'one'}}, [], {})
    dialog = EffectiveConfigurationDialog(NODES[0], config, rows)
    qtbot.addWidget(dialog)
    assert dialog.table.item(0, 0).text() == 'codes.0'
    assert yaml.safe_load(dialog.yaml_view.toPlainText()) == {'codes': {0: 'zero', 1: 'one'}}


def test_local_configuration_is_used_for_run_tree_exceptions(qapp):
    group = dict(ROOT, configuration_overrides={})
    profile = ExecutionProfile('Local config', [NODES[0]], '', '',
                               step_groups=[group], step_overrides=[{'card': {'timeout': 30}}])
    model = LiveProfileModel()
    model.configuration_base = BASE
    model.prepare(profile, [Reader('A', 0)])
    assert 'inherited 15' in model.index_for_nodeid('0:0').data(Qt.ToolTipRole)
