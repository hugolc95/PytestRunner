"""Les actions d'edition ne replient pas le travail en cours ni ne sautent de ligne."""
import copy

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QLineEdit, QVBoxLayout

from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE, _LABEL_ROLE
from runner.ui.tree_model import NODEID_ROLE


NODES = ['Suite/setup/test_prepare.py::TestCard::test_one',
         'Suite/setup/test_prepare.py::TestCard::test_two',
         'Suite/nominal/test_rsa.py::TestRSA::test_sign[T0]',
         'Suite/nominal/test_rsa.py::TestRSA::test_sign[T1]']
GROUPS = [dict(id=f'g{i}', name=f'Protocol {i}', color='#448aff', description='',
               configuration_overrides={'timeout': 15 + i}) for i in range(3)]


def group(page, identifier):
    return next(item for item, _, _ in page._sequence_ranges()[1]
                if not item.data(0, NODEID_ROLE) and (item.data(0, _GROUP_ROLE) or {}).get('id') == identifier)


def select(page, item):
    page.sequence_list.clearSelection()
    page.sequence_list.setCurrentItem(item)


@pytest.fixture
def page(qtbot, tmp_path):
    p = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(p)
    profile = ExecutionProfile('Protocols', NODES * 3, 'config.yaml', 'timeout: 15\n',
        profile_id=p.current_profile().profile_id,
        step_groups=[copy.deepcopy(metadata) for metadata in GROUPS for _ in NODES])
    p._profiles[p.profile_list.currentRow()] = profile
    p._populate(profile)
    p.resize(1400, 900)
    p.show()
    a = group(p, 'g0')
    a.setExpanded(True)
    a.child(0).setExpanded(True)
    a.child(0).child(0).setExpanded(True)
    a.child(0).child(0).child(0).setExpanded(True)
    group(p, 'g1').setExpanded(False)
    group(p, 'g2').setExpanded(False)
    yield p
    # Le presse-papiers offscreen ne doit pas garder un QMimeData Python
    # jusqu'a la destruction des statiques Qt, apres l'arret de Python.
    payload = p.sequence_clipboard.payload
    if payload and payload['owner'] == p.sequence_clipboard.owner:
        QApplication.clipboard().clear()
    p.close()


def state(page):
    a = group(page, 'g0')
    return (a.isExpanded(), a.child(0).isExpanded(), a.child(0).child(0).isExpanded(),
            group(page, 'g1').isExpanded(), group(page, 'g2').isExpanded())


@pytest.mark.parametrize('action', ['rename', 'yaml', 'duplicate_test', 'remove_test', 'reorder_test',
                                   'reorder_group', 'duplicate_group', 'paste', 'save', 'drop'])
def test_editor_actions_preserve_unaffected_open_and_closed_branches(page, action):
    expected = state(page)
    assert expected == (True, True, True, False, False)
    select(page, group(page, 'g0'))
    if action == 'rename':
        page._apply_group(list(range(4)), dict(GROUPS[0], name='Renamed protocol'), editing=True)
    elif action == 'yaml':
        page._apply_group_yaml('g0', {'timeout': 30})
    elif action == 'duplicate_test':
        select(page, page._step_items()[0])
        page.duplicate_steps()
    elif action == 'remove_test':
        select(page, page._step_items()[1])
        page.remove_steps()
    elif action == 'reorder_test':
        select(page, page._step_items()[0])
        page._move_step(1)
    elif action == 'reorder_group':
        page._move_step(1)
    elif action == 'duplicate_group':
        page.duplicate_steps()
    elif action == 'paste':
        select(page, page._step_items()[0])
        page.copy_elements()
        page.paste_elements()
    elif action == 'save':
        page.save_current()
    else:
        item = page._step_items()[0]
        select(page, item)
        parent = item.parent()
        parent.addChild(parent.takeChild(parent.indexOfChild(item)))
        page._settle_sequence_order()
    assert state(page) == expected
    ids = page._step_ids()
    assert len(ids) == len(set(ids)) == len(page._flatten_sequence())


