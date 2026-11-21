import copy
import time
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ExecutionProfile, ProfileStore, export_profile, inspect_profile
from runner.domain.models import Status, Reader, ReaderReport, RunRequest
from runner.domain.history import RunEntry
from runner.domain.campaign_coverage import coverage, summary
from runner.domain.campaign_revision import record, previous, digest
from runner.domain.report_data import report_payload
from runner.domain.report import html_report
from runner.ui.execution_profiles_page import ExecutionProfilesPage, _GROUP_ROLE
from runner.ui.main_window import MainWindow
from runner.domain.workspace import Workspace
from runner.domain.tree import build_tree

pytestmark = pytest.mark.usefixtures('isolated_run_state')
G = dict(id='t0', name='RSA T0', color='#8877cc', description='Prepare the card', configuration_overrides={'PROTOCOL': 'T0'})


def make_profile(tmp_path):
    profile = ExecutionProfile('Campaign', ['tests/test_a.py::test_a'], '', '', step_groups=[copy.deepcopy(G)])
    sync.follow(profile, [0], 'folder', 'tests', str(tmp_path))
    return profile


def test_coverage_never_calls_selected_or_unavailable_tests_complete():
    scope = dict(planned=4, selected=[0, 2], unavailable=[3])
    result = coverage(scope, {(0, 0, 0): Status.PASSED, (2, 0, 0): Status.PASSED}, 0)
    assert result == dict(planned=4, selected=2, executed=2, unavailable=1, not_selected=1, not_completed=0, complete=False)
    assert 'Campaign incomplete' in summary([result])
    full = coverage(dict(planned=2, selected=[0, 1], unavailable=[]), {(0, 0, 0): Status.PASSED, (1, 0, 0): Status.SKIPPED}, 0)
    assert full['complete']
    assert summary([full]) == ''


def test_latest_retry_and_each_reader_are_independent():
    scope = dict(planned=2, selected=[0, 1], unavailable=[])
    states = {(0, 0, 0): Status.FAILED, (0, 1, 0): Status.RUNNING, (1, 0, 0): Status.PASSED,
              (0, 0, 1): Status.PASSED, (1, 0, 1): Status.PASSED}
    assert coverage(scope, states, 0)['not_completed'] == 1
    assert coverage(scope, states, 1)['complete']
    assert 'test/reader checks' in summary([coverage(scope, states, i) for i in (0, 1)])


def test_report_retains_campaign_tree_and_reasons_for_omitted_tests(tmp_path):
    profile = make_profile(tmp_path)
    profile.sequence += ['tests/test_b.py::test_b', 'tests/test_c.py::test_c']
    profile.step_groups *= 3
    profile.step_ids += ['b', 'c']
    analysis = dict(schema=1, campaign_profile=asdict(profile), occurrences=[
        dict(nodeid=profile.sequence[0], attempts=[dict(attempt=0, status='PASSED', duration=.1)]),
        dict(nodeid=profile.sequence[1], attempts=[], not_run=True, reason='Not selected for this run'),
        dict(nodeid=profile.sequence[2], attempts=[], not_run=True, reason='Unavailable at launch')])
    c = dict(planned=3, selected=1, executed=1, unavailable=1, not_selected=1, not_completed=0, complete=False)
    entry = RunEntry(id='test', timestamp=time.time(), workspace=str(tmp_path), run_kind='profile', counts={'PASSED': 1},
                     nodeids=(profile.sequence[0],), replay_profile=dict(sequence=profile.sequence[:1]), analysis_data=analysis, campaign_coverage=c)
    data = report_payload([entry])
    assert len(data['rows']) == 3
    assert data['counts'] == {'passed': 1, 'notrun': 2}
    assert 'Unavailable' in data['rows'][2]['readers'][0]['notice']
    assert not data['complete']
    text = html_report(entry)
    assert 'Campaign incomplete' in text and 'Not selected for this run' in text and 'RSA T0' in text
    assert RunEntry.from_json(entry.to_json()).campaign_coverage == c


def test_persistent_undo_survives_store_recreation_and_respects_newer_edits(tmp_path):
    store = ProfileStore(tmp_path / 'profiles')
    before = make_profile(tmp_path)
    store.save(before)
    plan = sync.compare(before, before.sequence + ['tests/test_new.py::test_new'], str(tmp_path))
    after = sync.apply(before, plan, plan.additions, {})
    record(store, after, before, digest(store, before.profile_id))
    restored_store = ProfileStore(store.root)
    assert previous(restored_store, before.profile_id).sequence == before.sequence
    newer = copy.deepcopy(after)
    newer.description = 'Edited after the update'
    restored_store.save(newer)
    assert previous(restored_store, before.profile_id) is None


