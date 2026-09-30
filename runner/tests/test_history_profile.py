from dataclasses import replace

from runner.domain.execution_profile import (
    ExecutionOptions, ExecutionProfile, ReportOptions, export_profile, inspect_profile,
)
from runner.domain.history import History, RunEntry
from runner.domain.history_profile import capture_profile, profile_from_entry
from runner.domain.models import RunRequest


A = "tests/test_a.py::test_one"
B = "tests/test_b.py::test_two[value]"


def test_archived_profile_preserves_original_yaml_sequence_and_options(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("voltage: 5\n", encoding="utf-8")
    original = ExecutionProfile(
        name="Validation", sequence=[B, A, B], configuration_name="config.yaml",
        configuration_text="voltage: 5\n",
        execution=ExecutionOptions(3, 2, True), reports=ReportOptions(False))
    request = RunRequest(str(tmp_path), "python", tuple(original.sequence), (),
                         config_path=str(config))
    snapshot = capture_profile(request, original)
    config.write_text("voltage: 99\n", encoding="utf-8")
    original.sequence.clear()
    original.execution.repetitions = 99
    history = History(tmp_path / "history")
    history.add(RunEntry(id="run", timestamp=1, workspace=str(tmp_path),
                         nodeids=(A, B), replay_profile=snapshot))
    entry = History(tmp_path / "history").find("run")
    target = export_profile(profile_from_entry(entry), tmp_path / "shared")
    imported = inspect_profile(target, [A, B]).profile
    assert imported.sequence == [B, A, B]
    assert imported.configuration_text == "voltage: 5\n"
    assert imported.execution == ExecutionOptions(3, 2, True)
    assert imported.reports == ReportOptions(False)


def test_classic_snapshot_keeps_only_requested_tests_and_no_config(tmp_path):
    request = RunRequest(str(tmp_path), "python", (B, A), ())
    snapshot = capture_profile(request)
    entry = RunEntry(id="run", timestamp=1, workspace="", replay_profile=snapshot)
    profile = profile_from_entry(entry)
    assert profile.sequence == [B, A]
    assert profile.configuration_name == profile.configuration_text == ""
    assert profile.execution.repetitions == 1


def test_old_history_snapshot_ignores_retired_report_option(tmp_path):
    request = RunRequest(str(tmp_path), "python", (B, A), ())
    snapshot = capture_profile(request)
    snapshot["reports"]["generate_allure"] = True
    entry = RunEntry(id="old", timestamp=1, workspace="", replay_profile=snapshot)
    profile = profile_from_entry(entry)
    assert profile.sequence == [B, A]
    assert profile.reports == ReportOptions()


def test_legacy_export_preserves_occurrences_and_accepts_chosen_yaml(tmp_path):
    entry = RunEntry.from_json(dict(id="old", nodeids=[A, B],
                                   executions=[[B, "FAILED"], [B, "PASSED"], [A, "SKIPPED"]]))
    assert entry.replay_profile is None
    config = tmp_path / "chosen.yaml"
    config.write_text("mode: smoke\n", encoding="utf-8")
    profile = profile_from_entry(entry, configuration_path=config)
    assert profile.sequence == [B, B, A]
    assert profile.configuration_text == "mode: smoke\n"
    assert profile_from_entry(replace(entry, executions=())).sequence == [A, B]


def test_history_export_action_writes_an_importable_profile(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    from runner.ui.history_dashboard import HistoryWindow
    history = History(tmp_path / "history")
    request = RunRequest(str(tmp_path), "python", (B, A, B), ())
    history.add(RunEntry(id="run", timestamp=1, workspace=str(tmp_path),
                         nodeids=request.nodeids, replay_profile=capture_profile(request)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    from PySide6.QtCore import Qt
    item = next(window.run_list.item(row) for row in range(window.run_list.count())
                if window.run_list.item(row).data(Qt.UserRole) is not None)
    window.run_list.setCurrentItem(item)
    target = tmp_path / "shared.pytest-profile"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(target), ""))
    messages = []
    monkeypatch.setattr(window, "_say", lambda *a: messages.append(a))
    action = window.export_menu.actions()[0]
    assert "execution profile" in action.text()
    assert action.isEnabled(), (window._current_group(), history.entries())
    action.trigger()
    assert target.exists(), messages
    assert inspect_profile(target, [A, B]).profile.sequence == [B, A, B]
