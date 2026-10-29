"""Les personnalisations restent editables et lisibles dans les deux arbres."""
import copy

import pytest
import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from runner.domain.execution_profile import ExecutionProfile, ProfileStore, group_entry
from runner.domain.models import Reader, Status
from runner.domain.profile_configuration import configuration_annotation
from runner.ui import icons
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE, _OVERRIDES_ROLE, _KIND_ROLE
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.profile_dialogs import StepParametersDialog
from runner.ui.profile_group_delegate import YAML_ROLE, GROUP_COLOR_ROLE, EXCEPTION_ROLE, CONFIG_ISSUES_ROLE
from runner.ui.tree_model import NODEID_ROLE

BASE = {'Reader': 'Reader A', 'card': {'protocol': 'T0', 'timeout': 15}, 'verbose': False}
ROOT = dict(id='t1', name='Qualification T1', color='#a675ed', description='Complete qualification.',
            configuration_overrides={'card': {'protocol': 'T1'}})
CHILD = dict(id='pin', name='PIN checks', color='#00a99d', description='Check PIN behavior.',
             configuration_overrides={'card': {'timeout': 30}})
NODES = ['Card/Setup/test_card.py::TestCard::test_connect',
         'Card/Setup/test_card.py::TestCard::test_read[valid]',
         'Card/Setup/test_card.py::TestCard::test_read[invalid]',
         'Card/Other/test_close.py::test_close',
         'Security/test_pin.py::test_pin[ok]', 'Security/test_pin.py::test_pin[blocked]']


@pytest.fixture
def page(qtbot, tmp_path):
    result = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(result)
    profile = ExecutionProfile('Protocols', NODES.copy(), 'config.yaml', yaml.safe_dump(BASE),
        profile_id=result.current_profile().profile_id, step_groups=[ROOT] * 4 + [group_entry([ROOT, CHILD])] * 2,
        step_overrides=[{}, {'card': {'protocol': 'T0'}}, {'card': {'timeout': 50}}, {}, {}, {}])
    result._profiles[result.profile_list.currentRow()] = profile
    result._populate(profile)
    return result


def select(page, item):
    page.sequence_list.clearSelection()
    page.sequence_list.setCurrentItem(item)
    assert page.sequence_list.selectedItems() == [item]


def test_individual_test_yaml_opens_from_double_click_even_with_group_preselected(page, monkeypatch):
    select(page, page.sequence_list.topLevelItem(0))
    before = page._step_patches()
    def edit(dialog):
        assert dialog.windowTitle() == 'Test YAML parameters'
        mode, value = dialog.controls[('card', 'timeout')]
        mode.setCurrentText('Custom value')
        value.setText('75')
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', edit)
    page._edit_item(page._step_items()[0])
    assert page._step_patches() == [{'card': {'timeout': 75}}, *before[1:]]
    assert page._profile_from_editor().step_groups[0] == ROOT
    page.undo_stack.undo()
    assert page._step_patches() == before


def test_parameterized_test_can_edit_all_cases_preserving_untouched_mixed_fields(page, monkeypatch):
    parent = page._step_items()[1].parent()
    assert parent is page._step_items()[2].parent()
    select(page, parent)
    assert page.parameters_button.isEnabled()
    assert page._context_menu().actions()[0].isEnabled()
    before = page._step_patches()
    def edit(dialog):
        assert dialog.windowTitle() == 'Test selection YAML parameters'
        assert dialog.controls[('card', 'protocol')][0].currentText() == 'Mixed values — unchanged'
        assert dialog.controls[('card', 'timeout')][0].currentText() == 'Mixed values — unchanged'
        mode, value = dialog.controls[('verbose',)]
        mode.setCurrentText('Custom value')
        value.setCurrentText('true')
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', edit)
    page.parameters_button.click()
    expected = copy.deepcopy(before)
    expected[1]['verbose'] = expected[2]['verbose'] = True
    assert page._step_patches() == expected
    assert page.undo_stack.count() == 1
    page.undo_stack.undo()
    assert page._step_patches() == before
    page.undo_stack.redo()
    assert page._step_patches() == expected