def test_undo_redo_preserve_later_view_choices_and_restore_removed_expansions(page):
    before = state(page)
    select(page, group(page, 'g0'))
    page._apply_group(list(range(4)), dict(GROUPS[0], name='Renamed'), editing=True)
    group(page, 'g1').setExpanded(True)
    page.undo_stack.undo()
    assert group(page, 'g1').isExpanded()
    assert state(page)[:3] == before[:3]
    page.undo_stack.redo()
    assert group(page, 'g1').isExpanded()
    assert state(page)[:3] == before[:3]
    select(page, group(page, 'g0').child(0))
    page.remove_steps()
    page.undo_stack.undo()
    assert state(page)[:3] == before[:3]


def test_metadata_edit_keeps_the_viewport_anchor(page, qtbot):
    nodes, metadata = [], []
    for index in range(25):
        nodes.extend(NODES)
        metadata.extend([dict(GROUPS[0], id=f'large{index}', name=f'Group {index}')] * len(NODES))
    page._rebuild_sequence(nodes, groups=metadata)
    page.sequence_list.expandAll()
    qtbot.waitUntil(lambda: page.sequence_list.verticalScrollBar().maximum() > 0)
    item = group(page, 'large12')
    select(page, item)
    page.sequence_list.scrollToItem(item, QAbstractItemView.PositionAtTop)
    page.sequence_list.doItemsLayout()
    old_top = page.sequence_list.visualItemRect(item).top()
    _, ranges = page._sequence_ranges()
    start, end = next((start, end) for row, start, end in ranges if row is item)
    page._apply_group(list(range(start, end)), dict(item.data(0, _GROUP_ROLE), name='Renamed group 12'), editing=True)
    item = group(page, 'large12')
    assert abs(page.sequence_list.visualItemRect(item).top() - old_top) <= 1


def test_moving_a_subtree_keeps_its_expansion_and_unrelated_groups_closed(page):
    source = group(page, 'g0').child(0)
    assert source.isExpanded()
    select(page, source)
    page._move_to_target(group(page, 'g1'))
    assert not group(page, 'g2').isExpanded()
    destination = group(page, 'g1')
    # La destination s'ouvre pour montrer l'element deplace, son interieur
    # garde l'etat qu'il avait avant le mouvement.
    assert destination.isExpanded()
    matching = [item for item, _, _ in page._sequence_ranges()[1]
                if item.parent() is destination and item.data(0, _LABEL_ROLE) == 'setup']
    assert matching and any(item.isExpanded() for item in matching)


def test_programmed_focus_does_not_extend_selection_when_control_is_held(page):
    select(page, page._step_items()[0])
    tree = page.sequence_list
    QTest.keyPress(tree, Qt.Key_Control)
    try:
        page._move_step(1)
        assert len(tree.selectedItems()) == 1
        assert tree.selectedItems()[0] is tree.currentItem()
        page._apply_group_yaml('g0', {'timeout': 25})
        assert tree.selectedItems() == [group(page, 'g0')]
    finally:
        QTest.keyRelease(tree, Qt.Key_Control)


def test_real_control_click_still_selects_multiple_groups(page, qtbot):
    tree = page.sequence_list
    page.sequence_list.collapseAll()
    tree.doItemsLayout()
    first, second = group(page, 'g0'), group(page, 'g1')
    qtbot.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, tree.visualItemRect(first).center())
    qtbot.mouseClick(tree.viewport(), Qt.LeftButton, Qt.ControlModifier, tree.visualItemRect(second).center())
    QTest.keyRelease(tree, Qt.Key_Control)
    assert set(tree.selectedItems()) == {first, second}


def focus_tree(page, qtbot):
    page.activateWindow()
    page.sequence_list.setFocus()
    qtbot.waitUntil(page.sequence_list.hasFocus)


