"""Personal preferences and a session console, with native detachable pages."""
from __future__ import annotations

import json
import re
import shlex
import sys
import traceback
import weakref
from collections import deque
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)
from runner.ui import icons, theme, tokens as t
from runner.ui import timeouts
from runner.ui.trace_browser import TraceBrowser

DEFAULTS = dict(font_size=13, compact_header=False, atr_bottom=False,
                tree_density="Normal", selection_tab="Last used", follow_test=False,
                actions=True, commands=True, output=True, errors=True,
                timestamps=True, auto_scroll=True, limit=1000, notify_end=True,
                external_editor="Automatic", vscode_path="", pycharm_path="", retain_tree_results=True,
                show_duration=True)
DEFAULTS.update(timeouts.DEFAULTS)
# "Last used" garde l'onglet ouvert : forcer Detail a chaque nouveau test
# obligeait a recliquer Logs pour chaque test qu'on parcourait.
SELECTION_TABS = ("Last used", "Detail", "Source", "Output", "Logs")
GROUPS = (
    ("Interface", "Appearance and space", (
        ("theme", "Theme", "Keep the existing dark, light and accessible palettes.",
         ("dark", "light", "dark_colorblind", "light_colorblind")),
        ("font_size", "Text size", "Personal text size, without changing the layout.", (12, 16)),
        ("compact_header", "Compact top panels", "Reduce panel margins while keeping all controls.", bool),
        ("atr_bottom", "ATR in the bottom bar", "Keep the full, selectable ATR and refresh action below Run.", bool),
    )),
    ("Tree & details", "Browsing tests", (
        ("retain_tree_results", "Keep previous results in the test tree", "Outline icons keep older results; filled icons belong to the latest run. Clear results resets the tree, not History.", bool),
        ("tree_density", "Row spacing", "Choose how much space each test occupies.", ("Compact", "Normal", "Comfortable")),
        ("selection_tab", "Tab when selecting another test", "Last used keeps the tab you were reading, Logs for example.", SELECTION_TABS),
        ("show_duration", "Duration column", "Show each test's duration in the tree. Also from a right-click on the column headers.", bool),
        ("follow_test", "Follow the running test", "Bring the executing test into view.", bool),
    )),
    ("Timeouts", "Maximum waiting times • seconds • used by the next operation", (
        ("collection_timeout", "Test collection", "Stop collection if pytest has not finished within this time. Default: 120 s.", (1, 86400)),
        ("interpreter_timeout", "Python interpreter check", "Maximum time to check Python and its pytest installation. Default: 15 s.", (1, 86400)),
        ("reader_discovery_timeout", "Reader discovery", "Maximum time to list HubReader devices, here and in workspace configuration. Default: 10 s.", (1, 86400)),
        ("atr_startup_timeout", "ATR monitor startup", "Maximum wait for the first card status from the ATR monitor. Default: 10 s.", (1, 86400)),
    )),
    ("Console", "Recorded events", (
        ("actions", "Interface actions", "Record clicks, selections and navigation.", bool),
        ("commands", "Commands", "Record actual subprocess commands and working directories.", bool),
        ("output", "Process output", "Record live pytest output from every reader.", bool),
        ("errors", "Errors and tracebacks", "Keep actual exceptions and failed test reports.", bool),
        ("timestamps", "Show timestamps", "Display the time of each recorded event.", bool),
        ("auto_scroll", "Automatic scrolling", "Follow the latest trace when the view is not paused.", bool),
        ("limit", "Events kept in memory", "Bound the size of this session’s console.", (250, 1000, 5000)),
    )),
    ("Notifications", "Run completion", (
        ("notify_end", "Notify when a run ends", "Enable the existing desktop completion notification.", bool),
    )),
    ("External editor", "Source links • Ctrl+click always opens the external editor", (
        ("external_editor", "Preferred editor", "Automatic tries VS Code, then PyCharm. The other editor is used if the preferred one is unavailable.", ("Automatic", "VS Code", "PyCharm")),
        ("vscode_path", "VS Code executable", "Leave empty for automatic detection, or select your installation.", "executable"),
        ("pycharm_path", "PyCharm executable", "Leave empty for automatic detection, or select your installation.", "executable"),
    )),
)


