"""Exercise real pytest boundaries, fixtures, profiles and cancellation."""
import sys
import textwrap

import pytest

from runner.domain.models import Reader, RunRequest
from runner.services.run_service import RunService


@pytest.fixture
def pause_suite(tmp_path):
    (tmp_path / 'test_pause.py').write_text(textwrap.dedent('''
        import os
        import time
        from pathlib import Path
        import pytest

        root = Path(__file__).parent
        def note(text):
            with (root / ('events-' + os.environ.get('PYTESTRUNNER_READER', 'default') + '-' + str(os.getpid()))).open('a') as stream:
                stream.write(text + '\\n')

        @pytest.fixture(scope='session', autouse=True)
        def session():
            note('session-start')
            yield
            note('session-end')

        @pytest.fixture(autouse=True)
        def teardown():
            yield
            note('teardown')

        def test_first():
            note('first-start')
            deadline = time.monotonic() + 20
            while not (root / 'release').exists():
                assert time.monotonic() < deadline
                time.sleep(.02)
            note('first-end')

        def test_second():
            note('second')

        def test_third():
            note('third')
    '''), encoding='utf-8')
    return tmp_path


def events(root, reader='default'):
    return [line for path in sorted(root.glob('events-' + reader + '-*'))
            for line in path.read_text().splitlines()]


def request(root, readers=(), sequential=False):
    return RunRequest(str(root), sys.executable, tuple(
        'test_pause.py::test_' + name for name in ('first', 'second', 'third')),
        readers, sequential=sequential)


def test_confirmed_pause_cannot_regress_on_transient_acknowledgement_read(qtbot):
    from types import SimpleNamespace
    control = SimpleNamespace(paused=True, resume=lambda: None)
    worker = SimpleNamespace(isRunning=lambda: True, _run=SimpleNamespace(pause_control=control))
    service = RunService()
    service._workers = [worker]
    service._pause_requested = True
    changes = []
    service.pause_changed.connect(changes.append)
    service._set_pause_state('pending')
    service._pause_timer.start()
    service._poll_pause()
    assert service.pause_state == 'paused'
    assert not service._pause_timer.isActive()
    control.paused = False  # Empty/partial acknowledgement or temporary IO error.
    for _ in range(20):
        service._poll_pause()
    assert changes == ['pending', 'paused']
    service.resume()
    assert changes == ['pending', 'paused', 'running']
    service._workers = []


@pytest.mark.parametrize('sequential', [False, True])
def test_pause_finishes_current_test_and_teardown_then_resumes_same_sessions(qtbot, pause_suite, sequential):
    service = RunService()
    reports = []
    pause_states = []
    service.pause_changed.connect(pause_states.append)
    service.finished.connect(reports.append)
    readers = (Reader('A', 0), Reader('B', 1))
    try:
        assert service.start(request(pause_suite, readers, sequential), {})
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite, 'A'), timeout=15000)
        if not sequential:
            qtbot.waitUntil(lambda: 'first-start' in events(pause_suite, 'B'), timeout=15000)
        service.request_pause()
        assert service.pause_state == 'pending'
        assert 'first-end' not in events(pause_suite, 'A')
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: service.pause_state == 'paused', timeout=15000)
        assert service.busy and not reports
        assert events(pause_suite, 'A') == ['session-start', 'first-start', 'first-end', 'teardown']
        if sequential:
            assert not events(pause_suite, 'B')
        qtbot.wait(1500)
        assert pause_states == ['pending', 'paused']
        assert 'second' not in events(pause_suite, 'A')
        service.resume()
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        for name in ('A', 'B'):
            assert events(pause_suite, name) == [
                'session-start', 'first-start', 'first-end', 'teardown',
                'second', 'teardown', 'third', 'teardown', 'session-end']
        assert all(report.ok for report in reports[0])
        assert not service.busy
    finally:
        service.cancel()
        service.wait()


def test_pause_button_updates_existing_status_and_keeps_queue_waiting(qtbot, pause_suite, monkeypatch):
    from PySide6.QtCore import QSettings, QAbstractAnimation
    from runner.domain.execution import Collection
    from runner.domain.workspace import Workspace
    from runner.ui.main_window import MainWindow
    settings = QSettings(str(pause_suite / 'ui.ini'), QSettings.IniFormat)
    monkeypatch.setattr('runner.ui.main_window.QSettings', lambda *_: settings)
    monkeypatch.setattr('runner.domain.history.dossier', lambda: pause_suite / 'history')
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    monkeypatch.setattr(MainWindow, '_refresh_primary_reader', lambda *_, **__: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(pause_suite))
    window._interpreter_override = sys.executable
    window._on_collected(Collection(request(pause_suite).nodeids))
    window.show()
    try:
        assert window.pause_button.isHidden()
        window._start(list(request(pause_suite).nodeids))
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        assert window.pause_button.isVisible()
        window.pause_button.click()
        assert 'waiting for the current test to finish' in window.status_label.text()
        assert window.pause_button.text() == 'Cancel pause'
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: window.service.pause_state == 'paused', timeout=15000)
        assert window.pause_button.text() == 'Resume'
        assert window.status_label.text() == 'Paused · 3 tests'
        assert window.status_label.objectName() == 'StatusLive'
        assert window.live_dot._paused
        assert window.live_dot._anim.state() == QAbstractAnimation.State.Stopped
        assert window.live_dot.isVisible()
        assert not window._elapsed.isActive()
        if hasattr(window.model, '_running_groups_cache'):
            assert not window.model._running_groups_cache
        assert not window.workspace_combo.isEnabled()
        assert window.run_tabs.active.context is window
        assert window.run_tabs.active.state == 'running'
        window.pause_button.click()
        assert window._elapsed.isActive()
        assert not window.live_dot._paused
        qtbot.waitUntil(lambda: not window.service.busy, timeout=15000)
        qtbot.waitUntil(window.pause_button.isHidden, timeout=5000)
        assert events(pause_suite).count('first-start') == 1
    finally:
        window.service.cancel()
        window.service.wait()
        window.close()