@pytest.mark.parametrize('target', ['test', 'case', 'function', 'folder', 'group', 'parent_and_child', 'multiple'])
def test_delete_removes_selection_once_and_control_z_restores_it(page, qtbot, target):
    original = page._profile_from_editor()
    steps = page._step_items()
    if target == 'test':
        item, removed = steps[0], {0}
    elif target == 'case':
        item, removed = steps[2], {2}
    elif target == 'function':
        item, removed = steps[2].parent(), {2, 3}
    elif target == 'folder':
        item, removed = group(page, 'g0').child(0), {0, 1}
    elif target in ('group', 'parent_and_child'):
        item, removed = group(page, 'g0'), {0, 1, 2, 3}
    else:
        item, removed = steps[1], {1, 6}
    select(page, item)
    if target == 'parent_and_child':
        steps[0].setSelected(True)
    elif target == 'multiple':
        steps[6].setSelected(True)
    expected = [node for index, node in enumerate(NODES * 3) if index not in removed]
    focus_tree(page, qtbot)
    QTest.keyClick(page.sequence_list, Qt.Key_Delete)
    assert page._flatten_sequence() == expected
    assert page.undo_stack.count() == 1
    QTest.keyClick(page.sequence_list, Qt.Key_Z, Qt.ControlModifier)
    QTest.keyRelease(page.sequence_list, Qt.Key_Control)
    assert page._profile_from_editor() == original
    QTest.keyClick(page.sequence_list, Qt.Key_Y, Qt.ControlModifier)
    QTest.keyRelease(page.sequence_list, Qt.Key_Control)
    assert page._flatten_sequence() == expected


@pytest.mark.parametrize('field', ['name', 'description'])
def test_delete_keeps_its_text_editing_role_outside_the_tree(page, qtbot, field):
    select(page, group(page, 'g0'))
    before = page._flatten_sequence()
    widget = page.name_edit if field == 'name' else page.description_edit
    if field == 'name':
        widget.setText('abcdef')
        widget.setCursorPosition(2)
    else:
        widget.setPlainText('abcdef')
        cursor = widget.textCursor()
        cursor.setPosition(2)
        widget.setTextCursor(cursor)
    page.activateWindow()
    widget.setFocus()
    qtbot.waitUntil(widget.hasFocus)
    QTest.keyClick(widget, Qt.Key_Delete)
    assert (widget.text() if field == 'name' else widget.toPlainText()) == 'abdef'
    assert page._flatten_sequence() == before


def test_delete_in_a_parameter_dialog_does_not_remove_the_background_selection(page, qtbot):
    select(page, group(page, 'g0'))
    before = page._flatten_sequence()
    dialog = QDialog(page)
    qtbot.addWidget(dialog)
    dialog.setWindowModality(Qt.ApplicationModal)
    line = QLineEdit('abcdef', dialog)
    QVBoxLayout(dialog).addWidget(line)
    dialog.show()
    dialog.activateWindow()
    line.setFocus()
    line.setCursorPosition(2)
    qtbot.waitUntil(line.hasFocus)
    QTest.keyClick(line, Qt.Key_Delete)
    assert line.text() == 'abdef'
    assert page._flatten_sequence() == before
    dialog.close()


def test_delete_with_no_selection_or_in_the_library_does_not_remove_steps(page, qtbot):
    before = page._flatten_sequence()
    page.sequence_list.clearSelection()
    focus_tree(page, qtbot)
    QTest.keyClick(page.sequence_list, Qt.Key_Delete)
    assert page._flatten_sequence() == before
    select(page, group(page, 'g0'))
    page.profile_list.setFocus()
    qtbot.waitUntil(page.profile_list.hasFocus)
    QTest.keyClick(page.profile_list, Qt.Key_Delete)
    assert page._flatten_sequence() == before
    assert page.profile_list.count() == 1


def test_context_menu_shows_the_same_remove_action_and_its_shortcut(page):
    select(page, group(page, 'g0'))
    menu = page._context_menu()
    action = next(action for action in menu.actions() if action.text() == 'Remove')
    assert action is page.remove_action
    assert action.shortcut().toString() == 'Del'