def test_review_does_not_overwrite_a_file_changed_while_dialog_open(tmp_path):
    store = ProfileStore(tmp_path)
    before = make_profile(tmp_path)
    store.save(before)
    expected = digest(store, before.profile_id)
    newer = copy.deepcopy(before)
    newer.description = 'External edit'
    store.save(newer)
    with pytest.raises(ValueError, match='changed on disk'):
        record(store, before, before, expected)
    assert store.list()[0].description == 'External edit'


def test_empty_group_survives_update_export_and_new_tests_return(tmp_path):
    before = make_profile(tmp_path)
    gone = sync.compare(before, [], str(tmp_path))
    empty = sync.apply(before, gone, [], {0: 'remove'})
    assert empty.sequence == []
    assert empty.empty_groups[0]['group'] == G
    saved = inspect_profile(export_profile(empty, tmp_path / 'empty')).profile
    new = 'tests/test_new.py::test_new'
    plan = sync.compare(saved, [new], str(tmp_path))
    filled = sync.apply(saved, plan, plan.additions, {})
    assert filled.sequence == [new]
    assert filled.step_groups == [G]
    assert not filled.empty_groups


def test_editor_can_edit_duplicate_and_remove_empty_groups(qtbot, tmp_path):
    before = make_profile(tmp_path)
    empty = sync.apply(before, sync.compare(before, [], str(tmp_path)), [], {0: 'remove'})
    store = ProfileStore(tmp_path / 'profiles')
    store.save(empty)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    page.set_workspace_context([], '', workspace=str(tmp_path))
    item = page.sequence_list.topLevelItem(0)
    assert item.data(0, _GROUP_ROLE)['id'] == G['id']
    assert page.export_button.isEnabled() and not page.run_button.isEnabled()
    page.sequence_list.setCurrentItem(item)
    item.setSelected(True)
    page._apply_group_yaml(G['id'], {'PROTOCOL': 'T1'})
    value = page._profile_from_editor()
    assert value.empty_groups[0]['group']['configuration_overrides'] == {'PROTOCOL': 'T1'}
    assert value.tracking['sources'][0]['group']['configuration_overrides'] == {'PROTOCOL': 'T1'}
    item = page.sequence_list.topLevelItem(0)
    page.sequence_list.setCurrentItem(item)
    item.setSelected(True)
    page.duplicate_steps()
    assert len(page._profile_from_editor().empty_groups) == 2
    page.undo_stack.undo()
    assert len(page._profile_from_editor().empty_groups) == 1
    page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
    page.remove_steps()
    assert not page._profile_from_editor().empty_groups


