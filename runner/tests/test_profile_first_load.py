from types import SimpleNamespace

from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow


def test_open_profile_collects_first_then_opens_without_running(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    profile = ExecutionProfile('Imported', ['test_a.py::test_one'], '', '')
    calls = []

    def collect():
        calls.append('collect')
        window.workspace = Workspace.load(str(tmp_path))
        window._collector = SimpleNamespace(isRunning=lambda: True)

    monkeypatch.setattr(window, 'load_workspace', collect)
    window._load_execution_profile(profile)
    assert calls == ['collect']
    assert window._active_execution_profile is None
    window._on_collected(Collection(nodeids=tuple(profile.sequence)))
    qtbot.waitUntil(lambda: window._active_execution_profile is profile)
    assert window.pages.currentWidget() is window.workspace_page
    assert window.profile_tree_button.isChecked()
    assert window.run_button.isEnabled()
    assert not window.service.busy
    assert window._pending_execution_profile is None
    window._collector = None


def test_cancelling_workspace_choice_does_not_leave_a_pending_profile(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, 'load_workspace', lambda: None)
    window._load_execution_profile(ExecutionProfile('Imported', ['test_a.py::test_one'], '', ''))
    assert window._pending_execution_profile is None
    assert window._active_execution_profile is None
