import copy

import pytest
from PySide6.QtCore import Qt

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.ui.campaign_sync import CampaignSourcesDialog
from runner.ui.execution_profiles_page import AddTestsDialog, ExecutionProfilesPage

pytestmark = pytest.mark.usefixtures('isolated_run_state')
BASE = 'tests/test_hmac.py::test_hmac'
CASES = [BASE + '[' + name + ']' for name in ('SHA256', 'SHA384', 'SHA512', 'SHA224')]
OTHER = 'tests/test_hmac.py::test_other'
GROUP = dict(id='hmac', name='HMAC', color='#aa77cc', description='', configuration_overrides={'PROTOCOL': 'T0'})


def update(profile, available, tmp_path):
    plan = sync.compare(profile, available, str(tmp_path))
    return sync.apply(profile, plan, plan.additions, sync.recommended_decisions(profile, plan))


def page_for(qtbot, tmp_path, profile):
    store = ProfileStore(tmp_path / 'profiles')
    store.save(profile)
    page = ExecutionProfilesPage(store)
    qtbot.addWidget(page)
    page.set_workspace_context(CASES + [OTHER], '', workspace=str(tmp_path))
    return page


def tracked_case(tmp_path):
    profile = ExecutionProfile('HMAC', CASES[:1], '', '', step_groups=[copy.deepcopy(GROUP)])
    sync.follow(profile, [0], 'test', BASE, str(tmp_path))
    return profile


@pytest.mark.parametrize('initial', [CASES[:1], CASES[:3]])
def test_checking_a_single_collected_case_does_not_follow_its_parents(qtbot, tmp_path, initial):
    dialog = AddTestsDialog(initial)
    qtbot.addWidget(dialog)
    dialog.model.setData(dialog.model.index_for_nodeid(CASES[0]), Qt.Checked, Qt.CheckStateRole)
    assert not dialog.follow_selection.isEnabled()
    assert not dialog.follow_selection.isChecked()
    received = []
    dialog.tests_added.connect(lambda values: received.append((values, copy.deepcopy(dialog.pending_sources))))
    dialog._add()
    assert received == [(CASES[:1], [])]
    profile = ExecutionProfile('One case', CASES[:1], '', '', step_groups=[copy.deepcopy(GROUP)])
    assert not sync.compare(profile, CASES, str(tmp_path)).changed


def test_checking_a_complete_function_with_one_case_still_follows_future_cases(qtbot):
    dialog = AddTestsDialog(CASES[:1] + [OTHER])
    qtbot.addWidget(dialog)
    leaf = dialog.model.index_for_nodeid(CASES[0])
    function = leaf.parent()
    dialog.model.setData(function, Qt.Checked, Qt.CheckStateRole)
    assert dialog.follow_selection.isEnabled()
    dialog._add()
    assert dialog.pending_sources == [('test', BASE, CASES[:1])]


def test_checking_all_cases_individually_keeps_an_exact_selection(qtbot):
    dialog = AddTestsDialog(CASES[:3])
    qtbot.addWidget(dialog)
    for nodeid in CASES[:3]:
        dialog.model.setData(dialog.model.index_for_nodeid(nodeid), Qt.Checked, Qt.CheckStateRole)
    dialog._add()
    assert dialog.pending_sources == []


def test_duplicating_a_case_does_not_clone_the_whole_function_rule(qtbot, tmp_path):
    page = page_for(qtbot, tmp_path, tracked_case(tmp_path))
    page.sequence_list.setCurrentItem(page._step_items()[0])
    page.duplicate_steps()
    result = page._profile_from_editor()
    assert len(result.tracking['sources']) == 1
    assert result.step_ids[1] not in result.tracking['members']
    assert update(result, CASES, tmp_path).sequence == CASES + CASES[:1]


def test_copying_a_case_does_not_clone_the_whole_function_rule(qtbot, qapp, tmp_path):
    page = page_for(qtbot, tmp_path, tracked_case(tmp_path))
    try:
        page.sequence_list.setCurrentItem(page._step_items()[0])
        page.copy_elements()
        page.paste_elements()
        result = page._profile_from_editor()
        assert len(result.tracking['sources']) == 1
        assert result.step_ids[1] not in result.tracking['members']
        assert update(result, CASES, tmp_path).sequence == CASES + CASES[:1]
    finally:
        qapp.clipboard().clear()


