import json
import sys

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QComboBox, QMenu

from runner.domain.disabled_tests import DisabledTestsStore, DisabledTestsError, matching_record
from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.workspace import Workspace
from runner.domain.tree import build_tree, collapse_single_class
from runner.ui.disabled_tests import DisableTestDialog, DisabledTestsDialog
from runner.ui.main_window import MainWindow
from runner.ui.tree_model import TestTreeModel


NODES = ['test_card.py::test_erase', 'test_card.py::test_read',
         'test_card.py::test_protocol[T0]', 'test_card.py::test_protocol[T1]']


def test_store_persists_per_workspace_and_records_reactivation(tmp_path):
    root = tmp_path / 'registry'
    store = DisabledTestsStore(root)
    workspace = str(tmp_path / 'suite')
    store.disable(workspace, NODES[0], 'Destructive: erased once already.')
    restored = DisabledTestsStore(root)
    assert restored.records(workspace)[NODES[0]]['reason'] == 'Destructive: erased once already.'
    assert restored.records(str(tmp_path / 'other')) == {}
    restored.enable(workspace, NODES[0])
    assert restored.records(workspace) == {}
    data = json.loads(store.path(workspace).read_text(encoding='utf-8'))
    assert [e['action'] for e in data['events']] == ['disable', 'enable']
    assert all(e['author'] and e['date'] for e in data['events'])


def test_reason_is_optional_and_empty_reason_is_persisted(tmp_path):
    store = DisabledTestsStore(tmp_path)
    store.disable(str(tmp_path), NODES[0], '   ')
    assert store.records(str(tmp_path))[NODES[0]]['reason'] == ''


def test_corrupt_registry_is_never_silently_reset(tmp_path):
    store = DisabledTestsStore(tmp_path / 'registry')
    store.disable(str(tmp_path), NODES[0], 'Destructive')
    store.path(str(tmp_path)).write_text('{broken', encoding='utf-8')
    with pytest.raises(DisabledTestsError):
        store.records(str(tmp_path))
    with pytest.raises(DisabledTestsError):
        store.disable(str(tmp_path), NODES[1], 'Another reason')
    assert store.path(str(tmp_path)).read_text(encoding='utf-8') == '{broken'


def test_function_exclusion_covers_new_parameter_cases(tmp_path):
    store = DisabledTestsStore(tmp_path / 'registry')
    base = NODES[2].split('[', 1)[0]
    store.disable(str(tmp_path), base, 'Do not negotiate protocols again')
    records = store.records(str(tmp_path))
    assert matching_record(records, NODES[2])
    assert matching_record(records, NODES[3])
    assert matching_record(records, base + '[future]')
    assert matching_record(records, NODES[1]) is None


@pytest.mark.parametrize('target, covered, unrelated', [
    ('suite', 'suite/new/test_card.py::TestCard::test_future[x]', 'suite2/test_card.py::test_future'),
    ('suite/test_card.py', 'suite/test_card.py::FutureClass::test_future', 'suite/test_card.py.bak::test_future'),
    ('suite/test_card.py::TestCard', 'suite/test_card.py::TestCard::test_future', 'suite/test_card.py::TestCardExtra::test_future'),
    ('suite/test_card.py::TestCard::test_future', 'suite/test_card.py::TestCard::test_future[new]', 'suite/test_card.py::TestCard::test_future_extra'),
])
def test_group_exclusions_cover_future_descendants_with_exact_boundaries(tmp_path, target, covered, unrelated):
    store = DisabledTestsStore(tmp_path / 'registry')
    store.disable(str(tmp_path), target)
    records = store.records(str(tmp_path))
    assert matching_record(records, covered)
    assert not matching_record(records, unrelated)


def test_all_visible_tree_levels_have_stable_scope_identifiers(qtbot):
    model = TestTreeModel()
    nodes = ['suite/test_a.py::Outer::Inner::test_x[http::one]',
             'suite/test_a.py::Outer::Inner::test_x[two]',
             'suite/test_a.py::Other::test_y', 'suite/sub/test_b.py::test_z']
    model.set_tree(collapse_single_class(build_tree(nodes)))
    assert set(model.activation_targets()) == {
        'suite', 'suite/test_a.py', 'suite/test_a.py::Outer',
        'suite/test_a.py::Outer::Inner', 'suite/test_a.py::Outer::Inner::test_x',
        *nodes, 'suite/test_a.py::Other', 'suite/sub', 'suite/sub/test_b.py'}


