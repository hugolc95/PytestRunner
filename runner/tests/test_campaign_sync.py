import copy

import pytest

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import (ExecutionProfile, ProfileValidationError,
    export_profile, inspect_profile, validate_profile)


def profile(tmp_path):
    value = ExecutionProfile('Campaign', ['tests/test_a.py::test_a[T0]', 'tests/test_a.py::test_a[T1]'], '', '',
                             step_overrides=[{'timeout': 20}, {}])
    sync.follow(value, [0, 1], 'folder', 'tests', str(tmp_path))
    return value


def test_sources_round_trip_without_changing_older_formats(tmp_path):
    value = profile(tmp_path)
    restored = inspect_profile(export_profile(value, tmp_path / 'tracked')).profile
    assert restored.sequence == value.sequence
    assert restored.step_ids == value.step_ids
    assert restored.tracking == value.tracking
    legacy = ExecutionProfile('Old', ['test_a.py::test_a'], '', '')
    assert inspect_profile(export_profile(legacy, tmp_path / 'legacy')).profile.tracking == {}


def test_new_tests_inherited_yaml_and_repeat_review_is_idempotent(tmp_path):
    value = profile(tmp_path)
    available = value.sequence + ['tests/sub/test_new.py::test_new', 'elsewhere/test_z.py::test_z']
    plan = sync.compare(value, available, str(tmp_path))
    assert [n for _, n in plan.additions] == ['tests/sub/test_new.py::test_new']
    updated = sync.apply(value, plan, plan.additions, {})
    assert updated.step_overrides == [{'timeout': 20}, {}, {}]
    assert updated.step_ids[:2] == value.step_ids
    assert not sync.compare(updated, available, str(tmp_path)).changed


def test_parameter_change_is_reviewed_and_custom_yaml_not_transferred_by_default(tmp_path):
    value = profile(tmp_path)
    replacement = 'tests/test_a.py::test_a[T0-fast]'
    available = [replacement, value.sequence[1]]
    plan = sync.compare(value, available, str(tmp_path))
    assert plan.missing == [0]
    assert plan.candidates[0] == available
    updated = sync.apply(value, plan, plan.additions, {0: replacement})
    assert updated.sequence == available
    assert updated.step_overrides == [{}, {}]
    transferred = sync.apply(value, plan, plan.additions, {0: replacement}, transfer=[0])
    assert transferred.step_overrides[0] == {'timeout': 20}


def test_fixed_selection_detects_missing_but_does_not_expand(tmp_path):
    value = ExecutionProfile('Fixed', ['test_a.py::test_a[T0]'], '', '')
    plan = sync.compare(value, ['test_a.py::test_a[T1]', 'test_a.py::test_a[T2]'], str(tmp_path))
    assert not plan.additions
    assert plan.missing == [0]
    assert len(plan.candidates[0]) == 2


def test_failed_collection_and_other_environment_do_not_offer_deletions(tmp_path):
    value = profile(tmp_path)
    for plan in [sync.compare(value, [], str(tmp_path), complete=False),
                 sync.compare(value, [], str(tmp_path / 'other'))]:
        assert plan.problem
        assert not plan.missing and not plan.additions
        with pytest.raises(ProfileValidationError):
            sync.apply(value, plan, [], {})


def test_excluded_additions_stay_excluded_until_explicitly_restored(tmp_path):
    value = profile(tmp_path)
    available = value.sequence + ['tests/test_b.py::test_b']
    plan = sync.compare(value, available, str(tmp_path))
    updated = sync.apply(value, plan, [], {})
    assert not sync.compare(updated, available, str(tmp_path)).changed
    updated.tracking['sources'][0]['excluded'].clear()
    assert sync.compare(updated, available, str(tmp_path)).additions


def test_intentionally_deleted_occurrences_become_source_exclusions(tmp_path):
    value = profile(tmp_path)
    old = value.sequence[0]
    value.sequence.pop(0)
    value.step_ids.pop(0)
    value.step_overrides.pop(0)
    sync.reconcile(value)
    assert old in value.tracking['sources'][0]['excluded']
    assert not sync.compare(value, [old, *value.sequence], str(tmp_path)).changed


def test_incomplete_missing_decision_and_empty_campaign_are_rejected(tmp_path):
    value = profile(tmp_path)
    plan = sync.compare(value, [], str(tmp_path))
    with pytest.raises(ProfileValidationError):
        sync.apply(value, plan, [], {0: 'remove'})
    empty = sync.apply(value, plan, [], {0: 'remove', 1: 'remove'})
    assert not empty.sequence and empty.tracking['sources']
    kept = sync.apply(value, plan, [], {0: 'keep', 1: 'keep'})
    assert kept.sequence == value.sequence