def test_batch_apply_without_changes_and_cancel_preserve_all_individual_overrides(page, monkeypatch):
    select(page, page._step_items()[1].parent())
    before = page._profile_from_editor()
    monkeypatch.setattr(StepParametersDialog, 'exec', lambda self: QDialog.Accepted)
    page.edit_step_parameters()
    assert page._profile_from_editor() == before
    assert page.undo_stack.count() == 0
    def cancel(dialog):
        dialog.reset()
        return QDialog.Rejected
    monkeypatch.setattr(StepParametersDialog, 'exec', cancel)
    page.edit_step_parameters()
    assert page._profile_from_editor() == before


def test_batch_reset_uses_group_inheritance_without_modifying_the_group(page, monkeypatch):
    select(page, page._step_items()[1].parent())
    groups = page._step_groups()
    def reset(dialog):
        dialog.reset()
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', reset)
    page.edit_step_parameters()
    assert page._step_patches()[1:3] == [{}, {}]
    assert page._step_groups() == groups
    assert page._step_items()[1].data(0, YAML_ROLE)['state'] == 'inherited'


def test_normal_custom_yaml_and_inheritance_are_visible_without_any_exception(page):
    root = page.sequence_list.topLevelItem(0)
    assert root.data(0, YAML_ROLE)['state'] == 'custom'
    assert 'Group default: T1' in root.toolTip(0)
    assert 'Inherited value: T0' in root.toolTip(0)
    plain = page._step_items()[0]
    assert plain.data(0, YAML_ROLE)['state'] == 'inherited'
    assert 'Value used: T1' in plain.toolTip(0)
    assert 'Defined by: Group: Qualification T1' in plain.toolTip(0)
    assert not plain.data(0, EXCEPTION_ROLE)
    # Un patch volontaire identique a l'heritage reste identifiable comme explicite.
    plain.setData(0, _OVERRIDES_ROLE, {'card': {'protocol': 'T1'}})
    page._mark_dirty()
    assert plain.data(0, YAML_ROLE)['state'] == 'custom'
    assert 'same as inherited' in plain.toolTip(0).lower()
    assert not plain.data(0, EXCEPTION_ROLE)


def test_new_parameters_and_scalar_replacements_are_described_without_fake_null_values():
    annotation = configuration_annotation({'card': {'protocol': 'T0'}}, [], {'new': None, 'card': 'offline'})
    assert annotation['count'] == 2
    assert 'new\n  Value used: null\n  Inherited value: Not defined' in annotation['tooltip']
    assert 'Value used: offline' in annotation['tooltip']
    assert 'Inherited value: {protocol: T0}' in annotation['tooltip']


def test_editor_and_run_tree_agree_on_each_test_color_and_yaml_tooltip(page):
    model = LiveProfileModel()
    model.prepare(page._profile_from_editor(), [Reader('A', 0)])
    for position, item in enumerate(page._step_items()):
        index = model.index_for_nodeid(f'{position}:0')
        assert item.data(0, YAML_ROLE) == index.data(YAML_ROLE)
        color = CHILD['color'] if position >= 4 else ROOT['color']
        assert item.data(0, GROUP_COLOR_ROLE) == index.data(GROUP_COLOR_ROLE) == color
        assert item.data(0, YAML_ROLE)['tooltip'] in index.data(Qt.ToolTipRole)
        assert index.data(Qt.AccessibleDescriptionRole) == index.data(Qt.ToolTipRole)
        assert not index.data(Qt.CheckStateRole)
    root = model.index(0, 0, model.index(0, 0))
    assert root.data(YAML_ROLE)['state'] == 'custom'
    assert 'Group default: T1' in root.data(Qt.ToolTipRole)
    assert 'Inherited value: T0' in root.data(Qt.ToolTipRole)


def test_folder_module_class_and_parameterized_parent_icons_follow_nearest_group(page):
    _, ranges = page._sequence_ranges()
    for item, _, _ in ranges:
        path = page._item_group_path(item, include_self=not bool(item.data(0, NODEID_ROLE)))
        color = path[-1]['color']
        assert item.data(0, GROUP_COLOR_ROLE) == color
        if not item.data(0, _GROUP_ROLE) or item.data(0, NODEID_ROLE):
            from runner.domain.models import Kind
            expected = icons.kind_icon(Kind(item.data(0, _KIND_ROLE)), color)
            assert item.icon(0).cacheKey() == expected.cacheKey()
    parent = page._step_items()[1].parent()
    assert parent.data(0, YAML_ROLE)['state'] == 'descendants'
    assert '2 of 2 tests have customized YAML' in parent.toolTip(0)