def test_enabling_a_group_preserves_separately_disabled_cases(tmp_path):
    store = DisabledTestsStore(tmp_path / 'registry')
    store.disable(str(tmp_path), NODES[2], 'One case')
    store.disable(str(tmp_path), 'test_card.py::test_protocol', 'All cases')
    store.enable(str(tmp_path), 'test_card.py::test_protocol')
    assert matching_record(store.records(str(tmp_path)), NODES[2])
    assert not matching_record(store.records(str(tmp_path)), NODES[3])


def test_failed_write_preserves_saved_exclusions(tmp_path, monkeypatch):
    store = DisabledTestsStore(tmp_path / 'registry')
    store.disable(str(tmp_path), NODES[0], 'Original')
    def denied(*_):
        raise PermissionError('Read-only registry')
    monkeypatch.setattr('pathlib.Path.replace', denied)
    with pytest.raises(DisabledTestsError):
        store.enable(str(tmp_path), NODES[0])
    assert store.records(str(tmp_path))[NODES[0]]['reason'] == 'Original'


def test_enabled_subgroup_overrides_folder_for_future_children(tmp_path):
    store = DisabledTestsStore(tmp_path / 'registry')
    workspace = str(tmp_path)
    store.disable(workspace, 'suite')
    store.disable(workspace, 'suite/test_a.py::test_dangerous')
    store.enable(workspace, 'suite/test_a.py')
    records = store.records(workspace)
    assert not matching_record(records, 'suite/test_a.py::test_future[new]')
    assert matching_record(records, 'suite/test_a.py::test_dangerous')
    assert matching_record(records, 'suite/test_b.py::test_other')
    store.disable(workspace, 'suite')
    assert 'suite/test_a.py' not in store.records(workspace)
    assert matching_record(store.records(workspace), 'suite/test_a.py::test_future[new]')


def test_individual_exception_can_be_disabled_again(tmp_path):
    store = DisabledTestsStore(tmp_path / 'registry')
    workspace = str(tmp_path)
    store.disable(workspace, 'test_card.py')
    store.enable(workspace, NODES[0])
    assert not matching_record(store.records(workspace), NODES[0])
    store.disable(workspace, NODES[0])
    assert matching_record(store.records(workspace), NODES[0])


def test_bulk_write_failure_leaves_all_previous_decisions_intact(tmp_path, monkeypatch):
    store = DisabledTestsStore(tmp_path / 'registry')
    workspace = str(tmp_path)
    store.disable(workspace, 'test_card.py')
    store.enable(workspace, NODES[0])
    previous = store.records(workspace)
    def denied(*_):
        raise PermissionError('Read-only registry')
    monkeypatch.setattr('pathlib.Path.replace', denied)
    with pytest.raises(DisabledTestsError):
        store.set_many(workspace, ['test_card.py', *NODES], enabled=True)
    assert store.records(workspace) == previous


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    monkeypatch.setattr('runner.ui.main_window.QSettings', lambda *_: settings)
    monkeypatch.setattr('runner.domain.history.dossier', lambda: tmp_path / 'history')
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    monkeypatch.setattr(MainWindow, '_refresh_primary_reader', lambda *_, **__: None)
    w = MainWindow()
    qtbot.addWidget(w)
    w.workspace = Workspace.load(str(tmp_path))
    w.workspace_combo.setCurrentText(str(tmp_path))
    w._interpreter_override = sys.executable
    w._on_collected(Collection(tuple(NODES)))
    w.show()
    w.errors = []
    monkeypatch.setattr('runner.ui.disabled_tests.ErrorDialog.show_error',
                        lambda *args: w.errors.append(args))
    yield w
    w.close()


def test_icon_selection_and_button_visibility(window):
    controller = window.disabled_tests
    columns = window.model.columnCount()
    header_size = window.run_header.size()
    assert controller.button.isHidden()
    controller.disable(NODES[0], 'Destructive test')
    index = window.model.index_for_nodeid(NODES[0])
    assert not controller.button.isHidden()
    assert window.model.columnCount() == columns
    assert window.run_header.size() == header_size
    assert not (window.model.flags(index) & Qt.ItemIsUserCheckable)
    assert window.model.data(index, Qt.CheckStateRole) == Qt.Unchecked
    assert 'Destructive test' in window.model.data(index, Qt.ToolTipRole)
    assert not window.model.setData(index, Qt.Checked, Qt.CheckStateRole)
    window.model.set_all_checked(True)
    assert NODES[0] not in window.model.checked_nodeids()
    window.model.set_checked_nodeids(NODES)
    assert NODES[0] not in window.model.checked_nodeids()
    window.model.setData(window.model.index(0, 0), Qt.Checked, Qt.CheckStateRole)
    assert NODES[0] not in window.model.checked_nodeids()
    controller.enable(NODES[0])
    assert controller.button.isHidden()
    assert window.model.flags(index) & Qt.ItemIsUserCheckable
    assert NODES[0] not in window.model.checked_nodeids()