class DetachedWindow(QMainWindow):
    def __init__(self, page):
        super().__init__(page.owner, Qt.Window)
        self.page = page
        self.setWindowTitle(f"Pytest Runner — {page.title}")
        self.setWindowIcon(page.owner.windowIcon())
        self.resize(960, 680)

    def closeEvent(self, event):
        # Closing a floating page hides it; only Reattach changes its mode.
        self.page.save_detached_state()
        self.page.owner.preferences.record("actions", f"{self.page.title} detached window closed")
        event.accept()


class DetachablePage(QWidget):
    def __init__(self, owner, title, description, content):
        super().__init__()
        self.owner, self.title, self.content = owner, title, content
        self.detached_window = None
        self.settings_key = f"preferences/pages/{title.casefold()}"
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        labels = QVBoxLayout()
        name = QLabel(title)
        name.setObjectName("PageTitle")
        description_label = QLabel(description)
        description_label.setObjectName("Muted")
        labels.addWidget(name)
        labels.addWidget(description_label)
        header.addLayout(labels, 1)
        self.detach_button = QPushButton("Detach window")
        self.detach_button.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        self.detach_button.clicked.connect(self.toggle_detach)
        header.addWidget(self.detach_button)
        body.addLayout(header)
        body.addWidget(content, 1)
        root.addWidget(self.body, 1)
        self.placeholder = QWidget()
        placeholder = QVBoxLayout(self.placeholder)
        placeholder.addStretch()
        note = QLabel(f"{title} is open in a separate window.")
        note.setAlignment(Qt.AlignCenter)
        note.setObjectName("PageTitle")
        placeholder.addWidget(note)
        info = QLabel("Your current content is preserved when you reattach it.")
        info.setAlignment(Qt.AlignCenter)
        info.setObjectName("Muted")
        placeholder.addWidget(info)
        buttons = QHBoxLayout()
        buttons.addStretch()
        show = QPushButton("Show window")
        show.clicked.connect(self.show_detached)
        attach = QPushButton("Reattach to tab")
        attach.clicked.connect(self.reattach)
        buttons.addWidget(show)
        buttons.addWidget(attach)
        buttons.addStretch()
        placeholder.addLayout(buttons)
        placeholder.addStretch()
        root.addWidget(self.placeholder, 1)
        self.placeholder.hide()

    def show_detached(self):
        if self.detached_window:
            self.detached_window.showNormal()
            self.detached_window.raise_()
            self.detached_window.activateWindow()

    def restyle(self):
        self.detach_button.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        if self.detached_window:
            self.detached_window.setStyleSheet(self.owner.styleSheet())

    def toggle_detach(self):
        if self.detached_window:
            self.reattach()
            return
        self.detached_window = DetachedWindow(self)
        self.layout().removeWidget(self.body)
        self.body.layout().setContentsMargins(20, 18, 20, 18)
        self.detached_window.setCentralWidget(self.body)
        self.detached_window.setStyleSheet(self.owner.styleSheet())
        geometry = self.owner.settings.value(self.settings_key + "/geometry")
        if geometry is not None:
            self.detached_window.restoreGeometry(geometry)
        self.detach_button.setText("Reattach to tab")
        self.placeholder.show()
        self.detached_window.show()
        self.save_detached_state()
        if self.owner.pages.currentWidget() is self:
            self.owner._show_previous_attached_page()
        self.owner.preferences.record("actions", f"{self.title} detached into a native window")

    def save_detached_state(self):
        self.owner.settings.setValue(self.settings_key + "/detached", bool(self.detached_window))
        if self.detached_window:
            self.owner.settings.setValue(self.settings_key + "/geometry", self.detached_window.saveGeometry())

    def reattach(self, *, persist=True):
        floating = self.detached_window
        if not floating:
            return
        floating.takeCentralWidget()
        self.body.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().insertWidget(0, self.body, 1)
        self.body.show()
        self.placeholder.hide()
        self.detach_button.setText("Detach window")
        self.detached_window = None
        floating.hide()
        floating.deleteLater()
        if persist:
            self.save_detached_state()
            self.owner._show_page(self.title.casefold())
        self.owner.preferences.record("actions", f"{self.title} reattached to its tab")


