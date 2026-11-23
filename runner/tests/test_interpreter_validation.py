"""Le Python enregistre est celui qui vient d'etre verifie, jamais un ancien champ."""

import sys
from threading import Event

import pytest
from PySide6.QtCore import QObject, Signal, QTimer

from runner.domain.interpreter import InterpreterInfo, InterpreterUnavailable
from runner.ui.interpreter_dialog import InterpreterDialog


def valid(path, **changes):
    values = dict(path=path, version='3.12.8', bits=64, pytest_version='9.0')
    values.update(changes)
    return InterpreterInfo(**values)


@pytest.fixture
def controlled(monkeypatch):
    workers = []
    class Worker(QObject):
        done = Signal(object)
        finished = Signal()
        def __init__(self, path, parent=None, timeout=15):
            super().__init__(parent)
            self.path = path
            self.running = False
            workers.append(self)
        def start(self):
            self.running = True
        def isRunning(self):
            return self.running
        def wait(self, timeout=3000):
            return not self.running
        def complete(self, info):
            self.done.emit(info)
            self.running = False
            self.finished.emit()
    monkeypatch.setattr('runner.ui.interpreter_dialog.ProbeWorker', Worker)
    return workers


@pytest.fixture
def dialog(qtbot, controlled):
    d = InterpreterDialog('python-A', embedded=True)
    qtbot.addWidget(d)
    yield d
    for worker in controlled:
        if worker.running:
            worker.complete(InterpreterInfo(path=worker.path, error='Test cleanup'))


@pytest.mark.parametrize('info', [
    InterpreterInfo(path='python-A', error='Interpreter not found'),
    InterpreterInfo(path='python-A', version='3.12', bits=64),
    InterpreterInfo(path='python-A', version='not Python', bits=0, pytest_version='garbage'),
])
def test_invalid_python_cannot_be_saved(dialog, controlled, info):
    saved = []
    dialog.saved.connect(saved.append)
    dialog.test_now()
    controlled[-1].complete(info)
    dialog._save()
    assert not saved and not dialog.save_button.isEnabled()
    assert dialog._status_is_error
    assert 'Python interpreter not usable' in dialog.status_label.text()


def test_old_probe_cannot_validate_a_new_path(dialog, controlled):
    dialog.test_now()
    first = controlled[-1]
    dialog.path_field.setText('python-B')
    dialog.test_now()
    first.complete(valid('python-A'))
    assert controlled[-1].path == 'python-B'
    assert not dialog.save_button.isEnabled()
    assert 'Checking python-B' in dialog.status_label.text()
    controlled[-1].complete(InterpreterInfo(path='python-B', error='Interpreter not found'))
    assert not dialog.save_button.isEnabled()


def test_editing_a_verified_path_disables_save_immediately(dialog, controlled):
    dialog.test_now()
    controlled[-1].complete(valid('python-A'))
    assert dialog.save_button.isEnabled()
    dialog.path_field.setText('python-B')
    assert not dialog.save_button.isEnabled()
    dialog._auto_check.stop()


def test_save_rechecks_and_does_not_persist_a_removed_environment(dialog, controlled):
    saved = []
    dialog.saved.connect(saved.append)
    dialog.test_now()
    controlled[-1].complete(valid('python-A'))
    dialog.save_button.click()
    assert not saved and not dialog.save_button.isEnabled()
    controlled[-1].complete(InterpreterInfo(path='python-A', error='Interpreter not found'))
    assert not saved and dialog._status_is_error


def test_default_python_and_optional_xdist_are_saved_correctly(dialog, controlled, monkeypatch):
    monkeypatch.setattr('runner.ui.interpreter_dialog.default', lambda: 'default-python')
    saved = []
    dialog.saved.connect(saved.append)
    dialog.path_field.clear()
    dialog.test_now()
    controlled[-1].complete(valid('default-python'))
    assert dialog.save_button.isEnabled()
    dialog.save_button.click()
    controlled[-1].complete(valid('default-python'))
    assert saved == ['']
    assert 'Configuration saved' in dialog.status_label.text()
    assert 'pytest-xdist missing' in dialog.status_label.text()


def test_editing_during_save_cancels_that_save(dialog, controlled):
    saved = []
    dialog.saved.connect(saved.append)
    dialog.test_now()
    controlled[-1].complete(valid('python-A'))
    dialog.save_button.click()
    saving = controlled[-1]
    dialog.path_field.setText('python-B')
    dialog.test_now()
    saving.complete(valid('python-A'))
    assert not saved
    controlled[-1].complete(valid('python-B'))
    assert not saved and dialog.save_button.isEnabled()


