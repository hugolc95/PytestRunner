"""Copier/coller garde chaque occurrence, sa hierarchie et ses parametres."""
import copy
import datetime
import json

import pytest
import yaml
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtWidgets import QApplication, QDialog

from runner.domain.execution_profile import (
    ExecutionProfile, ProfileStore, ProfileValidationError, effective_step_overrides, group_entry, group_path,
)
from runner.domain.profile_clipboard import MIME, MAX_BYTES, decode_selection, encode_selection, inherited_base
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE, _KIND_ROLE, _OVERRIDES_ROLE
from runner.ui.profile_dialogs import PasteSequenceDialog
from runner.ui.profile_group_delegate import TRANSFER_ROLE
from runner.ui.tree_model import NODEID_ROLE

NODES = ['Card/Setup/test_prepare.py::test_connect', 'Card/Setup/test_prepare.py::test_read',
         'Card/Personalization/test_keys.py::test_write',
         'Security/test_pin.py::test_pin[valid]', 'Security/test_pin.py::test_pin[invalid]']
ROOT = dict(id='t0', name='Qualification T0', color='#448aff', description='Full T0 sequence',
            configuration_overrides={'card': {'protocol': 'T0'}})
CHILD = dict(id='setup', name='Preparation', color='#00a99d', description='Prepare the card',
             configuration_overrides={'card': {'timeout': 20}})
BASE = dict(Reader='Reader A', card=dict(protocol='T0', timeout=15))
PATCHES = [{}, {'card': {'protocol': 'T1'}}, {}, {}, {'card': {'timeout': 50}}]


@pytest.fixture(scope='session', autouse=True)
def synthetic_clipboard_lifetime(qapp):
    yield
    # Qt offscreen plante a la destruction si un QMimeData Python reste
    # dans son presse-papiers virtuel, meme sans notre application.
    if qapp.platformName() == 'offscreen':
        qapp.clipboard().clear()


@pytest.fixture
def clipboard(qapp):
    clipboard = qapp.clipboard()
    old = QMimeData()
    source = clipboard.mimeData()
    if source is not None:
        for name in source.formats():
            old.setData(name, source.data(name))
    clipboard.clear()
    yield clipboard
    if old.formats():
        clipboard.setMimeData(old)
    else:
        clipboard.clear()


def populate(page, *, name='Card qualification', protocol='T0'):
    base = copy.deepcopy(BASE)
    base['card']['protocol'] = protocol
    profile = ExecutionProfile(name, NODES.copy(), 'config.yaml', yaml.safe_dump(base),
                               profile_id=page.current_profile().profile_id,
                               step_overrides=copy.deepcopy(PATCHES),
                               step_groups=[group_entry([ROOT, CHILD])] * 2 + [ROOT] * 3)
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    page.set_workspace_context(NODES, '')


@pytest.fixture
def page(qtbot, tmp_path, clipboard):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    populate(page)
    return page


def data(page):
    value = page._profile_from_editor()
    return value.sequence, value.step_overrides, value.step_groups


def select_root(page):
    page.sequence_list.clearSelection()
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))


def test_copy_group_is_readonly_and_paste_preserves_complete_independent_hierarchy(page, clipboard):
    before = data(page)
    select_root(page)
    page.copy_elements()
    assert data(page) == before and page.undo_stack.count() == 0
    assert clipboard.text().splitlines() == NODES
    assert page.sequence_list.topLevelItem(0).data(0, TRANSFER_ROLE) == 'copied'
    assert 'Copied 1 group' in page.transfer_label.text()
    page.paste_elements()
    profile = page._profile_from_editor()
    assert profile.sequence == NODES * 2
    assert profile.step_overrides == PATCHES * 2
    first, second = group_path(profile.step_groups[0]), group_path(profile.step_groups[5])
    assert first[0]['id'] != second[0]['id'] and first[1]['id'] != second[1]['id']
    assert [{key: value for key, value in group.items() if key != 'id'} for group in first] == [
        {key: value for key, value in group.items() if key != 'id'} for group in second]
    assert page.sequence_list.topLevelItem(1).data(0, TRANSFER_ROLE) == 'pasted'
    assert 'Pasted 1 element' in page.transfer_label.text()
    assert page.undo_stack.count() == 1
    pasted = data(page)
    page.undo_stack.undo()
    assert data(page) == before and clipboard.mimeData().hasFormat(MIME)
    page.undo_stack.redo()
    assert data(page) == pasted


def test_repeated_pastes_make_siblings_with_fresh_group_ids(page):
    select_root(page)
    page.copy_elements()
    page.paste_elements()
    page.paste_elements()
    assert page._flatten_sequence() == NODES * 3
    tree = page.sequence_list
    assert tree.topLevelItemCount() == 3
    assert len({tree.topLevelItem(i).data(0, _GROUP_ROLE)['id'] for i in range(3)}) == 3