def test_run_retries_keep_configuration_badges_group_colors_and_status_columns(page):
    model = LiveProfileModel()
    model.prepare(page._profile_from_editor(), [Reader('A', 0)])
    original = model.index_for_nodeid('1:0')
    model.apply_execution(1, 1, 0, NODES[1], Status.PASSED)
    retry = model.index_for_nodeid('1:1')
    assert retry.data(YAML_ROLE) == original.data(YAML_ROLE)
    assert retry.data(GROUP_COLOR_ROLE) == original.data(GROUP_COLOR_ROLE)
    assert 'Value used: T0' in retry.data(Qt.ToolTipRole)
    assert 'Inherited value: T1' in retry.data(Qt.ToolTipRole)
    assert model.status_for(retry.internalPointer(), 0) is Status.PASSED
    assert not model.index(retry.row(), 1, retry.parent()).data(YAML_ROLE)


def test_ungrouping_and_undo_refresh_colors_and_remove_inherited_yaml(page):
    select(page, page.sequence_list.topLevelItem(0))
    page.ungroup_steps()
    assert page._step_items()[0].data(0, GROUP_COLOR_ROLE) == ''
    assert page._step_items()[0].data(0, YAML_ROLE)['state'] == ''
    assert page._step_items()[4].data(0, GROUP_COLOR_ROLE) == CHILD['color']
    page.undo_stack.undo()
    assert page._step_items()[0].data(0, GROUP_COLOR_ROLE) == ROOT['color']
    assert page._step_items()[0].data(0, YAML_ROLE)['state'] == 'inherited'


def test_batch_invalid_number_cannot_apply_or_remove_mixed_value(qtbot):
    patches = [{'timeout': 15}, {'timeout': 30}]
    dialog = StepParametersDialog('test_read', {'timeout': 10}, patches[0], patches=patches)
    qtbot.addWidget(dialog)
    mode, value = dialog.controls[('timeout',)]
    mode.setCurrentText('Custom value')
    value.setText('bad')
    assert not dialog.apply_button.isEnabled()
    mode.setCurrentText('Mixed values — unchanged')
    assert dialog.apply_button.isEnabled()
    assert [dialog.apply_to_patch(patch) for patch in patches] == patches


def test_batch_reset_and_specific_nested_edit_handle_scalar_overrides(qtbot):
    base = {'card': {'protocol': 'T0', 'timeout': 15}}
    patches = [{'card': 'offline'}, {'card': {'timeout': 30}}]
    dialog = StepParametersDialog('test_read', base, patches[0], patches=patches)
    qtbot.addWidget(dialog)
    mode, editor = dialog.controls[('card', 'protocol')]
    mode.setCurrentText('Custom value')
    editor.setCurrentText('T1')
    assert dialog.apply_to_patch(patches[0]) == {'card': {'protocol': 'T1'}}
    assert dialog.apply_to_patch(patches[1]) == {'card': {'protocol': 'T1', 'timeout': 30}}
    dialog.reset()
    assert dialog.apply_button.isEnabled()
    assert [dialog.apply_to_patch(patch) for patch in patches] == [{}, {}]


def test_folder_double_click_keeps_normal_expansion_without_opening_yaml(page, monkeypatch):
    item = page.sequence_list.topLevelItem(0).child(0)
    assert item.data(0, _KIND_ROLE) == 'folder'
    def unexpected(dialog):
        pytest.fail('Expanding a folder must not open a YAML dialog')
    monkeypatch.setattr(StepParametersDialog, 'exec', unexpected)
    page._edit_item(item)


