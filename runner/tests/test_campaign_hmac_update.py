import pytest

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ExecutionProfile, ProfileStore, export_profile, inspect_profile
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.campaign_sync import CampaignReviewDialog, CampaignSourcesDialog
from runner.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures('isolated_run_state')
HMAC = 'TSu/RA/Int/FlexiDep/tests/nominal/test_02_test_HMAC.py::TestSuite_test_02_test_HMAC::test_test_HMAC_nominal'
CASES = [HMAC + '[' + v + ']' for v in ('ALG_HMAC_SHA_256', 'ALG_HMAC_SHA_384', 'ALG_HMAC_SHA_512')]


def group(index):
    return dict(id=f'g{index}', name=f'Module {index}', color='#8877cc', description='Qualification',
                configuration_overrides={'PROTOCOL': 'T0' if index % 2 == 0 else 'T1'})


def review(profile, available, tmp_path):
    plan = sync.compare(profile, available, str(tmp_path))
    return sync.apply(profile, plan, plan.additions, sync.recommended_decisions(profile, plan))


def test_legacy_273_test_campaign_expands_hmac_at_all_13_calls(qtbot, tmp_path):
    other = [f'tests/test_other.py::test_other_{i}' for i in range(20)]
    block = other[:8] + [HMAC] + other[8:]
    profile = ExecutionProfile('FLEXI DEPT ALL', block * 13, '', '',
        step_groups=[group(i) for i in range(13) for _ in block],
        step_overrides=[{'timeout': i + 10} if n == HMAC else {} for i in range(13) for n in block])
    available = other + CASES
    plan = sync.compare(profile, available, str(tmp_path))
    assert len(plan.parameter_updates) == 13
    dialog = CampaignReviewDialog(profile, plan)
    qtbot.addWidget(dialog)
    assert dialog.apply_button.isEnabled()
    assert '+26' in dialog.summary.text() and '299' in dialog.summary.text()
    dialog._apply()
    result = dialog.result_profile
    assert len(result.sequence) == 299 and HMAC not in result.sequence
    for i in range(13):
        start = i * 23 + 8
        assert result.sequence[start:start + 3] == CASES
        assert result.step_groups[start:start + 3] == [group(i)] * 3
        assert result.step_overrides[start:start + 3] == [{'timeout': i + 10}] * 3
    result = inspect_profile(export_profile(result, tmp_path / 'campaign')).profile
    assert not sync.compare(result, available, str(tmp_path)).changed
    fourth = HMAC + '[ALG_HMAC_SHA_224]'
    later = review(result, [*available, fourth], tmp_path)
    assert len(later.sequence) == 312 and later.sequence.count(fourth) == 13
    assert not sync.compare(later, [*available, fourth], str(tmp_path)).changed
    assert 'tests/test_unrelated.py::test_new' not in review(later, [*available, fourth, 'tests/test_unrelated.py::test_new'], tmp_path).sequence


def test_adjacent_copies_keep_independent_parameter_calls_and_yaml(tmp_path):
    profile = ExecutionProfile('Repeated HMAC', [HMAC, HMAC], '', '',
        step_overrides=[{'timeout': 10}, {'timeout': 40}])
    result = review(profile, CASES, tmp_path)
    assert result.sequence == CASES * 2
    assert result.step_overrides == [{'timeout': 10}] * 3 + [{'timeout': 40}] * 3
    assert len(result.tracking['sources']) == 2


def test_existing_parameter_calls_in_same_followed_folder_each_receive_new_case(tmp_path):
    gap = 'tests/test_gap.py::test_gap'
    profile = ExecutionProfile('Two calls', [*CASES[:2], gap, *CASES[:2]], '', '')
    sync.follow(profile, range(5), 'folder', '.', str(tmp_path))
    result = review(profile, [*CASES, gap], tmp_path)
    assert result.sequence == [*CASES, gap, *CASES]
    fourth = HMAC + '[ALG_HMAC_SHA_224]'
    assert review(result, [*CASES, fourth, gap], tmp_path).sequence == [*CASES, fourth, gap, *CASES, fourth]


def test_declining_parameter_changes_and_fixed_case_selection_stay_unchanged(qtbot, tmp_path):
    profile = ExecutionProfile('HMAC', [HMAC], '', '')
    dialog = CampaignReviewDialog(profile, sync.compare(profile, CASES, str(tmp_path)))
    qtbot.addWidget(dialog)
    dialog.include_new.setChecked(False)
    assert not dialog.apply_button.isEnabled()
    fixed = ExecutionProfile('One explicit case', CASES[:1], '', '')
    assert not sync.compare(fixed, CASES, str(tmp_path)).changed


def test_intentional_case_exclusion_is_local_to_its_call(tmp_path):
    profile = ExecutionProfile('Two calls', [HMAC, HMAC], '', '')
    result = review(profile, CASES, tmp_path)
    excluded = result.sequence.pop(1)
    result.step_ids.pop(1)
    result.step_groups.pop(1)
    result.step_overrides.pop(1)
    sync.reconcile(result)
    fourth = HMAC + '[new]'
    updated = review(result, [*CASES, fourth], tmp_path)
    assert updated.sequence.count(excluded) == 1
    assert updated.sequence.count(fourth) == 2


