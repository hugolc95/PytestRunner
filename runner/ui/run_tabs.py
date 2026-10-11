"""Independent run workspaces and one serial queue for physical execution.

Each workspace owns its existing tree, result panel and service. Switching a
tab only changes widget visibility; signals always reach their originating
workspace. Requests queued here are snapshots, never callbacks into a draft.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton, QStackedWidget,
    QTabBar, QVBoxLayout, QWidget,
)

from runner.domain.execution import Collection
from runner.ui import icons, tokens as t
from runner.ui.widgets import ErrorDialog


@dataclass(eq=False)
class RunTab:
    context: object
    page: QWidget
    identifier: str
    state: str = "draft"
    job: object = None
    floating: QMainWindow | None = None
    placeholder: QWidget | None = None
    progress: tuple[int, int] = (0, 0)

    @property
    def name(self):
        profile = self.context._active_execution_profile
        return (self.context._pending_run_name or
                (profile.name if profile is not None else "New run"))


@dataclass(frozen=True)
class QueuedRun:
    request: object
    env: dict
    profile: object = None
    config_snapshot: Path | None = None


class DetachedRun(QMainWindow):
    def __init__(self, controller, entry):
        super().__init__(controller.window)
        self.controller, self.entry = controller, entry
        self.setMinimumSize(1000, 620)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        tools = QHBoxLayout()
        self.title = QLabel()
        tools.addWidget(self.title, 1)
        attach = QPushButton("Reattach tab")
        attach.clicked.connect(lambda: controller.reattach(entry))
        tools.addWidget(attach)
        layout.addLayout(tools)
        layout.addWidget(entry.page, 1)
        self.setCentralWidget(body)
        callbacks = {"F5": entry.context.run_selected,
                     "Esc": lambda: controller.active.context.stop_run() if controller.active else None,
                     "Ctrl+F": entry.context.search.field.setFocus}
        for number in range(4):
            callbacks[f"Ctrl+{number + 1}"] = lambda number=number: entry.context.results.show_tab(number)
        for sequence, callback in callbacks.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        geometry = controller.window.settings.value("runs/detached_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1300, 800)

    def closeEvent(self, event):
        # Closing hides this workspace. Its tab can reopen the same window.
        self.controller.window.settings.setValue("runs/detached_geometry", self.saveGeometry())
        event.accept()


class RunTabsController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.entries = []
        self.queue = []
        self.active = None
        self.paused = False
        self.closing = False
        self._refreshing = False
        self._restoring = False
        self._recent = []
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self.save_sessions)
        self.panel = QWidget()
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QWidget()
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, 0)
        tools.setSpacing(t.SPACE_2)
        self.tabs = QTabBar()
        self.tabs.setObjectName("PrimaryTabs")
        self.tabs.setExpanding(False)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        tools.addWidget(self.tabs, 1)
        self.new_button = QPushButton("+ New run")
        self.new_button.clicked.connect(lambda: self.new_run())
        tools.addWidget(self.new_button)
        self.pause_button = QPushButton("Pause queue")
        self.pause_button.clicked.connect(self.toggle_pause)
        tools.addWidget(self.pause_button)
        self.detach_button = QPushButton("Detach tab")
        self.detach_button.clicked.connect(self.detach_current)
        tools.addWidget(self.detach_button)
        layout.addWidget(toolbar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        original_page = window.workspace_page
        window.pages.removeWidget(original_page)
        window.pages.insertWidget(0, self.panel)
        window.workspace_page = self.panel
        window.pages.setCurrentWidget(self.panel)
        self._register(window, original_page)
        self.tabs.currentChanged.connect(self.select)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabMoved.connect(self.tab_moved)
        self.tabs.customContextMenuRequested.connect(self.context_menu)
        self.summary = QLabel()
        self.summary.setObjectName("Faint")
        window.statusBar().insertPermanentWidget(window._status_permanent_index, self.summary, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh_labels)
        self.timer.start()
        self.refresh_labels()
        self._recent.append(self.entries[0])
        QTimer.singleShot(0, self.restore_sessions)

    @property
    def current(self):
        index = self.tabs.currentIndex()
        return self.entries[max(0, index)]

    @property
    def busy(self):
        return self.active is not None or any(
            entry.context.service.busy or entry.context._stress_worker is not None
            for entry in self.entries)

    def entry_for(self, context):
        return next((entry for entry in self.entries if entry.context is context), None)

    def is_locked(self, context):
        entry = self.entry_for(context)
        return bool(entry and entry.state in ("waiting", "running", "finalizing"))

    def _register(self, context, page):
        entry = RunTab(context, page, uuid4().hex)
        self.entries.append(entry)
        self.stack.addWidget(page)
        self.tabs.addTab("New run · Draft")
        context.service.started.connect(lambda request: self.started(entry, request))
        context.service.progress.connect(lambda done, total: self.progress(entry, done, total))
        # MainWindow finalizes and archives before this connection runs.
        context.service.finished.connect(lambda reports: self.finished(entry, reports))
        context.model.selection_changed.connect(lambda *_: self.schedule_save())
        context.model.modelReset.connect(self.schedule_save)
        return entry

    def new_run(self, source=None):
        from runner.ui.main_window import MainWindow
        source = source or self.current.context
        context = MainWindow(self.window, run_host=self.window)
        context.history = self.window.history
        context._tray.deleteLater()
        context._tray = self.window._tray
        context.navigation.hide()
        context.menuBar().hide()
        context._interpreter_override = source._interpreter_override
        if source.workspace is not None:
            context.workspace = deepcopy(source.workspace)
            context.workspace_combo.setCurrentText(context.workspace.path)
            context._on_collected(Collection(
                tuple(source.model._by_nodeid), deepcopy(source._markers_by_nodeid)))
            context.model.set_all_checked(False)
        entry = self._register(context, context.workspace_page)
        self.tabs.setCurrentIndex(self.entries.index(entry))
        self.window._show_page("workspace")
        self.window.preferences.track_buttons()
        self.refresh()
        self.schedule_save()
        return context

    def profile_target(self):
        context = self.current.context
        return self.new_run(context) if self.is_locked(context) else context

    def show_context(self, context):
        entry = self.entry_for(context)
        if entry is not None:
            self.tabs.setCurrentIndex(self.entries.index(entry))
            self.select(self.entries.index(entry))
        self.window._show_page("workspace")

    def select(self, index):
        if index < 0 or index >= len(self.entries):
            return
        entry = self.entries[index]
        if not self._recent or self._recent[-1] is not entry:
            self._recent.append(entry)
            self._recent = self._recent[-30:]
        self.stack.setCurrentWidget(entry.placeholder if entry.floating else entry.page)
        if entry.floating:
            entry.floating.show()
            entry.floating.raise_()
            entry.floating.activateWindow()
        self.refresh_labels()
        self.schedule_save()

    def submit(self, context, request, env, profile=None):
        entry = self.entry_for(context)
        if self.closing or entry is None or self.is_locked(context):
            return False
        queued = self.busy or self.paused or bool(self.queue)
        snapshot = None
        if queued and request.config_path:
            try:
                source = Path(request.config_path)
                root = context.history.racine / "queued-configurations" / request.run_id
                root.mkdir(parents=True, exist_ok=True)
                snapshot = root / source.name
                snapshot.write_bytes(source.read_bytes())
                request = replace(request, config_path=str(snapshot))
            except OSError as exc:
                ErrorDialog.show_error(context, "Could not queue the run",
                                       "The configuration snapshot could not be saved.", str(exc))
                return False
        entry.job = QueuedRun(request, deepcopy(env), deepcopy(profile), snapshot)
        if queued:
            entry.state = "waiting"
            self.queue.append(entry)
            context.status_label.setText("Queued · selection and settings captured")
            self.refresh()
            self.schedule_save()
            return True
        return self.launch(entry)

    def launch(self, entry):
        job = entry.job
        if job is None or self.closing:
            return False
        context = entry.context
        self.active = entry
        entry.state = "running"
        context._run_id = job.request.run_id
        context._build_number = job.request.build_number
        context._running_execution_profile = job.profile
        if job.profile is None:
            accepted = context.service.start(job.request, job.env)
        else:
            execution = job.profile.execution
            accepted = context.service.start_profile(
                job.request, job.env, list(job.profile.sequence),
                repetitions=execution.repetitions,
                rerun_failures=execution.rerun_failures,
                stop_after_failure=execution.stop_after_failure)
        if not accepted:
            self.active = None
            entry.state = "draft"
            self.release_snapshot(entry)
            context.status_label.setText("The run could not start. Review it and try again.")
            self.paused = bool(self.queue)
        self.refresh()
        self.schedule_save()
        return bool(accepted)

    def started(self, entry, request):
        self.active = entry
        entry.state = "running"
        entry.progress = (0, request.total_tests)
        self.refresh()

    def progress(self, entry, done, total):
        entry.progress = (done, total)
        self.refresh_labels()

    def finished(self, entry, reports):
        if entry.state != "running":
            return
        worker = getattr(entry.context, "_archive_worker", None)
        if worker is not None:
            entry.state = "finalizing"
            worker.done.connect(lambda *_: self.complete(entry, reports))
            self.refresh()
            return
        self.complete(entry, reports)

    def complete(self, entry, reports):
        entry.state = "stopped" if any(report.cancelled for report in reports) else "finished"
        if self.active is entry:
            self.active = None
        self.release_snapshot(entry)
        self.refresh()
        QTimer.singleShot(0, self.start_next)

    def watch_stress(self, context, worker):
        entry = self.entry_for(context)
        self.active = entry
        entry.state = "running"
        worker.finished.connect(lambda: self.finished(entry, []))
        self.refresh()

    def start_next(self):
        if not self.closing and not self.paused and not self.busy and self.queue:
            entry = self.queue.pop(0)
            self.launch(entry)

    def release_snapshot(self, entry):
        job, entry.job = entry.job, None
        if job and job.config_snapshot:
            try:
                job.config_snapshot.unlink(missing_ok=True)
                job.config_snapshot.parent.rmdir()
            except OSError:
                pass

    def toggle_pause(self):
        self.paused = not self.paused
        self.refresh()
        if not self.paused:
            self.start_next()

    def edit_waiting(self, entry):
        if entry in self.queue:
            self.queue.remove(entry)
            self.release_snapshot(entry)
            entry.state = "draft"
            entry.context.status_label.setText("Removed from queue · edit this draft and queue it again")
            self.refresh()

    def tab_moved(self, old, new):
        entry = self.entries.pop(old)
        self.entries.insert(new, entry)
        self.queue.sort(key=self.entries.index)
        self.refresh_labels()
        self.schedule_save()

    def context_menu(self, position):
        global_position = self.tabs.mapToGlobal(position)
        index = self.tabs.tabAt(position)
        if index < 0:
            return
        entry = self.entries[index]
        menu = QMenu(self.tabs)
        menu.addAction("Duplicate as a new draft", lambda: self.duplicate(entry))
        menu.addAction("Reattach tab" if entry.floating else "Detach tab",
                       lambda: self.reattach(entry) if entry.floating else self.detach(entry))
        if entry.state == "waiting":
            menu.addAction("Remove from queue and edit", lambda: self.edit_waiting(entry))
            queue_position = self.queue.index(entry)
            for label, delta in (("Move earlier", -1), ("Move later", 1)):
                action = menu.addAction(label, lambda delta=delta: self.move_waiting(entry, delta))
                action.setEnabled(0 <= queue_position + delta < len(self.queue))
        menu.addSeparator()
        close = menu.addAction("Close tab", lambda: self.close_tab(self.entries.index(entry)))
        close.setEnabled(len(self.entries) > 1 and entry.state not in ("running", "finalizing"))
        menu.exec(global_position)

    def move_waiting(self, entry, delta):
        index = self.queue.index(entry)
        if 0 <= index + delta < len(self.queue):
            other = self.queue[index + delta]
            self.tabs.moveTab(self.entries.index(entry), self.entries.index(other))

    def duplicate(self, entry):
        context = self.new_run(entry.context)
        context.model.set_checked_nodeids(entry.context.model.checked_nodeids())
        if entry.context._active_execution_profile is not None:
            context._open_collected_profile(deepcopy(entry.context._active_execution_profile))
        self.refresh()

    def detach_current(self):
        entry = self.current
        if entry.floating:
            self.reattach(entry)
        else:
            self.detach(entry)

    def detach(self, entry):
        if entry.floating:
            entry.floating.show()
            return
        previous = next((item for item in reversed(self._recent)
                         if item is not entry and item in self.entries and not item.floating), None)
        if previous is None:
            previous = next((item for item in self.entries if item is not entry and not item.floating), None)
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(QLabel("This run is open in a separate window."))
        reopen = QPushButton("Show detached run")
        reopen.clicked.connect(lambda: self.select(self.entries.index(entry)))
        layout.addWidget(reopen)
        self.stack.removeWidget(entry.page)
        self.stack.addWidget(placeholder)
        entry.placeholder = placeholder
        entry.floating = DetachedRun(self, entry)
        entry.floating.show()
        if previous is not None:
            self.tabs.setCurrentIndex(self.entries.index(previous))
        else:
            self.stack.setCurrentWidget(placeholder)
        self.refresh_labels()
        self.window.preferences.track_buttons()
        self.schedule_save()

    def reattach(self, entry):
        if not entry.floating:
            return
        floating, entry.floating = entry.floating, None
        self.window.settings.setValue("runs/detached_geometry", floating.saveGeometry())
        self.stack.addWidget(entry.page)
        self.stack.removeWidget(entry.placeholder)
        entry.placeholder.deleteLater()
        entry.placeholder = None
        floating.hide()
        floating.deleteLater()
        self.show_context(entry.context)
        self.schedule_save()

    def close_tab(self, index):
        entry = self.entries[index]
        if len(self.entries) == 1 or entry.state in ("running", "finalizing"):
            return
        collector = entry.context._collector
        if collector is not None and collector.isRunning():
            entry.context.status_label.setText("Collecting tests… close this tab after collection finishes")
            return
        if not entry.context.results.source.save():
            return
        self.edit_waiting(entry)
        if entry.floating:
            self.reattach(entry)
        self.tabs.blockSignals(True)
        self.tabs.removeTab(index)
        self.entries.remove(entry)
        self.tabs.blockSignals(False)
        self.stack.removeWidget(entry.page)
        entry.page.hide()
        entry.context.reader_selector.stop_discovery()
        entry.context.reader_atr.release()
        if entry.context is not self.window:
            for page in (entry.context.yaml_page, entry.context.python_page):
                self.window.pages.removeWidget(page)
                page.setParent(entry.context)
            entry.page.setParent(entry.context)
            entry.context.deleteLater()
        self.select(self.tabs.currentIndex())
        self.refresh()
        self.schedule_save()

    def schedule_save(self):
        if not self.closing and not self._restoring:
            self.save_timer.start()

    def save_sessions(self):
        """Remember drafts and detached geometry, never silently resume work."""
        data = []
        for entry in self.entries:
            context = entry.context
            workspace = context.workspace
            geometry = entry.floating.saveGeometry().toBase64().data().decode("ascii") if entry.floating else ""
            data.append(dict(
                workspace=workspace.path if workspace else "",
                config=workspace.config_path if workspace else "",
                name=context._pending_run_name,
                nodeids=list(context.model._by_nodeid),
                markers=context._markers_by_nodeid,
                checked=context.model.checked_nodeids(),
                profile=asdict(context._active_execution_profile) if context._active_execution_profile else None,
                profile_visible=context.profile_tree_button.isChecked(),
                readers=context.readers_bar.selected_indexes(),
                detached=entry.floating is not None, geometry=geometry,
                interpreter=context._interpreter_override,
            ))
        self.window.settings.setValue("runs/session", json.dumps(data))
        self.window.settings.setValue("runs/selected", self.tabs.currentIndex())

    def restore_sessions(self):
        from PySide6.QtCore import QByteArray
        from runner.domain.workspace import Workspace
        from runner.domain.execution_profile import (
            ExecutionProfile, ExecutionOptions, ReportOptions, validate_profile,
        )
        if self.closing or self.window.workspace is not None or self.window.model._by_nodeid:
            return
        try:
            data = json.loads(self.window.settings.value("runs/session", "[]", type=str))
        except (ValueError, TypeError):
            return
        if not isinstance(data, list) or not data:
            return
        self._restoring = True
        selected = self.window.settings.value("runs/selected", 0, type=int)
        try:
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                path = item.get("workspace", "")
                if path and not Path(path).is_dir():
                    continue
                context = self.window if index == 0 else self.new_run(self.window)
                if path:
                    context.workspace = Workspace.load(path, item.get("config", ""))
                    context.workspace_combo.setCurrentText(path)
                    context._tree_workspace = None
                    nodeids = item.get("nodeids", [])
                    if isinstance(nodeids, list) and all(isinstance(node, str) for node in nodeids):
                        context._on_collected(Collection(tuple(nodeids), item.get("markers", {})))
                    context.model.set_checked_nodeids(item.get("checked", []))
                context._interpreter_override = item.get("interpreter", "")
                context._pending_run_name = item.get("name", "")
                context.run_name_button.setText(context._pending_run_name or "Run name (optional)")
                profile = item.get("profile")
                if isinstance(profile, dict):
                    try:
                        profile = dict(profile)
                        profile["execution"] = ExecutionOptions(**profile["execution"])
                        profile["reports"] = ReportOptions(**profile["reports"])
                        profile = ExecutionProfile(**profile)
                        validate_profile(profile)
                        if all(node in context.model._by_nodeid for node in profile.sequence):
                            context._open_collected_profile(profile)
                            if not item.get("profile_visible"):
                                context._set_profile_tree_visible(False)
                    except (ValueError, KeyError, TypeError):
                        pass
                wanted = set(item.get("readers", []))
                readers = context.workspace.readers if context.workspace else ()
                context.readers_bar.select_names(readers, [reader.name for reader in readers if reader.index in wanted])
                context._update_actions()
                entry = self.entry_for(context)
                if item.get("detached"):
                    self.detach(entry)
                    if item.get("geometry"):
                        entry.floating.restoreGeometry(QByteArray.fromBase64(item["geometry"].encode("ascii")))
            self.tabs.setCurrentIndex(min(max(0, selected), len(self.entries) - 1))
            self.select(self.tabs.currentIndex())
        finally:
            self._restoring = False
        self.refresh()

    def apply_context_actions(self, context):
        locked = self.is_locked(context)
        context.model.selection_locked = locked
        context.run_name_button.setEnabled(not locked)
        context.run_name_edit.setEnabled(not locked)
        collecting = context._collector is not None and context._collector.isRunning()
        context.browse_button.setEnabled(not locked and not collecting)
        context.load_button.setEnabled(not locked and not collecting)
        context.config_button.setEnabled(context.workspace is not None and not locked and not self.busy)
        context.reader_config_button.setEnabled(context.workspace is not None and not locked and not self.busy)
        context.workspace_config_button.setEnabled(context.workspace is not None and not locked and not self.busy)
        context.act_config.setEnabled(context.workspace is not None and not locked and not self.busy)
        context.yaml_page.setEnabled(not locked and not self.busy)
        for button in (context.select_all_button, context.select_none_button):
            button.setEnabled(not locked and bool(context.model._by_nodeid)
                              and not context.profile_tree_button.isChecked())
        context.profile_picker.setEnabled(not locked)
        context.workspace_combo.setEnabled(not locked)
        context.readers_bar.setEnabled(not locked)
        context.run_button.setEnabled(context.run_button.isEnabled() and not locked)
        context.act_run.setEnabled(context.run_button.isEnabled())
        context.results.source.edit_button.setEnabled(not self.busy and not locked)
        if self.busy and context.results.source.edit_button.isChecked():
            context.results.source.edit_button.setChecked(False)
        entry = self.entry_for(context)
        if entry is not None:
            profile_visible = context.profile_tree_button.isChecked()
            text = "Add to queue" if (not locked and (self.busy or self.paused or self.queue)) else (
                "Queued" if entry.state == "waiting" else "Run profile" if profile_visible else "Run tests")
            context.run_button.setText(text)
            context.run_button.setToolTip("Queue a snapshot of this run" if text == "Add to queue" else text)
            context.run_button.setIcon(icons.icon(
                "mdi.playlist-plus" if text == "Add to queue" else "mdi.play", t.ON_RUN))

    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            for entry in self.entries:
                entry.context._update_actions()
                self.apply_context_actions(entry.context)
            self.refresh_labels()
        finally:
            self._refreshing = False

    def refresh_labels(self):
        for index, entry in enumerate(self.entries):
            if entry.state == "waiting":
                state = f"Waiting {self.queue.index(entry) + 1}"
                glyph = "mdi.clock-outline"
            elif entry.state == "running":
                done, total = entry.progress
                state = f"Running {done}/{total}" if total else "Running"
                glyph = "mdi.progress-clock"
            else:
                state = entry.state.capitalize()
                glyph = "mdi.pencil-outline" if entry.state == "draft" else "mdi.check-circle-outline"
            self.tabs.setTabText(index, f"{entry.name} · {state}")
            self.tabs.setTabToolTip(index, f"{entry.name}\n{state}" + ("\nDetached window" if entry.floating else ""))
            self.tabs.setTabIcon(index, icons.icon(glyph, t.ACCENT if entry is self.active else t.TEXT_MUTED))
            for side in (QTabBar.LeftSide, QTabBar.RightSide):
                close = self.tabs.tabButton(index, side)
                if close is not None:
                    close.setEnabled(len(self.entries) > 1 and entry.state not in ("running", "finalizing"))
            if entry.floating:
                entry.floating.setWindowTitle(f"{entry.name} · {state} — Pytest Runner")
                entry.floating.title.setText(f"{entry.name} · {state}")
        self.pause_button.setText("Resume queue" if self.paused else "Pause queue")
        self.pause_button.setVisible(bool(self.queue) or self.paused)
        self.detach_button.setText("Reattach tab" if self.current.floating else "Detach tab")
        self.detach_button.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        selected = self.current.context
        for name, enabled in (
                ("act_run", selected.run_button.isEnabled()),
                ("act_stop", bool(self.active and self.active.context.stop_button.isEnabled())),
                ("act_rerun", selected.rerun_button.isEnabled())):
            getattr(self.window, name).setEnabled(enabled)
        if hasattr(self, "summary"):
            active = f"{self.active.name} running · " if self.active else ""
            self.summary.setText(f"{active}{len(self.queue)} waiting" + (" · queue paused" if self.paused else ""))

    def shutdown(self):
        self.save_timer.stop()
        self.save_sessions()
        self.closing = True
        self.timer.stop()
        ready = True
        for entry in self.entries:
            context = entry.context
            context.reader_selector.stop_discovery()
            context.reader_atr.release()
            context._elapsed.stop()
            if context.service.busy:
                context.service.cancel()
                ready = context.service.wait(3000) is not False and ready
            if context._stress_worker is not None:
                context._stress_worker.cancel()
                ready = context._stress_worker.wait(3000) and ready
            if context._collector is not None and context._collector.isRunning():
                ready = context._collector.wait(3000) and ready
            archive = getattr(context, "_archive_worker", None)
            if archive is not None:
                ready = archive.wait(3000) and ready
            if entry.floating:
                entry.floating.hide()
            context.results.source.save()
        if not ready:
            self.paused = True
            self.closing = False
            self.timer.start()
            self.window.status_label.setText("Stopping workers… close again when they have finished")
            return False
        for entry in self.entries:
            self.release_snapshot(entry)
        return True