def test_copy_is_a_snapshot_even_after_original_yaml_changes(page):
    select_root(page)
    page.copy_elements()
    page._apply_group_yaml('t0', {'card': {'protocol': 'T1'}})
    select_root(page)
    page.paste_elements()
    profile = page._profile_from_editor()
    assert group_path(profile.step_groups[0])[0]['configuration_overrides']['card']['protocol'] == 'T1'
    assert group_path(profile.step_groups[5])[0]['configuration_overrides']['card']['protocol'] == 'T0'
    assert profile.step_overrides == PATCHES * 2


def test_subgroup_copy_does_not_copy_its_parent_and_keeps_parameter_overrides(page):
    group = page.sequence_list.topLevelItem(0).child(0)
    page.sequence_list.setCurrentItem(group)
    page.copy_elements()
    page.paste_elements()
    profile = page._profile_from_editor()
    assert profile.sequence == NODES[:2] + NODES[:2] + NODES[2:]
    assert profile.step_overrides == PATCHES[:2] + PATCHES[:2] + PATCHES[2:]
    original, pasted = group_path(profile.step_groups[0]), group_path(profile.step_groups[2])
    assert original[0]['id'] == pasted[0]['id'] == 't0'
    assert original[1]['id'] != pasted[1]['id']
    assert page.sequence_list.topLevelItemCount() == 1


def test_parent_and_child_selection_is_copied_only_once_and_mixed_selection_keeps_order(page):
    root = page.sequence_list.topLevelItem(0)
    root.setSelected(True)
    page._step_items()[0].setSelected(True)
    page.copy_elements()
    assert len(page.sequence_clipboard.payload['items']) == 1
    page.sequence_list.clearSelection()
    root.child(0).setSelected(True)
    page._step_items()[-1].setSelected(True)
    page.copy_elements()
    items = page.sequence_clipboard.payload['items']
    assert [item['sequence'] for item in items] == [NODES[:2], NODES[-1:]]
    assert [item['kind'] for item in items] == ['group', 'case']


def test_parameterized_test_and_single_case_are_independently_copyable(page):
    _, ranges = page._sequence_ranges()
    item = next(item for item, _, _ in ranges if item.data(0, _KIND_ROLE) == 'test')
    page.sequence_list.setCurrentItem(item)
    page.copy_elements()
    assert page.sequence_clipboard.payload['items'][0]['kind'] == 'parameterized'
    page.paste_elements()
    assert page._flatten_sequence() == NODES + NODES[-2:]
    assert page._step_patches()[-2:] == PATCHES[-2:]
    assert len(page.sequence_list.selectedItems()) == 2
    page.sequence_list.setCurrentItem(page._step_items()[-1])
    page.copy_elements()
    assert page.sequence_clipboard.payload['items'][0]['kind'] == 'case'
    page.paste_elements()
    assert page._flatten_sequence()[-1] == NODES[-1]
    assert page._step_patches()[-1] == PATCHES[-1]


def test_paste_into_another_group_previews_inheritance_cancel_then_accept(page, monkeypatch):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.copy_elements()
    original = data(page)
    # Ce test herite de timeout=20 dans Preparation ; la racine donne 15.
    select_root(page)
    seen = []
    def cancel(dialog):
        from PySide6.QtWidgets import QLabel
        text = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
        assert 'card.timeout: 20 → 15' in text
        seen.append(text)
        return QDialog.Rejected
    monkeypatch.setattr(PasteSequenceDialog, 'exec', cancel)
    page.paste_elements(into_group=True)
    assert seen and data(page) == original and page.undo_stack.count() == 0
    monkeypatch.setattr(PasteSequenceDialog, 'exec', lambda self: QDialog.Accepted)
    page.paste_elements(into_group=True)
    assert page._flatten_sequence() == NODES + NODES[:1]
    assert len(group_path(page._step_groups()[-1])) == 1
    assert page.sequence_list.topLevelItemCount() == 1


def test_paste_between_profiles_keeps_clipboard_and_uses_destination_context(page, qtbot, tmp_path, monkeypatch):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.copy_elements()
    other = ExecutionProfilesPage(ProfileStore(tmp_path / 'other'))
    qtbot.addWidget(other)
    populate(other, name='Other profile', protocol='T1')
    other._apply_group_yaml('t0', {'card': {'protocol': 'T1'}})
    select_root(other)
    monkeypatch.setattr(PasteSequenceDialog, 'exec', lambda self: QDialog.Accepted)
    other.paste_elements(into_group=True)
    assert effective_step_overrides(other._profile_from_editor())[-1]['card']['protocol'] == 'T1'
    assert page._flatten_sequence() == NODES
    assert other._step_patches()[-1] == {}


