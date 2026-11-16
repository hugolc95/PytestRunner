import copy

import pytest
from PySide6.QtCore import Qt

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.domain.workspace import Workspace
from runner.domain.tree import build_tree
from runner.domain.models import Reader, Status
from runner.ui.execution_profiles_page import ExecutionProfilesPage, AddTestsDialog
from runner.ui.campaign_sync import CampaignReviewDialog, CampaignSourcesDialog
from runner.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures('isolated_run_state')


def tracked(tmp_path):
    value = ExecutionProfile('RSA campaign', ['tests/test_a.py::test_a[T0]', 'tests/test_a.py::test_a[T1]'], '', '',
                             step_overrides=[{'timeout': 20}, {}])
    sync.follow(value, [0, 1], 'folder', 'tests', str(tmp_path))
    return value


def page(qtbot, tmp_path):
    value = tracked(tmp_path)
    store = ProfileStore(tmp_path / 'profiles')
    store.save(value)
    widget = ExecutionProfilesPage(store)
    qtbot.addWidget(widget)
    widget.set_workspace_context(value.sequence + ['tests/test_new.py::test_new'], '', workspace=str(tmp_path))
    return widget, value


def test_editor_notice_and_library_status_are_visible(qtbot, tmp_path):
    widget, value = page(qtbot, tmp_path)
    assert 'Campaign update available' in widget.campaign_sync.notice.label.text()
    assert not widget.campaign_sync.notice.isHidden()
    assert 'Update' in widget.profile_list.item(0).text()
    assert widget._profile_from_editor().step_ids == value.step_ids


def test_review_requires_decisions_and_applies_exact_yaml_choice(qtbot, tmp_path):
    value = tracked(tmp_path)
    replacement = 'tests/test_a.py::test_a[T0-fast]'
    plan = sync.compare(value, [replacement, value.sequence[1]], str(tmp_path))
    dialog = CampaignReviewDialog(value, plan)
    qtbot.addWidget(dialog)
    dialog._apply()
    assert dialog.result_profile is None
    assert 'Choose an action' in dialog.message.text()
    combo = dialog.decisions[0]
    combo.setCurrentIndex(combo.findData(replacement))
    dialog.transfers[0].setChecked(True)
    dialog._apply()
    assert dialog.result_profile.sequence == [replacement, value.sequence[1]]
    assert dialog.result_profile.step_overrides[0] == {'timeout': 20}


def test_running_review_cannot_be_applied(qtbot, tmp_path):
    value = tracked(tmp_path)
    plan = sync.compare(value, value.sequence + ['tests/test_new.py::test_new'], str(tmp_path))
    dialog = CampaignReviewDialog(value, plan, locked=True)
    qtbot.addWidget(dialog)
    assert not dialog.apply_button.isEnabled()
    assert 'running or queued' in dialog.message.text()


def test_whole_selected_branch_tracks_its_source_and_leaves_can_stay_fixed(qtbot, tmp_path):
    value = tracked(tmp_path)
    dialog = AddTestsDialog(value.sequence)
    qtbot.addWidget(dialog)
    received = []
    dialog.tests_added.connect(lambda nodeids: received.append((nodeids, copy.deepcopy(dialog.pending_sources))))
    dialog.model.set_all_checked(True)
    dialog._add()
    assert received[0][1] == [('folder', 'tests', value.sequence)]
    dialog.follow_selection.setChecked(False)
    dialog._add_again()
    assert received[-1][1] == []


def test_sources_legacy_migration_keeps_current_exclusions(qtbot, tmp_path):
    value = ExecutionProfile('Old', ['tests/test_a.py::test_a'], '', '')
    available = value.sequence + ['tests/test_b.py::test_b']
    dialog = CampaignSourcesDialog(value, [0], available, str(tmp_path))
    qtbot.addWidget(dialog)
    dialog._follow()
    assert dialog.profile.tracking['sources'][0]['excluded'] == ['tests/test_b.py::test_b']
    dialog._stop()
    assert not dialog.profile.tracking
    assert dialog.profile.sequence == value.sequence


def test_update_publish_and_undo_keep_editor_view_and_disk(qtbot, tmp_path):
    widget, value = page(qtbot, tmp_path)
    root = widget.sequence_list.topLevelItem(0)
    root.setExpanded(True)
    before = widget._profile_from_editor()
    plan = widget.campaign_sync.plan(before)
    updated = sync.apply(before, plan, plan.additions, {})
    widget.store.save(updated)
    widget.campaign_sync.undo_updates[updated.profile_id] = (before, updated)
    widget.campaign_sync._publish(updated, before)
    assert widget.sequence_list.topLevelItem(0).isExpanded()
    assert len(widget._flatten_sequence()) == 3
    widget.campaign_sync.undo()
    assert widget.store.list()[0].sequence == before.sequence
    assert widget._flatten_sequence() == before.sequence


