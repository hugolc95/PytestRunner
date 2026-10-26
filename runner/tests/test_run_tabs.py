import sys
from pathlib import Path
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


def test_yaml_switch_keeps_each_run_copy_and_updates_active_configuration(window, tmp_path, monkeypatch):
    from runner.ui.config_dialog import ONGLET_YAML
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text("timeout: 10\n", encoding="utf-8")
    second.write_text("timeout: 20\n", encoding="utf-8")
    controller = window.run_tabs
    first_copy = controller.configuration_path(window, str(tmp_path), str(first))
    window.workspace = Workspace.load(str(tmp_path), first_copy)
    window._refresh_yaml_page(force=True)
    monkeypatch.setattr(window, "load_workspace", lambda: None)
    editor = window.yaml_editor
    editor.tabs.setCurrentIndex(ONGLET_YAML)
    editor.raw.setPlainText("# First edited\ntimeout: 11\n")
    editor.file_combo.setCurrentIndex(editor.file_combo.findData(str(second)))
    second_copy = str(editor.path)
    assert second_copy != first_copy
    assert window.workspace.config_path == second_copy
    editor.raw.setPlainText("timeout: 22\n")
    editor.file_combo.setCurrentIndex(editor.file_combo.findData(str(first)))
    assert str(editor.path) == first_copy
    assert editor.raw.toPlainText() == "# First edited\ntimeout: 11\n"
    assert window.workspace.settings["timeout"] == 11
    assert Path(second_copy).read_text(encoding="utf-8") == "timeout: 22\n"
    assert first.read_text(encoding="utf-8") == "timeout: 10\n"
    assert second.read_text(encoding="utf-8") == "timeout: 20\n"
    from runner.domain.reader_isolation import ENV_CONFIG_SOURCE
    assert controller.configuration_env(window, {})[ENV_CONFIG_SOURCE] == str(first)


def test_restart_retains_inactive_yaml_copies(window, tmp_path, qtbot):
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text("timeout: 10\n", encoding="utf-8")
    second.write_text("timeout: 20\n", encoding="utf-8")
    controller = window.run_tabs
    first_copy = controller.configuration_path(window, str(tmp_path), str(first))
    Path(first_copy).write_text("timeout: 11\n", encoding="utf-8")
    second_copy = controller.configuration_path(window, str(tmp_path), str(second))
    window.workspace = Workspace.load(str(tmp_path), second_copy)
    window.close()
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    try:
        qtbot.waitUntil(lambda: reopened.workspace is not None)
        restored = reopened.run_tabs.configuration_path(reopened, str(tmp_path), str(first))
        assert restored == first_copy
        assert Path(restored).read_text(encoding="utf-8") == "timeout: 11\n"
        assert reopened.run_tabs.configuration_path(reopened, str(tmp_path), str(second)) == second_copy
    finally:
        reopened.close()


def test_each_run_edits_its_own_configuration_and_keeps_source(window, tmp_path, monkeypatch):
    source = tmp_path / "settings.yaml"
    source.write_text("# retained comment\nmode: original\n", encoding="utf-8")
    window.workspace = Workspace.load(str(tmp_path), str(source))
    window._on_collected(Collection(tuple(window.model._by_nodeid)))
    first = Path(window.workspace.config_path)
    draft = window.run_tabs.new_run()
    second = Path(draft.workspace.config_path)
    assert first != second and first != source and second != source
    assert second.read_bytes() == source.read_bytes()
    from runner.domain.reader_isolation import ENV_CONFIG_SOURCE
    assert window.run_tabs.configuration_env(draft, {})[ENV_CONFIG_SOURCE] == str(source)
    second.write_text("mode: second\n", encoding="utf-8")
    monkeypatch.setattr(draft, "load_workspace", lambda: None)
    draft._on_yaml_page_saved(str(second))
    assert draft.workspace.settings["mode"] == "second"
    assert window.workspace.settings["mode"] == "original"
    assert source.read_text(encoding="utf-8").endswith("mode: original\n")
    assert first.read_bytes() == source.read_bytes()
    assert draft._config_retenue(str(tmp_path)) == str(second)
    assert window._config_retenue(str(tmp_path)) == str(first)
    assert window.settings.value("workspace/config_files", {}) == {}


