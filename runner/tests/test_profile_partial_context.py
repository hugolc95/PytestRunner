"""Une selection partielle execute un sous-ensemble, jamais un arbre tronque."""
import json
import sys

import pytest
from PySide6.QtCore import QPersistentModelIndex

from runner.domain.diagnostics import PREFIX
from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile, ExecutionOptions, ProfileStore
from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.profile_logs import ProfileLogIndex
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow
from runner.ui.profile_run_tree import ProfileSelectionRun


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'config.yaml').write_text('Reader: Reader A\nReaders:\n  - Reader A\n  - Reader B\ntimeout: 15\n')
    (tmp_path / 'test_repeat.py').write_text('''import json, os, yaml
from pathlib import Path
class TestRepeat:
    def test_value(self):
        value = yaml.safe_load(Path(os.environ['PYTESTRUNNER_READER_CONFIG']).read_text())
        with Path('received-' + value['Reader'] + '.jsonl').open('a') as stream:
            stream.write(json.dumps(value['timeout']) + '\\n')
''')
    w = MainWindow()
    qtbot.addWidget(w)
    w.profiles_page.store = ProfileStore(tmp_path / 'profiles')
    w.workspace = Workspace.load(str(tmp_path), str(tmp_path / 'config.yaml'))
    node = 'test_repeat.py::TestRepeat::test_value'
    w._on_collected(Collection((node,)))
    w._interpreter_override = sys.executable
    yield w, tmp_path, node
    w.service.cancel()
    w.service.wait()
    if getattr(w, '_archive_worker', None) is not None:
        qtbot.waitUntil(lambda: w._archive_worker is None, timeout=15000)
    w.close()


def loaded(w, node, repetitions=1):
    p = ExecutionProfile('Protocol checks', [node] * 3, 'config.yaml',
                         'Reader: Reader A\nReaders:\n  - Reader A\n  - Reader B\ntimeout: 15\n',
                         execution=ExecutionOptions(repetitions=repetitions),
                         step_overrides=[{'timeout': 10}, {'timeout': 20}, {'timeout': 30}])
    w._open_collected_profile(p)
    return p


def wait_finished(w, qtbot):
    qtbot.waitUntil(lambda: not w.service.busy, timeout=30000)
    qtbot.waitUntil(lambda: w.run_tabs.active is None, timeout=15000)


def test_partial_run_retains_all_occurrences_results_logs_and_checkboxes(window, qtbot):
    w, root, node = window
    original = loaded(w, node, repetitions=2)
    readers = w._readers_to_run()
    assert len(readers) == 2
    old_reports = {}
    logs = ProfileLogIndex(root, 1)
    for position in range(6):
        key = w.profile_model.key(position)
        for reader in readers:
            w._on_profile_execution(position, 0, reader.index, node, Status.FAILED)
            detail = dict(kind='test', nodeid=node, phase='call', message='OLD failure', body='OLD failure')
            report = ReaderReport(reader, output=PREFIX + json.dumps(detail), durations={node: 12.0})
            old_reports[key, reader.index] = report
            w._profile_reports[key, reader.index] = report
            w.profile_model.set_duration(key, reader.index, 12.0)
            log = root / f'old-{position}-{reader.index}.log'
            log.write_text(f'OLD log {position} {reader.index}')
            logs.paths[key, reader.index] = log
    w._profile_logs = logs
    w.profile_model.apply_execution(0, 1, readers[0].index, node, Status.ERROR)
    w.profile_model.apply_execution(2, 1, readers[0].index, node, Status.ERROR)
    w.profile_tree.expandAll()
    w.profile_tree.setCurrentIndex(w.profile_model.index_for_nodeid('2:0'))
    watched = QPersistentModelIndex(w.profile_model.index_for_nodeid('2:0'))
    w.profile_model.set_checked_nodeids(['0:0', '4:0'])
    w.run_selected()
    assert w.run_tabs.current.context is w
    assert watched.isValid()
    wait_finished(w, qtbot)
    for reader in readers:
        received = [json.loads(line) for line in (root / f'received-{reader.name}.jsonl').read_text().splitlines()]
        assert received == [10, 20]
        for key in ('0:0', '4:0'):
            assert w.profile_model.statuses_for_nodeid(key)[reader.index] is Status.PASSED
        for key in ('1:0', '2:0', '3:0', '5:0'):
            assert w.profile_model.statuses_for_nodeid(key)[reader.index] is Status.FAILED
            assert w._profile_reports[key, reader.index] is old_reports[key, reader.index]
            assert w.profile_model._durations[key][reader.index] == 12.0
            assert w._profile_logs.paths[key, reader.index] == logs.paths[key, reader.index]
    assert watched.isValid() and w._profile_selected_key == '2:0'
    assert w._active_execution_profile is original
    assert w.profile_model.counts() == (2, 6)
    assert w.profile_model.checked_nodeids() == ['0:0', '4:0']
    assert '0:1' not in w.profile_model.locations
    assert '2:1' in w.profile_model.locations
    w._refresh_profile_selection()
    assert 'OLD failure' in w.profile_results.detail.body.toPlainText()
    assert w.profile_results.detail._result_origins
    assert 'OLD log 2' in w.profile_results.logs.views[0].text()
    assert w._archive_replay_profile['sequence'] == [node, node]
    assert w._archive_replay_profile['execution']['repetitions'] == 1
    assert [patch['timeout'] for patch in w._archive_replay_profile['step_overrides']] == [10, 20]


