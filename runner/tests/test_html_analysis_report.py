"""Rapport portable, sans confusion entre lecteurs et occurrences."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re

import pytest

from runner.domain.execution_profile import ExecutionProfile, ExecutionOptions
from runner.domain.history import History, RunEntry
from runner.domain.report import html_report, write_html
from runner.domain.report_data import report_payload


NODE = 'TSu/Card/tests/nominal/test_card.py::TestCard::test_card[T0]'


def group(identifier, name, **extra):
    return dict(id=identifier, name=name, color='#3388cc', description=name + ' description', **extra)


def entry(tmp_path, reader='Reader A', **changes):
    root = group('root', 'Protocol T0', configuration_overrides={'Protocol': 'T0'})
    child = group('child', 'Nominal', parents=[root])
    profile = ExecutionProfile('Card qualification', [NODE, NODE], 'config.yaml',
        'Reader: original\nProtocol: default\nTimeout: 15\n',
        execution=ExecutionOptions(repetitions=2), step_groups=[child, child],
        step_overrides=[{}, {'Timeout': 30}])
    data = dict(schema=1, app_version='1.5.5', interpreter='C:/Python312/python.exe',
                commands=[['python', '-m', 'pytest', NODE]], issues=[], atr='3B123456',
                occurrences=[dict(position=i, nodeid=NODE, attempts=[dict(attempt=0,
                    status='PASSED', duration=.2+i)]) for i in range(4)])
    data['occurrences'][1]['attempts'] = [dict(attempt=0, status='FAILED', duration=.1,
        details=[dict(nodeid=NODE, phase='call', kind='test', body='E AssertionError: first failure', message='first failure')]),
        dict(attempt=1, status='PASSED', duration=.3)]
    data['occurrences'][3] = dict(position=3, nodeid=NODE, attempts=[], not_run=True)
    fields = dict(id='run-one', timestamp=1700000000, workspace=str(tmp_path), reader=reader,
        run_kind='profile', profile_name=profile.name, replay_profile=asdict(profile),
        nodeids=tuple([NODE]*4), counts={'PASSED': 3}, analysis_data=data)
    fields.update(changes)
    return RunEntry(**fields)


def payload_from_html(page):
    return json.loads(re.search(r'<script type="application/json" id="report-data">(.*?)</script>', page, re.S)[1])


def test_nested_groups_order_repetitions_and_custom_yaml_are_preserved(tmp_path):
    e = entry(tmp_path)
    data = report_payload([e])
    assert len(data['rows']) == 4
    assert [row['repetition'] for row in data['rows']] == [1, 1, 2, 2]
    assert [row['nodeid'] for row in data['rows']] == [NODE]*4
    assert all(row['groups'] == ['Protocol T0', 'Nominal'] for row in data['rows'])
    names = [node['name'] for node in data['nodes'].values()]
    assert 'Repetition 1 / 2' in names and 'Repetition 2 / 2' in names
    assert 'Protocol T0' in names and 'Nominal' in names
    assert 'TestCard' not in names and 'TSu' not in names
    assert data['rows'][1]['custom']
    yaml = data['rows'][1]['readers'][0]['yaml']
    assert 'Timeout: 30' in yaml['effective'] and 'Reader: Reader A' in yaml['effective']
    assert 'Protocol: T0' in yaml['effective']
    assert {'parameter': 'Timeout', 'source': 'This occurrence'} in yaml['origins']
    assert data['rows'][0]['readers'][0]['yaml']['base'].endswith('Timeout: 15\n')


def test_attempts_and_missing_results_are_never_merged(tmp_path):
    data = report_payload([entry(tmp_path)])
    second = data['rows'][1]['readers'][0]
    assert second['status'] == 'passed'
    assert [a['status'] for a in second['attempts']] == ['failed', 'passed']
    assert 'first failure' in second['attempts'][0]['trace']
    assert data['rows'][3]['readers'][0]['status'] == 'notrun'
    assert data['counts'] == {'passed': 3, 'notrun': 1}


def test_complete_report_compares_readers_without_crossing_runs(tmp_path):
    a = entry(tmp_path)
    other = json.loads(json.dumps(a.analysis_data))
    other['occurrences'][0]['attempts'][0]['status'] = 'ERROR'
    b = replace(a, reader='Reader B', analysis_data=other)
    data = report_payload([a, b])
    assert data['readers'] == ['Reader A', 'Reader B']
    assert [r['status'] for r in data['rows'][0]['readers']] == ['passed', 'error']
    with pytest.raises(ValueError, match='same run'):
        report_payload([a, replace(b, id='different')])
    with pytest.raises(ValueError, match='same run'):
        report_payload([a, replace(b, workspace='different')])


def test_analysis_is_a_sidecar_and_logs_survive_deletion(tmp_path):
    log = tmp_path / 'original.log'
    log.write_text('APDU 00 A4\nResponse 9000\n')
    e = entry(tmp_path)
    e.analysis_data['occurrences'][0]['attempts'][0]['log_path'] = str(log)
    history = History(tmp_path / 'history')
    saved = history.add(e, 'original console')
    assert saved.analysis_data is None and Path(saved.analysis_file).exists()
    assert 'Response 9000' not in history.fichier.read_text()
    log.unlink()
    reloaded = History(history.racine).entries()[0]
    data = report_payload([reloaded])
    assert 'Response 9000' in data['rows'][0]['readers'][0]['attempts'][0]['log']
    page = html_report([reloaded])
    assert 'Response 9000' in page and 'original console' in page
    sidecar = Path(saved.analysis_file)
    history.clear()
    assert not sidecar.exists()


def test_disabled_complete_logs_are_respected(tmp_path):
    log = tmp_path / 'private.log'; log.write_text('NOT_TO_BE_ARCHIVED')
    e = entry(tmp_path)
    e.analysis_data['save_logs'] = False
    e.analysis_data['occurrences'][0]['attempts'][0]['log_path'] = str(log)
    saved = History(tmp_path / 'history').add(e)
    text = Path(saved.analysis_file).read_text()
    assert 'NOT_TO_BE_ARCHIVED' not in text
    assert 'disabled in this profile' in text


@pytest.mark.parametrize('field', ['name', 'description', 'nodeid', 'trace', 'yaml', 'console'])
def test_untrusted_text_remains_text_in_static_html_and_json(tmp_path, field):
    attack = '</script><script>window.PWNED=1</script><img src=x onerror=alert(1)> & "'
    e = entry(tmp_path)
    data = json.loads(json.dumps(e.analysis_data))
    profile = json.loads(json.dumps(e.replay_profile))
    output = ''
    if field == 'name': profile['name'] = attack
    if field == 'description': profile['step_groups'][0]['description'] = attack
    if field == 'nodeid':
        profile['sequence'] = [attack, NODE]
        for i in (0, 2): data['occurrences'][i]['nodeid'] = attack
    if field == 'trace': data['occurrences'][1]['attempts'][0]['details'][0]['body'] = attack
    if field == 'yaml': profile['configuration_text'] = 'value: ' + json.dumps(attack)
    if field == 'console': output = attack
    e = replace(e, replay_profile=profile, analysis_data=data, run_name=attack if field == 'name' else '')
    page = html_report(e, output)
    assert '<script>window.PWNED=1</script>' not in page
    assert '<img src=x onerror=' not in page
    assert page.count('<script') == 3
    parsed = payload_from_html(page)
    assert parsed['schema'] == 1
    assert '\\u003c' in page


def test_legacy_duplicate_with_unknown_attempt_mapping_stays_unknown(tmp_path):
    e = entry(tmp_path, analysis_data=None, executions=(), test_statuses={NODE: 'PASSED'})
    data = report_payload([e])
    assert all(result['readers'][0]['status'] == 'unknown' for result in data['rows'])
    assert data['contexts'][0]['interpreter'].startswith('Not recorded')


def test_missing_or_corrupt_sidecar_remains_exportable(tmp_path):
    e = entry(tmp_path, analysis_data=None, analysis_file=str(tmp_path / 'missing.json'))
    assert html_report(e).startswith('<!DOCTYPE html>')
    Path(e.analysis_file).write_text('{not-json')
    assert html_report(e).startswith('<!DOCTYPE html>')


def test_no_network_assets_and_readable_fallback_are_embedded(tmp_path):
    page = html_report(entry(tmp_path), '\x1b[31mraw console\x1b[0m')
    assert '<script src=' not in page and '<link' not in page
    assert 'fetch(' not in page and 'XMLHttpRequest' not in page
    assert 'data:image/png;base64,' in page and 'alt="IN Groupe"' in page
    assert 'tr-static' in page and 'Protocol T0' in page and 'raw console' in page
    assert '\x1b[' not in page


def test_atomic_export_does_not_destroy_existing_file_on_invalid_selection(tmp_path):
    path = tmp_path / 'report.html';path.write_text('previous report')
    a = entry(tmp_path)
    ok, message = write_html([a, replace(a, id='other')], path)
    assert not ok and 'same run' in message
    assert path.read_text() == 'previous report'
    assert not path.with_name('report.html.tmp').exists()


def test_background_archive_commits_metadata_before_reading_analysis(qtbot, tmp_path, monkeypatch):
    from runner.services.finalize_service import RunArchiveWorker
    from runner.domain import report_capture
    root = tmp_path / 'history'
    real = report_capture.persist_analysis
    observed = []
    def persist(e, directory):
        stored = History(directory).find(e.id)
        observed.append(stored is not None and not stored.analysis_file)
        return real(e, directory)
    monkeypatch.setattr(report_capture, 'persist_analysis', persist)
    worker = RunArchiveWorker(root, 100, ((entry(tmp_path), 'recorded stdout'),))
    done = []
    worker.done.connect(lambda ok, message: done.append((ok, message)))
    worker.start()
    qtbot.waitUntil(lambda: bool(done), timeout=15000)
    worker.wait(1000)
    assert observed == [True]
    assert done == [(True, '')]
    saved = History(root).find('run-one')
    assert saved.analysis_file and saved.output() == 'recorded stdout'
    assert report_payload([saved])['rows'][1]['readers'][0]['status'] == 'passed'
    worker.deleteLater()


def test_recorded_executions_survive_a_missing_legacy_nodeid_list(tmp_path):
    e = RunEntry('old', 1, str(tmp_path), executions=(('a.py::test_a', 'PASSED'),))
    payload = report_payload([e])
    assert payload['rows'][0]['nodeid'] == 'a.py::test_a'
    assert payload['rows'][0]['readers'][0]['status'] == 'passed'