def test_draft_configuration_remains_editable_during_another_run(window, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    assert draft.act_config.isEnabled()
    assert draft.yaml_page.isEnabled()
    assert not window.config_button.isEnabled()
    assert not window.yaml_stack.isEnabled()
    assert window.configuration_tabs.isEnabled()


def test_configuration_editor_imports_into_run_copy(window, tmp_path, monkeypatch):
    monkeypatch.setattr(window, "load_workspace", lambda: None)
    window._refresh_yaml_page(force=True)
    editor = window.yaml_editor
    source = tmp_path / "another.yaml"
    source.write_text("mode: imported\n", encoding="utf-8")
    editor.file_combo.setCurrentIndex(editor._ajouter_candidat(source))
    assert editor.path != source
    editor.raw.setPlainText("mode: edited\n")
    editor._enregistrer_texte()
    assert source.read_text(encoding="utf-8") == "mode: imported\n"
    assert editor.path.read_text(encoding="utf-8") == "mode: edited\n"


def test_embedded_profile_initializes_run_copy_and_keeps_subsequent_edits(window):
    profile = ExecutionProfile(name="Private profile", sequence=["test_demo.py::test_a"],
                               configuration_name="profile.yaml", configuration_text="mode: profile\n")
    window._open_collected_profile(profile)
    path = Path(window.workspace.config_path)
    assert path.read_text(encoding="utf-8") == "mode: profile\n"
    path.write_text("mode: edited\n", encoding="utf-8")
    window._open_collected_profile(profile)
    assert window._profile_configuration_path(profile) == str(path)
    assert path.read_text(encoding="utf-8") == "mode: edited\n"
    window.run_tabs.duplicate(window.run_tabs.entries[0])
    copy = window.run_tabs.current.context
    assert copy.workspace.config_path != str(path)
    assert Path(copy.workspace.config_path).read_text(encoding="utf-8") == "mode: edited\n"


def test_serial_runs_use_their_own_yaml_even_when_tests_open_source(window, qtbot, tmp_path):
    source = tmp_path / "config.yaml"
    source.write_text("original", encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from pathlib import Path\n"
        "def test_a(): assert Path('config.yaml').read_text() == 'first'\n"
        "def test_b(): assert Path('config.yaml').read_text() == 'second'\n", encoding="utf-8")
    window.workspace = Workspace.load(str(tmp_path), str(source))
    window._on_collected(Collection(("test_demo.py::test_a", "test_demo.py::test_b")))
    Path(window.workspace.config_path).write_text("first", encoding="utf-8")
    draft = window.run_tabs.new_run()
    Path(draft.workspace.config_path).write_text("second", encoding="utf-8")
    window.model.set_checked_nodeids(["test_demo.py::test_a"])
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.run_selected()
    draft.run_selected()
    qtbot.waitUntil(lambda: all(entry.state == "finished" for entry in window.run_tabs.entries), timeout=20000)
    assert window.model.statuses_for_nodeid("test_demo.py::test_a")[0] == Status.PASSED
    assert draft.model.statuses_for_nodeid("test_demo.py::test_b")[0] == Status.PASSED
    assert source.read_text(encoding="utf-8") == "original"


def test_context_menu_renames_target_run_and_updates_detached_title(window, monkeypatch):
    from PySide6.QtWidgets import QMenu, QInputDialog
    controller = window.run_tabs
    draft = controller.new_run()
    entry = controller.entry_for(draft)
    controller.detach(entry)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("  Card qualification  ", True))
    def trigger_rename(menu, position):
        action = next(action for action in menu.actions() if action.text() == "Rename run…")
        action.trigger()
    class TestMenu(QMenu):
        def exec(self, position):
            trigger_rename(self, position)
    monkeypatch.setattr("runner.ui.run_tabs.QMenu", TestMenu)
    controller.context_menu(controller.tabs.tabRect(controller.entries.index(entry)).center())
    assert entry.name == "Card qualification"
    assert draft.run_name_button.text() == entry.name
    assert controller.tabs.tabData(1)["name"] == entry.name
    assert entry.floating.windowTitle().startswith(entry.name)
    assert controller.entries[0].name != entry.name
    assert controller.save_timer.isActive()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Ignored", False))
    controller.rename(entry)
    assert entry.name == "Card qualification"
    controller.reattach(entry)