def test_disable_dialog_accepts_optional_reason_and_preserves_parameter_scope(qtbot):
    dialog = DisableTestDialog(NODES, NODES[2])
    qtbot.addWidget(dialog)
    assert dialog.disable_button.isEnabled()
    dialog.reason.setPlainText('Destructive')
    assert dialog.disable_button.isEnabled()
    dialog.accept()
    assert dialog.target() == 'test_card.py::test_protocol'
    dialog.all_cases.setChecked(False)
    assert dialog.target() == NODES[2]


def test_new_tab_and_recollection_keep_workspace_exclusions(window):
    window.disabled_tests.disable('test_card.py::test_protocol', 'Protocol changes card state')
    draft = window.run_tabs.new_run()
    assert draft.disabled_tests.store is window.disabled_tests.store
    draft.model.set_all_checked(True)
    assert draft.model.checked_nodeids() == NODES[:2]
    window._on_collected(Collection(tuple(NODES + ['test_card.py::test_protocol[new]'])))
    window.model.set_all_checked(True)
    assert window.model.checked_nodeids() == NODES[:2]
    draft.disabled_tests.enable('test_card.py::test_protocol')
    assert not window.model._disabled
    assert not draft.model._disabled
    assert draft.disabled_tests.button.isHidden()


def test_switching_workspace_does_not_carry_disabled_selection_to_another_suite(window, tmp_path):
    window.disabled_tests.disable(NODES[0], 'Only disabled in the first workspace')
    other = tmp_path / 'other-suite'
    other.mkdir()
    window.workspace = Workspace.load(str(other))
    window.workspace_combo.setCurrentText(str(other))
    window._on_collected(Collection(tuple(NODES)))
    assert window.model.checked_nodeids() == NODES
    assert not window.disabled_tests.records
    assert window.disabled_tests.button.isHidden()


def test_disable_menu_and_detail(window):
    window.disabled_tests.disable(NODES[0], 'Must not erase again')
    menu = QMenu()
    window._construire_menu_test(menu, NODES[0])
    assert any(a.text() == 'Activate test' for a in menu.actions())
    assert not next(a for a in menu.actions() if a.text() == 'Run only this test').isEnabled()
    index = window.model.index_for_nodeid(NODES[0])
    window.tree.setCurrentIndex(index)
    window._select_test(index)
    page = window.results.detail.stack.currentWidget()
    assert page.reason.toPlainText() == 'Must not erase again'
    page.enable.click()
    assert not window.disabled_tests.records
    assert window.results.detail.stack.currentWidget() is not page


def test_module_group_menu_disables_all_children_and_survives_new_collection(window):
    index = window.model.index(0, 0)
    target = window.model.activation_target(index)
    assert target == 'test_card.py'
    menu = QMenu()
    window._construire_menu_groupe(menu, index)
    assert any(action.text() == 'Deactivate group…' for action in menu.actions())
    window.disabled_tests.disable(target, '')
    assert window.model.checked_nodeids() == []
    assert not (window.model.flags(index) & Qt.ItemIsUserCheckable)
    assert 'No reason provided' in window.model.data(index, Qt.ToolTipRole)
    window._on_collected(Collection(tuple(NODES + ['test_card.py::test_new'])))
    window.model.set_all_checked(True)
    assert window.model.checked_nodeids() == []
    menu = QMenu()
    window._construire_menu_groupe(menu, window.model.index(0, 0))
    assert any(action.text() == 'Activate group' for action in menu.actions())
    window.disabled_tests.enable(target)
    window.model.set_all_checked(True)
    assert window.model.checked_nodeids() == NODES + ['test_card.py::test_new']


def test_manager_reenables_and_can_undo_without_author_filter(window, qtbot):
    controller = window.disabled_tests
    controller.disable(NODES[0], 'Destructive')
    dialog = DisabledTestsDialog(controller)
    qtbot.addWidget(dialog)
    assert dialog.table.columnCount() == 3
    assert not dialog.findChildren(QComboBox)
    toggle = dialog._items[NODES[0]]
    assert toggle.checkState(2) == Qt.Unchecked
    toggle.setCheckState(2, Qt.Checked)
    qtbot.waitUntil(lambda: dialog._items[NODES[0]].checkState(2) == Qt.Checked)
    assert controller.button.isHidden()
    assert dialog.table.topLevelItemCount() == 1
    dialog._items[NODES[0]].setCheckState(2, Qt.Unchecked)
    assert matching_record(controller.records, NODES[0])


