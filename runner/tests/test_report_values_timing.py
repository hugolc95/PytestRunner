"""Valeurs effectives et durees archivees : aucun zero ou lien invente."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from runner.domain.execution_profile import ExecutionProfile
from runner.domain.history import RunEntry
from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.report_data import report_payload
from runner.domain.report_timing import archived_timings, valid_duration

NODE = 'TSu/RA/Int/FlexiDep/tests/test_card.py::TestCard::test_card[T0]'
SHORT = 'tests/test_card.py::TestCard::test_card[T0]'


def entry(config='Timeout: 15\n', analysis=None):
    profile = ExecutionProfile('Protocol checks', [NODE], 'config.yml', config)
    return RunEntry('run', 1, '/recorded', reader='simuSCR700U1132 Reader', nodeids=(NODE,),
                    counts={'PASSED': 1}, test_statuses={NODE: 'PASSED'}, replay_profile=asdict(profile), analysis_data=analysis)


def test_table_contains_typed_effective_values_and_unambiguous_nested_keys():
    e = entry('Reader: original\nEnabled: false\nRetries: 0\nReaders: []\nEmpty: ""\nNullable: null\nMap: {}\ncard:\n  timeout: 15\n"card.timeout": literal\n')
    data = report_payload([e])
    parameters = {p['parameter']: p['value'] for p in data['rows'][0]['readers'][0]['yaml']['parameters']}
    assert parameters == {'Reader': e.reader, 'Enabled': False, 'Retries': 0, 'Readers': [], 'Empty': '',
                          'Nullable': None, 'Map': {}, 'card.timeout': 15, '["card.timeout"]': 'literal'}


def test_empty_mapping_patch_keeps_the_existing_children_values():
    e = entry('card:\n  timeout: 15\n')
    e.replay_profile['step_overrides'] = [{'card': {}}]
    values = report_payload([e])['rows'][0]['readers'][0]['yaml']['parameters']
    assert values == [{'parameter': 'card.timeout', 'value': 15, 'source': 'Base config.yml'}]


def test_none_duration_is_recovered_with_pytest_root_normalization():
    snapshot = dict(schema=1, occurrences=[dict(nodeid=NODE, attempts=[dict(attempt=0, status='PASSED', duration=None)])])
    text = f'0.20s setup {SHORT}\n1.00s call {SHORT}\n0.03s teardown {SHORT}\n'
    result = report_payload([entry(analysis=snapshot)], [text])['rows'][0]['readers'][0]['attempts'][0]
    assert result['duration'] == pytest.approx(1.23)
    assert result['duration_source'] == 'Recovered from archived pytest timing'


def test_recorded_zero_duration_is_preserved():
    snapshot = dict(schema=1, occurrences=[dict(nodeid=NODE, attempts=[dict(attempt=0, status='PASSED', duration=0.0)])])
    result = report_payload([entry(analysis=snapshot)], [f'12.00s call {SHORT}\n'])['rows'][0]['readers'][0]['attempts'][0]
    assert result['duration'] == 0.0


def test_batch_timings_distinguish_retries_and_duplicate_occurrences_with_commas():
    a = 'TSu/tests/test_card.py::test_card[a, b]'
    b = 'TSu/tests/test_card.py::test_card[c]'
    text = f'''--- {a}, {b} - attempt 1 ---
0.20s call tests/test_card.py::test_card[a, b]
0.40s call tests/test_card.py::test_card[c]
--- {a}, {b} - attempt 2 ---
0.30s call tests/test_card.py::test_card[a, b]
0.50s call tests/test_card.py::test_card[c]
--- {a} - attempt 1 ---
0.70s call tests/test_card.py::test_card[a, b]
'''
    assert archived_timings(text, [a, b, a]) == {(0, 0): .2, (1, 0): .4, (0, 1): .3, (1, 1): .5, (2, 0): .7}


def test_ambiguous_plain_summary_is_not_assigned_to_repeated_tests():
    sequence = ['SuiteA/' + SHORT, 'SuiteB/' + SHORT]
    assert archived_timings(f'2.00s call {SHORT}', sequence) == {}
    assert archived_timings(f'2.00s call {SHORT}', [NODE, NODE]) == {}


def test_not_run_snapshot_does_not_borrow_an_older_timing():
    snapshot = dict(schema=1, occurrences=[dict(nodeid=NODE, attempts=[], not_run=True)])
    result = report_payload([entry(analysis=snapshot)], [f'12.00s call {SHORT}\n'])['rows'][0]['readers'][0]
    assert result['status'] == 'notrun' and result['attempts'] == []


def test_missing_duration_stays_explicitly_missing():
    result = report_payload([entry()], ['No timing was recorded'])['rows'][0]['readers'][0]['attempts'][0]
    assert result['duration'] is None
    for invalid in (True, '0.2', -1, float('nan'), float('inf'), None):
        assert not valid_duration(invalid)


def test_capture_uses_live_then_batch_duration_for_the_exact_partial_occurrence():
    from runner.ui.report_capture import capture_report
    reader = Reader('Reader A', 7)
    batch = ReaderReport(reader, durations={NODE: 3.5})
    model = SimpleNamespace(occurrence_keys=lambda _: ['42:0'], locations={'42:0': (42, 0, NODE)}, _durations={})
    window = SimpleNamespace(_archive_run_nodeids=(NODE,), _running_execution_profile=object(),
        profile_run_tree=SimpleNamespace(position=lambda _: 42), profile_model=model,
        _profile_count_statuses={(42, 0, 7): Status.PASSED},
        _profile_live_details={('42:0', 7): {'duration': 1.25}}, _profile_logs=None,
        _profile_reports={('42:0', 7): batch}, _archive_reader_atrs={}, _archive_save_logs=True)
    first = capture_report(window, batch)['occurrences'][0]['attempts'][0]
    assert first['duration'] == 1.25
    window._profile_live_details.clear()
    assert capture_report(window, batch)['occurrences'][0]['attempts'][0]['duration'] == 3.5