def test_custom_close_button_keeps_target_after_tab_move(window, qtbot):
    from PySide6.QtWidgets import QTabBar
    from runner.ui.run_tabs_strip import RunTabClose
    controller = window.run_tabs
    draft = controller.new_run()
    entry = controller.entry_for(draft)
    controller.tabs.moveTab(1, 0)
    button = controller.tabs.tabButton(0, QTabBar.RightSide)
    assert isinstance(button, RunTabClose)
    qtbot.mouseClick(button, Qt.LeftButton)
    assert entry not in controller.entries
    assert len(controller.entries) == 1


def test_new_run_button_follows_last_tab_and_handles_overflow(window, qtbot):
    controller = window.run_tabs
    window.resize(1600, 900)
    controller.new_run()
    qtbot.wait(20)
    assert controller.new_button.geometry().left() == (
        controller.tabs.geometry().right() + controller.tabs.parentWidget().layout().spacing() + 1
    )
    assert controller.tabs.tabRect(controller.tabs.count() - 1).right() < controller.tabs.width()
    old_left = controller.new_button.x()
    controller.close_tab(1)
    qtbot.wait(20)
    assert controller.new_button.x() < old_left
    for _ in range(6):
        controller.new_run()
    window.resize(1100, 900)
    qtbot.wait(20)
    assert controller.new_button.isVisible()
    assert controller.new_button.parentWidget().rect().contains(controller.new_button.geometry())
    assert not controller.tabs.geometry().intersects(controller.new_button.geometry())


