"""Run-page layout using the existing controls and their existing signals."""
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QPushButton, QPlainTextEdit, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QSize, Qt, QTimer

from runner.ui import tokens as t
from runner.ui import icons


class ResponsiveAtr(QWidget):
    """Keep the ATR visible inline with compact, adaptive text."""
    def __init__(self, field):
        super().__init__()
        self.field = field
        field.maximum_text_size = 10
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(0)
        self.stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        field._refresh_action.setVisible(False)
        self.stack.addWidget(field)
        self.button = QPushButton("ATR…")
        self.button.setToolTip("Show the full card ATR and diagnostic details")
        self.button.clicked.connect(self.open_details)
        self.stack.addWidget(self.button)
        row.addWidget(self.stack, 1)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("AtrRefresh")
        self.refresh_button.setFixedSize(t.CONTROL_SM, t.CONTROL_SM)
        self.refresh_button.setIconSize(QSize(16, 16))
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.setAccessibleName("Refresh ATR")
        self.refresh_button.setToolTip("Read the card again")
        self.refresh_button.clicked.connect(lambda: field.refresh())
        row.addWidget(self.refresh_button)
        field.textChanged.connect(lambda: QTimer.singleShot(0, self.update_presentation))
        self.restyle()

    def restyle(self):
        self.refresh_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def set_bottom_bar(self, enabled):
        self.field.setProperty("bottomBar", enabled)
        self.field.bottom_bar = enabled
        self.field.maximum_text_size = t.TEXT_SM if enabled else 10
        self.refresh_button.setProperty("bottomBar", enabled)
        row = self.layout()
        row.removeWidget(self.refresh_button)
        if enabled:
            row.insertWidget(0, self.refresh_button)
        else:
            row.addWidget(self.refresh_button)
        row.setSpacing(6 if enabled else 2)
        height = 20 if enabled else t.CONTROL_SM
        self.refresh_button.setFixedSize(height, height)
        icon_size = 14 if enabled else 16
        self.refresh_button.setIconSize(QSize(icon_size, icon_size))
        self.setMaximumHeight(20 if enabled else 16777215)
        self.stack.setMaximumHeight(20 if enabled else 16777215)
        self.field.style().unpolish(self.field)
        self.field.style().polish(self.field)
        self.refresh_button.style().unpolish(self.refresh_button)
        self.refresh_button.style().polish(self.refresh_button)
        self.field._fit()

    def update_presentation(self):
        # Never replace the ATR with an extra button, even in narrow windows.
        # The read-only field supports selection/copy and horizontal scrolling.
        self.stack.setCurrentIndex(0)
        self.field._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_presentation()

    def open_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Card ATR")
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        def sync():
            text = self.field.text() + "\n\n" + self.field.toolTip()
            if details.toPlainText() != text:
                details.setPlainText(text)
        sync()
        layout.addWidget(details)
        buttons = QHBoxLayout()
        copy = QPushButton("Copy ATR")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.field.text()))
        buttons.addWidget(copy)
        close = QPushButton("Close")
        close.clicked.connect(dialog.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.resize(520, 230)
        from PySide6.QtCore import Qt
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        timer = QTimer(dialog)
        timer.timeout.connect(sync)
        timer.start(500)
        dialog.show()


class StructuredRunHeader(QWidget):
    def __init__(self, window, command_bar, run_bar):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(t.SPACE_3)
        self._compact = None

        self.environment, environment = self._panel("ENVIRONMENT")
        self.execution, execution = self._panel("EXECUTION")
        self.results, results = self._panel("RESULTS")
        environment_fields = QGridLayout()
        environment_fields.setContentsMargins(0, 0, 0, 0)
        environment_fields.setHorizontalSpacing(t.SPACE_3)
        environment_fields.setVerticalSpacing(t.SPACE_1)
        workspace_column = QVBoxLayout()
        workspace_column.setSpacing(t.SPACE_1)
        workspace_column.setAlignment(Qt.AlignTop)
        self.reader_fields = QWidget()
        reader_column = QVBoxLayout(self.reader_fields)
        reader_column.setContentsMargins(0, 0, 0, 0)
        reader_column.setSpacing(t.SPACE_2)
        reader_column.setAlignment(Qt.AlignTop)
        environment_fields.addLayout(workspace_column, 0, 0, Qt.AlignTop)
        self.environment_fields = environment_fields
        self._window = window
        environment_fields.setColumnStretch(0, 1)
        environment.addLayout(environment_fields)

        # Reparent the actual controls; do not duplicate actions or state.
        window.workspace_combo.setMinimumWidth(180)
        window.workspace_combo.setMaximumWidth(16777215)
        self._move(workspace_column, window.workspace_combo)
        for button, text in ((window.browse_button, "Browse…"),
                             (window.load_button, "Collect")):
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setText(text)
        workspace_actions = QHBoxLayout()
        workspace_actions.setSpacing(t.SPACE_2)
        for control in (window.browse_button, window.load_button,
                        window.config_button, window.history_button):
            self._move(workspace_actions, control)
        workspace_actions.addStretch()
        window.run_name_stack.setMinimumWidth(90)
        window.run_name_stack.setMaximumWidth(260)
        window.run_name_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._move(workspace_actions, window.run_name_stack)
        workspace_column.addLayout(workspace_actions)

        window.reader_controls.layout().setContentsMargins(0, 0, 0, 0)
        reader_layout = window.reader_controls.layout()
        reader_layout.setSizeConstraint(QLayout.SetMinimumSize)
        while reader_layout.count():
            item = reader_layout.takeAt(0)
            if isinstance(item.widget(), QLabel):
                item.widget().hide()
        reader_layout.addWidget(window.reader_selector, 0, 1)
        window.reader_selector.setMinimumContentsLength(16)
        window.reader_selector.setMaximumWidth(16777215)
        window.reader_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.atr_presentation = ResponsiveAtr(window.reader_atr)
        # A full-width compact line keeps long ATRs readable without squeezing
        # the reader name or falling back to the ATR details button.
        reader_layout.addWidget(self.atr_presentation, 1, 1)
        reader_layout.setColumnStretch(0, 0)
        reader_layout.setColumnStretch(1, 2)
        reader_layout.setColumnStretch(2, 0)
        execution_fields = QHBoxLayout()
        execution_fields.setContentsMargins(0, 0, 0, 0)
        execution_fields.setSpacing(t.SPACE_2)
        execution_fields.setAlignment(Qt.AlignTop)
        window.readers_bar.set_integrated()
        self._move(reader_column, window.readers_bar)
        reader_layout.addWidget(self.reader_fields, 2, 1)
        reader_layout.setVerticalSpacing(t.SPACE_1)
        # Launch controls form the left column; inspection and selection share
        # the right column in selector / ATR / run-readers order.
        command_fields = QWidget()
        command_fields.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        commands = QVBoxLayout(command_fields)
        commands.setContentsMargins(0, 0, 0, 0)
        commands.setSpacing(t.SPACE_2)
        commands.setAlignment(Qt.AlignTop)
        window.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        window.pause_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._move(commands, window.launch_stack)
        secondary = QHBoxLayout()
        secondary.setSpacing(t.SPACE_1)
        for control in (window.stop_button, window.rerun_button):
            self._move(secondary, control)
        commands.addLayout(secondary)
        self._move(commands, window.profile_chip)
        commands.addStretch()
        execution_fields.addWidget(command_fields, 0, Qt.AlignTop)
        self._move(execution_fields, window.reader_controls)
        execution_fields.setStretch(1, 1)
        execution_fields.addStretch(0)
        self.commands = commands
        self.execution_fields = execution_fields
        self.execution_heading = QHBoxLayout()
        heading = execution.takeAt(0).widget()
        self.execution_heading.addWidget(heading)
        self.execution_heading.addStretch()
        execution.insertLayout(0, self.execution_heading)
        self.run_config_button = window.reader_config_button
        self.run_config_button.setToolTip("Open this run’s independent YAML configuration")
        self._reader_mode = None
        execution.addLayout(execution_fields)
        execution.addStretch()

        progress = QHBoxLayout()
        progress.setSpacing(t.SPACE_2)
        # Share the heading row with the ring instead of reserving a separate
        # line above it. Result actions stay together on the left.
        result_heading = results.takeAt(0).widget()
        result_actions = QVBoxLayout()
        result_actions.setSpacing(t.SPACE_1)
        result_actions.addWidget(result_heading, 0, Qt.AlignTop)
        result_buttons = QHBoxLayout()
        result_buttons.setSpacing(t.SPACE_2)
        self._move(result_buttons, window.view_failures_button)
        self._move(result_buttons, window.view_differences_button)
        result_buttons.addStretch()
        result_actions.addLayout(result_buttons)
        result_actions.addStretch()
        progress.addLayout(result_actions, 1)
        self._move(progress, window.compass_pct)
        self._move(progress, window.compass_ring)
        progress.setAlignment(window.compass_ring, Qt.AlignRight | Qt.AlignTop)
        results.addLayout(progress)
        counters = QHBoxLayout()
        counters.setSpacing(t.SPACE_2)
        self._result_pills = tuple(window.pills.values())
        for pill in window.pills.values():
            self._move(counters, pill)
        results.addLayout(counters)
        results.addStretch()

        # Keep any legacy decoration owned, but never visible in the page.
        for old in (command_bar, run_bar):
            old.setParent(self)
            old.hide()
        self._arrange(False)
        self.update_environment()

    def update_environment(self):
        visible = not self._window.readers_bar.isHidden()
        self.reader_fields.setVisible(visible)
        reader_mode = not self._window.reader_controls.isHidden()
        if reader_mode != self._reader_mode:
            self._reader_mode = reader_mode
            self.commands.setDirection(QBoxLayout.TopToBottom if reader_mode else QBoxLayout.LeftToRight)
            self.execution_fields.removeWidget(self.run_config_button)
            self._window.reader_controls.layout().removeWidget(self.run_config_button)
            self.execution_fields.setStretch(2, 0 if reader_mode else 1)
            if reader_mode:
                self._window.reader_controls.layout().addWidget(self.run_config_button, 0, 0)
            else:
                self.execution_fields.addWidget(self.run_config_button)
            self.run_config_button.show()

    @staticmethod
    def _panel(title):
        panel = QFrame()
        panel.setObjectName("Surface")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        layout.setSpacing(t.SPACE_1)
        layout.setAlignment(Qt.AlignTop)
        heading = QLabel(title)
        heading.setObjectName("Faint")
        layout.addWidget(heading)
        return panel, layout

    @staticmethod
    def _move(layout, widget):
        explicitly_hidden = widget.isHidden()
        layout.addWidget(widget)
        widget.setVisible(not explicitly_hidden)

    def _arrange(self, compact):
        if compact == self._compact:
            return
        self._compact = compact
        for panel in (self.environment, self.execution, self.results):
            self._grid.removeWidget(panel)
        if compact == "stacked":
            for row, panel in enumerate((self.environment, self.execution, self.results)):
                self._grid.addWidget(panel, row, 0)
            for column in range(3):
                self._grid.setColumnStretch(column, 1 if column == 0 else 0)
            return
        self._grid.addWidget(self.environment, 0, 0)
        self._grid.addWidget(self.execution, 0, 1)
        if compact:
            self._grid.addWidget(self.results, 1, 0, 1, 2)
        else:
            self._grid.addWidget(self.results, 0, 2)
        for column in range(3):
            self._grid.setColumnStretch(column, 0 if compact and column == 2 else
                                        5 if column == 1 else 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        counter_width = sum(max(72, pill.fontMetrics().horizontalAdvance(pill._status.label.upper()) + 45)
                            for pill in self._result_pills)
        self.results.setMinimumWidth(counter_width + 2 * t.SPACE_3 + 3 * t.SPACE_2)
        required = sum(max(panel.minimumWidth(), panel.minimumSizeHint().width()) for panel in
                       (self.environment, self.execution, self.results))
        pair_width = sum(max(panel.minimumWidth(), panel.minimumSizeHint().width())
                         for panel in (self.environment, self.execution))
        width = event.size().width()
        self._arrange("stacked" if width < pair_width + self._grid.spacing() else
                      width < required + 2 * self._grid.spacing())