def test_text_copy_paste_shortcuts_keep_their_native_behavior(page, qtbot, clipboard):
    page.resize(1300, 800)
    page.show()
    page.activateWindow()
    select_root(page)
    page.sequence_list.setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is page and page.sequence_list.hasFocus())
    qtbot.keyClick(page.sequence_list, Qt.Key_C, Qt.ControlModifier)
    assert clipboard.mimeData().hasFormat(MIME)
    page.name_edit.setText('Native text')
    page.name_edit.setFocus()
    page.name_edit.selectAll()
    qtbot.keyClick(page.name_edit, Qt.Key_C, Qt.ControlModifier)
    assert clipboard.text() == 'Native text' and not clipboard.mimeData().hasFormat(MIME)
    assert not page.sequence_clipboard.paste_action.isEnabled()
    assert not page.transfer_label.isVisible()
    page.description_edit.setFocus()
    page.description_edit.clear()
    qtbot.keyClick(page.description_edit, Qt.Key_V, Qt.ControlModifier)
    assert page.description_edit.toPlainText() == 'Native text'
    assert page._flatten_sequence() == NODES


def test_shortcuts_copy_paste_undo_and_paste_inside(page, qtbot):
    page.resize(1300, 800)
    page.show()
    page.activateWindow()
    select_root(page)
    page.sequence_list.setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is page and page.sequence_list.hasFocus())
    qtbot.keyClick(page.sequence_list, Qt.Key_C, Qt.ControlModifier)
    qtbot.keyClick(page.sequence_list, Qt.Key_V, Qt.ControlModifier)
    assert page._flatten_sequence() == NODES * 2
    qtbot.keyClick(page.sequence_list, Qt.Key_Z, Qt.ControlModifier)
    assert page._flatten_sequence() == NODES


def test_external_clipboard_change_clears_marks_and_duplicate_notifications_do_not(page, clipboard):
    select_root(page)
    page.copy_elements()
    root = page.sequence_list.topLevelItem(0)
    clipboard.dataChanged.emit()
    assert root.data(0, TRANSFER_ROLE) == 'copied'
    clipboard.setText('ordinary text')
    assert root.data(0, TRANSFER_ROLE) is None
    assert not page.sequence_clipboard.paste_action.isEnabled()


def test_flash_marks_are_transient_but_pasted_selection_and_clipboard_remain(page):
    select_root(page)
    page.copy_elements()
    page.paste_elements()
    pasted = page.sequence_list.topLevelItem(1)
    assert pasted.data(0, TRANSFER_ROLE) == 'pasted'
    page.sequence_clipboard.feedback_timer.timeout.emit()
    assert pasted.data(0, TRANSFER_ROLE) is None
    assert pasted.isSelected()
    assert page.sequence_clipboard.paste_action.isEnabled()


def test_missing_workspace_tests_require_confirmation_but_are_not_dropped(page, monkeypatch):
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.copy_elements()
    page.set_workspace_context(NODES[1:], '')
    seen = []
    def confirm(dialog):
        seen.append(dialog.paste_button.text())
        return QDialog.Accepted
    monkeypatch.setattr(PasteSequenceDialog, 'exec', confirm)
    page.paste_elements()
    assert seen == ['Paste anyway']
    assert page._flatten_sequence().count(NODES[0]) == 2


def test_paste_limits_and_invalid_clipboard_do_not_modify_profile(page, monkeypatch, clipboard):
    select_root(page)
    page.copy_elements()
    before = data(page)
    monkeypatch.setattr('runner.ui.profile_clipboard.MAX_STEPS', len(NODES))
    page.paste_elements()
    assert data(page) == before and not page.undo_stack.canUndo()
    assert page.transfer_label.text() == 'Could not paste'
    mime = QMimeData()
    mime.setData(MIME, b'{invalid')
    clipboard.setMimeData(mime)
    assert not page.sequence_clipboard.paste_action.isEnabled()
    page.paste_elements()
    assert data(page) == before