def test_reactivated_child_overrides_disabled_parent_and_survives_reload(window, qtbot):
    controller = window.disabled_tests
    controller.disable(NODES[0], 'Individual exclusion')
    controller.disable('test_card.py', '')
    dialog = DisabledTestsDialog(controller)
    qtbot.addWidget(dialog)
    assert set(NODES).issubset(dialog._items)
    assert dialog._items[NODES[0]].parent() is dialog._items['test_card.py']
    dialog._items[NODES[0]].setCheckState(2, Qt.Checked)
    qtbot.waitUntil(lambda: dialog._items[NODES[0]].checkState(2) == Qt.Checked)
    restored = DisabledTestsStore(controller.store.root).records(controller.workspace)
    assert restored[NODES[0]]['enabled'] is True
    assert 'test_card.py' in restored
    assert not matching_record(restored, NODES[0])
    assert matching_record(restored, NODES[1])
    window.model.set_all_checked(True)
    assert window.model.checked_nodeids() == [NODES[0]]
    assert controller.check_launch([NODES[0]], strict=True) == [NODES[0]]
    assert not controller.check_launch(NODES[:2], strict=True)
    menu = QMenu()
    window._construire_menu_test(menu, NODES[0])
    assert next(a for a in menu.actions() if a.text() == 'Run only this test').isEnabled()


def test_disabled_test_never_reaches_individual_stress_or_profile_launch(window, monkeypatch):
    window.disabled_tests.disable(NODES[0], 'Do not erase')
    calls = []
    monkeypatch.setattr(window, '_require_interpreter', lambda: calls.append(True))
    window._start([NODES[0]])
    window._lancer_stress(NODES[0], 'n_times', 2)
    window._start_profile(ExecutionProfile('Dangerous', NODES[:2], '', ''))
    assert calls == []
    assert len(window.errors) == 3


def test_detail_enables_only_selected_inherited_test(window):
    controller = window.disabled_tests
    controller.disable('test_card.py', '')
    index = window.model.index_for_nodeid(NODES[1])
    window.tree.setCurrentIndex(index)
    window._select_test(index)
    window.results.detail.stack.currentWidget().enable.click()
    assert not matching_record(controller.records, NODES[1])
    assert matching_record(controller.records, NODES[0])
    assert 'test_card.py' in controller.records


def test_profile_detail_updates_when_inherited_test_is_reenabled(window):
    window.profile_model.prepare(ExecutionProfile('Profile', NODES[:2], '', ''), ())
    window._set_profile_tree_visible(True)
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid('0:0'))
    window.disabled_tests.disable('test_card.py', '')
    window._refresh_profile_selection()
    page = window.profile_results.detail.stack.currentWidget()
    assert page.reason.toPlainText() == 'No reason provided'
    page.enable.click()
    assert not matching_record(window.disabled_tests.records, NODES[0])
    assert window.profile_results.detail.stack.currentWidget() is not page


def test_manager_bulk_buttons_include_group_children_and_retained_enabled_rows(window, qtbot):
    controller = window.disabled_tests
    controller.disable('test_card.py', 'Group reason')
    dialog = DisabledTestsDialog(controller)
    qtbot.addWidget(dialog)
    assert set(dialog._items) == {'test_card.py', 'test_card.py::test_protocol', *NODES}
    dialog.enable_all_button.click()
    assert controller.records == {}
    assert controller.button.isHidden()
    assert set(dialog._items) == {'test_card.py', 'test_card.py::test_protocol', *NODES}
    assert all(item.checkState(2) == Qt.Checked for item in dialog._items.values())
    dialog.disable_all_button.click()
    assert all(matching_record(controller.records, nodeid) for nodeid in NODES)
    assert all(item.checkState(2) == Qt.Unchecked for item in dialog._items.values())
    assert controller.records['test_card.py']['reason'] == 'Group reason'
    dialog._items[NODES[0]].setCheckState(2, Qt.Checked)
    qtbot.waitUntil(lambda: dialog._items[NODES[0]].checkState(2) == Qt.Checked)
    dialog.disable_all_button.click()
    assert matching_record(controller.records, NODES[0])
    dialog.enable_all_button.click()
    assert controller.records == {}


def test_bulk_enable_inside_unlisted_disabled_parent_keeps_other_tests_disabled(window):
    controller = window.disabled_tests
    controller.disable('test_card.py', '')
    controller.set_many([NODES[0]], enabled=True)
    assert not matching_record(controller.records, NODES[0])
    assert matching_record(controller.records, NODES[1])
    assert 'test_card.py' in controller.records