@pytest.mark.parametrize('position', [0, 4])
def test_parameter_dialog_shows_the_actual_origin_of_each_inherited_field(page, monkeypatch, position):
    select(page, page._step_items()[position])
    before = page._profile_from_editor()
    def inspect(dialog):
        assert dialog._hints[('card', 'protocol')].text() == 'Defined by: Group: Qualification T1'
        if position == 4:
            assert dialog._hints[('card', 'timeout')].text() == 'Defined by: Group: Qualification T1 / PIN checks'
            assert dialog.controls[('card', 'timeout')][0].currentText() == 'Inherited value'
        else:
            assert dialog._hints[('card', 'timeout')].text() == 'Defined by: Profile'
            assert dialog.controls[('card', 'timeout')][0].currentText() == 'Profile value'
        return QDialog.Rejected
    monkeypatch.setattr(StepParametersDialog, 'exec', inspect)
    page.edit_step_parameters()
    assert page._profile_from_editor() == before


def test_custom_filter_combines_search_and_exact_origins_without_changing_values(qtbot):
    patch = {'card': {'timeout': 60}}
    dialog = StepParametersDialog('test_a', {'card': {'protocol': 'T1', 'timeout': 15}}, patch,
        origins={('card', 'protocol'): 'Group: Qualification T1', ('card', 'timeout'): 'Profile'})
    qtbot.addWidget(dialog)
    dialog.custom_only.setChecked(True)
    rows = {path: label for path, label, _, _ in dialog._rows}
    assert rows[('card', 'protocol')].isHidden()
    assert not rows[('card', 'timeout')].isHidden()
    dialog.search.setText('Qualification')
    assert all(label.isHidden() for label in rows.values())
    assert dialog.empty.text() == 'No parameters match these filters.'
    dialog.custom_only.setChecked(False)
    assert not rows[('card', 'protocol')].isHidden()
    assert rows[('card', 'timeout')].isHidden()
    assert dialog.patch == patch
    assert not dialog.changed_paths


def test_custom_filter_preserves_mixed_values_and_refreshes_after_reset(qtbot):
    patches = [{'timeout': 30}, {}, {'timeout': 15}]
    dialog = StepParametersDialog('test_read', {'timeout': 15, 'enabled': True}, patches[0], patches=patches)
    qtbot.addWidget(dialog)
    dialog.custom_only.setChecked(True)
    rows = {path: label for path, label, _, _ in dialog._rows}
    assert not rows[('timeout',)].isHidden()
    assert rows[('enabled',)].isHidden()
    assert [dialog.apply_to_patch(patch) for patch in patches] == patches
    dialog.reset()
    assert rows[('timeout',)].isHidden()
    assert 'No custom parameters' in dialog.empty.text()
    assert [dialog.apply_to_patch(patch) for patch in patches] == [{}, {}, {}]
    dialog.custom_only.setChecked(False)
    assert all(not label.isHidden() for label in rows.values())


def test_custom_filter_keeps_explicit_values_equal_to_inheritance_and_invalid_edits(qtbot):
    dialog = StepParametersDialog('test_read', {'timeout': 15}, {'timeout': 15})
    qtbot.addWidget(dialog)
    dialog.custom_only.setChecked(True)
    assert not dialog._rows[0][1].isHidden()
    mode, value = dialog.controls[('timeout',)]
    value.setText('invalid')
    assert not dialog.apply_button.isEnabled()
    assert not dialog._rows[0][1].isHidden()
    mode.setCurrentText('Profile value')
    assert dialog.apply_button.isEnabled()
    assert dialog._rows[0][1].isHidden()


@pytest.mark.parametrize('text', ['card: [', '- one\n- two'])
def test_invalid_yaml_has_a_real_configuration_warning_that_clears_after_fix(page, text):
    page._configuration_text = text
    page._mark_dirty()
    assert page._step_items()[0].data(0, CONFIG_ISSUES_ROLE)
    assert 'Configuration problem' in page._step_items()[0].toolTip(0)
    model = LiveProfileModel()
    profile = page._profile_from_editor()
    model.prepare(profile, [Reader('A', 0)])
    index = model.index_for_nodeid('0:0')
    assert index.data(CONFIG_ISSUES_ROLE)
    assert 'Configuration problem' in index.data(Qt.ToolTipRole)
    page._configuration_text = yaml.safe_dump(BASE)
    page._mark_dirty()
    model.prepare(page._profile_from_editor(), [Reader('A', 0)])
    assert not page._step_items()[0].data(0, CONFIG_ISSUES_ROLE)
    assert not model.index_for_nodeid('0:0').data(CONFIG_ISSUES_ROLE)


