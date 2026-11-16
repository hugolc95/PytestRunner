import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.campaign_sync import CampaignReviewDialog, CampaignSourcesDialog
from runner.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures('isolated_run_state')


def test_38_tests_under_new_root_are_updated_once_without_individual_choices(qtbot, tmp_path):
    old = [f'security/test_pin.py::TestPin::test_pin[{i}]' for i in range(38)]
    current = ['suite/' + n for n in old]
    profile = ExecutionProfile('Run #0081', old, '', '', step_overrides=[{'timeout': i} for i in range(38)])
    plan = sync.compare(profile, current, str(tmp_path))
    assert len(plan.path_changes) == 38
    dialog = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(dialog)
    assert dialog.findChildren(QComboBox) == []
    assert dialog.apply_button.isEnabled()
    dialog._apply()
    assert dialog.result_profile.sequence == current
    assert dialog.result_profile.step_overrides == profile.step_overrides


def test_unknown_project_does_not_offer_to_delete_all_38_tests(qtbot, tmp_path):
    profile = ExecutionProfile('Run #0081', [f'old/test_old.py::test_old[{i}]' for i in range(38)], '', '')
    plan = sync.compare(profile, ['other/test_new.py::test_new'], str(tmp_path))
    dialog = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(dialog)
    assert dialog.findChildren(QComboBox) == []
    assert dialog.remove_missing.isHidden()
    assert dialog.apply_button.text() == 'Collect again'
    assert '38' in dialog.summary.text()
    dialog._apply()
    assert dialog.request_collection
    assert dialog.result_profile is None


def test_bulk_keep_or_remove_requires_no_per_test_decision(qtbot, tmp_path):
    nodes = [f'test_a.py::test_a[{i}]' for i in range(40)]
    profile = ExecutionProfile('Campaign', nodes, '', '')
    plan = sync.compare(profile, nodes[:2], str(tmp_path))
    kept = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(kept)
    kept._apply()
    assert kept.result_profile.sequence == nodes
    removed = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(removed)
    removed.remove_missing.setChecked(True)
    removed._apply()
    assert removed.result_profile.sequence == nodes[:2]


def test_tracked_parameter_family_refresh_preserves_custom_cases(qtbot, tmp_path):
    old = ['tests/test_a.py::test_a[T0]', 'tests/test_a.py::test_a[T1]']
    current = ['tests/test_a.py::test_a[T0-new]', 'tests/test_a.py::test_a[T1-new]', 'tests/test_a.py::test_a[T2]']
    profile = ExecutionProfile('Campaign', old, '', '', step_overrides=[{}, {'timeout': 20}])
    sync.follow(profile, [0, 1], 'file', 'tests/test_a.py', str(tmp_path))
    plan = sync.compare(profile, current, str(tmp_path))
    dialog = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(dialog)
    dialog._apply()
    assert old[0] not in dialog.result_profile.sequence
    assert old[1] in dialog.result_profile.sequence
    assert set(current) <= set(dialog.result_profile.sequence)
    index = dialog.result_profile.sequence.index(old[1])
    assert dialog.result_profile.step_overrides[index] == {'timeout': 20}


def test_same_filename_in_two_collections_is_not_guessed():
    old = ['test_a.py::TestA::test_run[T0]']
    current = ['suite1/test_a.py::TestA::test_run[T0]', 'suite2/test_a.py::TestA::test_run[T0]']
    assert sync.location_matches(old, current) == {}
    assert sync.location_matches(['security/test_a.py::TestA::test_run[T0]'], ['other/test_a.py::TestA::test_run[T0]']) == {}