def test_contents_save_does_not_enable_following_for_other_fixed_cases(qtbot, tmp_path):
    profile = ExecutionProfile('Mixed', [OTHER, CASES[0]], '', '', step_groups=[copy.deepcopy(GROUP)] * 2)
    sync.follow(profile, [0], 'test', OTHER, str(tmp_path))
    before = copy.deepcopy(profile.tracking)
    dialog = CampaignSourcesDialog(profile, [0, 1], CASES[:3] + [OTHER], str(tmp_path))
    qtbot.addWidget(dialog)
    assert dialog.following.isChecked()
    dialog._save()
    assert dialog.profile.tracking == before
    assert not sync.compare(dialog.profile, CASES + [OTHER], str(tmp_path)).changed


def test_followed_file_does_not_add_siblings_of_a_fixed_case_in_same_group(tmp_path):
    profile = ExecutionProfile('Mixed', [OTHER, CASES[0]], '', '', step_groups=[copy.deepcopy(GROUP)] * 2)
    sync.follow(profile, [0], 'file', 'tests/test_hmac.py', str(tmp_path))
    unrelated = 'tests/test_hmac.py::test_new'
    result = update(profile, CASES + [OTHER, unrelated], tmp_path)
    assert result.sequence.count(CASES[0]) == 1
    assert not any(c in result.sequence for c in CASES[1:])
    assert unrelated in result.sequence


@pytest.mark.parametrize('kind', ['group', 'function'])
@pytest.mark.parametrize('operation', ['duplicate', 'copy'])
def test_whole_group_or_function_copies_still_follow_all_cases(qtbot, qapp, tmp_path, kind, operation):
    page = page_for(qtbot, tmp_path, tracked_case(tmp_path))
    try:
        item = page.sequence_list.topLevelItem(0) if kind == 'group' else page._step_items()[0].parent()
        page.sequence_list.setCurrentItem(item)
        if operation == 'duplicate':
            page.duplicate_steps()
        else:
            page.copy_elements()
            page.paste_elements()
        result = page._profile_from_editor()
        assert len(result.tracking['sources']) == 2
        assert update(result, CASES, tmp_path).sequence == CASES * 2
    finally:
        qapp.clipboard().clear()


def test_unchecking_one_case_in_a_whole_file_keeps_other_complete_functions_followed(qtbot):
    extra = 'tests/test_hmac.py::test_aux[one]'
    dialog = AddTestsDialog(CASES[:3] + [extra])
    qtbot.addWidget(dialog)
    file = dialog.model.index_for_nodeid(CASES[0]).parent().parent()
    dialog.model.setData(file, Qt.Checked, Qt.CheckStateRole)
    dialog.model.setData(dialog.model.index_for_nodeid(CASES[1]), Qt.Unchecked, Qt.CheckStateRole)
    dialog._add()
    assert dialog.pending_sources == [('test', 'tests/test_hmac.py::test_aux', [extra])]


def test_selecting_a_class_follows_its_complete_parameterized_function(qtbot):
    nodeid = 'tests/test_hmac.py::TestHmac::test_run[one]'
    dialog = AddTestsDialog([nodeid, OTHER])
    qtbot.addWidget(dialog)
    cls = dialog.model.index_for_nodeid(nodeid).parent().parent()
    dialog.model.setData(cls, Qt.Checked, Qt.CheckStateRole)
    dialog._add()
    assert dialog.pending_sources == [('test', 'tests/test_hmac.py::TestHmac::test_run', [nodeid])]


def test_removing_a_fixed_case_does_not_let_the_file_add_back_its_entire_family(qtbot, tmp_path):
    profile = ExecutionProfile('Mixed', [OTHER, CASES[0]], '', '', step_groups=[copy.deepcopy(GROUP)] * 2)
    sync.follow(profile, [0], 'file', 'tests/test_hmac.py', str(tmp_path))
    page = page_for(qtbot, tmp_path, profile)
    page.sequence_list.setCurrentItem(page._step_items()[1])
    page.remove_steps()
    result = page._profile_from_editor()
    assert result.sequence == [OTHER]
    assert len(result.tracking['sources']) == 1
    assert BASE in result.tracking['sources'][0]['excluded']
    assert not sync.compare(result, [OTHER, *CASES], str(tmp_path)).changed
    page.undo_stack.undo()
    assert page._profile_from_editor().sequence == [OTHER, CASES[0]]


