"""Un processus perdu ne doit ni inventer un succes ni faire disparaitre la suite."""
import json
import os
import sys

import pytest

from runner.domain import diagnostics, execution
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.process_crash import native_crash


@pytest.mark.parametrize('code', [3221225477, -1073741819])
@pytest.mark.parametrize('phase', ['setup', 'call', 'teardown'])
def test_windows_crash_is_attached_to_active_test_even_after_terminal_pass(tmp_path, monkeypatch, code, phase):
    node = 'test_card.py::test_card[T0 value]'
    phase_line = diagnostics.PHASE_PREFIX + json.dumps(dict(nodeid=node, phase=phase)) + '\n'
    lines = [f'PYTESTRUNNER_START\t{node}\n', phase_line,
             f'{node} PASSED\n', 'Windows fatal exception: access violation\n',
             '  File "C:\\project\\test_card.py", line 12 in test_card\n']
    class Process:
        def __init__(self):
            self.returncode = code
            self.stdout = self
        def readline(self):
            return lines.pop(0) if lines else ''
        def wait(self):
            return code
        def poll(self):
            return code
    monkeypatch.setattr(execution.subprocess, 'Popen', lambda *a, **kw: Process())
    outcomes, details = [], []
    request = RunRequest(str(tmp_path), sys.executable, (node, 'test_card.py::test_after'), (Reader('A', 0),))
    report = execution.ReaderRun(request, Reader('A', 0), {}).run(lambda _: None, outcomes.append, on_detail=details.append)
    assert report.counts == {Status.ERROR: 1, Status.NOT_RUN: 1}
    assert [(item.nodeid, item.status) for item in outcomes] == [(node, Status.ERROR), ('test_card.py::test_after', Status.NOT_RUN)]
    assert report.not_run.keys() == {'test_card.py::test_after'}
    assert details[0]['phase'] == phase
    assert '0xC0000005' in details[0]['body']
    assert 'line 12 in test_card' in details[0]['body']
    assert diagnostics.PREFIX in report.output and 'PYTESTRUNNER_PHASE' not in report.output
    assert not report.ok


@pytest.mark.parametrize('capture', [True, False])
def test_real_subprocess_preserves_completed_tests_and_marks_the_rest_not_run(tmp_path, capture):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_native.py').write_text(
        'import os\n'
        'def test_before(): pass\n'
        'def test_crash():\n'
        '    print("Windows fatal exception: access violation", flush=True)\n'
        '    print("Native driver stack frame", flush=True)\n'
        '    os._exit(23)\n'
        'def test_after():\n'
        '    raise AssertionError("must never run")\n')
    nodes = tuple('test_native.py::test_' + name for name in ('before', 'crash', 'after'))
    request = RunRequest(str(tmp_path), sys.executable, nodes, (Reader('', 0),), run_id='crash', junit_dir=str(tmp_path / 'junit'))
    details, outcomes = [], []
    report = execution.ReaderRun(request, Reader('', 0), {} if capture else {'PYTEST_ADDOPTS': '-s'}).run(
        lambda _: None, outcomes.append, on_detail=details.append)
    assert report.counts == {Status.PASSED: 1, Status.ERROR: 1, Status.NOT_RUN: 1}
    assert report.not_run.keys() == {nodes[2]}
    assert details[-1]['nodeid'] == nodes[1] and details[-1]['phase'] == 'call'
    if not capture:
        assert 'Native driver stack frame' in details[-1]['body']
    assert not report.junit_path
    assert report.issues and not report.ok


@pytest.mark.skipif(os.name == 'nt', reason='Le code Windows est couvert par les retours signes et non signes ci-dessus.')
def test_real_native_segfault_without_junit_still_has_an_error_verdict(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_crash.py').write_text(
        'import ctypes, resource\n'
        'def test_driver():\n'
        '    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n'
        '    ctypes.string_at(0)\n')
    node = 'test_crash.py::test_driver'
    request = RunRequest(str(tmp_path), sys.executable, (node,), (Reader('', 0),))
    details = []
    report = execution.ReaderRun(request, Reader('', 0), {}).run(lambda _: None, lambda _: None, on_detail=details.append)
    assert report.counts == {Status.ERROR: 1}
    assert 'SIGSEGV' in details[0]['body']
    assert 'test_crash.py' in details[0]['body']
    assert not report.not_run


def test_successful_process_with_fatal_words_in_its_output_is_not_a_crash():
    assert native_crash('Windows fatal exception: access violation', 0) is None
    assert native_crash('ordinary pytest failure', 1) is None


def test_native_crash_during_import_does_not_blame_the_first_selected_test(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'conftest.py').write_text('import os\nos._exit(23)\n')
    node = 'test_card.py::test_driver'
    request = RunRequest(str(tmp_path), sys.executable, (node,), (Reader('', 0),))
    outcomes, details = [], []
    report = execution.ReaderRun(request, Reader('', 0), {}).run(
        lambda _: None, outcomes.append, on_detail=details.append)
    assert len(outcomes) == 1 and outcomes[0].status is Status.NOT_RUN
    assert not details and report.counts == {Status.NOT_RUN: 1}
    assert node in report.not_run
    assert 'exit code 23' in report.not_run[node]
    assert report.issues and not report.ok


def test_user_stop_does_not_turn_termination_into_a_native_error(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_card.py').write_text('def test_driver(): pass\n')
    node = 'test_card.py::test_driver'
    request = RunRequest(str(tmp_path), sys.executable, (node,), (Reader('', 0),))
    run = execution.ReaderRun(request, Reader('', 0), {})
    outcomes = []
    def stop_when_preparing(line):
        if line.startswith('PYTESTRUNNER_PREPARE\t'):
            run.cancel()
    report = run.run(stop_when_preparing, outcomes.append)
    assert report.cancelled and not report.issues
    assert outcomes[0].status is Status.NOT_RUN
    assert 'stopped by the user' in report.not_run[node]


@pytest.mark.skipif(os.name == 'nt', reason='Le worker natif est reproduit ici sur POSIX sans ouvrir de boite Windows.')
def test_xdist_worker_crash_has_an_error_verdict_and_keeps_missing_tests(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_worker.py').write_text(
        'import ctypes, resource\n'
        'def test_before(): pass\n'
        'def test_native():\n'
        '    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n'
        '    ctypes.string_at(0)\n'
        'def test_after(): pass\n')
    nodes = tuple('test_worker.py::test_' + name for name in ('before', 'native', 'after'))
    request = RunRequest(str(tmp_path), sys.executable, nodes, (Reader('', 0),))
    report = execution.ReaderRun(request, Reader('', 0), {'PYTEST_ADDOPTS': '-n 1 --max-worker-restart=0'}).run(
        lambda _: None, lambda _: None)
    assert report.counts.get(Status.ERROR) == 1, report.output
    assert nodes[1] not in report.not_run
    assert 'Fatal Python error' in report.output
    assert report.exit_code != 0
