"""Le point du clic droit reste l'ancrage des ajouts successifs du selecteur."""
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QMenu

from runner.domain.execution_profile import ExecutionProfile, ProfileStore, effective_step_overrides, group_entry, group_path
from runner.ui.execution_profiles_page import ExecutionProfilesPage, AddTestsDialog, _GROUP_ROLE, _LABEL_ROLE
from runner.ui.tree_model import NODEID_ROLE

ROOT = dict(id='t0', name='Protocol T0', color='#448aff', description='',
            configuration_overrides={'protocol': 'T0'})
SUB = dict(id='setup', name='Setup', color='#00a99d', description='',
           configuration_overrides={'timeout': 25})
OTHER = dict(id='other', name='Other checks', color='#a675ed', description='')
NODES = ['outside/test_before.py::test_ok',
         'cards/setup/test_card.py::TestCard::test_init',
         'cards/setup/test_card.py::TestCard::test_write',
         'cards/nominal/test_rsa.py::test_sign[T0]',
         'cards/nominal/test_rsa.py::test_sign[T1]',
         'cards/other/test_other.py::test_ok',
         'outside/test_tail.py::test_ok']
ADD = ['cards/setup/test_new.py::test_added', 'elsewhere/test_extra.py::test_extra']


def named(page, identifier):
    return next(item for item, _, _ in page._sequence_ranges()[1]
                if not item.data(0, NODEID_ROLE) and (item.data(0, _GROUP_ROLE) or {}).get('id') == identifier)


@pytest.fixture
def page(qtbot, tmp_path):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    groups = [{}, *[group_entry([ROOT, SUB]) for _ in range(4)], group_entry([ROOT, OTHER]), {}]
    patches = [{}, {}, {'timeout': 90}, {}, {}, {}, {}]
    profile = ExecutionProfile('Card checks', list(NODES), 'config.yaml', 'protocol: AUTO\ntimeout: 15\n',
        profile_id=page.current_profile().profile_id, step_groups=groups, step_overrides=patches)
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    page.set_workspace_context(NODES + ADD, '')
    named(page, 't0').setExpanded(True)
    named(page, 'setup').setExpanded(True)
    named(page, 'setup').child(0).setExpanded(True)
    named(page, 'other').setExpanded(False)
    page.resize(1400, 1000)
    page.show()
    yield page
    page.close()


def add_action(menu):
    return next(action for action in menu.actions() if action.text() == 'Add tests / groups…')


def test_right_click_uses_clicked_subgroup_even_with_another_current_selection(page, monkeypatch):
    other, target = named(page, 'other'), named(page, 'setup')
    page.sequence_list.setCurrentItem(other)
    target.setSelected(True)
    assert page.sequence_list.currentItem() is other
    seen = []
    def picker(dialog):
        seen.append(dialog.destination_label.text())
        dialog.tests_added.emit([ADD[0]])
        return QDialog.Accepted
    monkeypatch.setattr(AddTestsDialog, 'exec', picker)
    class Menu(QMenu):
        def exec(self, _):
            add_action(self).trigger()
    monkeypatch.setattr('runner.ui.execution_profiles_page.QMenu', Menu)
    page.sequence_list.doItemsLayout()
    page._show_context_menu(page.sequence_list.visualItemRect(target).center())
    assert page._flatten_sequence() == NODES[:5] + [ADD[0]] + NODES[5:]
    assert 'Setup' in seen[0] and 'inside' in seen[0]
    assert [entry['id'] for entry in group_path(page._step_groups()[5])] == ['t0', 'setup']
    assert not named(page, 'other').isExpanded()


def test_repeated_picker_adds_keep_order_yaml_and_occurrence_ids_and_support_undo(page, monkeypatch):
    original = page._profile_from_editor()
    old_ids = page._step_ids()
    def picker(dialog):
        dialog.model.set_checked_nodeids(ADD)
        dialog.add_button.click()
        dialog.add_again_button.click()
        return QDialog.Accepted
    monkeypatch.setattr(AddTestsDialog, 'exec', picker)
    add_action(page._context_menu(named(page, 'setup'))).trigger()
    assert page._flatten_sequence() == NODES[:5] + ADD + ADD + NODES[5:]
    assert page._step_ids()[:5] + page._step_ids()[9:] == old_ids
    assert len(set(page._step_ids())) == len(NODES) + 4
    added = page._profile_from_editor()
    assert effective_step_overrides(added)[5:9] == [{'protocol': 'T0', 'timeout': 25}] * 4
    assert added.step_overrides[2] == {'timeout': 90}
    assert named(page, 'setup').isExpanded()
    assert not named(page, 'other').isExpanded()
    assert page.undo_stack.count() == 2
    page.undo_stack.undo()
    assert page._flatten_sequence() == NODES[:5] + ADD + NODES[5:]
    page.undo_stack.undo()
    assert page._profile_from_editor() == original
    page.undo_stack.redo()
    page.undo_stack.redo()
    assert page._profile_from_editor() == added