def test_review_removing_a_missing_fixed_case_keeps_other_followed_tests(tmp_path):
    profile = ExecutionProfile('Mixed', [OTHER, CASES[0]], '', '', step_groups=[copy.deepcopy(GROUP)] * 2)
    sync.follow(profile, [0], 'file', 'tests/test_hmac.py', str(tmp_path))
    plan = sync.compare(profile, [OTHER, *CASES[1:]], str(tmp_path))
    result = sync.apply(profile, plan, plan.additions, sync.recommended_decisions(profile, plan, remove_unmatched=True))
    assert result.sequence == [OTHER]
    assert len(result.tracking['sources']) == 1
    assert not sync.compare(result, [OTHER, *CASES], str(tmp_path)).changed


def test_copying_a_case_does_not_include_a_neighbouring_empty_group(qtbot, qapp, tmp_path):
    from runner.domain.execution_profile import group_entry
    profile = tracked_case(tmp_path)
    empty = dict(GROUP, id='empty', name='Empty')
    profile.empty_groups = [dict(position=1, group=group_entry([GROUP, empty]))]
    page = page_for(qtbot, tmp_path, profile)
    try:
        page.sequence_list.setCurrentItem(page._step_items()[0])
        page.copy_elements()
        payload = page.sequence_clipboard.payload
        assert payload['version'] == 1
        assert not payload['items'][0].get('empty_groups')
    finally:
        qapp.clipboard().clear()


def test_following_preference_is_restored_after_selecting_a_fixed_case(qtbot):
    dialog = AddTestsDialog(CASES[:3])
    qtbot.addWidget(dialog)
    leaf = dialog.model.index_for_nodeid(CASES[0])
    dialog.model.setData(leaf.parent(), Qt.Checked, Qt.CheckStateRole)
    dialog.follow_selection.setChecked(False)
    dialog.model.set_all_checked(False)
    dialog.model.setData(leaf, Qt.Checked, Qt.CheckStateRole)
    assert not dialog.follow_selection.isChecked() and not dialog.follow_selection.isEnabled()
    dialog.model.setData(leaf.parent(), Qt.Checked, Qt.CheckStateRole)
    assert dialog.follow_selection.isEnabled() and not dialog.follow_selection.isChecked()
    dialog.follow_selection.setChecked(True)
    dialog._add()
    first = copy.deepcopy(dialog.pending_sources)
    dialog._add_again()
    assert dialog.pending_sources == first and first


def test_pasting_a_case_from_an_older_clipboard_ignores_its_implicit_following(qtbot, qapp, tmp_path):
    from PySide6.QtCore import QMimeData
    from runner.domain.profile_clipboard import MIME, encode_selection
    profile = tracked_case(tmp_path)
    page = page_for(qtbot, tmp_path, profile)
    try:
        page.sequence_list.setCurrentItem(page._step_items()[0])
        page.copy_elements()
        payload = copy.deepcopy(page.sequence_clipboard.payload)
        payload['version'] = 2
        source = copy.deepcopy(profile.tracking['sources'][0])
        source.update(group={}, anchor='0')
        payload['items'][0]['tracking'] = dict(workspace=profile.tracking['workspace'], sources=[source],
            members={'0': dict(source=source['id'], nodeid=CASES[0])})
        mime = QMimeData()
        mime.setData(MIME, encode_selection(payload))
        qapp.clipboard().setMimeData(mime)
        page.paste_elements()
        result = page._profile_from_editor()
        assert len(result.tracking['sources']) == 1
        assert result.step_ids[1] not in result.tracking['members']
    finally:
        qapp.clipboard().clear()


def test_double_click_then_add_again_does_not_reuse_a_previous_function_rule(qtbot):
    dialog = AddTestsDialog(CASES[:3])
    qtbot.addWidget(dialog)
    leaf = dialog.model.index_for_nodeid(CASES[0])
    dialog.model.setData(leaf.parent(), Qt.Checked, Qt.CheckStateRole)
    dialog._add()
    assert dialog._last_sources
    dialog._add_clicked_test(dialog.proxy.mapFromSource(leaf))
    dialog._add_again()
    assert dialog.pending_sources == []
    assert dialog._last_added == CASES[:1]
