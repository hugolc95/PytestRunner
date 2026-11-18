"""Une collecte incomplete ne peut devenir verte, ni executer un autre projet."""

import sys

import pytest

from runner.domain import interpreter
from runner.domain.history import History, RunEntry
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Status
from runner.domain.report import html_report
from runner.domain.report_data import report_payload
from runner.ui import end_run_feedback
from runner.ui.main_window import MainWindow
from runner.ui.widgets import ErrorDialog


ERRORS = {'test_bad.py': dict(location='test_bad.py:1', message='SyntaxError', body='SyntaxError: bad syntax')}


def test_collection_errors_survive_history_and_portable_report(tmp_path):
    entry = RunEntry('partial', 1, str(tmp_path), counts={'PASSED': 1},
        nodeids=('test_ok.py::test_ok',), test_statuses={'test_ok.py::test_ok': 'PASSED'},
        collection_errors=ERRORS, analysis_data=dict(schema=1, occurrences=[dict(position=0,
            nodeid='test_ok.py::test_ok', attempts=[dict(status='PASSED', attempt=0)])]))
    assert not entry.ok
    assert '1 file not collected' in entry.summary
    stored = History(tmp_path).add(entry)
    restored = History(tmp_path).find(stored.id)
    assert restored.collection_errors == ERRORS
    payload = report_payload([restored])
    assert not payload['complete']
    assert payload['counts']['passed'] == 1
    assert payload['collection_errors'] == ERRORS
    page = html_report(restored)
    assert 'Incomplete · 1 file not collected' in page
    assert 'SyntaxError: bad syntax' in page
    legacy = restored.to_json()
    legacy.pop('collection_errors')
    assert RunEntry.from_json(legacy).ok


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    for name in ('_on_run_started', '_on_outcome', '_on_progress', '_on_run_finished'):
        monkeypatch.setattr(MainWindow, name, getattr(MainWindow, name))
    end_run_feedback.install()
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    monkeypatch.setattr(MainWindow, '_require_interpreter', lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, '_refresh_primary_reader', lambda *args: None)
    monkeypatch.setattr(MainWindow, '_notifier_fin_de_run', lambda *args: None)
    monkeypatch.setattr(interpreter, 'cached_probe', lambda path: InterpreterInfo(
        path=path, version='3', bits=64, pytest_version='test'))
    monkeypatch.setattr(ErrorDialog, 'show_error', lambda *args, **kwargs: None)
    monkeypatch.setattr(ErrorDialog, 'show_diagnostics', lambda *args, **kwargs: None)
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()


def project(folder, broken=False):
    folder.mkdir()
    (folder / 'pytest.ini').write_text('[pytest]\n')
    (folder / 'test_ok.py').write_text('def test_ok(): pass\n')
    if broken:
        (folder / 'test_bad.py').write_text('def test_bad(:\n    pass\n')
        (folder / 'test_import.py').write_text('import absent_collection_regression_xyz\n')
    return folder


def collect(window, qtbot, folder):
    window.workspace_combo.setCurrentText(str(folder))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None and not window._collector.isRunning()
                    and not window._collecting, timeout=20000)
    qtbot.waitUntil(lambda: window._tree_workspace == str(folder))


def run(window, qtbot):
    previous = {entry.id for entry in window.history.entries()}
    window.run_selected()
    qtbot.waitUntil(lambda: bool({entry.id for entry in window.history.entries()} - previous)
                    and not getattr(window, '_archive_workers', ()), timeout=20000)


@pytest.mark.parametrize('profile', [False, True])
def test_partial_collection_remains_incomplete_after_execution(window, qtbot, tmp_path, profile, monkeypatch):
    folder = project(tmp_path / 'partial', broken=True)
    collect(window, qtbot, folder)
    if profile:
        from runner.domain.execution_profile import ExecutionProfile
        window._open_collected_profile(ExecutionProfile('Partial collection', ['test_ok.py::test_ok'], '', ''))
        window.profile_model.set_all_checked(True)
    else:
        window.model.set_all_checked(True)
    run(window, qtbot)
    assert 'Collection incomplete' in window.status_label.text()
    assert 'All tests passed' not in window.status_label.text()
    state, _, _ = window.run_tabs.presentation(window.run_tabs.entry_for(window))
    assert state == 'Incomplete · 2 files not collected'
    assert window._run_status_counts() == {Status.PASSED: 1}
    assert not window.collection_errors_button.isHidden()
    assert 'Collection incomplete' in window.compass_ring.toolTip()
    saved = window.history.entries()[0]
    assert not saved.ok and len(saved.collection_errors) == 2
    assert 'SyntaxError' in html_report(saved)
    shown = []
    monkeypatch.setattr(ErrorDialog, 'show_diagnostics', lambda *args, **kwargs: shown.append(args[2]))
    window.collection_errors_button.click()
    assert 'SyntaxError' in shown[0] and 'absent_collection_regression_xyz' in shown[0]
    (folder / 'test_bad.py').unlink()
    (folder / 'test_import.py').unlink()
    collect(window, qtbot, folder)
    if profile:
        window.profile_model.set_all_checked(True)
    else:
        window.model.set_all_checked(True)
    run(window, qtbot)
    assert 'All tests passed' in window.status_label.text()
    assert window.collection_errors_button.isHidden()
    assert len(saved.collection_errors) == 2