def test_numeric_and_date_inherited_yaml_values_survive_clipboard(page):
    current = page.current_profile()
    current.configuration_text += 'date: 2026-10-28\ncodes:\n  0: zero\n'
    page._populate(current)
    select_root(page)
    page.copy_elements()
    payload = decode_selection(bytes(QApplication.clipboard().mimeData().data(MIME)))
    base = inherited_base(payload, payload['items'][0])
    assert base['date'] == datetime.date(2026, 10, 28)
    assert base['codes'] == {0: 'zero'}


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(version=2),
    lambda p: p['items'][0].update(kind=[]),
    lambda p: p['items'][0].update(base=True),
    lambda p: p['items'][0]['sequence'].__setitem__(0, '../unsafe.py::test_a'),
    lambda p: p['items'][0].update(patches=[]),
    lambda p: p['bases'].__setitem__(0, 'a: &a {b: *a}'),
    lambda p: p.update(source='\ud800'),
    lambda p: p['items'][0]['patches'].__setitem__(0, {'timeout': float('nan')}),
])
def test_malformed_structured_payload_is_rejected(page, mutation):
    select_root(page)
    page.copy_elements()
    payload = copy.deepcopy(page.sequence_clipboard.payload)
    mutation(payload)
    with pytest.raises(ProfileValidationError):
        encode_selection(payload)
    with pytest.raises(ProfileValidationError):
        decode_selection(json.dumps(payload, ensure_ascii=True, allow_nan=True).encode('utf-8'))


def test_oversized_payload_is_rejected_before_parsing():
    with pytest.raises(ProfileValidationError):
        decode_selection(b' ' * (MAX_BYTES + 1))


@pytest.mark.parametrize('kind', ['folder', 'module', 'class'])
def test_workspace_folder_module_and_class_copy_keep_all_descendants(page, kind):
    nodes = ['Suite/Nominal/test_card.py::TestCard::test_one',
             'Suite/Nominal/test_card.py::TestCard::test_two',
             'Suite/Nominal/test_card.py::TestOther::test_three',
             'Suite/Nominal/test_more.py::test_four', 'Suite/Other/test_last.py::test_five']
    profile = ExecutionProfile('Folder tree', nodes, 'config.yaml', yaml.safe_dump(BASE),
                               profile_id=page.current_profile().profile_id)
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    page.set_workspace_context(nodes, '')
    _, ranges = page._sequence_ranges()
    item, start, end = next(row for row in ranges if row[0].data(0, _KIND_ROLE) == kind)
    selected = nodes[start:end]
    page.sequence_list.setCurrentItem(item)
    page.copy_elements()
    assert page.sequence_clipboard.payload['items'][0]['kind'] == kind
    assert page.sequence_clipboard.payload['items'][0]['sequence'] == selected
    page.paste_elements()
    assert page._flatten_sequence() == nodes[:end] + selected + nodes[end:]


def test_copy_failure_keeps_previous_system_clipboard(page, clipboard):
    clipboard.setText('Keep this text')
    select_root(page)
    page.config_edit.setProperty('fullPath', '/missing/profile/config.yaml')
    page.copy_elements()
    assert clipboard.text() == 'Keep this text'
    assert page.transfer_label.text() == 'Could not copy'


def test_paste_depth_limit_is_checked_before_mutation(page):
    select_root(page)
    page.copy_elements()
    path = [dict(id=f'depth-{index}', name=f'Level {index}', color='#448aff', description='') for index in range(20)]
    profile = ExecutionProfile('Deep hierarchy', NODES.copy(), 'config.yaml', yaml.safe_dump(BASE),
                               profile_id=page.current_profile().profile_id,
                               step_groups=[group_entry(path)] * len(NODES))
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    _, ranges = page._sequence_ranges()
    deepest = next(item for item, _, _ in ranges if (item.data(0, _GROUP_ROLE) or {}).get('id') == 'depth-19' and not item.data(0, NODEID_ROLE))
    page.sequence_list.setCurrentItem(deepest)
    before = data(page)
    page.paste_elements(into_group=True)
    assert data(page) == before and not page.undo_stack.canUndo()
    assert '20 nested levels' in page.transfer_label.toolTip()


def test_paste_into_group_shortcut_is_explicit_and_keeps_destination(page, qtbot):
    page.resize(1300, 800)
    page.show()
    page.activateWindow()
    page.sequence_list.setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is page and page.sequence_list.hasFocus())
    page._expand_groups()
    page.sequence_list.setCurrentItem(page._step_items()[2])
    qtbot.keyClick(page.sequence_list, Qt.Key_C, Qt.ControlModifier)
    select_root(page)
    assert page.sequence_clipboard.paste_into_action.isEnabled()
    qtbot.keyClick(page.sequence_list, Qt.Key_V, Qt.ControlModifier | Qt.ShiftModifier)
    assert page._flatten_sequence() == NODES + NODES[2:3]
    assert page.sequence_list.topLevelItemCount() == 1


def test_paste_follows_the_last_selected_range_even_if_focus_is_on_the_first(page):
    group = page.sequence_list.topLevelItem(0).child(0)
    page.sequence_list.setCurrentItem(group)
    page._step_items()[-1].setSelected(True)
    page.copy_elements()
    page.paste_elements()
    assert page._flatten_sequence() == NODES + NODES[:2] + NODES[-1:]
    assert page._step_patches() == PATCHES + PATCHES[:2] + PATCHES[-1:]
