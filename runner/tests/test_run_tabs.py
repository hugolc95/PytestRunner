import sys
from copy import deepcopy
from dataclasses import replace

import pytest
from PySide6.QtCore import QSettings, Qt

from runner.domain import history
from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.models import Outcome, Status
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    w = MainWindow()
    qtbot.addWidget(w)
    (tmp_path / "test_demo.py").write_text(
        "def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")
    w.workspace = Workspace.load(str(tmp_path))
    w._on_collected(Collection(("test_demo.py::test_a", "test_demo.py::test_b")))
    w._interpreter_override = sys.executable
    w.show()
    yield w
    w.close()


def fake_start(context, calls, monkeypatch):
    def start(request, env):
        calls.append((context, request, deepcopy(env)))
        context.service.started.emit(request)
        return True
    monkeypatch.setattr(context.service, "start", start)


def test_drafts_keep_independent_selection_and_live_results(window, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    assert draft.workspace is not window.workspace
    assert draft.model.checked_nodeids() == []
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.service.outcome.emit(Outcome("test_demo.py::test_a", Status.PASSED))
    window.service.line.emit(0, "live output from first run")
    window.service.progress.emit(1, 2)
    assert window.model.statuses_for_nodeid("test_demo.py::test_a")[0] == Status.PASSED
    assert draft.model.statuses_for_nodeid("test_demo.py::test_a")[0] == Status.PENDING
    assert draft.model.checked_nodeids() == ["test_demo.py::test_b"]
    assert "Running 1/2" in window.run_tabs.tabs.tabText(0)
    window.run_tabs.show_context(window)
    assert window.run_tabs.stack.currentWidget() is window.run_tabs.entries[0].page
    assert window.model.checked_nodeids() == ["test_demo.py::test_a", "test_demo.py::test_b"]


def test_queue_waits_then_starts_exact_snapshot(window, qtbot, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    fake_start(draft, calls, monkeypatch)
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    monkeypatch.setenv("QUEUE_TEST", "before")
    draft.run_selected()
    assert len(calls) == 1
    assert window.run_tabs.current.state == "waiting"
    monkeypatch.setenv("QUEUE_TEST", "after")
    draft.model.set_all_checked(True)
    window.service.finished.emit([])
    qtbot.waitUntil(lambda: len(calls) == 2)
    assert calls[1][1].nodeids == ("test_demo.py::test_b",)
    assert calls[1][2]["QUEUE_TEST"] == "before"
    assert window.run_tabs.active.context is draft
    assert window.run_tabs.entries[0].state == "finished"


def test_waiting_configuration_is_frozen(window, tmp_path, qtbot, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    fake_start(draft, calls, monkeypatch)
    config = tmp_path / "queued.yaml"
    config.write_text("reader: first\n", encoding="utf-8")
    draft.workspace = replace(draft.workspace, config_path=str(config))
    draft.model.set_all_checked(True)
    draft.run_selected()
    snapshot = window.run_tabs.current.job.config_snapshot
    config.write_text("reader: second\n", encoding="utf-8")
    window.service.finished.emit([])
    qtbot.waitUntil(lambda: len(calls) == 2)
    assert snapshot.read_text(encoding="utf-8") == "reader: first\n"
    assert calls[1][1].config_path == str(snapshot)
    draft.service.finished.emit([])
    assert not snapshot.exists()


def test_queue_can_pause_reorder_and_remove_without_starting(window, monkeypatch, qtbot):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    second = window.run_tabs.new_run()
    third = window.run_tabs.new_run()
    for context in (second, third):
        fake_start(context, calls, monkeypatch)
        context.model.set_all_checked(True)
        context.run_selected()
    second_entry = window.run_tabs.entry_for(second)
    third_entry = window.run_tabs.entry_for(third)
    window.run_tabs.move_waiting(third_entry, -1)
    assert window.run_tabs.queue == [third_entry, second_entry]
    window.run_tabs.toggle_pause()
    window.service.finished.emit([])
    qtbot.wait(30)
    assert len(calls) == 1
    window.run_tabs.edit_waiting(third_entry)
    assert third_entry.state == "draft"
    window.run_tabs.toggle_pause()
    assert calls[-1][0] is second


def test_profile_sequence_and_options_are_captured(window, qtbot, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    profile = ExecutionProfile("Ordered profile", ["test_demo.py::test_b", "test_demo.py::test_a", "test_demo.py::test_b"], "", "")
    profile.execution.repetitions = 2
    draft._load_execution_profile(profile)
    launched = []
    def start(request, env, sequence, **options):
        launched.append((request, sequence, options))
        draft.service.started.emit(request)
        return True
    monkeypatch.setattr(draft.service, "start_profile", start)
    draft.run_selected()
    profile.sequence.clear()
    profile.execution.repetitions = 99
    window.service.finished.emit([])
    qtbot.waitUntil(lambda: bool(launched))
    assert launched[0][1] == ["test_demo.py::test_b", "test_demo.py::test_a", "test_demo.py::test_b"]
    assert launched[0][2]["repetitions"] == 2


def test_detached_run_keeps_same_tree_after_close_and_reopen(window):
    draft = window.run_tabs.new_run()
    entry = window.run_tabs.current
    original_tree = draft.tree
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.run_tabs.detach_current()
    floating = entry.floating
    assert floating.isVisible()
    assert window.run_tabs.current.context is window
    floating.close()
    assert entry.floating is floating
    assert not floating.isVisible()
    window.run_tabs.show_context(draft)
    assert floating.isVisible()
    window.run_tabs.reattach(entry)
    assert entry.floating is None
    assert draft.tree is original_tree
    assert draft.model.checked_nodeids() == ["test_demo.py::test_b"]


def test_active_and_waiting_tabs_lock_selection_but_keep_results_readable(window, monkeypatch):
    fake_start(window, [], monkeypatch)
    window.run_selected()
    index = window.model.index_for_nodeid("test_demo.py::test_a")
    assert not window.model.flags(index) & Qt.ItemIsUserCheckable
    assert not window.model.setData(index, Qt.Unchecked)
    assert window.tree.isEnabled()
    assert not window.workspace_combo.isEnabled()
    assert not window.run_name_button.isEnabled()
    window.service.finished.emit([])
    assert window.workspace_combo.isEnabled()
    assert window.load_button.isEnabled()
    assert window.model.flags(index) & Qt.ItemIsUserCheckable


def test_f5_routes_to_selected_draft(window, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    draft.model.set_all_checked(True)
    window.act_run.trigger()
    assert len(window.run_tabs.queue) == 1
    assert window.run_tabs.queue[0].context is draft


def test_closing_application_does_not_launch_waiting_work(window, monkeypatch, qtbot):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    fake_start(draft, calls, monkeypatch)
    draft.model.set_all_checked(True)
    draft.run_selected()
    window.close()
    window.service.finished.emit([])
    qtbot.wait(30)
    assert len(calls) == 1


def test_real_runs_execute_serially_and_archive_separately(window, qtbot):
    draft = window.run_tabs.new_run()
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.model.set_checked_nodeids(["test_demo.py::test_a"])
    window.run_selected()
    draft.run_selected()
    qtbot.waitUntil(lambda: all(entry.state == "finished" for entry in window.run_tabs.entries), timeout=20000)
    assert window.model.statuses_for_nodeid("test_demo.py::test_a")[0] == Status.PASSED
    assert draft.model.statuses_for_nodeid("test_demo.py::test_b")[0] == Status.PASSED
    entries = window.history.entries()
    assert len(entries) == 2
    assert len({entry.build_number for entry in entries}) == 2


def test_restart_restores_draft_and_detached_mode_without_starting(window, qtbot):
    draft = window.run_tabs.new_run()
    draft._pending_run_name = "Preserved draft"
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.run_tabs.detach_current()
    window.run_tabs.entry_for(draft).floating.resize(1000, 650)
    window.close()
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.show()
    try:
        qtbot.waitUntil(lambda: len(reopened.run_tabs.entries) == 2)
        restored = reopened.run_tabs.entries[1]
        assert restored.name == "Preserved draft"
        assert restored.context.model.checked_nodeids() == ["test_demo.py::test_b"]
        assert restored.floating is not None
        assert restored.floating.isVisible()
        assert restored.floating.size().width() == 1000
        assert restored.floating.size().height() == 650
        assert restored.state == "draft"
        assert not reopened.run_tabs.busy
        assert not reopened.run_tabs.queue
    finally:
        reopened.close()


def test_saved_session_does_not_replace_explicitly_loaded_workspace(window):
    window.run_tabs.save_sessions()
    window.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.run_tabs.restore_sessions()
    assert window.model.checked_nodeids() == ["test_demo.py::test_b"]
    assert len(window.run_tabs.entries) == 1