def test_invalid_path_restores_the_workspace_that_will_run(window, qtbot, tmp_path):
    folder = project(tmp_path / 'good')
    collect(window, qtbot, folder)
    before = window.model.nodeids()
    window.workspace_combo.setCurrentText(str(tmp_path / 'not-a-directory'))
    window._pending_history_run = object()
    window._pending_execution_profile = object()
    assert not window.run_button.isEnabled()
    window.load_workspace()
    assert window.workspace_combo.currentText() == str(folder)
    assert window.workspace.path == str(folder)
    assert window._pending_history_run is None and window._pending_execution_profile is None
    assert window.model.nodeids() == before
    window.model.set_all_checked(True)
    run(window, qtbot)
    assert window.history.entries()[0].workspace == str(folder)


def test_edited_path_cannot_launch_old_tests_from_shortcuts_or_context_menu(window, qtbot, tmp_path, monkeypatch):
    folder = project(tmp_path / 'good')
    other = project(tmp_path / 'other')
    collect(window, qtbot, folder)
    window.model.set_all_checked(True)
    window.workspace_combo.setCurrentText(str(other))
    started = []
    monkeypatch.setattr(window.service, 'start', lambda *args: started.append(args))
    window.run_selected()
    window._start(['test_ok.py::test_ok'], preserve_results=True)
    assert not started
    assert not window.act_run.isEnabled()
    assert 'Collect' in window.run_button.toolTip()


def test_collection_in_progress_cannot_launch_the_previous_tree(window, qtbot, tmp_path, monkeypatch):
    collect(window, qtbot, project(tmp_path / 'first'))
    other = project(tmp_path / 'second')
    release = other / 'release-collection'
    (other / 'conftest.py').write_text(
        'from pathlib import Path\nimport time\nwhile not Path("release-collection").exists():\n    time.sleep(.01)\n')
    window.workspace_combo.setCurrentText(str(other))
    window.load_workspace()
    started = []
    monkeypatch.setattr(window.service, 'start', lambda *args: started.append(args))
    try:
        assert window._collector.isRunning()
        window._start(['test_ok.py::test_ok'])
        assert not started and not window.run_button.isEnabled()
        draft = window.run_tabs.new_run(window)
        assert not draft.model.nodeids()
        assert not draft._workspace_ready()
    finally:
        release.touch()
        qtbot.waitUntil(lambda: not window._collector.isRunning(), timeout=20000)
    assert window._tree_workspace == str(other)


def test_new_run_keeps_collection_errors_and_session_snapshot(window, qtbot, tmp_path):
    import json
    collect(window, qtbot, project(tmp_path / 'partial', broken=True))
    draft = window.run_tabs.new_run(window)
    assert len(draft._collection_errors) == 2
    assert draft.model.broken_file_count() == 2
    draft.model.set_all_checked(True)
    run(draft, qtbot)
    assert len(window.history.entries()[0].collection_errors) == 2
    window.run_tabs.save_sessions()
    saved = json.loads(window.settings.value('runs/session', '[]', type=str))
    assert all(len(item['collection_errors']) == 2 for item in saved)


def test_repeated_run_also_records_incomplete_collection(window, qtbot, tmp_path):
    from runner.domain.stress import MODE_N_TIMES
    collect(window, qtbot, project(tmp_path / 'partial', broken=True))
    window._lancer_stress('test_ok.py::test_ok', MODE_N_TIMES, 2)
    qtbot.waitUntil(lambda: bool(window.history.entries()), timeout=20000)
    assert 'Collection incomplete' in window.status_label.text()
    saved = window.history.entries()[0]
    assert len(saved.collection_errors) == 2 and not saved.ok


def test_reopening_a_draft_keeps_collection_warnings(window, qtbot, tmp_path):
    folder = project(tmp_path / 'partial', broken=True)
    collect(window, qtbot, folder)
    window.close()
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    try:
        qtbot.waitUntil(lambda: reopened.workspace is not None and len(reopened._collection_errors) == 2)
        assert reopened.model.broken_file_count() == 2
        assert not reopened.collection_errors_button.isHidden()
    finally:
        reopened.close()