def test_unchecking_a_group_is_not_a_content_exclusion_and_new_tests_stay_unchecked(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    before = make_profile(tmp_path)
    window.model.set_tree(build_tree(before.sequence + ['tests/test_new.py::test_new']))
    window._campaign_collection_complete = True
    window._open_collected_profile(before)
    window.profile_model.set_all_checked(False)
    window.search.field.setText('test_a')
    window._on_search('test_a', reveal=False)
    plan = sync.compare(before, window.model._by_nodeid, str(tmp_path))
    after = sync.apply(before, plan, plan.additions, {})
    window.campaign_sync.updated(after, before)
    assert window.profile_model.checked_nodeids() == []
    assert window.search.field.text() == 'test_a'
    assert not after.tracking['sources'][0]['excluded']


def test_switching_profiles_and_refresh_keep_unsaved_drafts(qtbot, tmp_path):
    store = ProfileStore(tmp_path / 'profiles')
    first = make_profile(tmp_path)
    second = replace(first, name='Second', profile_id='second')
    store.save(first)
    store.save(second)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    row = next(i for i, p in enumerate(page._profiles) if p.profile_id == first.profile_id)
    page.profile_list.setCurrentRow(row)
    page.description_edit.setPlainText('My unsaved draft')
    assert page._dirty
    page.profile_list.setCurrentRow(1 - row)
    page.profile_list.setCurrentRow(row)
    assert page.description_edit.toPlainText() == 'My unsaved draft'
    assert page._dirty
    page.refresh()
    assert page.description_edit.toPlainText() == 'My unsaved draft'
    assert next(p for p in store.list() if p.profile_id == first.profile_id).description == ''
    page.new_profile()
    new_id = page.current_profile().profile_id
    page.name_edit.setText('My new unsaved campaign')
    page.refresh()
    assert page.current_profile().profile_id == new_id
    assert page.name_edit.text() == 'My new unsaved campaign'


def test_external_edit_keeps_draft_and_offers_reload(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    store = ProfileStore(tmp_path / 'profiles')
    before = make_profile(tmp_path)
    store.save(before)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    page.description_edit.setPlainText('Local draft')
    newer = replace(before, description='Changed on disk')
    store.save(newer)
    assert not page.save_current()
    assert not page.reload_button.isHidden()
    assert page.description_edit.toPlainText() == 'Local draft'
    assert store.list()[0].description == 'Changed on disk'
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **kw: QMessageBox.Yes)
    page.reload_current_campaign()
    assert page.description_edit.toPlainText() == 'Changed on disk'
    assert not page._dirty


def test_editor_can_undo_update_after_restart(qtbot, tmp_path):
    store = ProfileStore(tmp_path / 'profiles')
    before = make_profile(tmp_path)
    store.save(before)
    plan = sync.compare(before, before.sequence + ['tests/test_new.py::test_new'], str(tmp_path))
    after = sync.apply(before, plan, plan.additions, {})
    record(store, after, before, digest(store, before.profile_id))
    page = ExecutionProfilesPage(ProfileStore(store.root))
    qtbot.addWidget(page)
    page.set_workspace_context(after.sequence, '', workspace=str(tmp_path))
    assert page.campaign_sync.has_undo(before.profile_id)
    assert not page.undo_update_button.isHidden()
    page.campaign_sync.undo()
    assert page._flatten_sequence() == before.sequence
    assert store.list()[0].sequence == before.sequence
    assert not page.campaign_sync.has_undo(before.profile_id)


def test_empty_group_copy_paste_keeps_yaml_and_independent_source(qtbot, qapp, tmp_path):
    before = make_profile(tmp_path)
    empty = sync.apply(before, sync.compare(before, [], str(tmp_path)), [], {0: 'remove'})
    store = ProfileStore(tmp_path / 'profiles')
    store.save(empty)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    try:
        page.sequence_list.setCurrentItem(page.sequence_list.topLevelItem(0))
        page.copy_elements()
        page.paste_elements()
        value = page._profile_from_editor()
        assert len(value.empty_groups) == 2
        one, two = [r['group'] for r in value.empty_groups]
        assert one['id'] != two['id']
        assert one['configuration_overrides'] == two['configuration_overrides'] == G['configuration_overrides']
        assert len(value.tracking['sources']) == 2
        assert len({s['id'] for s in value.tracking['sources']}) == 2
        page.undo_stack.undo()
        assert len(page._profile_from_editor().empty_groups) == 1
    finally:
        qapp.clipboard().clear()


def test_stopped_profile_archives_unfinished_attempt_as_not_run(tmp_path):
    from runner.ui.report_capture import capture_report
    profile = make_profile(tmp_path)
    key = '0:0'
    window = SimpleNamespace(_running_execution_profile=profile,
        _archive_campaign=dict(profile=asdict(profile), sequence=profile.sequence, selected=[0], unavailable=[], planned=1),
        _profile_count_statuses={(0, 0, 0): Status.RUNNING},
        profile_model=SimpleNamespace(occurrence_keys=lambda p: [key], locations={key: (0, 0, profile.sequence[0])}, _durations={}),
        _profile_live_details={}, _profile_logs=None, _profile_reports={})
    report = SimpleNamespace(reader=SimpleNamespace(index=0, name='Reader'), cancelled=True, commands=[], issues=[])
    analysis = capture_report(window, report)
    assert analysis['coverage']['stopped'] and not analysis['coverage']['complete']
    row = analysis['occurrences'][0]
    # Le statut est normalise a la lecture (NOT_RUN / NOTRUN / notrun).
    assert row['not_run'] and row['attempts'][0]['status'].replace('_', '') == 'NOTRUN'
    assert row['reason'] == 'Stopped before this test finished'


def test_existing_empty_group_moves_with_remaining_tests_during_update(tmp_path):
    from runner.domain.empty_groups import retained
    from runner.domain.execution_profile import validate_profile
    nodes = ['tests/test_a.py::test_a', 'tests/test_b.py::test_b']
    before = ExecutionProfile('Campaign', nodes, '', '', step_ids=['a', 'b'],
        empty_groups=[dict(position=2, group=copy.deepcopy(G))])
    after = replace(before, sequence=nodes[:1], step_ids=['a'])
    after.empty_groups = retained(before, after.sequence, [], before.step_ids, after.step_ids)
    assert after.empty_groups[0]['position'] == 1
    validate_profile(after)


def test_empty_followed_groups_refill_in_their_display_order(tmp_path):
    first = make_profile(tmp_path)
    second_group = dict(G, id='t1', name='RSA T1', configuration_overrides={'PROTOCOL': 'T1'})
    first.sequence *= 2
    first.step_groups += [second_group]
    first.step_ids += ['second']
    sync.follow(first, [1], 'folder', 'tests', str(tmp_path))
    empty = sync.apply(first, sync.compare(first, [], str(tmp_path)), [], {0: 'remove', 1: 'remove'})
    empty.empty_groups.reverse()
    new = 'tests/test_new.py::test_new'
    plan = sync.compare(empty, [new], str(tmp_path))
    result = sync.apply(empty, plan, plan.additions, {})
    assert result.sequence == [new, new]
    assert [g['id'] for g in result.step_groups] == ['t1', 't0']


def test_history_distinguishes_current_not_run_from_old_unknowns(qtbot, tmp_path):
    from runner.domain.history import History
    from runner.ui.history_dashboard import HistoryWindow
    before = make_profile(tmp_path)
    before.sequence += ['tests/test_b.py::test_b']
    before.step_groups *= 2
    analysis = dict(schema=1, campaign_profile=asdict(before), occurrences=[
        dict(nodeid=before.sequence[0], attempts=[dict(attempt=0, status='PASSED')]),
        dict(nodeid=before.sequence[1], attempts=[], not_run=True, reason='Not selected for this run')])
    c = dict(planned=2, selected=1, executed=1, unavailable=0, not_selected=1, not_completed=0, complete=False)
    history = History(tmp_path / 'history')
    history.add(RunEntry(id='run', timestamp=1, workspace=str(tmp_path), nodeids=(before.sequence[0],),
        counts={'PASSED': 1}, analysis_data=analysis, campaign_coverage=c))
    dialog = HistoryWindow(history)
    qtbot.addWidget(dialog)
    assert dialog.ribbon._counts == {Status.PASSED: 1, Status.NOT_RUN: 1}
    assert '2 planned tests' in dialog.detail_meta.text()
    model = dialog.execution_model
    branch_result = model.index(0, 1).data()
    assert branch_result == 'Not all tests run'
    dialog._select_execution_reader(0)
    item = model.index_for_nodeid('2')
    assert 'Not selected' in model.index(item.row(), 1, item.parent()).data()


def test_launch_snapshot_is_independent_of_later_editor_changes(tmp_path):
    from runner.ui.campaign_archive import begin
    profile = make_profile(tmp_path)
    window = SimpleNamespace(model=SimpleNamespace(_by_nodeid=dict.fromkeys(profile.sequence)))
    begin(window, profile, SimpleNamespace(positions=(0,)))
    profile.sequence.append('tests/test_later.py::test_later')
    profile.step_groups[0]['configuration_overrides']['PROTOCOL'] = 'T1'
    assert window._archive_campaign['planned'] == 1
    assert window._archive_campaign['sequence'] == ['tests/test_a.py::test_a']
    assert window._archive_campaign['profile']['step_groups'][0]['configuration_overrides'] == {'PROTOCOL': 'T0'}


def test_queued_campaign_defers_display_reload(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    before = make_profile(tmp_path)
    nodes = before.sequence + ['tests/test_new.py::test_new']
    window.model.set_tree(build_tree(nodes))
    window._campaign_collection_complete = True
    window._open_collected_profile(before)
    after = sync.apply(before, sync.compare(before, nodes, str(tmp_path)), [(before.tracking['sources'][0]['id'], nodes[1])], {})
    assert window.run_tabs is not None
    monkeypatch.setattr(window.run_tabs, 'is_locked', lambda context: True)
    window.campaign_sync.updated(after, before)
    assert window._active_execution_profile.sequence == before.sequence
    assert window.campaign_sync.pending[0].sequence == after.sequence
    monkeypatch.setattr(window.run_tabs, 'is_locked', lambda context: False)
    window.campaign_sync._apply_pending()
    assert window._active_execution_profile.sequence == after.sequence


def test_manual_insertion_before_empty_group_keeps_its_order(qtbot, tmp_path):
    profile = make_profile(tmp_path)
    profile.empty_groups = [dict(position=1, group=dict(G, id='empty', name='Later group'))]
    store = ProfileStore(tmp_path / 'profiles')
    store.save(profile)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    page._insert_tests(['tests/test_0.py::test_first'], 0, [])
    assert page._profile_from_editor().empty_groups[0]['position'] == 2
    assert page.sequence_list.topLevelItem(page.sequence_list.topLevelItemCount() - 1).data(0, _GROUP_ROLE)['id'] == 'empty'


def test_root_and_parameter_changes_keep_custom_yaml_until_explicit_replacement(tmp_path):
    old = 'tests/test_a.py::test_a[old]'
    current = 'suite/tests/test_a.py::test_a[new]'
    profile = ExecutionProfile('Campaign', [old], '', '', step_overrides=[{'timeout': 25}], step_groups=[copy.deepcopy(G)])
    sync.follow(profile, [0], 'folder', 'tests', str(tmp_path))
    plan = sync.compare(profile, [current], str(tmp_path))
    assert plan.candidates[0] == [current]
    assert plan.source_paths == {profile.tracking['sources'][0]['id']: 'suite/tests'}
    safe = sync.apply(profile, plan, plan.additions, sync.recommended_decisions(profile, plan))
    assert old in safe.sequence and current in safe.sequence
    assert safe.step_overrides[safe.sequence.index(old)] == {'timeout': 25}
    explicit = sync.apply(profile, plan, plan.additions, {0: current}, transfer=[0])
    assert explicit.sequence == [current] and explicit.step_overrides == [{'timeout': 25}]
    assert not sync.compare(explicit, [current], str(tmp_path)).changed


def test_renamed_file_is_only_a_suggestion_until_confirmed(tmp_path):
    before = make_profile(tmp_path)
    renamed = 'tests/test_renamed.py::test_a'
    plan = sync.compare(before, [renamed], str(tmp_path))
    assert plan.path_changes == {} and plan.suggestions == {0: [renamed]}
    assert sync.recommended_decisions(before, plan)[0] == 'keep'
    result = sync.apply(before, plan, [], {0: renamed})
    assert result.sequence == [renamed]


def test_update_keeps_expansion_filter_scroll_and_selects_removed_tests_neighbour(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QAbstractItemView
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1440, 960)
    window.show()
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    nodes = [f'tests/test_cases.py::test_case_{i:02d}' for i in range(80)]
    second = dict(G, id='t1', name='RSA T1')
    before = ExecutionProfile('Campaign', nodes, '', '', step_groups=[copy.deepcopy(G)] * 60 + [second] * 20)
    sync.follow(before, range(80), 'folder', 'tests', str(tmp_path))
    available = nodes[:40] + nodes[41:]
    window.model.set_tree(build_tree(available))
    window._campaign_collection_complete = True
    window._open_collected_profile(before)
    for p, node in enumerate(nodes):
        window.profile_model.apply_execution(p, 0, 0, node, Status.PASSED)
    window.search.field.setText('test_case')
    window._on_search('test_case', reveal=False)
    window._status_filter = Status.PASSED
    window._apply_status_filter()
    tree, model = window.profile_tree, window.profile_model
    tree.expandAll()
    tree.collapse(model.index(1, 0))
    tree.setCurrentIndex(model.index_for_nodeid('40:0'))
    tree.scrollTo(model.index_for_nodeid('20:0'), QAbstractItemView.PositionAtTop)
    qtbot.waitUntil(lambda: tree.indexAt(QPoint(1, 1)).isValid())
    top = tree.indexAt(QPoint(1, 1)).internalPointer().node.nodeid
    assert top
    plan = sync.compare(before, available, str(tmp_path))
    after = sync.apply(before, plan, [], {40: 'remove'})
    window.campaign_sync.updated(after, before)
    assert tree.isExpanded(model.index(0, 0)) and not tree.isExpanded(model.index(1, 0))
    assert window._status_filter == Status.PASSED and window.search.field.text() == 'test_case'
    selected = tree.currentIndex().internalPointer().node.nodeid
    assert model.locations[selected][2] == nodes[41]
    assert tree.indexAt(QPoint(1, 1)).internalPointer().node.nodeid == top
