import json
import sys

import pytest
from PySide6.QtCore import QSettings, Qt

from runner.domain.execution import Collection
from runner.domain.models import Outcome, Reader, RunRequest, Status
from runner.domain.tree import build_tree
from runner.domain.tree_results import TreeResultsStore
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow
from runner.ui.tree_model import TestTreeModel

NODES = ['test_card.py::test_read', 'test_card.py::test_pin', 'test_card.py::test_serial']


def row(model, nodeid):
    return model.index_for_nodeid(nodeid).internalPointer()


def test_partial_run_keeps_outlines_but_counts_only_new_results(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree(NODES))
    model.begin_run(meta={'run_id': 'first'})
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    model.apply_outcome(NODES[1], Status.FAILED, 0)
    model.begin_run(retain=True, meta={'run_id': 'second'})
    assert model.status_counts() == {}
    assert model.done() == 0
    assert model.status_for(row(model, NODES[1]), 0) is Status.FAILED
    assert model.statuses_for_nodeid(NODES[1])[0] is Status.PENDING
    assert model.is_previous(row(model, NODES[1]), 0)
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    assert not model.is_previous(row(model, NODES[0]), 0)
    assert model.status_counts() == {Status.PASSED: 1}
    assert model.failed_nodeids_for(0) == []  # Archives never inherit old failures.
    assert model.result_source(NODES[0], 0)['run_id'] == 'second'
    assert model.result_source(NODES[1], 0)['run_id'] == 'first'


def test_group_can_improve_when_old_failure_is_rerun(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree(NODES))
    model.apply_outcome(NODES[0], Status.FAILED, 0)
    model.apply_outcome(NODES[1], Status.PASSED, 0)
    model.begin_run(retain=True)
    parent = model.index(0, 0).internalPointer()
    assert model.status_for(parent, 0) is Status.FAILED
    assert model.is_previous(parent, 0)
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    assert model.status_for(parent, 0) is Status.PASSED
    assert not model.is_previous(parent, 0)
    model.apply_outcome(NODES[0], Status.ERROR, 0)
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    assert model.status_for(parent, 0) is Status.PASSED
    assert model.status_counts() == {Status.PASSED: 1}


def test_freshness_is_per_reader_and_clear_keeps_selection(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree(NODES))
    model.set_readers((Reader('A', 0), Reader('B', 1)))
    model.set_checked_nodeids(NODES[:1])
    model.apply_outcome(NODES[0], Status.FAILED, 0)
    model.apply_outcome(NODES[0], Status.PASSED, 1)
    model.begin_run(retain=True)
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    assert not model.is_previous(row(model, NODES[0]), 0)
    assert model.is_previous(row(model, NODES[0]), 1)
    model.clear_statuses()
    assert model.checked_nodeids() == NODES[:1]
    assert model.export_results() == {}
    assert all(s is Status.PENDING for s in model.display_statuses_for_nodeid(NODES[0]).values())


def test_store_is_per_workspace_and_failed_save_preserves_data(tmp_path, monkeypatch):
    store = TreeResultsStore(tmp_path / 'registry')
    data = {NODES[0]: {'A': dict(status='PASSED', meta={'run_id': 'first'})}}
    store.write(str(tmp_path), data)
    assert store.read(str(tmp_path / 'other')) == {}
    def denied(*_):
        raise PermissionError('read only')
    monkeypatch.setattr('pathlib.Path.replace', denied)
    with pytest.raises(PermissionError):
        store.write(str(tmp_path), {})
    assert store.read(str(tmp_path)) == data


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
    w._interpreter_override = sys.executable
    w._on_collected(Collection(tuple(NODES)))
    w.show()
    yield w
    w.close()


def start(window, nodes=NODES, run_id='first'):
    request = RunRequest(window.workspace.path, sys.executable, tuple(nodes), (), run_id=run_id)
    window._on_run_started(request)
    return request


def deliver(window, nodeid, status):
    window._on_outcome(Outcome(nodeid, status, 0))


def test_clear_action_is_shared_by_toolbar_and_all_tree_context_menus(window):
    from PySide6.QtCore import QModelIndex
    start(window)
    deliver(window, NODES[0], Status.PASSED)
    window.tree_results.completed()
    action = window.tree_results.action
    assert action.isEnabled()
    assert not window.tree_results.button.isHidden()
    for index in (QModelIndex(), window.model.index(0, 0),
                  window.model.index_for_nodeid(NODES[0])):
        assert action in window._tree_context_menu(index).actions()
    window.tree_tools.populate_menu()
    assert action in window.tree_tools.menu.actions()
    action.trigger()
    assert window.model.export_results() == {}
    assert window.tree_results.store.read(window.workspace.path) == {}
    assert not action.isEnabled()