def test_manager_keeps_module_class_and_parameter_family_levels(window, qtbot):
    nodes = ['suite/test_pin.py::TestPin::test_attempt[1]',
             'suite/test_pin.py::TestPin::test_attempt[2]',
             'suite/test_pin.py::TestPin::test_other',
             'suite/test_other.py::test_untouched']
    window._on_collected(Collection(tuple(nodes)))
    controller = window.disabled_tests
    controller.disable('suite/test_pin.py::TestPin', '')
    controller.disable(nodes[0], 'Individual rule')
    dialog = DisabledTestsDialog(controller)
    qtbot.addWidget(dialog)
    module = 'suite/test_pin.py'
    group = module + '::TestPin'
    family = group + '::test_attempt'
    assert dialog._items[group].parent() is dialog._items[module]
    assert dialog._items[family].parent() is dialog._items[group]
    assert dialog._items[nodes[0]].parent() is dialog._items[family]
    assert nodes[3] not in dialog._items
    dialog._items[family].setCheckState(2, Qt.Checked)
    qtbot.waitUntil(lambda: dialog._items[group].checkState(2) == Qt.PartiallyChecked)
    assert not matching_record(controller.records, nodes[0])
    assert not matching_record(controller.records, nodes[1])
    assert matching_record(controller.records, nodes[2])
    dialog._items[module].setCheckState(2, Qt.Checked)
    qtbot.waitUntil(lambda: dialog._items[module].checkState(2) == Qt.Checked)
    assert not any(matching_record(controller.records, node) for node in nodes)
    dialog._items[module].setCheckState(2, Qt.Unchecked)
    qtbot.waitUntil(lambda: dialog._items[module].checkState(2) == Qt.Unchecked)
    assert all(matching_record(controller.records, node) for node in nodes[:3])
    assert not matching_record(controller.records, nodes[3])


def test_mixed_selection_filters_disabled_tests_before_service_start(window, monkeypatch):
    window.disabled_tests.disable(NODES[0], 'Do not erase')
    calls = []
    monkeypatch.setattr(window.service, 'start', lambda request, env: calls.append(request) or True)
    window._start(NODES[:2])
    assert len(calls) == 1
    assert calls[0].nodeids == (NODES[1],)


def test_queue_rechecks_activation_before_starting(window, monkeypatch):
    controller = window.run_tabs
    controller.paused = True
    window._start(NODES[:2])
    assert len(controller.queue) == 1
    window.disabled_tests.disable(NODES[0], 'Disabled after queuing')
    calls = []
    monkeypatch.setattr(window.service, 'start', lambda *args: calls.append(args) or True)
    controller.paused = False
    controller.start_next()
    assert not calls
    assert controller.current.state == 'draft'
    assert controller.active is None
    assert window.errors


def test_queue_accepts_enabled_exception_with_ancestor_still_disabled(window, monkeypatch):
    controller = window.disabled_tests
    controller.disable('test_card.py', '')
    controller.enable(NODES[0])
    window.run_tabs.paused = True
    window._start(NODES)
    assert len(window.run_tabs.queue) == 1
    calls = []
    monkeypatch.setattr(window.service, 'start', lambda request, env: calls.append(request) or True)
    window.run_tabs.paused = False
    window.run_tabs.start_next()
    assert len(calls) == 1
    assert calls[0].nodeids == (NODES[0],)
    assert not window.errors


def test_corrupt_registry_blocks_launch(window, monkeypatch):
    store = window.disabled_tests.store
    store.disable(window.workspace.path, NODES[0], 'Do not erase')
    store.path(window.workspace.path).write_text('broken', encoding='utf-8')
    calls = []
    monkeypatch.setattr(window, '_require_interpreter', lambda: calls.append(True))
    window._start([NODES[1]])
    assert not calls
    assert window.errors


def test_running_workspace_cannot_change_activation(window):
    window.run_tabs.current.state = 'running'
    with pytest.raises(DisabledTestsError):
        window.disabled_tests.disable(NODES[0], 'Too late for current run')
    window.run_tabs.current.state = 'draft'
    assert window.disabled_tests.records == {}


def test_restart_applies_saved_exclusions_before_selection(window, qtbot):
    window.disabled_tests.disable(NODES[0], 'Keep disabled across restart')
    window.close()
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    try:
        reopened.show()
        qtbot.waitUntil(lambda: bool(reopened.model._by_nodeid))
        assert NODES[0] in reopened.model._disabled
        assert not reopened.disabled_tests.button.isHidden()
        reopened.model.set_all_checked(True)
        assert NODES[0] not in reopened.model.checked_nodeids()
    finally:
        reopened.close()