def test_stop_while_paused_does_not_run_remaining_tests(qtbot, pause_suite):
    service = RunService()
    reports = []
    service.finished.connect(reports.append)
    try:
        service.start(request(pause_suite), {})
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        service.request_pause()
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: service.pause_state == 'paused', timeout=15000)
        service.cancel()
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        assert reports[0][0].cancelled
        assert 'second' not in events(pause_suite)
        assert not service.busy
    finally:
        service.cancel()
        service.wait()


@pytest.mark.parametrize('reruns', [0, 1])
def test_profile_pause_preserves_batch_repetitions_and_next_position(qtbot, pause_suite, reruns):
    service = RunService()
    reports, positions = [], []
    service.finished.connect(reports.append)
    service.profile_execution.connect(lambda pos, attempt, reader, nodeid, status: positions.append((pos, status)))
    req = request(pause_suite)
    try:
        service.start_profile(req, {}, list(req.nodeids), repetitions=2, rerun_failures=reruns)
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        service.request_pause()
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: service.pause_state == 'paused', timeout=15000)
        assert 'second' not in events(pause_suite)
        assert service.busy and not reports
        service.resume()
        qtbot.waitUntil(lambda: bool(reports), timeout=30000)
        assert events(pause_suite).count('first-start') == 2
        assert events(pause_suite).count('second') == 2
        assert events(pause_suite).count('third') == 2
        assert {pos for pos, status in positions if status.is_final} == set(range(6))
    finally:
        service.cancel()
        service.wait()


def test_cancel_pause_request_does_not_interrupt_current_test(qtbot, pause_suite):
    service = RunService()
    reports = []
    service.finished.connect(reports.append)
    try:
        service.start(request(pause_suite), {})
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        service.request_pause()
        service.resume()
        assert service.pause_state == 'running'
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        assert reports[0][0].ok
        assert 'third' in events(pause_suite)
    finally:
        service.cancel()
        service.wait()


def test_last_test_finishes_run_even_when_pause_was_requested(qtbot, pause_suite):
    from dataclasses import replace
    service = RunService()
    reports = []
    service.finished.connect(reports.append)
    req = request(pause_suite)
    try:
        service.start(replace(req, nodeids=req.nodeids[:1]), {})
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        service.request_pause()
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        assert reports[0][0].ok
        assert not service.busy
        assert service.pause_state == 'running'
    finally:
        service.cancel()
        service.wait()


def test_profile_pause_before_retry_retains_failed_attempt_and_retries_once(qtbot, pause_suite):
    path = pause_suite / 'test_pause.py'
    path.write_text(path.read_text().replace("note('first-end')", """note('first-end')
    marker = root / 'attempted'
    if not marker.exists():
        marker.touch()
        assert False, 'first attempt only'"""), encoding='utf-8')
    service = RunService()
    reports, positions = [], []
    service.finished.connect(reports.append)
    service.profile_execution.connect(lambda pos, attempt, reader, nodeid, status: positions.append((pos, attempt, status)))
    req = request(pause_suite)
    try:
        service.start_profile(req, {}, list(req.nodeids), rerun_failures=1)
        qtbot.waitUntil(lambda: 'first-start' in events(pause_suite), timeout=15000)
        service.request_pause()
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: service.pause_state == 'paused', timeout=15000)
        assert events(pause_suite).count('first-start') == 1
        service.resume()
        qtbot.waitUntil(lambda: bool(reports), timeout=20000)
        assert reports[0][0].ok
        assert events(pause_suite).count('first-start') == 2
        assert events(pause_suite).count('second') == 1
        assert any(pos == 0 and attempt == 0 and status.is_bad for pos, attempt, status in positions)
        assert any(pos == 0 and attempt == 1 and status.is_final and not status.is_bad
                   for pos, attempt, status in positions)
    finally:
        service.cancel()
        service.wait()


@pytest.mark.parametrize('distribution', ['loadfile', 'each'])
def test_xdist_waits_for_all_current_tests_before_acknowledging_pause(qtbot, pause_suite, distribution):
    pytest.importorskip('xdist')
    path = pause_suite / 'test_pause.py'
    path.write_text(path.read_text().replace('def test_first():',
        '@pytest.mark.parametrize("case", [1, 2])\ndef test_first(case):'), encoding='utf-8')
    req = request(pause_suite)
    service = RunService()
    reports = []
    service.finished.connect(reports.append)
    try:
        service.start(req, {'PYTEST_ADDOPTS': '-n 2 --dist=' + distribution})
        active_workers = 2 if distribution == 'each' else 1
        qtbot.waitUntil(lambda: events(pause_suite).count('first-start') == active_workers, timeout=20000)
        service.request_pause()
        (pause_suite / 'release').touch()
        qtbot.waitUntil(lambda: service.pause_state == 'paused', timeout=20000)
        assert 'second' not in events(pause_suite)
        service.resume()
        qtbot.waitUntil(lambda: bool(reports), timeout=20000)
        assert reports[0][0].ok
        assert events(pause_suite).count('first-start') == 2 * active_workers
        assert events(pause_suite).count('second') == active_workers
    finally:
        service.cancel()
        service.wait()
