"""Les details doivent etre lisibles pendant qu'un autre test attend encore."""
import json
import sys
import textwrap

import pytest

from runner.domain import diagnostics, execution, failures
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.models import Reader, ReaderReport, RunRequest, Status
from runner.tests.test_collection_diagnostics import window
from runner.ui.results_panel import ResultsPanel


SOURCE = '''
import time
from pathlib import Path
import pytest

@pytest.fixture
def cleanup_error():
    yield
    raise RuntimeError("live cleanup error")

@pytest.fixture
def setup_error():
    raise RuntimeError("live setup error")

def test_01_failure(cleanup_error):
    assert False, "live assertion failure"

def test_02_setup(setup_error):
    pass

@pytest.mark.skip(reason="live skipped reason")
def test_03_skip():
    pass

def test_04_pass():
    pass

def test_99_wait():
    Path("waiting").touch()
    deadline = time.monotonic() + 25
    while not Path("release").exists():
        if time.monotonic() > deadline:
            pytest.fail("test driver did not release the gate")
        time.sleep(.01)
'''


@pytest.mark.parametrize('profile', [False, True], ids=['classic', 'profile'])
def test_details_are_visible_before_run_finishes(window, qtbot, tmp_path, profile):
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_live.py').write_text(textwrap.dedent(SOURCE))
    window.workspace_combo.setCurrentText(str(tmp_path))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None and not window._collector.isRunning(), timeout=15000)
    nodes = sorted(window.model._by_nodeid)
    assert len(nodes) == 5
    if profile:
        window._open_collected_profile(ExecutionProfile('Live details', nodes, '', ''))
    else:
        window.model.set_all_checked(True)
    window.run_selected()
    try:
        qtbot.waitUntil(lambda: (tmp_path / 'waiting').exists(), timeout=15000)
        qtbot.waitUntil(lambda: window.model.statuses_for_nodeid(nodes[3]).get(0) is Status.PASSED)
        assert window.service.busy
        panel = window.profile_results if profile else window.results
        def choose(index):
            if profile:
                window._profile_selected_key = f'{index}:0'
                window._refresh_profile_selection()
            else:
                panel.show_test(nodes[index], window.model.statuses_for_nodeid(nodes[index]), str(tmp_path))
        choose(0)
        qtbot.waitUntil(lambda: 'live cleanup error' in panel.detail.body.toPlainText())
        body = panel.detail.body.toPlainText()
        assert 'live assertion failure' in body
        assert 'Phase: CALL' in body and 'Phase: TEARDOWN' in body
        assert panel._durations[0][nodes[0]] >= 0
        choose(1)
        assert 'live setup error' in panel.detail.body.toPlainText()
        choose(2)
        assert 'live skipped reason' in panel.detail.body.toPlainText()
        choose(3)
        assert panel._statuses[0] is Status.PASSED
        assert panel._durations[0][nodes[3]] >= 0
        assert panel.failure_for(nodes[3], 0) is None
        choose(0)
        assert 'live assertion failure' in panel.detail.body.toPlainText()
        assert window.service.busy
        assert not window.run_tabs.active is None
    finally:
        (tmp_path / 'release').touch()
        qtbot.waitUntil(lambda: not window.service.busy, timeout=15000)
        qtbot.waitUntil(lambda: window.run_tabs.active is None, timeout=15000)
    choose(0)
    assert 'live assertion failure' in panel.detail.body.toPlainText()
    assert 'live cleanup error' in panel.detail.body.toPlainText()


def detail(node='a.py::test_a', message='new failure', phase='call'):
    return dict(kind='test', nodeid=node, phase=phase, message=message, body=message)


def test_live_result_replaces_previous_failure_and_success_clears_it(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    node = 'a.py::test_a'
    panel.set_readers((Reader('A', 0), Reader('B', 2)))
    old = diagnostics.PREFIX + json.dumps(detail(message='old failure'))
    panel.set_report(ReaderReport(reader=Reader('A', 0), output=old))
    panel.begin_run(preserve_results=True, nodeids=[node])
    panel.set_test_detail(0, detail())
    assert panel.failure_for(node, 0).body == 'new failure'
    assert panel.failure_for(node, 2) is None
    panel.update_statuses(node, {0: Status.PASSED}, reader_index=0)
    assert panel.failure_for(node, 0) is None


def test_profile_live_details_are_scoped_to_occurrence_attempt_and_reader(window):
    node = 'test_live.py::test_repeat'
    window._running_execution_profile = ExecutionProfile('Repeated', [node, node], '', '')
    window._on_run_started(RunRequest('', sys.executable, (node, node), (Reader('A', 0), Reader('B', 2))))
    window._on_profile_execution(0, 0, 0, node, Status.FAILED)
    window._on_profile_execution(1, 0, 0, node, Status.PASSED)
    window._on_profile_execution(0, 1, 2, node, Status.ERROR)
    window._on_profile_test_detail(0, 0, 0, detail(node, 'first occurrence'))
    window._on_profile_test_detail(0, 1, 2, detail(node, 'retry on B', 'setup'))
    window._on_profile_test_duration(0, 0, 0, node, .125)
    window._profile_selected_key = '0:0'
    window._refresh_profile_selection()
    assert window.profile_results.failure_for(node, 0).body == 'first occurrence'
    assert window.profile_results.failure_for(node, 2) is None
    assert window.profile_results._durations[0][node] == .125
    window._profile_selected_key = '1:0'
    window._refresh_profile_selection()
    assert window.profile_results.failure_for(node, 0) is None
    window._profile_selected_key = '0:1'
    window._refresh_profile_selection()
    assert window.profile_results.failure_for(node, 2).body == 'retry on B'
    assert window.profile_results.failure_for(node, 0) is None


@pytest.mark.parametrize('line', ['PYTESTRUNNER_DIAGNOSTIC\t[]', 'PYTESTRUNNER_DIAGNOSTIC\tnot json',
    'PYTESTRUNNER_DIAGNOSTIC\t{"kind":"test","nodeid":2}', 'PYTESTRUNNER_SKIP\t[]'])
def test_malformed_live_detail_is_ignored(line):
    assert diagnostics.parse_live_detail(line) is None


@pytest.mark.parametrize('options', ['', '-n 2', '--tb=no'])
def test_domain_streams_diagnostics_before_process_exit_without_duplicating_archive(tmp_path, options):
    (tmp_path / 'pytest.ini').write_text('[pytest]\naddopts = ' + options + '\n')
    (tmp_path / 'test_live.py').write_text(textwrap.dedent(SOURCE))
    nodes = ('test_live.py::test_01_failure', 'test_live.py::test_99_wait')
    run = execution.ReaderRun(RunRequest(str(tmp_path), sys.executable, nodes, ()), Reader('', 0), {})
    received, lines = [], []
    def collect_detail(item):
        received.append((item, run._process.poll()))
        (tmp_path / 'release').touch()
    report = run.run(lines.append, lambda outcome: None, on_detail=collect_detail)
    assert received[0][1] is None
    assert any('live assertion failure' in item['body'] for item, _ in received)
    assert any('live cleanup error' in item['body'] for item, _ in received)
    assert len([line for line in report.output.splitlines() if line.startswith(diagnostics.PREFIX)]) == 2
    assert not any(diagnostics.PREFIX in line for line in lines)
    result = failures.failure_for(failures.index_failures(report.output), nodes[0])
    assert result.phase == 'call / teardown'
    assert result.body.count('Phase: CALL') == 1
