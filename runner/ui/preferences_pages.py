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

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)
from runner.ui import icons, theme, tokens as t

DEFAULTS = dict(font_size=13, compact_header=False, atr_bottom=False,
                tree_density="Normal", default_tab="Detail", follow_test=False,
                actions=True, commands=True, output=True, errors=True,
                timestamps=True, auto_scroll=True, limit=1000, notify_end=True)
GROUPS = (
    ("Interface", "Appearance and space", (
        ("theme", "Theme", "Keep the existing dark, light and accessible palettes.",
         ("dark", "light", "dark_colorblind", "light_colorblind")),
        ("font_size", "Text size", "Personal text size, without changing the layout.", (12, 16)),
        ("compact_header", "Compact top panels", "Reduce panel margins while keeping all controls.", bool),
        ("atr_bottom", "ATR in the bottom bar", "Keep the full, selectable ATR and refresh action below Run.", bool),
    )),
    ("Tree & details", "Browsing tests", (
        ("tree_density", "Row spacing", "Choose how much space each test occupies.", ("Compact", "Normal", "Comfortable")),
        ("default_tab", "Default detail tab", "Open this tab when selecting another test.", ("Detail", "Source", "Output", "Logs")),
        ("follow_test", "Follow the running test", "Bring the executing test into view.", bool),
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
)


class DetachedWindow(QMainWindow):
    def __init__(self, page):
        super().__init__(page.owner, Qt.Window)
        self.page = page
        self.setWindowTitle(f"Pytest Runner — {page.title}")
        self.setWindowIcon(page.owner.windowIcon())
        self.resize(960, 680)

    def closeEvent(self, event):
        self.page.reattach()
        event.accept()


class DetachablePage(QWidget):
    def __init__(self, owner, title, description, content):
        super().__init__()
        self.owner, self.title, self.content = owner, title, content
        self.detached_window = None
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
        self.detach_button.setText("Reattach to tab")
        self.placeholder.show()
        self.detached_window.show()
        self.owner.preferences.record("actions", f"{self.title} detached into a native window")

    def reattach(self):
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
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
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
        if self._dirty and not self.paused:
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
        self.text.setPlainText("\n".join(lines))
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
                control.setAccessibleName(title)
                self.controls[key] = control
                row.addWidget(control)
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
        self.controller.apply()
        self.notice.setText("Unsaved preview • click Apply settings to keep it")

    def cancel(self):
        self.controller.values = dict(self.controller.saved)
        for key, control in self.controls.items():
            control.blockSignals(True)
            value = self.controller.values.get(key, t.current_theme())
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QSlider):
                control.setValue(value)
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
        self.values = dict(DEFAULTS)
        self.values.update({key: value for key, value in stored.items()
                            if key in DEFAULTS and type(value) is type(DEFAULTS[key])})
        self.values["font_size"] = min(16, max(12, self.values["font_size"]))
        for key, choices in (("tree_density", ("Compact", "Normal", "Comfortable")),
                             ("default_tab", ("Detail", "Source", "Output", "Logs")),
                             ("limit", (250, 1000, 5000))):
            if self.values[key] not in choices:
                self.values[key] = DEFAULTS[key]
        self.values["theme"] = t.current_theme()
        self.saved = dict(self.values)
        self.bus = TraceBus(self)
        self.active = True
        self.console = DiagnosticConsole(self)
        self.bus.event.connect(self.console.append)
        self.settings_panel = PreferencesPanel(self)
        self.settings_page = DetachablePage(window, "Settings", "Personal preferences for the interface — live preview, applied per user", self.settings_panel)
        self.console_page = DetachablePage(window, "Console", "Actual commands, interface actions, process output and tracebacks", self.console)
        window.pages.addWidget(self.settings_page)
        window.pages.addWidget(self.console_page)
        window.settings_page = self.settings_page
        window.console_page = self.console_page
        self.apply()
        window.service.line.connect(self.process_line)
        window.service.started.connect(lambda request: self.record("actions", f"Execution started: {len(request.nodeids)} tests"))
        window.service.reader_finished.connect(self.reader_finished)
        window.service.finished.connect(lambda reports: self.record("actions", "Execution finished"))
        window.model.selection_changed.connect(lambda: self.record("actions", f"Test selection changed: {len(window.model.checked_nodeids())} selected"))
        window.tree.selectionModel().currentChanged.connect(self.selected_test)
        QApplication.instance().installEventFilter(self)
        self.install_command_trace()
        self.record("actions", "Pytest Runner started • Settings and Console pages ready")

    def record(self, kind, message):
        if self.active:
            self.bus.event.emit(kind, str(message))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and isinstance(watched, (QPushButton, QCheckBox)):
            if self.window.isAncestorOf(watched):
                self.record("actions", f"Click: {watched.text() or watched.toolTip() or watched.objectName()}")
        return False

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

    def selected_test(self, current, previous):
        if current.isValid():
            from runner.ui.tree_model import NODEID_ROLE
            nodeid = current.data(NODEID_ROLE)
            if nodeid:
                self.record("actions", f"Selected test: {nodeid}")
                self.window.results.tabs.setCurrentIndex(("Detail", "Source", "Output", "Logs").index(self.values["default_tab"]))

    def process_line(self, index, text):
        self.record("output", f"Reader {index}: {text}")
        prefix = "PYTESTRUNNER_START\t"
        if self.values["follow_test"] and text.strip().startswith(prefix):
            nodeid = text.strip()[len(prefix):]
            item = self.window.model.index_for_nodeid(nodeid)
            if item.isValid():
                self.window.tree.setCurrentIndex(item)
                self.window.tree.scrollTo(item)

    def reader_finished(self, report):
        self.record("commands", f"Reader {report.reader.index} finished • exit code {report.exit_code}")
        if report.exit_code not in (0, 5) or report.issues:
            self.record("errors", report.output)

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
        self._applied_font_key = None
        self.apply_font()
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
        if t.current_theme() != values["theme"]:
            self._applying_theme = True
            try:
                window.apply_theme(values["theme"])
            finally:
                self._applying_theme = False
        self.apply_font()
        for panel in (window.run_header.environment, window.run_header.execution, window.run_header.results):
            layout = panel.layout()
            margin, spacing = (8, 4) if values["compact_header"] else (12, 8)
            layout.setContentsMargins(margin, spacing, margin, spacing)
            layout.setSpacing(spacing)
        atr = window.run_header.atr_presentation
        if values["atr_bottom"]:
            if atr.parentWidget() != window.statusBar():
                window.reader_controls.layout().removeWidget(atr)
                window.statusBar().addPermanentWidget(atr, 1)
                atr.setMinimumWidth(400)
        elif atr.parentWidget() != window.reader_controls:
            window.statusBar().removeWidget(atr)
            window.reader_controls.layout().addWidget(atr, 1, 0, 1, 2)
            atr.setMinimumWidth(80)
        atr.show()
        height = {"Compact": 23, "Normal": 29, "Comfortable": 35}[values["tree_density"]]
        window.tree.setStyleSheet(f"QTreeView::item {{ min-height: {height}px; }}")
        self.console.scroll.setChecked(values["auto_scroll"])
        while len(self.console.events) > values["limit"]:
            self.console.events.popleft()
        self.console._dirty = True
        self.settings_panel.restyle()
        for name in ("settings_page", "console_page"):
            page = getattr(self, name, None)
            if page and page.detached_window:
                page.detached_window.setStyleSheet(window.styleSheet())

    def save(self):
        self.saved = dict(self.values)
        self.window.settings.setValue("preferences/personal", json.dumps(self.saved))
        self.window.settings.sync()
        self.settings_panel.notice.setText("Settings applied and saved for this user")
        self.record("actions", "Personal settings applied and saved")

    def shutdown(self):
        for page in (self.settings_page, self.console_page):
            page.reattach()
        self.active = False
        QApplication.instance().removeEventFilter(self)
        self.console.timer.stop()
        if sys.excepthook is self.exception_handler:
            sys.excepthook = self.previous_excepthook
