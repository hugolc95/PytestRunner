"""Compact primary-reader editor using the workspace's test interpreter."""
import json

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtWidgets import QComboBox

from runner.domain import reader_discovery


class ReaderSelector(QComboBox):
    committed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setAccessibleName("Primary reader")
        self.setMinimumWidth(200)
        self.setMaximumWidth(440)
        self.setMinimumContentsLength(38)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.lineEdit().setPlaceholderText("Select or enter a reader…")
        self.activated.connect(lambda *_: self._commit())
        self.lineEdit().editingFinished.connect(self._commit)
        self._context = None
        self._value = ""
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._timed_out)
        self._expired = False

    def set_context(self, workspace, interpreter, value, known=()):
        context = (workspace, interpreter, value, tuple(known))
        if context == self._context:
            return
        self.stop_discovery()
        self._context = context
        self._value = value
        self.setCurrentText(value)
        self._set_names(known)
        if workspace and interpreter:
            QTimer.singleShot(0, self.discover)

    def _set_names(self, names):
        current = self.currentText() if self.hasFocus() or self.lineEdit().hasFocus() else self._value
        self.blockSignals(True)
        self.clear()
        self.addItems(list(dict.fromkeys([current, self._value, *names])))
        self.setCurrentText(current)
        self.blockSignals(False)

    def _commit(self):
        value = self.currentText().strip()
        if self.isEnabled() and value != self._value:
            self.committed.emit(value)

    def showPopup(self):
        # Long device names can use more space in the open list than in the header.
        width = max((self.fontMetrics().horizontalAdvance(self.itemText(i))
                     for i in range(self.count())), default=0) + 48
        self.view().setMinimumWidth(min(max(self.width(), width),
                                       self.screen().availableGeometry().width()))
        super().showPopup()

    def discover(self):
        if not self._context or self._process.state() != QProcess.NotRunning:
            return
        workspace, interpreter, *_ = self._context
        if not workspace or not interpreter:
            return
        env = QProcessEnvironment()
        for key, value in reader_discovery.discovery_environment().items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(workspace)
        self._expired = False
        self.setToolTip("Looking for HubReader devices… Manual entry remains available.")
        self._process.start(interpreter, ["-u", "-c", reader_discovery.PROBE])
        self._timeout.start(10000)

    def _finished(self, code, *_):
        self._timeout.stop()
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        errors = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        if self._expired:
            return
        try:
            line = next(line for line in output.splitlines() if line.startswith("HUBREADERS_JSON:"))
            names = json.loads(line.split(":", 1)[1])
            if code or not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise ValueError()
        except (StopIteration, ValueError):
            message = errors.strip().splitlines()[-1] if errors.strip() else "No valid response from HubReader."
            self.setToolTip(message + " Manual entry remains available.")
            return
        names = tuple(dict.fromkeys(name.strip() for name in names if name.strip()))
        self._set_names(names)
        self.setToolTip(f"{len(names)} available HubReader devices. Select or enter the primary reader.")

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self.setToolTip("Could not start the test Python interpreter. Manual entry remains available.")

    def _timed_out(self):
        self._expired = True
        self._process.kill()
        self.setToolTip("HubReader discovery timed out. Manual entry remains available.")

    def stop_discovery(self):
        self._timeout.stop()
        self._expired = True
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)
