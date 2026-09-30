"""Compact primary-reader editor using the workspace's test interpreter."""
import json

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QLineEdit

from runner.domain import reader_discovery
from runner.ui import icons
from runner.ui import tokens as t


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


class ReaderAtrField(QLineEdit):
    """ATR de la carte presente dans le lecteur principal, sous son selecteur.

    Lu par PROBE_ATR dans l'interpreteur des tests, comme la liste des
    lecteurs : jamais dans le processus de l'interface, qui n'a pas forcement
    la meme architecture que les DLL du lecteur. Jamais pendant un run non
    plus -- les tests ont besoin du lecteur -- mais aussitot apres, puisqu'une
    carte a pu changer entre-temps.
    """

    NO_CARD = "No card in reader"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReaderAtr")
        self.setReadOnly(True)
        self.setAccessibleName("Card ATR")
        self.setPlaceholderText("ATR")
        self._refresh_action = self.addAction(
            icons.icon("mdi.refresh", t.TEXT_MUTED), QLineEdit.TrailingPosition)
        self._refresh_action.setToolTip("Read the card again")
        self._refresh_action.triggered.connect(self.refresh)
        self._context = None
        self._busy = False
        self._stale = False
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._timed_out)
        self._expired = False
        self.state = ""

    def restyle(self):
        # Appele par le balayage de `MainWindow._restyle()` a chaque bascule :
        # l'icone est teintee une fois pour toutes a sa creation.
        self._refresh_action.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def set_context(self, workspace, interpreter, reader, busy=False):
        context = (workspace, interpreter, (reader or "").strip())
        was_busy, self._busy = self._busy, busy
        if busy:
            self.stop()
            self._stale = True
            return
        if context != self._context:
            self._context = context
            self.refresh()
        elif was_busy or self._stale:
            self.refresh()

    def refresh(self):
        self._stale = False
        if not self._context or self._busy:
            return
        workspace, interpreter, reader = self._context
        if not reader:
            self._show("", "", "No reader selected.")
            return
        if not workspace or not interpreter:
            return
        self.stop()
        env = QProcessEnvironment()
        for key, value in reader_discovery.discovery_environment().items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(workspace)
        self._expired = False
        self._show("reading", "Reading card…", f"Reading the card in {reader}…")
        self._process.start(interpreter, ["-u", "-c", reader_discovery.PROBE_ATR, reader])
        self._timeout.start(10000)

    def stop(self):
        self._timeout.stop()
        self._expired = True
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)

    def _finished(self, *_):
        self._timeout.stop()
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        errors = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        if self._expired:
            return
        state, atr, detail = reader_discovery.parse_atr_output(output, errors)
        if state == reader_discovery.ATR_OK:
            self._show(state, atr, f"ATR of the card in {self._context[2]}:\n{atr}")
        elif state == reader_discovery.ATR_NO_CARD:
            self._show(state, self.NO_CARD, detail or "No card could be read in this reader.")
        else:
            self._show(state, "ATR unavailable", detail)

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable",
                       "Could not start the test Python interpreter.")

    def _timed_out(self):
        self._expired = True
        self._process.kill()
        self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable", "Reading the ATR timed out.")

    def _show(self, state, text, tooltip):
        self.state = state
        self.setText(text)
        self.setCursorPosition(0)
        self.setToolTip(tooltip)
        # L'etat pilote la couleur depuis la feuille de style : elle suit ainsi
        # la bascule de theme sans rien repeindre a la main.
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
