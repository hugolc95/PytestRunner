"""Run-page layout using the existing controls and their existing signals."""
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontMetrics

from runner.ui import tokens as t
from runner.ui import icons


class ResponsiveAtr(QWidget):
    """Keep the full ATR at normal size, or expose it through a detail button."""
    def __init__(self, field):
        super().__init__()
        self.field = field
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
        self.refresh_button.setObjectName("NavigationUtilityIcon")
        self.refresh_button.setFixedSize(t.CONTROL_SM, t.CONTROL_SM)
        self.refresh_button.setAccessibleName("Refresh ATR")
        self.refresh_button.setToolTip("Read the card again")
        self.refresh_button.clicked.connect(lambda: field.refresh())
        row.addWidget(self.refresh_button)
        field.textChanged.connect(lambda: QTimer.singleShot(0, self.update_presentation))
        self.restyle()

    def restyle(self):
        self.refresh_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def update_presentation(self):
        font = self.field.font()
        font.setPixelSize(t.TEXT_SM)
        needed = QFontMetrics(font).horizontalAdvance(self.field.text() or "ATR") + self.field._margin()
        self.stack.setCurrentIndex(0 if self.stack.width() >= needed else 1)

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

        # Reparent the actual controls; do not duplicate actions or state.
        window.workspace_combo.setMinimumWidth(180)
        window.workspace_combo.setMaximumWidth(16777215)
        self._move(environment, window.workspace_combo)
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
        environment.addLayout(workspace_actions)
        environment.addStretch()
        self._move(environment, window.run_name_stack)

        window.reader_controls.layout().setContentsMargins(0, 0, 0, 0)
        reader_layout = window.reader_controls.layout()
        while reader_layout.count():
            item = reader_layout.takeAt(0)
            if isinstance(item.widget(), QLabel):
                item.widget().hide()
        reader_layout.addWidget(window.reader_selector, 0, 0)
        reader_layout.addWidget(window.reader_config_button, 0, 1)
        self.atr_presentation = ResponsiveAtr(window.reader_atr)
        reader_layout.addWidget(self.atr_presentation, 0, 2)
        reader_layout.setColumnStretch(0, 2)
        reader_layout.setColumnStretch(2, 2)
        self._move(execution, window.reader_controls)
        window.readers_bar.set_integrated()
        self._move(execution, window.readers_bar)
        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        for control in (window.run_button, window.stop_button, window.rerun_button):
            self._move(actions, control)
        actions.addStretch()
        execution.addLayout(actions)
        self._move(execution, window.profile_chip)
        execution.addStretch()

        progress = QHBoxLayout()
        progress.setSpacing(t.SPACE_2)
        self._move(progress, window.compass_ring)
        self._move(progress, window.compass_pct)
        progress.addStretch()
        self._move(progress, window.view_failures_button)
        results.addLayout(progress)
        counters = QHBoxLayout()
        counters.setSpacing(t.SPACE_2)
        for pill in window.pills.values():
            self._move(counters, pill)
        results.addLayout(counters)
        results.addStretch()

        # Keep any legacy decoration owned, but never visible in the page.
        for old in (command_bar, run_bar):
            old.setParent(self)
            old.hide()
        self._arrange(False)

    @staticmethod
    def _panel(title):
        panel = QFrame()
        panel.setObjectName("Surface")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        layout.setSpacing(t.SPACE_2)
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
        self._grid.addWidget(self.environment, 0, 0)
        self._grid.addWidget(self.execution, 0, 1)
        if compact:
            self._grid.addWidget(self.results, 1, 0, 1, 2)
        else:
            self._grid.addWidget(self.results, 0, 2)
        for column in range(3):
            self._grid.setColumnStretch(column, 0 if compact and column == 2 else 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        required = sum(panel.minimumSizeHint().width() for panel in
                       (self.environment, self.execution, self.results))
        self._arrange(event.size().width() < required + 2 * self._grid.spacing())