def test_source_edits_participate_in_editor_undo(qtbot, tmp_path):
    widget, _ = page(qtbot, tmp_path)
    before = widget._editor_state()
    widget._tracking['sources'][0]['recursive'] = False
    widget._record_edit(before, 'Change tracking')
    widget.undo_stack.undo()
    assert widget._tracking['sources'][0]['recursive'] is True
    widget.undo_stack.redo()
    assert widget._tracking['sources'][0]['recursive'] is False


def test_run_tree_reload_preserves_checks_results_and_unrelated_page(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    value = tracked(tmp_path)
    window.model.set_tree(build_tree(value.sequence + ['tests/test_new.py::test_new']))
    window._campaign_collection_complete = True
    window._open_collected_profile(value)
    window.profile_model.set_checked_nodeids(['1:0'])
    window.profile_model.apply_execution(1, 0, 0, value.sequence[1], Status.PASSED)
    window.profile_model.set_duration('1:0', 0, 2.5)
    index = window.profile_model.index_for_nodeid('1:0')
    window.profile_tree.setCurrentIndex(index)
    plan = sync.compare(value, window.model._by_nodeid, str(tmp_path))
    updated = sync.apply(value, plan, plan.additions, {})
    window.campaign_sync.updated(updated, value)
    assert window._active_execution_profile.sequence == updated.sequence
    assert window.profile_model.checked_nodeids() == ['1:0', '2:0']
    assert window.profile_model._by_nodeid['1:0'].statuses[0] == Status.PASSED
    assert window.profile_model._durations['1:0'][0] == 2.5
    assert window.profile_tree.currentIndex().internalPointer().node.nodeid == '1:0'


def test_missing_profile_can_be_opened_for_review(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    value = tracked(tmp_path)
    window.model.set_tree(build_tree([value.sequence[0]]))
    window._campaign_collection_complete = True
    window._open_collected_profile(value)
    assert window._active_execution_profile == value
    assert 'unavailable' in window.campaign_notice.label.text()


def test_duplicate_complete_source_and_clipboard_copy_are_independent(qtbot, tmp_path, qapp):
    widget, _ = page(qtbot, tmp_path)
    root = widget.sequence_list.topLevelItem(0)
    widget.sequence_list.setCurrentItem(root)
    root.setSelected(True)
    widget.duplicate_steps()
    copied = widget._profile_from_editor()
    assert len(copied.tracking['sources']) == 2
    assert len({source['id'] for source in copied.tracking['sources']}) == 2
    widget.sequence_list.clearSelection()
    # Copier les deux blocs complets conserve deux nouvelles sources, sans
    # partager les identites de suivi avec les originales.
    for i in range(widget.sequence_list.topLevelItemCount()):
        widget.sequence_list.topLevelItem(i).setSelected(True)
    try:
        widget.copy_elements()
        assert widget.sequence_clipboard.payload['version'] == 2
        widget.sequence_list.clearSelection()
        widget.paste_elements()
        pasted = widget._profile_from_editor()
        assert len(pasted.sequence) == 8
        assert len(pasted.tracking['sources']) == 4
        new = 'tests/test_new.py::test_new'
        assert len(sync.compare(pasted, pasted.sequence + [new], str(tmp_path)).additions) == 4
    finally:
        qapp.clipboard().clear()


def test_inserting_before_results_and_replacing_case_never_reuses_wrong_verdict(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    value = tracked(tmp_path)
    replacement = value.sequence[0].replace('[T0]', '[T0-fast]')
    available = ['tests/test_0.py::test_first', replacement, value.sequence[1]]
    window.model.set_tree(build_tree(available))
    window._campaign_collection_complete = True
    window._open_collected_profile(value)
    window.profile_model.apply_execution(0, 0, 0, value.sequence[0], Status.FAILED)
    window.profile_model.apply_execution(1, 0, 0, value.sequence[1], Status.PASSED)
    window.profile_model.set_duration('1:0', 0, 4.2)
    window.profile_model.set_checked_nodeids(['1:0'])
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid('0:0'))
    plan = sync.compare(value, available, str(tmp_path))
    result = sync.apply(value, plan, plan.additions, {0: replacement})
    assert result.sequence == available
    window.campaign_sync.updated(result, value)
    assert not window.profile_model._by_nodeid['1:0'].statuses
    assert window.profile_model._by_nodeid['2:0'].statuses[0] == Status.PASSED
    assert window.profile_model._durations['2:0'][0] == 4.2
    assert window.profile_model.checked_nodeids() == ['0:0', '2:0']
    assert window.profile_tree.currentIndex().internalPointer().node.nodeid == '1:0'