def test_new_run_never_shows_temporary_top_level_widgets(window, qtbot):
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtWidgets import QApplication, QWidget

    shown = []
    class Probe(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(type(obj).__name__)
            return False

    probe = Probe(window)
    app = QApplication.instance()
    app.installEventFilter(probe)
    try:
        window.run_tabs.new_run()
        qtbot.wait(20)
        assert shown == []
    finally:
        app.removeEventFilter(probe)


def test_new_runs_receive_preferences_and_context_specific_console(window, qtbot):
    preferences = window.preferences
    preferences.values.update(compact_header=True, atr_bottom=True,
                              tree_density="Comfortable", selection_tab="Output", follow_test=True)
    preferences.apply()
    draft = window.run_tabs.new_run()
    assert draft.run_header.atr_presentation.parentWidget() is draft.statusBar()
    assert draft.run_header.execution.layout().spacing() == window.run_header.execution.layout().spacing() == 4
    assert "35px" in draft.tree.styleSheet()
    assert draft.profile_tree.styleSheet() == draft.tree.styleSheet()
    index = draft.model.index_for_nodeid("test_demo.py::test_b")
    draft.tree.setCurrentIndex(index)
    assert draft.results.tabs.currentIndex() == 2
    draft.service.line.emit(0, "PYTESTRUNNER_START\ttest_demo.py::test_a")
    assert draft.tree.currentIndex() == draft.model.index_for_nodeid("test_demo.py::test_a")
    assert not window.tree.currentIndex().isValid()
    output = [message for _, kind, message in preferences.console.events if kind == "output"]
    assert sum("PYTESTRUNNER_START" in message for message in output) == 1
    assert "[New run]" in output[-1]
    preferences.values.update(atr_bottom=False, tree_density="Compact")
    preferences.apply()
    assert draft.run_header.atr_presentation.parentWidget() is draft.reader_controls
    assert "23px" in draft.tree.styleSheet()
    second = window.run_tabs.new_run()
    assert second.tree.styleSheet() == draft.tree.styleSheet()


def test_draft_collection_footer_follows_tabs_and_detachment(window, qtbot, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    class Collector(QObject):
        collected = Signal(object)
        failed = Signal(str)
        def __init__(self, path, python, env, parent, timeout=120):
            super().__init__(parent)
            self.running = False
        def start(self):
            self.running = True
        def isRunning(self):
            return self.running
        def wait(self, *_):
            return not self.running

    draft = window.run_tabs.new_run()
    monkeypatch.setattr("runner.ui.main_window.CollectWorker", Collector)
    monkeypatch.setattr("runner.ui.main_window.interpreter_mod.cached_probe", lambda *_: object())
    monkeypatch.setattr(draft, "_on_interpreter_probed", lambda *_: None)
    monkeypatch.setattr(draft, "_require_interpreter", lambda: sys.executable)
    draft.load_workspace()
    qtbot.wait(10)
    assert draft.progress.isVisible()
    assert draft.progress.maximum() == 0
    assert draft.status_label.text() == "Collecting tests…"
    assert window.run_tabs.footer_stack.currentWidget() is draft.statusBar()
    window.run_tabs.show_context(window)
    assert not draft.progress.isVisible()
    assert not window.progress.isVisible()
    window.run_tabs.show_context(draft)
    assert draft.progress.isVisible()
    window.run_tabs.detach_current()
    entry = window.run_tabs.entry_for(draft)
    qtbot.wait(10)
    assert entry.floating.statusBar() is draft.statusBar()
    assert draft.progress.isVisible()
    draft._collector.running = False
    draft._collector.collected.emit(Collection(("test_demo.py::test_a", "test_demo.py::test_b")))
    assert draft.progress.isHidden()
    window.run_tabs.reattach(entry)
    assert window.run_tabs.footer_stack.currentWidget() is draft.statusBar()
    draft._tick()
    assert draft.elapsed_label.text()
    assert window.elapsed_label.text() == ""


def test_new_run_inherits_reader_choices_recent_workspaces_and_layout(window, qtbot):
    from runner.domain.models import Reader
    from runner.ui.main_window import K_RECENT
    readers = [Reader(index=i, name=f"Reader {i}") for i in range(2)]
    window.workspace = replace(window.workspace, settings={"Reader": "Reader 0", "Readers": ["Reader 1"]})
    window._on_collected(Collection(("test_demo.py::test_a", "test_demo.py::test_b")))
    window.readers_bar.select_names(readers, ["Reader 1"])
    window.settings.setValue(K_RECENT, [window.workspace.path, "C:/recent-environment"])
    window.split.setSizes([650, 300])
    window.tree.setColumnWidth(1, 123)
    qtbot.wait(10)
    draft = window.run_tabs.new_run()
    qtbot.wait(10)
    assert draft.readers_bar.selected_indexes() == (1,)
    assert draft.workspace_combo.findText("C:/recent-environment") >= 0
    assert draft.tree.columnWidth(1) == window.tree.columnWidth(1)
    assert abs(draft.split.sizes()[0] / sum(draft.split.sizes()) -
               window.split.sizes()[0] / sum(window.split.sizes())) < .02
    assert window.act_diverge.isEnabled()
    window.run_tabs.show_context(window)
    assert window.act_diverge.isEnabled()


def test_draft_shortcuts_target_visible_run_and_detached_window(window, qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication
    calls = []
    draft = window.run_tabs.new_run()
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    fake_start(draft, calls, monkeypatch)
    window.activateWindow()
    qtbot.wait(20)
    qtbot.keyClick(window, Qt.Key_F5)
    assert len(calls) == 1 and calls[0][0] is draft
    window.run_tabs.paused = True
    draft.service.finished.emit([])
    window.run_tabs.detach_current()
    floating = window.run_tabs.entry_for(draft).floating
    floating.activateWindow()
    qtbot.wait(20)
    qtbot.keyClick(floating, Qt.Key_F, Qt.ControlModifier)
    assert QApplication.focusWidget() is draft.search.field
    qtbot.keyClick(floating, Qt.Key_3, Qt.ControlModifier)
    assert draft.results.tabs.currentIndex() == 2
    window.run_tabs.reattach(window.run_tabs.entry_for(draft))


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
    profile.step_overrides = [{"protocol": "T0"}, {}, {"protocol": "T1"}]
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
    profile.step_overrides[0]["protocol"] = "changed after queuing"
    window.service.finished.emit([])
    qtbot.waitUntil(lambda: bool(launched))
    assert launched[0][1] == ["test_demo.py::test_b", "test_demo.py::test_a", "test_demo.py::test_b"]
    assert launched[0][2]["repetitions"] == 2
    assert launched[0][2]["step_overrides"] == [{"protocol": "T0"}, {}, {"protocol": "T1"}]


def test_detached_run_keeps_same_tree_after_close_and_reopen(window):
    draft = window.run_tabs.new_run()
    entry = window.run_tabs.current
    original_tree = draft.tree
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    window.run_tabs.detach_current()
    floating = entry.floating
    assert floating.isVisible()
    assert entry.page.isVisibleTo(floating)
    assert original_tree.isVisibleTo(floating)
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
    configuration = Path(draft.workspace.config_path)
    configuration.write_text("mode: preserved\n", encoding="utf-8")
    from PySide6.QtWidgets import QHeaderView
    draft.tree.header().setStretchLastSection(False)
    draft.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    draft.tree.setColumnWidth(0, 357)
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
        assert restored.context.workspace.config_path == str(configuration)
        assert restored.context.workspace.settings["mode"] == "preserved"
        assert restored.context.model.checked_nodeids() == ["test_demo.py::test_b"]
        assert restored.context.tree.columnWidth(0) == 357
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


def test_new_run_button_shows_preparation_and_shares_application_pages(window, qtbot):
    window.run_tabs.new_button.click()
    assert window.run_tabs.new_button.text() == "Preparing…"
    assert not window.run_tabs.new_button.isEnabled()
    qtbot.waitUntil(lambda: len(window.run_tabs.entries) == 2)
    draft = window.run_tabs.current.context
    assert draft.history is window.history
    assert draft.history_dashboard is window.history_dashboard
    assert draft.profiles_page is window.profiles_page
    assert draft.comparison_page is window.comparison_page
    assert draft.model is not window.model
    assert window.run_tabs.new_button.isEnabled()


def test_run_colours_results_and_live_navigation(window, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.model.set_checked_nodeids(["test_demo.py::test_a"])
    window.run_selected()
    active = window.run_tabs.entries[0]
    draft = window.run_tabs.new_run()
    assert window.run_tabs.live_button.isVisibleTo(window.run_tabs.panel)
    running_colour = window.run_tabs.tabs.tabData(0)["colour"]
    draft.model.set_checked_nodeids(["test_demo.py::test_b"])
    draft.run_selected()
    assert window.run_tabs.tabs.tabData(1)["colour"] != running_colour
    window.run_tabs.live_button.click()
    assert window.run_tabs.current is active
    window.service.outcome.emit(Outcome("test_demo.py::test_a", Status.FAILED))
    window.run_tabs.paused = True
    window.service.finished.emit([])
    assert window.run_tabs.tabs.tabData(0)["detail"].startswith("Failed")
    assert window._run_status_counts()[Status.FAILED] == 1
    failed_colour = window.run_tabs.tabs.tabData(0)["colour"]
    assert failed_colour != running_colour
    assert not window.run_tabs.detach_button.isVisible()


def test_incomplete_run_is_not_presented_as_success(window):
    entry = window.run_tabs.entries[0]
    entry.state = "finished"
    entry.progress = (1, 2)
    window.model.apply_outcome("test_demo.py::test_a", Status.PASSED, 0)
    window.run_tabs.refresh_labels()
    assert window.run_tabs.tabs.tabData(0)["detail"] == "Incomplete"


@pytest.mark.parametrize("change", ["workspace", "configuration"])
def test_environment_change_returns_completed_run_to_clean_draft(window, tmp_path, change):
    entry = window.run_tabs.entries[0]
    entry.state = "finished"
    entry.progress = (1, 1)
    window.model.apply_outcome("test_demo.py::test_a", Status.PASSED, 0)
    if change == "workspace":
        other = tmp_path / "other"
        other.mkdir()
        window.workspace = Workspace.load(str(other))
    else:
        config = tmp_path / "new-config.yaml"
        config.write_text("demo: changed\n", encoding="utf-8")
        window.workspace = Workspace.load(str(tmp_path), str(config))
    window._on_collected(Collection(("test_demo.py::test_a",)))
    assert entry.state == "draft"
    assert entry.progress == (0, 0)
    assert window._run_status_counts() == {}
    assert window.run_tabs.tabs.tabData(0)["detail"].startswith("Draft")
    assert window.pills[Status.PASSED]._value == 0


def test_configuration_tabs_follow_runs_and_shortcut_selects_own_copy(window, qtbot):
    draft = window.run_tabs.new_run()
    draft._pending_run_name = "Second run"
    window.run_tabs.refresh_labels()
    assert window.configuration_tabs.count() == draft.configuration_tabs.count() == 2
    assert draft.configuration_tabs.tabData(1)["name"] == "Second run"
    qtbot.mouseClick(window.run_header.run_config_button, Qt.LeftButton)
    assert window.run_tabs.current.context is window
    assert window.pages.currentWidget() is window.yaml_page
    window.configuration_tabs.setCurrentIndex(1)
    assert window.run_tabs.current.context is draft
    assert window.pages.currentWidget() is draft.yaml_page
    assert draft.yaml_editor.path == Path(draft.workspace.config_path)
    assert draft.yaml_editor.path != Path(window.workspace.config_path)
    window.run_tabs.tabs.moveTab(1, 0)
    assert draft.configuration_tabs.tabData(0)["name"] == "Second run"
    assert draft.configuration_tabs.currentIndex() == 0


def test_no_reader_actions_share_one_row(window, qtbot):
    from PySide6.QtWidgets import QBoxLayout
    qtbot.wait(50)
    header = window.run_header
    assert header.commands.direction() == QBoxLayout.LeftToRight
    assert header.execution_fields.indexOf(header.run_config_button) >= 0
    assert abs(window.run_button.mapTo(header, window.run_button.rect().center()).y()
               - window.stop_button.mapTo(header, window.stop_button.rect().center()).y()) <= 2


def test_config_navigation_stays_available_while_run_is_locked(window, monkeypatch):
    calls = []
    fake_start(window, calls, monkeypatch)
    window.run_selected()
    draft = window.run_tabs.new_run()
    window._open_run_configuration()
    assert window.pages.currentWidget() is window.yaml_page
    assert not window.yaml_stack.isEnabled()
    assert window.configuration_tabs.isEnabled()
    window.configuration_tabs.setCurrentIndex(1)
    assert window.pages.currentWidget() is draft.yaml_page
    assert draft.yaml_stack.isEnabled()
    assert window.run_tabs.active.context is window


def test_config_shortcut_of_detached_run_does_not_raise_run_window(window, monkeypatch):
    draft = window.run_tabs.new_run()
    entry = window.run_tabs.entry_for(draft)
    window.run_tabs.detach(entry)
    calls = []
    monkeypatch.setattr(entry.floating, "raise_", lambda: calls.append("raised"))
    draft._open_run_configuration()
    assert window.pages.currentWidget() is draft.yaml_page
    assert window.run_tabs.current is entry
    assert entry.floating is not None
    assert calls == []


def test_only_one_icon_configuration_shortcut_with_and_without_readers(window, tmp_path, qtbot):
    button = window.reader_config_button
    assert window.run_header.run_config_button is button
    assert button.text() == ""
    assert not button.icon().isNull()
    config = tmp_path / "readers.yaml"
    config.write_text("Reader: Demo reader\nReaders:\n  - Demo reader\n", encoding="utf-8")
    window.workspace = Workspace.load(str(tmp_path), str(config))
    window._on_collected(Collection(tuple(window.model._by_nodeid)))
    qtbot.wait(20)
    assert window.reader_controls.layout().indexOf(button) >= 0
    assert window.run_header.execution_fields.indexOf(button) == -1
    assert button.isVisible()
    assert button.width() <= 32