def test_unreadable_yaml_file_is_reported_in_the_editor(page, tmp_path):
    page.config_edit.setProperty('fullPath', str(tmp_path / 'deleted.yaml'))
    page._mark_dirty()
    assert 'deleted.yaml' in page._step_items()[0].toolTip(0)
    assert page._step_items()[0].data(0, CONFIG_ISSUES_ROLE)


def test_real_tree_paint_reserves_alert_icon_for_invalid_configuration(page, qtbot, monkeypatch):
    page.resize(1400, 900)
    page.sequence_list.expandAll()
    page.show()
    glyphs = []
    real = icons.icon
    def capture(name, color=''):
        glyphs.append(name)
        return real(name, color)
    monkeypatch.setattr(icons, 'icon', capture)
    page.sequence_list.grab()
    assert 'mdi.alert-outline' not in glyphs
    page._configuration_text = 'card: ['
    page._mark_dirty()
    glyphs.clear()
    page.sequence_list.grab()
    assert 'mdi.alert-outline' in glyphs


def test_filter_hidden_validation_error_can_be_found_and_fixed_without_losing_input(qtbot):
    dialog = StepParametersDialog('test_a', {'timeout': 15, 'protocol': 'T0'}, {})
    qtbot.addWidget(dialog)
    mode, value = dialog.controls[('timeout',)]
    mode.setCurrentText('Custom value')
    value.setText('invalid')
    dialog.search.setText('protocol')
    assert not dialog.apply_button.isEnabled()
    assert not dialog.validation_summary.isHidden()
    assert '1 invalid parameter is hidden' in dialog.validation_summary.text()
    dialog.validation_summary.linkActivated.emit('show')
    assert dialog.search.text() == ''
    assert not dialog._rows[0][1].isHidden()
    assert value.text() == 'invalid'
    assert dialog.validation_summary.isHidden()
    value.setText('25')
    assert dialog.apply_button.isEnabled()
    assert dialog.patch == {'timeout': 25}


def test_dot_is_painted_only_for_local_customizations_in_both_trees(page, monkeypatch):
    from runner.ui.profile_group_delegate import ProfileGroupDelegate
    from PySide6.QtWidgets import QTreeView
    drawn = []
    original = ProfileGroupDelegate._custom_dot
    def record(self, painter, option, index):
        drawn.append(index.data(YAML_ROLE)['state'])
        original(self, painter, option, index)
    monkeypatch.setattr(ProfileGroupDelegate, '_custom_dot', record)
    page.resize(1400, 950)
    page.show()
    page.sequence_list.expandAll()
    page.sequence_list.grab()
    assert drawn and set(drawn) == {'custom'}
    model = LiveProfileModel()
    model.prepare(page._profile_from_editor(), [Reader('A', 0)])
    view = QTreeView(page)
    view.setModel(model)
    view.setItemDelegate(ProfileGroupDelegate(view))
    view.resize(700, 800)
    view.expandAll()
    drawn.clear()
    view.grab()
    assert drawn and set(drawn) == {'custom'}


def test_tooltip_explains_value_used_and_inherited_value_once(page):
    tooltip = page._step_items()[1].toolTip(0)
    assert 'Value used: T0' in tooltip
    assert 'Inherited value: T1 — Group: Qualification T1' in tooltip
    assert tooltip.count('Value used: T0') == 1
    assert 'Values differing from inheritance' not in tooltip
    assert 'To change values: right-click → Edit YAML parameters…' in tooltip
    model = LiveProfileModel()
    model.prepare(page._profile_from_editor(), [Reader('A', 0)])
    assert 'future runs' in model.index_for_nodeid('1:0').data(Qt.ToolTipRole)


def test_editor_separates_current_value_from_fallback_without_changing_custom_patch(qtbot):
    dialog = StepParametersDialog('test_read', {'timeout': 15}, {'timeout': 75})
    qtbot.addWidget(dialog)
    mode, value = dialog.controls[('timeout',)]
    assert value.text() == '75'
    assert dialog._hints[('timeout',)].text() == 'Without this customization: 15 — Profile'
    mode.setCurrentText('Profile value')
    assert value.text() == '15'
    assert dialog._hints[('timeout',)].text() == 'Defined by: Profile'
    assert dialog.patch == {}