def test_followed_folder_and_exclusions_move_with_collection_root(tmp_path):
    profile = ExecutionProfile('Campaign', ['tests/test_a.py::test_a'], '', '')
    sync.follow(profile, [0], 'folder', 'tests', str(tmp_path))
    profile.tracking['sources'][0]['excluded'] = ['tests/test_a.py::test_manual']
    available = ['suite/tests/test_a.py::test_a', 'suite/tests/test_a.py::test_manual', 'suite/tests/test_new.py::test_new']
    plan = sync.compare(profile, available, str(tmp_path))
    assert len(plan.path_changes) == 1
    assert [n for _, n in plan.additions] == [available[2]]
    updated = sync.apply(profile, plan, plan.additions, sync.recommended_decisions(profile, plan))
    assert updated.tracking['sources'][0]['selector'] == 'suite/tests'
    assert updated.tracking['sources'][0]['excluded'] == [available[1]]
    assert not sync.compare(updated, available, str(tmp_path)).changed


def test_contents_dialog_has_no_empty_expert_form_in_fixed_mode(qtbot, tmp_path):
    profile = ExecutionProfile('Campaign', ['tests/security/test_a.py::test_a'], '', '')
    dialog = CampaignSourcesDialog(profile, [0], profile.sequence, str(tmp_path))
    qtbot.addWidget(dialog)
    assert dialog.fixed.isChecked()
    assert dialog.folders.isHidden()
    assert dialog.include_existing.isHidden()
    dialog.following.setChecked(True)
    assert not dialog.folders.isHidden()
    assert dialog.folders.topLevelItemCount() == 1
    dialog._save()
    assert dialog.profile.tracking['sources'][0]['selector'] == 'tests/security'


def test_missing_tests_are_kept_but_select_all_never_launches_them(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    nodes = ['test_a.py::test_a', 'test_b.py::test_b']
    profile = ExecutionProfile('Campaign', nodes, '', '')
    window.model.set_tree(build_tree(nodes[:1]))
    window._campaign_collection_complete = True
    window._open_collected_profile(profile)
    window.profile_model.set_all_checked(True)
    assert window.profile_model.checked_nodeids() == ['0:0']
    assert not window.profile_model.flags(window.profile_model.index_for_nodeid('1:0')) & Qt.ItemIsUserCheckable
    menu = window.profile_run_tree.menu(window.profile_model.index_for_nodeid('1:0'))
    assert not menu.actions()[0].isEnabled()
    launches = []
    monkeypatch.setattr(window, '_start_profile', lambda value, **kw: launches.append(value))
    window.run_selected()
    assert launches[0].sequence == nodes[:1]
    assert window._active_execution_profile.sequence == nodes


def test_root_update_restores_user_selection_after_temporarily_unavailable(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    old = ['test_a.py::test_a', 'test_b.py::test_b']
    available = ['suite/' + n for n in old]
    profile = ExecutionProfile('Campaign', old, '', '')
    sync.ensure_ids(profile)
    window.model.set_tree(build_tree(available))
    window._campaign_collection_complete = True
    window._open_collected_profile(profile)
    assert window.profile_model.checked_nodeids() == []
    plan = sync.compare(profile, available, str(tmp_path))
    result = sync.apply(profile, plan, [], sync.recommended_decisions(profile, plan))
    window.campaign_sync.updated(result, profile)
    assert window.profile_model.checked_nodeids() == ['0:0', '1:0']


def test_campaign_contents_is_saved_with_one_confirmation(qtbot, monkeypatch, tmp_path):
    from runner.ui.execution_profiles_page import ExecutionProfilesPage
    from runner.domain.execution_profile import ProfileStore
    store = ProfileStore(tmp_path / 'profiles')
    profile = ExecutionProfile('Campaign', ['tests/test_a.py::test_a'], '', '')
    store.save(profile)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    page.set_workspace_context(profile.sequence, '', workspace=str(tmp_path))
    def save_once(dialog):
        dialog.following.setChecked(True)
        dialog._save()
        return QDialog.Accepted
    monkeypatch.setattr(CampaignSourcesDialog, 'exec', save_once)
    page.manage_campaign_sources()
    assert store.list()[0].tracking['sources']
    assert not page._dirty