def test_markers_live_in_execution_and_shortcut_respects_queue_lock(window):
    window._on_collected(Collection(tuple(NODES), {
        NODES[0]: ('smoke',), NODES[1]: ('destructive',), NODES[2]: ()}))
    assert window.run_header.execution.isAncestorOf(window.markers)
    assert window.run_header.execution.isAncestorOf(window.filter_label)
    assert window.tree_toolbar.layout().indexOf(window.markers) == -1
    window.markers.popup.field.setText('not destructive')
    assert window.model.checked_nodeids() == [NODES[0], NODES[2]]
    assert not window.run_header.marker_filter_row.isHidden()
    window.clear_marker_filter()
    assert window.model.checked_nodeids() == [NODES[0], NODES[2]]
    assert window.run_header.marker_filter_row.isHidden()
    entry = window.run_tabs.entry_for(window)
    entry.state = 'waiting'
    window.run_tabs.queue.append(entry)
    try:
        window._update_actions()
        assert not window.markers.isEnabled()
        assert not window.filter_clear.isEnabled()
        assert not window.act_markers.isEnabled()
        window._open_markers()
        assert not window.markers.popup.isVisible()
    finally:
        window.run_tabs.queue.remove(entry)
        entry.state = 'draft'
        window._update_actions()


def test_compact_search_toggle_returns_to_names_and_menu_follows_scope(window):
    from runner.ui.widgets import SCOPE_TESTS, SCOPE_FAILURES
    assert window.search.tests_button.isHidden()
    window.search.failures_button.click()
    assert window.search.scope == SCOPE_FAILURES
    window.tree_tools.populate_menu()
    scopes = {action.text(): action for action in window.tree_tools.menu.actions()}
    assert scopes['Search in failure output'].isChecked()
    window.search.failures_button.click()
    assert window.search.scope == SCOPE_TESTS
    assert not window.search.failures_button.isChecked()
    scopes['Search in failure output'].trigger()
    assert window.search.scope == SCOPE_FAILURES
    assert window.search.failures_button.isChecked()


def test_clear_icon_resets_only_tree_and_persisted_cache(window):
    request = start(window)
    deliver(window, NODES[0], Status.PASSED)
    deliver(window, NODES[1], Status.FAILED)
    window.tree_results.completed()
    archived = window.history.entries()
    window.disabled_tests.disable(NODES[2], 'Keep inactive')
    disabled = dict(window.disabled_tests.records)
    selected = window.model.checked_nodeids()
    window.tree.expandAll()
    assert window.tree_results.button.text() == ''
    assert window.tree_results.button.isEnabled()
    window.tree_results.button.click()
    assert window.model.export_results() == {}
    assert window.tree_results.store.read(request.workspace) == {}
    assert window.model.checked_nodeids() == selected
    assert window._run_status_counts() == {Status.PASSED: 1, Status.FAILED: 1}
    assert window._completed_executions() == 2
    assert window.history.entries() == archived
    assert window.disabled_tests.records == disabled
    assert not window.tree_results.button.isEnabled()
    window._rafraichir_compteurs()
    assert window.pills[Status.PASSED].value() == 1
    start(window, NODES[:1], 'new')
    assert window._run_status_counts() == {}


def test_recollection_new_tab_and_restart_keep_old_results(window, qtbot):
    start(window)
    deliver(window, NODES[0], Status.PASSED)
    deliver(window, NODES[1], Status.FAILED)
    window.tree_results.completed()
    start(window, NODES[:1], 'second')
    deliver(window, NODES[0], Status.PASSED)
    window.tree_results.completed()
    window._on_collected(Collection(tuple(NODES)))
    assert not window.model.is_previous(row(window.model, NODES[0]), 0)
    assert window.model.is_previous(row(window.model, NODES[1]), 0)
    draft = window.run_tabs.new_run(window)
    assert draft.model.display_statuses_for_nodeid(NODES[1])[0] is Status.FAILED
    assert draft.model.status_counts() == {}
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.workspace = window.workspace
    reopened._on_collected(Collection(tuple(NODES)))
    assert reopened.model.display_statuses_for_nodeid(NODES[1])[0] is Status.FAILED
    assert reopened.model.is_previous(row(reopened.model, NODES[1]), 0)
    reopened.close()