@pytest.mark.parametrize('kind', ['root_group', 'subgroup', 'folder', 'file', 'parameterized', 'test'])
def test_toolbar_inserts_at_the_selected_item(page, monkeypatch, kind):
    sub = named(page, 'setup')
    if kind == 'root_group':
        target, end, path = named(page, 't0'), 6, ['t0']
    elif kind == 'subgroup':
        target, end, path = sub, 5, ['t0', 'setup']
    elif kind == 'folder':
        target, end, path = sub.child(0), 3, ['t0', 'setup']
    elif kind == 'file':
        target, end, path = sub.child(0).child(0), 3, ['t0', 'setup']
    elif kind == 'parameterized':
        target, end, path = page._step_items()[3].parent(), 5, ['t0', 'setup']
    else:
        target, end, path = page._step_items()[1], 2, ['t0', 'setup']
    page.sequence_list.setCurrentItem(target)
    def picker(dialog):
        assert dialog.destination_label.text()
        dialog.tests_added.emit([ADD[1]])
        return QDialog.Accepted
    monkeypatch.setattr(AddTestsDialog, 'exec', picker)
    page.add_tests_button.click()
    assert page._flatten_sequence() == NODES[:end] + [ADD[1]] + NODES[end:]
    assert [entry['id'] for entry in group_path(page._step_groups()[end])] == path


@pytest.mark.parametrize('background_menu', [False, True])
def test_no_selection_or_background_context_adds_at_profile_end(page, monkeypatch, background_menu):
    page.sequence_list.setCurrentItem(named(page, 'setup'))
    def picker(dialog):
        assert dialog.destination_label.text() == 'Destination: end of profile'
        dialog.tests_added.emit([ADD[0]])
        return QDialog.Accepted
    monkeypatch.setattr(AddTestsDialog, 'exec', picker)
    if background_menu:
        class Menu(QMenu):
            def exec(self, _):
                add_action(self).trigger()
        monkeypatch.setattr('runner.ui.execution_profiles_page.QMenu', Menu)
        point = QPoint(5, page.sequence_list.viewport().height() - 3)
        assert page.sequence_list.itemAt(point) is None
        page._show_context_menu(point)
    else:
        page.sequence_list.clearSelection()
        page.add_tests_button.click()
    assert page._flatten_sequence() == NODES + [ADD[0]]
    assert page._step_groups()[-1] == {}


def test_cancel_picker_preserves_data_expansion_and_history(page, monkeypatch):
    original, ids = page._profile_from_editor(), page._step_ids()
    monkeypatch.setattr(AddTestsDialog, 'exec', lambda _: QDialog.Rejected)
    add_action(page._context_menu(named(page, 'setup'))).trigger()
    assert page._profile_from_editor() == original
    assert page._step_ids() == ids
    assert page.undo_stack.count() == 0
    assert named(page, 'setup').isExpanded() and not named(page, 'other').isExpanded()


def test_add_context_action_requires_a_collected_workspace(page):
    page.set_workspace_context([], '')
    assert not add_action(page._context_menu(named(page, 'setup'))).isEnabled()


def test_occurrence_limit_rejects_addition_without_mutation(page, monkeypatch):
    original = page._profile_from_editor()
    notices = []
    monkeypatch.setattr('runner.ui.execution_profiles_page.MAX_STEPS', len(NODES))
    monkeypatch.setattr(page, '_show_notice', lambda text, warning: notices.append(text))
    assert not page._insert_tests([ADD[0]], 3, [ROOT, SUB])
    assert page._profile_from_editor() == original
    assert notices and page.undo_stack.count() == 0


def test_first_addition_to_an_empty_profile_works_and_can_be_undone(page, monkeypatch):
    page._rebuild_sequence([])
    def picker(dialog):
        dialog.tests_added.emit([ADD[0]])
        return QDialog.Accepted
    monkeypatch.setattr(AddTestsDialog, 'exec', picker)
    add_action(page._context_menu(None)).trigger()
    assert page._flatten_sequence() == [ADD[0]]
    page.undo_stack.undo()
    assert page._flatten_sequence() == []
