from types import SimpleNamespace

from runner.domain.execution_profile import ExecutionProfile
from runner.domain.history import History
from runner.domain.models import Outcome, Reader, ReaderReport, RunRequest, Status
from runner.ui import end_run_feedback
from runner.ui.main_window import MainWindow


def test_background_archive_keeps_profile_name_then_classic_origin(qtbot, tmp_path, monkeypatch):
    # Install the same replacement handlers as python -m runner, restoring
    # them after this test so other tests still get the original class.
    for name in ("_on_run_started", "_on_outcome", "_on_progress", "_on_run_finished"):
        monkeypatch.setattr(MainWindow, name, getattr(MainWindow, name))
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    monkeypatch.setattr(MainWindow, "_notifier_fin_de_run", lambda *args: None)
    end_run_feedback.install()
    window = MainWindow()
    qtbot.addWidget(window)
    window.history = History(tmp_path / "history")
    window.workspace = SimpleNamespace(path=str(tmp_path), log_root=tmp_path)
    monkeypatch.setattr(window, "_update_actions", lambda: None)
    profile = ExecutionProfile(name="Smoke", sequence=["test_a"],
                               configuration_name="", configuration_text="")
    reader = Reader("Reader A", 0)
    request = RunRequest(workspace=str(tmp_path), interpreter="python",
                         nodeids=("test_a", "test_a"), readers=(reader,))
    for run_id, active in (("profile-run", profile), ("classic-run", None)):
        window._pending_run_name = "Firmware validation"
        window._running_execution_profile = active
        window._run_id = run_id
        window._on_run_started(request)
        window._on_outcome(Outcome(nodeid='test_a', status=Status.PASSED, reader_index=0))
        window._on_outcome(Outcome(nodeid='test_a', status=Status.PASSED, reader_index=0))
        window._on_run_finished([ReaderReport(reader=reader, counts={Status.PASSED: 2})])
        qtbot.waitUntil(lambda: window._archive_worker is None)
        assert window._running_execution_profile is None
    saved = History(tmp_path / "history")
    assert saved.find("profile-run").profile_name == "Smoke"
    assert saved.find("profile-run").run_kind == "profile"
    assert saved.find("classic-run").run_kind == "classic"
    assert saved.find("classic-run").profile_name == ""
    assert saved.find("classic-run").run_name == "Firmware validation"
    assert saved.find("profile-run").run_name == "Firmware validation"
    assert saved.find('profile-run').executions == (('test_a', 'PASSED'), ('test_a', 'PASSED'))
    saved.rename_run("classic-run", "Renamed run")
    assert History(tmp_path / "history").find("classic-run").run_name == "Renamed run"


def test_configless_profile_uses_current_local_configuration():
    profile = ExecutionProfile(name="Smoke", sequence=["test_a"],
                               configuration_name="", configuration_text="")
    window = SimpleNamespace(workspace=SimpleNamespace(config_path="chosen.yaml"))
    assert MainWindow._profile_configuration_path(window, profile) == "chosen.yaml"
    window.workspace.config_path = "other.yaml"
    assert MainWindow._profile_configuration_path(window, profile) == "other.yaml"
    window.workspace.config_path = ""
    assert MainWindow._profile_configuration_path(window, profile) == ""