def test_setting_off_restores_original_reset_behavior_and_is_saved(window, qtbot):
    start(window)
    deliver(window, NODES[0], Status.FAILED)
    window.tree_results.completed()
    start(window, NODES[1:2], 'second')
    assert window.model.is_previous(row(window.model, NODES[0]), 0)
    control = window.preferences.settings_panel.controls['retain_tree_results']
    control.setChecked(False)
    window.preferences.save()
    assert window.model.display_statuses_for_nodeid(NODES[0])[0] is Status.PENDING
    window.preferences.values['retain_tree_results'] = True
    window.preferences.apply()
    assert window.model.display_statuses_for_nodeid(NODES[0])[0] is Status.FAILED
    window.preferences.values['retain_tree_results'] = False
    window.preferences.save()
    deliver(window, NODES[1], Status.PASSED)
    start(window, NODES[2:], 'third')
    assert window.model.display_statuses_for_nodeid(NODES[1])[0] is Status.PENDING
    saved = json.loads(window.settings.value('preferences/personal'))
    assert saved['retain_tree_results'] is False
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert not reopened.tree_results.enabled
    reopened.close()


def test_reader_names_survive_reordering_and_workspace_does_not_leak(window, tmp_path):
    window.tree_results.store.write(window.workspace.path, {
        NODES[0]: {'A': dict(status='FAILED', meta={}), 'B': dict(status='PASSED', meta={})}})
    window.model.set_readers((Reader('B', 0), Reader('A', 1)))
    window.tree_results.collected(False)
    assert window.model.display_statuses_for_nodeid(NODES[0]) == {0: Status.PASSED, 1: Status.FAILED}
    other = tmp_path / 'other'
    other.mkdir()
    window.workspace = Workspace.load(str(other))
    window._on_collected(Collection(tuple(NODES)))
    assert window.model.export_results() == {}


def test_existing_draft_refreshes_previous_results_when_it_starts(window):
    draft = window.run_tabs.new_run(window)
    start(window)
    deliver(window, NODES[0], Status.FAILED)
    window.tree_results.completed()
    start(draft, NODES[1:], 'queued')
    assert draft.model.display_statuses_for_nodeid(NODES[0])[0] is Status.FAILED
    assert draft.model.is_previous(row(draft.model, NODES[0]), 0)
    assert draft.model.status_counts() == {}


def test_previous_result_has_explicit_provenance_and_clear_is_locked(window):
    start(window)
    deliver(window, NODES[0], Status.FAILED)
    start(window, NODES[1:], 'second')
    index = window.model.index_for_nodeid(NODES[0])
    window.tree.setCurrentIndex(index)
    window._select_test(index)
    assert 'Previous run result' in window.tree_results.origin.text()
    assert not window.tree_results.origin.isHidden()
    assert window.results._statuses[0] is Status.FAILED
    window.service._profile_active = True
    window.tree_results.clear()
    assert not window.tree_results.button.isEnabled()
    assert window.model.display_statuses_for_nodeid(NODES[0])[0] is Status.FAILED
    window.service._profile_active = False


def test_real_partial_rerun_does_not_pollute_archived_statuses(window, qtbot):
    from pathlib import Path
    Path(window.workspace.path, 'test_card.py').write_text(
        'def test_read(): pass\ndef test_pin(): assert False\ndef test_serial(): pass\n')
    window._start(NODES)
    qtbot.waitUntil(lambda: not window.service.busy and window.run_tabs.active is None, timeout=20000)
    window._start(NODES[:1])
    qtbot.waitUntil(lambda: not window.service.busy and window.run_tabs.active is None, timeout=20000)
    assert window.model.display_statuses_for_nodeid(NODES[1])[0] is Status.FAILED
    assert window.model.is_previous(row(window.model, NODES[1]), 0)
    assert window._run_status_counts() == {Status.PASSED: 1}
    latest = window.history.entries()[0]
    assert latest.nodeids == (NODES[0],)
    assert latest.failed_nodeids == ()
    archived = window.history.entries()
    assert len(archived) >= 2
    window.tree_results.clear()
    assert window.history.entries() == archived