def test_full_then_partial_run_keeps_the_unchecked_report_in_the_same_tab(window, qtbot):
    w, root, node = window
    loaded(w, node)
    w.run_selected()
    wait_finished(w, qtbot)
    old = dict(w._profile_reports)
    tab_count = len(w.run_tabs.entries)
    w.profile_model.set_checked_nodeids(['2:0'])
    w.run_selected()
    wait_finished(w, qtbot)
    assert len(w.run_tabs.entries) == tab_count
    assert list(w.profile_model.locations) == ['0:0', '1:0', '2:0']
    assert w.profile_model.checked_nodeids() == ['2:0']
    for reader in w.profile_model.readers:
        assert w._profile_reports['0:0', reader.index] is old['0:0', reader.index]
        received = [json.loads(line) for line in (root / f'received-{reader.name}.jsonl').read_text().splitlines()]
        assert received == [10, 20, 30, 30]


def test_non_contiguous_batch_routes_output_and_reports_to_original_rows(window):
    w, root, node = window
    original = loaded(w, node)
    w.profile_run_tree.selection = ProfileSelectionRun(original, (0, 2))
    old = ReaderReport(Reader('Reader A', 0), output='OLD')
    w._profile_reports['1:0', 0] = old
    w.profile_tree.setCurrentIndex(w.profile_model.index_for_nodeid('2:0'))
    w._on_profile_execution(1, 0, 0, node, Status.RUNNING)
    w._on_profile_output(0, 2, 0, 0, 'NEW OUTPUT')
    w._refresh_profile_selection()
    assert w._profile_selected_key == '2:0'
    assert w.profile_results.output.views[0].text() == 'NEW OUTPUT'
    report = ReaderReport(Reader('Reader A', 0), output='NEW OUTPUT')
    w._on_profile_batch_report(0, 2, 0, report)
    assert w._profile_reports['0:0', 0] is report
    assert w._profile_reports['2:0', 0] is report
    assert w._profile_reports['1:0', 0] is old


def test_queued_partial_run_keeps_the_full_profile_and_the_frozen_positions(window, qtbot):
    w, root, node = window
    original = loaded(w, node)
    w.profile_model.set_checked_nodeids(['0:0', '2:0'])
    w.run_tabs.paused = True
    w.run_selected()
    entry = w.run_tabs.entry_for(w)
    assert entry.state == 'waiting'
    assert entry.job.profile_selection.positions == (0, 2)
    assert entry.job.profile_selection.profile.sequence == [node] * 3
    assert entry.job.profile_selection.profile is not original
    assert entry.job.profile.sequence == [node] * 2
    w.run_tabs.toggle_pause()
    wait_finished(w, qtbot)
    assert w.profile_model.counts() == (2, 3)
    assert w.profile_model.checked_nodeids() == ['0:0', '2:0']
    assert w.profile_model.statuses_for_nodeid('2:0')[0] is Status.PASSED


def test_restarting_one_reader_keeps_the_other_readers_retry_and_duration(window):
    w, root, node = window
    original = loaded(w, node)
    for reader in (0, 1):
        w._on_profile_execution(0, 0, reader, node, Status.FAILED)
        w._on_profile_execution(0, 1, reader, node, Status.ERROR)
        w.profile_model.set_duration('0:1', reader, 7)
    w.profile_run_tree.selection = ProfileSelectionRun(original, (0,))
    w.profile_run_tree.begin_run(True)
    w._on_profile_execution(0, 0, 0, node, Status.PASSED)
    assert w.profile_model.statuses_for_nodeid('0:0')[0] is Status.PASSED
    assert w.profile_model.statuses_for_nodeid('0:1') == {0: Status.PENDING, 1: Status.ERROR}
    assert w.profile_model._durations['0:1'] == {1: 7}
    assert ('0:1', 1) in w.profile_model.previous_results
    assert ('0:1', 0) not in w.profile_model.previous_results