def test_cancel_during_probe_keeps_qt_responsive(qtbot, monkeypatch):
    from runner.domain import interpreter
    started, released = Event(), Event()
    def slow(path, **kwargs):
        started.set()
        assert released.wait(15)
        return valid(path)
    monkeypatch.setattr(interpreter, 'probe', slow)
    d = InterpreterDialog(sys.executable)
    qtbot.addWidget(d)
    d.show()
    try:
        qtbot.waitUntil(started.is_set)
        d.reject()
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qtbot.waitUntil(lambda: bool(heartbeat))
        assert d.isVisible()
        released.set()
        qtbot.waitUntil(lambda: d._probe is None and not d.isVisible())
    finally:
        released.set()
        d.wait_for_probe(15000)


def test_collector_rejects_unusable_python_before_pytest(qtbot, tmp_path, monkeypatch):
    from runner.domain import interpreter
    from runner.services.run_service import CollectWorker
    monkeypatch.setattr(interpreter, 'probe', lambda *a, **k: InterpreterInfo(path='bad', error='not found'))
    monkeypatch.setattr('runner.services.run_service.execution.collect',
                        lambda *a, **k: pytest.fail('pytest must not start with an invalid interpreter'))
    worker = CollectWorker(str(tmp_path), 'bad', {})
    failures = []
    worker.diagnostic_failed.connect(failures.append)
    worker.start()
    qtbot.waitUntil(lambda: bool(failures))
    worker.wait(3000)
    assert isinstance(failures[0], InterpreterUnavailable)
    assert 'Python interpreter not usable' in str(failures[0])


def test_frozen_app_cannot_be_probed_as_its_own_python(monkeypatch):
    from runner.domain import interpreter
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(interpreter.subprocess, 'run', lambda *a, **k: pytest.fail('App must not relaunch itself'))
    info = interpreter.probe(sys.executable, use_cache=False)
    assert not info.usable and 'Pytest Runner' in info.error


@pytest.mark.parametrize('bits', [32, 64])
def test_both_python_architectures_are_supported(bits):
    assert valid('python', bits=bits).usable


def test_saving_python_during_collection_discards_the_old_result(qtbot, tmp_path, monkeypatch):
    from runner.ui.main_window import MainWindow
    from runner.domain.execution import Collection
    from runner.domain.workspace import Workspace
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    w = MainWindow()
    qtbot.addWidget(w)
    w.workspace = Workspace.load(str(tmp_path))
    w.workspace_combo.setCurrentText(str(tmp_path))
    w._collecting = True
    class Finished(QObject):
        finished = Signal()
    worker = Finished(w)
    w._collector = worker
    worker.finished.connect(w._finish_collection)
    loads = []
    monkeypatch.setattr(w, 'load_workspace', lambda: loads.append(w._effective_interpreter()))
    monkeypatch.setattr(w, '_refresh_interpreter_alert', lambda: None)
    w._save_python_from_page('python-B')
    assert not loads and w._recollect_after_interpreter_change
    w._on_collected(Collection(('old_python.py::test_a',)))
    assert not w.model.nodeids()
    worker.finished.emit()
    assert loads == ['python-B'] and not w._collecting
    w._collector = None
    w.close()


def test_opening_the_page_shows_a_known_result_without_starting_python(qtbot, controlled, monkeypatch):
    """Chaque visite de Python Environment relancait une verification complete
    (environ 0,6 s « Checking… »). Un Python deja verifie s'affiche aussitot ;
    « Test » relance toujours une vraie verification."""
    from runner.domain import interpreter
    monkeypatch.setattr(interpreter, 'cached_probe',
                        lambda path: valid(path) if path == 'python-A' else None)
    d = InterpreterDialog('python-A', embedded=True)
    qtbot.addWidget(d)
    controlled.clear()

    d.show_known_or_check()
    assert controlled == []
    assert d.save_button.isEnabled()
    assert 'Ready' in d.status_label.text()

    d.test_now()
    assert len(controlled) == 1
    controlled[0].complete(valid('python-A'))

    # Un Python jamais verifie part en verification comme avant.
    d.path_field.setText('python-B')
    d.show_known_or_check()
    assert controlled[-1].path == 'python-B'
    assert not d.save_button.isEnabled()
    for worker in controlled:
        if worker.running:
            worker.complete(valid(worker.path))