def test_dialogs_keep_size_while_paths_and_source_modes_change(qtbot, tmp_path):
    profile = ExecutionProfile('HMAC', [HMAC] * 13, '', '')
    dialog = CampaignReviewDialog(profile, sync.compare(profile, CASES, str(tmp_path)))
    qtbot.addWidget(dialog)
    dialog.show()
    initial = dialog.size()
    dialog.details_button.click()
    qtbot.waitUntil(lambda: dialog.details_button.isChecked())
    assert dialog.size() == initial
    dialog.details_button.click()
    assert dialog.size() == initial
    sources = CampaignSourcesDialog(profile, range(13), CASES, str(tmp_path))
    qtbot.addWidget(sources)
    sources.show()
    initial = sources.size()
    sources.following.setChecked(True)
    assert sources.size() == initial
    sources.fixed.setChecked(True)
    assert sources.size() == initial


def test_expansion_copies_the_original_call_checkbox_to_every_new_case(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    gap = 'tests/test_gap.py::test_gap'
    before = ExecutionProfile('HMAC', [HMAC, gap, HMAC], '', '', step_groups=[group(0)] * 3)
    sync.ensure_ids(before)
    window.model.set_tree(build_tree([*CASES, gap]))
    window._campaign_collection_complete = True
    window._open_collected_profile(before)
    window.profile_model.set_checked_nodeids(['0:0', '1:0'])
    result = review(before, [*CASES, gap], tmp_path)
    window.campaign_sync.updated(result, before)
    assert window.profile_model.checked_nodeids() == ['0:0', '1:0', '2:0', '3:0']


def test_collection_root_changes_keep_excluded_cases_and_function_yaml(tmp_path):
    result = review(ExecutionProfile('HMAC', [HMAC], '', '', step_overrides=[{'timeout': 25}]), CASES, tmp_path)
    result.sequence.pop(1)
    result.step_ids.pop(1)
    result.step_overrides.pop(1)
    result.step_groups.pop(1)
    sync.reconcile(result)
    new = HMAC + '[new]'
    available = ['suite/' + n for n in [*CASES, new]]
    updated = review(result, available, tmp_path)
    assert updated.sequence == ['suite/' + CASES[0], 'suite/' + CASES[2], 'suite/' + new]
    assert updated.step_overrides == [{'timeout': 25}] * 3
    assert not sync.compare(updated, available, str(tmp_path)).changed


def test_incomplete_or_ambiguous_collection_never_expands_legacy_calls(tmp_path):
    profile = ExecutionProfile('HMAC', [HMAC], '', '')
    assert not sync.compare(profile, CASES, str(tmp_path), complete=False).parameter_updates
    available = ['a/' + n for n in CASES] + ['b/' + n for n in CASES]
    plan = sync.compare(profile, available, str(tmp_path))
    assert not plan.parameter_updates
    assert sync.recommended_decisions(profile, plan) == {0: 'keep'}


def test_changing_group_yaml_after_conversion_does_not_duplicate_parameter_cases(tmp_path):
    profile = ExecutionProfile('HMAC', [HMAC], '', '', step_groups=[group(0)])
    sync.follow(profile, [0], 'folder', '.', str(tmp_path))
    result = review(profile, CASES, tmp_path)
    for entry in result.step_groups:
        entry['configuration_overrides'] = {'PROTOCOL': 'T1'}
        entry['color'] = '#998800'
    sync.reconcile(result)
    fourth = HMAC + '[new]'
    updated = review(result, [*CASES, fourth], tmp_path)
    assert updated.sequence == [*CASES, fourth]
    assert all(g['configuration_overrides'] == {'PROTOCOL': 'T1'} for g in updated.step_groups)
    assert not sync.compare(updated, [*CASES, fourth], str(tmp_path)).changed


def test_function_wide_yaml_survives_changed_case_ids_without_leaving_old_cases(tmp_path):
    before = ExecutionProfile('HMAC', [HMAC], '', '', step_overrides=[{'timeout': 25}])
    converted = review(before, CASES, tmp_path)
    changed = [n.replace('ALG_HMAC', 'ALG_HMAC_FAST') for n in CASES]
    updated = review(converted, changed, tmp_path)
    assert updated.sequence == changed
    assert updated.step_overrides == [{'timeout': 25}] * 3
    assert not sync.compare(updated, changed, str(tmp_path)).changed


def test_run_tests_update_keeps_legacy_checks_when_editor_shows_another_profile(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QDialog
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    gap = 'tests/test_gap.py::test_gap'
    before = ExecutionProfile('Legacy HMAC', [HMAC, gap, HMAC], '', '', step_groups=[group(0)] * 3)
    other = ExecutionProfile('Another campaign', [gap], '', '')
    page = window.profiles_page
    page.store = ProfileStore(tmp_path / 'profiles')
    page.store.save(before)
    page.store.save(other)
    page.refresh()
    page.profile_list.setCurrentRow(next(i for i, p in enumerate(page._profiles) if p.profile_id == other.profile_id))
    window.model.set_tree(build_tree([*CASES, gap]))
    window._campaign_collection_complete = True
    window._open_collected_profile(before)
    window.profile_model.set_checked_nodeids(['0:0', '1:0'])
    def apply(dialog):
        dialog._apply()
        return QDialog.Accepted
    monkeypatch.setattr(CampaignReviewDialog, 'exec', apply)
    window.campaign_sync.review()
    assert window.profile_model.checked_nodeids() == ['0:0', '1:0', '2:0', '3:0']
    assert page.current_profile().profile_id == other.profile_id