class TraceBus(QObject):
    event = Signal(str, str)


class DiagnosticConsole(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.events = deque()
        self.paused = False
        self._dirty = False
        self._rendered = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 16, 0, 0)
        filters = QHBoxLayout()
        self.kind = QComboBox()
        for title, value in (("All events", ""), ("Interface actions", "actions"),
                             ("Commands", "commands"), ("Process output", "output"),
                             ("Errors / tracebacks", "errors")):
            self.kind.addItem(title, value)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search commands, messages or tracebacks…")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.kind)
        filters.addWidget(self.search, 1)
        root.addLayout(filters)
        actions = QHBoxLayout()
        self.scroll = QCheckBox("Automatic scrolling")
        self.scroll.setChecked(True)
        self.pause = QPushButton("Pause display")
        self.pause.setCheckable(True)
        self.pause.toggled.connect(self.set_paused)
        actions.addWidget(self.scroll)
        actions.addWidget(self.pause)
        actions.addStretch()
        for title, slot in (("Copy", self.copy), ("Export .log", self.export), ("Clear", self.clear)):
            button = QPushButton(title)
            button.clicked.connect(slot)
            actions.addWidget(button)
        root.addLayout(actions)
        self.text = TraceBrowser()
        self.text.require_context = True
        self.text.source_requested.connect(lambda location, external: controller.window._open_source_reference(
            location, external, on_return=lambda: controller.window._show_page("console")))
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(TraceBrowser.NoWrap)
        font = QFont("DejaVu Sans Mono")
        font.setPointSize(10)
        self.text.setFont(font)
        root.addWidget(self.text, 1)
        self.summary = QLabel("Session console • recording continues on every page")
        self.summary.setObjectName("Muted")
        root.addWidget(self.summary)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._flush)
        self.timer.start()

    def append(self, kind, message):
        if not self.controller.values.get(kind, True):
            return
        self.events.append((datetime.now().strftime("%H:%M:%S"), kind, message.rstrip()))
        while len(self.events) > int(self.controller.values["limit"]):
            self.events.popleft()
        self._dirty = True

    def _flush(self):
        if self._dirty and not self.paused and self.isVisible():
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def refresh(self, *_):
        if self.paused:
            return
        kind, query = self.kind.currentData(), self.search.text().casefold()
        lines = []
        for stamp, category, message in self.events:
            if kind and kind != category or query and query not in message.casefold():
                continue
            prefix = f"{stamp}  " if self.controller.values["timestamps"] else ""
            lines.append(f"{prefix}[{category.upper()}]  {message}")
        scroll = self.text.verticalScrollBar()
        position = scroll.value()
        if lines != self._rendered:
            # The usual output batch only appends events. Preserve the existing
            # document and selection instead of laying out the entire log again.
            previous = self._rendered
            dropped = next((i for i, line in enumerate(previous)
                            if lines and line == lines[0]
                            and previous[i:] == lines[:len(previous) - i]), None)
            if previous and dropped is not None:
                cursor = QTextCursor(self.text.document())
                cursor.beginEditBlock()
                if dropped:
                    cursor.setPosition(0)
                    # Qt cursor offsets are UTF-16 units, including emoji in
                    # test names and console messages.
                    chars = sum(len(line.encode("utf-16-le")) // 2 + 1 for line in previous[:dropped])
                    cursor.setPosition(chars, QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                cursor.movePosition(QTextCursor.End)
                added = lines[len(previous) - dropped:]
                if added:
                    self.text.insert_trace_text(cursor, "\n" + "\n".join(added))
                cursor.endEditBlock()
            else:
                self.text.setPlainText("\n".join(lines))
            self._rendered = lines
        scroll.setValue(scroll.maximum() if self.scroll.isChecked() else position)
        self.summary.setText(f"{len(lines)} / {len(self.events)} events • recording active • session only")
        self._dirty = False

    def set_paused(self, paused):
        self.paused = paused
        self.pause.setText("Resume display" if paused else "Pause display")
        if not paused:
            self.refresh()

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export console", "pytestrunner.log", "Log files (*.log)")
        if path:
            from pathlib import Path
            try:
                Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
            except OSError as exc:
                self.controller.record("errors", f"Export failed: {exc}")

    def clear(self):
        self.events.clear()
        self._dirty = True
        self.refresh()


class PreferencesPanel(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.controls = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 16, 0, 0)
        top = QHBoxLayout()
        self.categories = QListWidget()
        self.categories.setFixedWidth(190)
        self.stack = QStackedWidget()
        for category, subtitle, options in GROUPS:
            self.categories.addItem(category)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            content = QWidget()
            layout = QVBoxLayout(content)
            layout.setContentsMargins(24, 8, 24, 16)
            heading = QLabel(category)
            heading.setObjectName("PageTitle")
            layout.addWidget(heading)
            note = QLabel(subtitle)
            note.setObjectName("Muted")
            layout.addWidget(note)
            layout.addSpacing(16)
            for key, title, description, choices in options:
                row = QHBoxLayout()
                labels = QVBoxLayout()
                label = QLabel(title)
                label.setStyleSheet("font-weight: 600;")
                copy = QLabel(description)
                copy.setWordWrap(True)
                copy.setObjectName("Muted")
                labels.addWidget(label)
                labels.addWidget(copy)
                row.addLayout(labels, 1)
                if choices is bool:
                    control = QCheckBox("Enabled")
                    control.setChecked(controller.values[key])
                    control.toggled.connect(lambda value, k=key: self.update_value(k, value))
                elif choices == "executable":
                    control = QLineEdit(controller.values[key])
                    control.setPlaceholderText("Automatic detection")
                    control.setMinimumWidth(180)
                    control.textChanged.connect(lambda value, k=key: self.update_value(k, value))
                elif key in timeouts.DEFAULTS:
                    control = QSpinBox()
                    control.setObjectName("TimeoutInput")
                    control.setAlignment(Qt.AlignCenter)
                    control.setRange(timeouts.MIN_SECONDS, timeouts.MAX_SECONDS)
                    control.setValue(controller.values[key])
                    control.setMinimumWidth(160)
                    control.valueChanged.connect(lambda value, k=key: self.update_value(k, value))
                elif key == "font_size":
                    control = QSlider(Qt.Horizontal)
                    control.setRange(*choices)
                    control.setValue(controller.values[key])
                    control.setFixedWidth(150)
                    control.valueChanged.connect(lambda value, k=key: self.update_value(k, value))
                else:
                    control = QComboBox()
                    for choice in choices:
                        control.addItem(str(choice), choice)
                    value = t.current_theme() if key == "theme" else controller.values[key]
                    control.setCurrentIndex(max(0, control.findData(value)))
                    control.setMinimumWidth(160)
                    control.currentIndexChanged.connect(lambda _, k=key, c=control: self.update_value(k, c.currentData()))
                control.setAccessibleName(title + " (seconds)" if key in timeouts.DEFAULTS else title)
                self.controls[key] = control
                row.addWidget(control)
                if choices == "executable":
                    browse = QPushButton("Browse…")
                    browse.clicked.connect(lambda _, c=control: self.browse_editor(c))
                    row.addWidget(browse)
                if key in timeouts.DEFAULTS:
                    unit = QLabel("s")
                    unit.setObjectName("Muted")
                    unit.setToolTip("Seconds")
                    unit.setMinimumWidth(14)
                    row.addWidget(unit)
                layout.addLayout(row)
                line = QFrame()
                line.setObjectName("PreferencesDivider")
                line.setFixedHeight(1)
                layout.addWidget(line)
                layout.addSpacing(12)
            layout.addStretch()
            scroll.setWidget(content)
            self.stack.addWidget(scroll)
        self.categories.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.categories.setCurrentRow(0)
        top.addWidget(self.categories)
        top.addWidget(self.stack, 1)
        root.addLayout(top, 1)
        footer = QHBoxLayout()
        self.notice = QLabel("Personal preferences • preview updates immediately")
        self.notice.setObjectName("Muted")
        footer.addWidget(self.notice, 1)
        restore = QPushButton("Cancel changes")
        restore.clicked.connect(self.cancel)
        apply = QPushButton("Apply settings")
        apply.setObjectName("Primary")
        apply.clicked.connect(controller.save)
        footer.addWidget(restore)
        footer.addWidget(apply)
        root.addLayout(footer)

    def update_value(self, key, value):
        self.controller.values[key] = value
        if key in ("theme", "font_size"):
            self.notice.setText("Updating appearance…")
            self.notice.repaint()
            self.controller.preview_timer.start(80 if key == "font_size" else 20)
            return
        self.controller.apply()
        self.notice.setText("Unsaved preview • click Apply settings to keep it")

    def browse_editor(self, control):
        path, _ = QFileDialog.getOpenFileName(self, "Choose editor executable", control.text(), "All files (*)")
        if path:
            control.setText(path)

    def cancel(self):
        self.controller.preview_timer.stop()
        self.controller.values = dict(self.controller.saved)
        for key, control in self.controls.items():
            control.blockSignals(True)
            value = self.controller.values.get(key, t.current_theme())
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, (QSlider, QSpinBox)):
                control.setValue(value)
            elif isinstance(control, QLineEdit):
                control.setText(value)
            else:
                control.setCurrentIndex(control.findData(value))
            control.blockSignals(False)
        self.controller.apply()
        self.notice.setText("Changes cancelled • saved preferences restored")

    def restyle(self):
        for line in self.findChildren(QFrame, "PreferencesDivider"):
            line.setStyleSheet(f"background: {t.BORDER}; border: none;")


class PreferencesController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        try:
            stored = json.loads(window.settings.value("preferences/personal", "{}", type=str))
        except (ValueError, TypeError):
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        # Ancien reglage `default_tab`, qui valait Detail par defaut : seul un
        # autre onglet choisi expres est repris, Detail devient "Last used".
        if "selection_tab" not in stored and stored.get("default_tab") in ("Source", "Output", "Logs"):
            stored["selection_tab"] = stored["default_tab"]
        self.values = dict(DEFAULTS)
        self.values.update({key: value for key, value in stored.items()
                            if key in DEFAULTS and type(value) is type(DEFAULTS[key])})
        self.values["font_size"] = min(16, max(12, self.values["font_size"]))
        for key in timeouts.DEFAULTS:
            self.values[key] = min(timeouts.MAX_SECONDS, max(timeouts.MIN_SECONDS, self.values[key]))
        for key, choices in (("tree_density", ("Compact", "Normal", "Comfortable")),
                             ("external_editor", ("Automatic", "VS Code", "PyCharm")),
                             ("selection_tab", SELECTION_TABS),
                             ("limit", (250, 1000, 5000))):
            if self.values[key] not in choices:
                self.values[key] = DEFAULTS[key]
        self.values["theme"] = t.current_theme()
        self.saved = dict(self.values)
        self._applied_values = {}
        self._contexts = weakref.WeakSet()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.finish_preview)
        self.bus = TraceBus(self)
        self.active = True
        self.console = DiagnosticConsole(self)
        self.bus.event.connect(self.console.append)
        self.settings_panel = PreferencesPanel(self)
        self.settings_page = DetachablePage(window, "Settings", "Personal preferences and operation timeouts — applied per user", self.settings_panel)
        self.console_page = DetachablePage(window, "Console", "Actual commands, interface actions, process output and tracebacks", self.console)
        window.pages.addWidget(self.settings_page)
        window.pages.addWidget(self.console_page)
        window.settings_page = self.settings_page
        window.console_page = self.console_page
        self.apply()
        self.attach_context(window)
        self._traced_buttons = weakref.WeakSet()
        self.track_buttons()
        self.install_command_trace()
        self.record("actions", "Pytest Runner started • Settings and Console pages ready")
        QTimer.singleShot(0, self.restore_detached_pages)

    def attach_context(self, context):
        if context in self._contexts:
            return
        self._contexts.add(context)
        context.service.line.connect(lambda index, text: self.process_line(index, text, context))
        context.service.started.connect(lambda request: self.context_record(
            context, "actions", f"Execution started: {len(request.nodeids)} tests"))
        context.service.reader_finished.connect(lambda report: self.reader_finished(report, context))
        context.service.profile_execution.connect(lambda position, attempt, reader, nodeid, status:
            self.follow_profile(context, position, attempt, status))
        context.service.finished.connect(lambda reports: self.context_record(context, "actions", "Execution finished"))
        context.model.selection_changed.connect(lambda: self.context_record(
            context, "actions", f"Test selection changed: {len(context.model.checked_nodeids())} selected"))
        for tree in (context.tree, context.profile_tree):
            tree.selectionModel().currentChanged.connect(
                lambda current, previous: self.selected_test(current, previous, context))
        self.apply_context(context)

    def context_record(self, context, kind, message):
        workspace = getattr(context, "workspace", None)
        if workspace is not None and (kind == "errors" or message.startswith("Collection ")):
            message = f"Workspace: {workspace.path}\n{message}"
        if context is not self.window:
            entry = context.run_tabs.entry_for(context) if context.run_tabs else None
            message = f"[{entry.name if entry else 'New run'}] {message}"
        self.record(kind, message)

    def forget_context(self, context):
        self._contexts.discard(context)

    def follow_profile(self, context, position, attempt, status):
        from runner.domain.models import Status
        if self.values["follow_test"] and status == Status.RUNNING:
            item = context.profile_model.index_for_nodeid(context.profile_model.key(position, attempt))
            if item.isValid():
                context.profile_tree.setCurrentIndex(item)
                context.profile_tree.scrollTo(item)

    def restore_detached_pages(self):
        if not self.active:
            return
        for page in (self.settings_page, self.console_page):
            if (not page.detached_window and
                    self.window.settings.value(page.settings_key + "/detached", False, type=bool)):
                page.toggle_detach()

    def record(self, kind, message):
        if self.active:
            self.bus.event.emit(kind, str(message))

    def track_buttons(self):
        # Signals avoid inspecting every native Qt event, including events from
        # viewports being destroyed or reparented while switching tree modes.
        for button in self.window.findChildren(QAbstractButton):
            if button not in self._traced_buttons:
                button.clicked.connect(self.button_clicked)
                self._traced_buttons.add(button)

    def button_clicked(self):
        if self.active:
            button = self.sender()
            self.record("actions", f"Click: {button.text() or button.toolTip() or button.objectName()}")
            self.track_buttons()

    def install_command_trace(self):
        ref = weakref.ref(self)
        def audit(event, args):
            controller = ref()
            if controller and controller.active and event == "subprocess.Popen":
                command = args[1]
                rendered = shlex.join(str(part) for part in command) if isinstance(command, (list, tuple)) else str(command)
                controller.record("commands", f"{rendered}\n    cwd: {args[2] or '(inherited)'}")
        sys.addaudithook(audit)
        self.previous_excepthook = sys.excepthook
        def handle_exception(exc_type, value, tb):
            self.record("errors", "".join(traceback.format_exception(exc_type, value, tb)))
            self.previous_excepthook(exc_type, value, tb)
        self.exception_handler = handle_exception
        sys.excepthook = handle_exception

    def selected_test(self, current, previous, context=None):
        context = context or self.window
        self.track_buttons()
        if current.isValid():
            from runner.ui.tree_model import NODEID_ROLE
            nodeid = current.data(NODEID_ROLE)
            if nodeid:
                self.context_record(context, "actions", f"Selected test: {nodeid}")
            onglet = self.values["selection_tab"]
            if onglet == "Last used":
                return
            panel = context.profile_results if context.profile_tree_button.isChecked() else context.results
            panel.tabs.setCurrentIndex(SELECTION_TABS.index(onglet) - 1)

    def process_line(self, index, text, context=None):
        context = context or self.window
        self.context_record(context, "output", f"Reader {index}: {text}")
        prefix = "PYTESTRUNNER_START\t"
        if self.values["follow_test"] and text.strip().startswith(prefix):
            nodeid = text.strip()[len(prefix):]
            item = context.model.index_for_nodeid(nodeid)
            if item.isValid():
                context.tree.setCurrentIndex(item)
                context.tree.scrollTo(item)

    def reader_finished(self, report, context=None):
        context = context or self.window
        self.context_record(context, "commands", f"Reader {report.reader.index} finished • exit code {report.exit_code}")
        if report.exit_code not in (0, 5) or report.issues:
            detail = "\n\n".join(filter(None, ("\n".join(report.issues), report.output)))
            self.context_record(context, "errors", detail or f"Process exited with code {report.exit_code}.")

    def show_errors(self):
        """Open the diagnostic console with the error trace immediately visible."""
        self.console.search.clear()
        self.console.kind.setCurrentIndex(self.console.kind.findData("errors"))
        self.console.pause.setChecked(False)
        self.console.set_paused(False)
        self.console.refresh()
        self.window._show_page("console")
        if self.console_page.detached_window:
            self.console_page.show_detached()

    def apply_font(self):
        key = (t.current_theme(), self.values["font_size"])
        if getattr(self, "_applied_font_key", None) != key:
            delta = self.values["font_size"] - 13
            stylesheet = re.sub(r"font-size: (\d+)px", lambda match:
                                f"font-size: {max(9, int(match.group(1)) + delta)}px",
                                theme.app_stylesheet())
            self.window.setStyleSheet(stylesheet)
            self._applied_font_key = key
            font = self.window.font()
            font.setPixelSize(self.values["font_size"])
            self.window.setFont(font)

    def theme_changed(self):
        # Sidebar shortcuts use the same preferences as the Settings page.
        if not getattr(self, "_applying_theme", False):
            self.values["theme"] = t.current_theme()
            self.saved["theme"] = t.current_theme()
            control = self.settings_panel.controls["theme"]
            control.blockSignals(True)
            control.setCurrentIndex(control.findData(t.current_theme()))
            control.blockSignals(False)
            self.record("actions", f"Theme changed: {t.current_theme()}")
        self.settings_panel.restyle()
        for page in (self.settings_page, self.console_page):
            page.restyle()

    def apply(self):
        window, values = self.window, self.values
        changed = {key for key, value in values.items()
                   if self._applied_values.get(key) != value}
        if t.current_theme() != values["theme"]:
            self._applying_theme = True
            try:
                window.apply_theme(values["theme"])
            finally:
                self._applying_theme = False
        if changed & {"font_size", "theme"}:
            self.apply_font()
        for context in tuple(self._contexts) or (window,):
            self.apply_context(context)
        if "auto_scroll" in changed:
            self.console.scroll.setChecked(values["auto_scroll"])
        while len(self.console.events) > values["limit"]:
            self.console.events.popleft()
        if changed & {"timestamps", "limit"}:
            self.console._dirty = True
        if "font_size" in changed:
            for page in (self.settings_page, self.console_page):
                if page.detached_window:
                    page.detached_window.setStyleSheet(window.styleSheet())
        self._applied_values = dict(values)

    def apply_context(self, window):
        values = self.values
        previous = getattr(window, "_applied_run_preferences", {})
        changed = {key for key, value in values.items() if previous.get(key) != value}
        if 'retain_tree_results' in changed and hasattr(window, 'tree_results'):
            window.tree_results.apply_preference()
        if "compact_header" in changed:
            for panel in (window.run_header.environment, window.run_header.execution, window.run_header.results):
                layout = panel.layout()
                margin, spacing = (8, 4) if values["compact_header"] else (12, 8)
                layout.setContentsMargins(margin, spacing, margin, spacing)
                layout.setSpacing(spacing)
        atr = window.run_header.atr_presentation
        if values["atr_bottom"]:
            if atr.parentWidget() != window.statusBar():
                window.reader_controls.layout().removeWidget(atr)
                atr.set_bottom_bar(True)
                window.statusBar().insertPermanentWidget(window._status_permanent_index, atr, 1)
                atr.setMinimumWidth(80)
        elif atr.parentWidget() != window.reader_controls:
            window.statusBar().removeWidget(atr)
            atr.set_bottom_bar(False)
            window.reader_controls.layout().addWidget(atr, 1, 0, 1, 2)
            atr.setMinimumWidth(80)
        atr.show()
        if "show_duration" in changed and hasattr(window, "tree_columns"):
            window.tree_columns.set_duration_visible(values["show_duration"])
        if "tree_density" in changed:
            height = {"Compact": 23, "Normal": 29, "Comfortable": 35}[values["tree_density"]]
            for tree in (window.tree, window.profile_tree):
                tree.setStyleSheet(f"QTreeView::item {{ min-height: {height}px; }}")
        window._applied_run_preferences = dict(values)

    def finish_preview(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.apply()
        finally:
            QApplication.restoreOverrideCursor()
        self.settings_panel.notice.setText("Unsaved preview • click Apply settings to keep it")

    def set_saved_value(self, key, value):
        """Un reglage change hors de la page Settings (menu de l'arbre) :
        applique et enregistre tout de suite, sans toucher aux autres reglages
        en cours d'apercu sur la page."""
        self.values[key] = value
        self.saved[key] = value
        control = self.settings_panel.controls.get(key)
        if isinstance(control, QCheckBox) and control.isChecked() != value:
            control.blockSignals(True)
            control.setChecked(value)
            control.blockSignals(False)
        self.apply()
        self.window.settings.setValue("preferences/personal", json.dumps(self.saved))

    def save(self):
        self.preview_timer.stop()
        self.apply()
        self.saved = dict(self.values)
        self.window.settings.setValue("preferences/personal", json.dumps(self.saved))
        self.window.settings.sync()
        self.settings_panel.notice.setText("Settings applied and saved for this user")
        self.record("actions", "Personal settings applied and saved")

    def shutdown(self):
        if not self.active:
            return
        for page in (self.settings_page, self.console_page):
            page.save_detached_state()
            page.reattach(persist=False)
        self.window.settings.sync()
        self.active = False
        self.preview_timer.stop()
        if hasattr(self.window, "_theme_preview_timer"):
            self.window._theme_preview_timer.stop()
        self.console.timer.stop()
        if sys.excepthook is self.exception_handler:
            sys.excepthook = self.previous_excepthook