def test_folder_matching_is_bounded_and_recursive_option_is_respected(tmp_path):
    value = profile(tmp_path)
    source = value.tracking['sources'][0]
    source['recursive'] = False
    plan = sync.compare(value, value.sequence + ['tests/sub/test_b.py::test_b', 'tests_other/test_b.py::test_b'], str(tmp_path))
    assert not plan.additions


def test_rebinding_same_selection_does_not_create_duplicate_followers(tmp_path):
    value = profile(tmp_path)
    sync.follow(value, [0, 1], 'file', 'tests/test_a.py', str(tmp_path))
    assert len(value.tracking['sources']) == 1
    validate_profile(value)


def test_invalid_imported_tracking_is_rejected(tmp_path):
    value = profile(tmp_path)
    value.tracking['sources'][0]['selector'] = '../outside'
    with pytest.raises(ProfileValidationError):
        validate_profile(value)


def test_repeated_source_blocks_keep_independent_additions_and_exclusions(tmp_path):
    value = profile(tmp_path)
    value.sequence += value.sequence[:]
    value.step_ids += ['copy-0', 'copy-1']
    value.step_overrides += [{}, {}]
    sync.follow(value, [2, 3], 'folder', 'tests', str(tmp_path))
    new = 'tests/test_new.py::test_new'
    plan = sync.compare(value, value.sequence + [new], str(tmp_path))
    assert len(plan.additions) == 2
    updated = sync.apply(value, plan, plan.additions[:1], {})
    assert updated.sequence.count(new) == 1
    assert not sync.compare(updated, value.sequence + [new], str(tmp_path)).changed
    assert updated.tracking['sources'][0]['excluded'] == []
    assert updated.tracking['sources'][1]['excluded'] == [new]


def test_failed_atomic_save_leaves_the_previous_profile_intact(tmp_path, monkeypatch):
    import runner.domain.execution_profile as module
    value = profile(tmp_path)
    path = export_profile(value, tmp_path / 'campaign')
    original = path.read_bytes()
    def failure(*_):
        raise OSError('Simulated replacement failure')
    monkeypatch.setattr(module.os, 'replace', failure)
    value.name = 'Changed'
    with pytest.raises(OSError):
        export_profile(value, path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


def test_additions_fit_their_files_without_reordering_existing_tests(tmp_path):
    value = ExecutionProfile('Campaign', ['tests/test_rsa.py::test_verify', 'tests/test_rsa.py::test_sign[T0]'], '', '')
    sync.follow(value, range(2), 'folder', 'tests', str(tmp_path))
    available = ['tests/test_aes.py::test_encrypt', value.sequence[0],
                 'tests/test_rsa.py::test_verify_negative', value.sequence[1], 'tests/test_rsa.py::test_sign[T1]']
    plan = sync.compare(value, available, str(tmp_path))
    updated = sync.apply(value, plan, plan.additions, {})
    assert updated.sequence == available
    assert [n for n in updated.sequence if n in value.sequence] == value.sequence


def test_custom_sequence_is_not_sorted_during_update(tmp_path):
    value = ExecutionProfile('Campaign', ['tests/test_b.py::test_b', 'tests/test_a.py::test_a'], '', '')
    sync.follow(value, range(2), 'folder', 'tests', str(tmp_path))
    available = [value.sequence[1], value.sequence[0], 'tests/test_c.py::test_c']
    plan = sync.compare(value, available, str(tmp_path))
    assert sync.apply(value, plan, plan.additions, {}).sequence[:2] == value.sequence


def test_enabling_tracking_across_t0_t1_groups_creates_independent_sources(tmp_path):
    node = 'tests/test_a.py::test_a'
    groups = [dict(id='t0', name='T0', color='#4466aa', description='', configuration_overrides={'PROTOCOL': 'T0'}),
              dict(id='t1', name='T1', color='#44aa88', description='', configuration_overrides={'PROTOCOL': 'T1'})]
    value = ExecutionProfile('Both protocols', [node, node], '', '', step_groups=groups)
    sync.follow(value, [0, 1], 'folder', 'tests', str(tmp_path))
    assert len(value.tracking['sources']) == 2
    new = 'tests/test_b.py::test_b'
    plan = sync.compare(value, [node, new], str(tmp_path))
    updated = sync.apply(value, plan, plan.additions, {})
    assert updated.step_groups == [groups[0], groups[0], groups[1], groups[1]]
