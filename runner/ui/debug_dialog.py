"""Single-test DAP client. The adapter and pytest use the test interpreter."""
from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from runner.domain.execution import ReaderRun
from runner.domain.reader_isolation import reader_plugin
from runner.ui.code_editor import CodeEditor


class DebugDialog(QDialog):
    def __init__(self, request, reader, env, breakpoints, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Debug — ' + request.nodeids[0])
        self.resize(1100, 750)
        self.request = request
        self.reader = reader
        self.env = env
        self.breakpoints = {str(Path(p).resolve()): set(lines) for p, lines in breakpoints.items()}
        self.path = ''
        self.thread_id = None
        self.buffer = bytearray()
        self.seq = 0
        self.pending = {}
        self.resources = ExitStack()
        self.configured = False
        self.finished = False
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.start_button = QPushButton('Start debug')
        self.start_button.clicked.connect(self.start)
        bar.addWidget(self.start_button)
        self.actions = []
        for label, command in [('Continue', 'continue'), ('Step over', 'next'),
                               ('Step into', 'stepIn'), ('Step out', 'stepOut')]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, c=command: self.resume(c))
            button.setEnabled(False)
            self.actions.append(button)
            bar.addWidget(button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        bar.addWidget(self.stop_button)
        layout.addLayout(bar)
        self.status = QLabel('Click the line margin to set breakpoints, then Start debug.')
        layout.addWidget(self.status)
        split = QSplitter()
        self.editor = CodeEditor()
        self.editor.breakpoints_changed.connect(self.update_breakpoints)
        split.addWidget(self.editor)
        self.variables = QTreeWidget()
        self.variables.setHeaderLabels(['Variable', 'Value'])
        split.addWidget(self.variables)
        split.setStretchFactor(0, 3)
        layout.addWidget(split, 3)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(5000)
        layout.addWidget(self.output, 1)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_messages)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.started.connect(self.initialize)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(30000)
        self.timeout.timeout.connect(self.startup_timeout)
        self.show_source(str(Path(request.workspace) / request.nodeids[0].split('::')[0]))

    def show_source(self, path, line=0):
        path = str(Path(path).resolve())
        try:
            import tokenize
            with tokenize.open(path) as source:
                content = source.read()
        except (OSError, UnicodeError, SyntaxError) as exc:
            self.status.setText(f'Could not read {path}: {exc}')
            return
        self.path = path
        self.editor.set_execution_line(0)
        self.editor.setPlainText(content)
        self.editor.breakpoints = set(self.breakpoints.get(path, ()))
        self.editor.set_execution_line(line)
        self.editor._gutter.update()

    def start(self):
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText('Starting debugger…')
        self.process.setWorkingDirectory(self.request.workspace)
        self.process.start(self.request.interpreter, ['-u', '-m', 'debugpy.adapter'])
        self.timeout.start()

    def send(self, command, arguments=None, callback=None):
        self.seq += 1
        message = {'seq': self.seq, 'type': 'request', 'command': command,
                   'arguments': arguments or {}}
        self.pending[self.seq] = callback
        data = json.dumps(message).encode('utf-8')
        self.process.write(f'Content-Length: {len(data)}\r\n\r\n'.encode() + data)

    def initialize(self):
        self.send('initialize', {'clientID': 'pytest-runner', 'adapterID': 'python',
            'pathFormat': 'path', 'linesStartAt1': True, 'columnsStartAt1': True,
            'supportsRunInTerminalRequest': False}, self.launch)

    def launch(self, body):
        args, folder = self.resources.enter_context(reader_plugin(self.request.config_path))
        env = ReaderRun(self.request, self.reader, self.env)._environnement(folder)
        self.send('launch', {'name': 'Pytest Runner', 'type': 'python', 'request': 'launch',
            'python': [self.request.interpreter], 'module': 'pytest',
            'args': ['-o', 'addopts=', '-s', '-v', *args, *self.request.nodeids],
            'cwd': self.request.workspace, 'env': {**env, 'PYTEST_ADDOPTS': ''},
            'console': 'internalConsole', 'redirectOutput': True,
            'justMyCode': True, 'subProcess': False})

    def read_messages(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b'\r\n\r\n' in self.buffer:
            header, rest = self.buffer.split(b'\r\n\r\n', 1)
            length = next(int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                          if line.lower().startswith(b'content-length:'))
            if len(rest) < length:
                return
            self.buffer = bytearray(rest[length:])
            self.handle(json.loads(rest[:length]))

    def handle(self, message):
        body = message.get('body', {})
        if message['type'] == 'response':
            callback = self.pending.pop(message['request_seq'], None)
            if not message.get('success', False):
                self.status.setText(message.get('message', 'Debugger request failed'))
                self.output.appendPlainText(self.status.text())
                if message.get('command') in ('initialize', 'launch', 'configurationDone'):
                    self.stop()
            elif callback:
                callback(body)
        elif message['type'] == 'event':
            event = message['event']
            if event == 'initialized':
                self.configured = True
                paths = list(self.breakpoints)
                def configure_next(_=None):
                    if paths:
                        self.send_breakpoints(paths.pop(), configure_next)
                    else:
                        self.send('configurationDone', callback=self.running)
                configure_next()
            elif event == 'stopped':
                self.timeout.stop()
                self.thread_id = body.get('threadId')
                self.status.setText('Paused — ' + body.get('reason', 'breakpoint'))
                for button in self.actions:
                    button.setEnabled(True)
                self.send('stackTrace', {'threadId': self.thread_id}, self.stack_received)
            elif event == 'continued':
                self.running({})
            elif event == 'output':
                self.output.moveCursor(QTextCursor.End)
                self.output.insertPlainText(body.get('output', ''))
            elif event == 'exited':
                self.status.setText(f"Test process exited (code {body.get('exitCode')})")
            elif event == 'terminated':
                self.stop()

    def send_breakpoints(self, path, callback=None):
        self.send('setBreakpoints', {'source': {'path': path}, 'breakpoints':
            [{'line': line} for line in sorted(self.breakpoints.get(path, ()))]},
            lambda body: self.breakpoints_received(body, callback))

    def breakpoints_received(self, body, callback):
        for point in body.get('breakpoints', []):
            if not point.get('verified'):
                self.output.appendPlainText('Unverified breakpoint: ' + point.get('message', str(point.get('line', ''))))
        if callback:
            callback(body)

    def update_breakpoints(self):
        self.breakpoints[self.path] = set(self.editor.breakpoints)
        if self.configured and not self.finished:
            self.send_breakpoints(self.path)

    def stack_received(self, body):
        frames = body.get('stackFrames', [])
        if not frames or self.thread_id is None:
            return
        frame = frames[0]
        path = frame.get('source', {}).get('path')
        if path:
            self.show_source(path, frame['line'])
        self.send('scopes', {'frameId': frame['id']}, self.scopes_received)

    def scopes_received(self, body):
        self.variables.clear()
        if self.thread_id is None:
            return
        for scope in body.get('scopes', []):
            if not scope.get('expensive'):
                self.send('variables', {'variablesReference': scope['variablesReference']}, self.variables_received)

    def variables_received(self, body):
        if self.thread_id is not None:
            for value in body.get('variables', []):
                self.variables.addTopLevelItem(QTreeWidgetItem([value['name'], value.get('value', '')]))

    def running(self, body):
        self.timeout.stop()
        self.thread_id = None
        self.status.setText('Running…')
        self.editor.set_execution_line(0)
        self.variables.clear()
        for button in self.actions:
            button.setEnabled(False)

    def resume(self, command):
        if self.thread_id is not None:
            self.send(command, {'threadId': self.thread_id})
            self.running({})

    def read_errors(self):
        text = bytes(self.process.readAllStandardError()).decode('utf-8', 'replace')
        self.output.appendPlainText(text)
        if 'No module named debugpy' in text:
            self.status.setText('Install debugpy in the configured test Python: python -m pip install debugpy')

    def process_error(self, error):
        self.status.setText(self.process.errorString())
        if error == QProcess.FailedToStart:
            self.on_finished()

    def startup_timeout(self):
        self.status.setText('Debugger startup timed out.')
        self.stop()

    def stop(self):
        self.timeout.stop()
        if self.process.state() != QProcess.NotRunning:
            if self.status.text().startswith(('Running', 'Paused', 'Starting')):
                self.status.setText('Stopping debugger…')
            self.send('disconnect', {'terminateDebuggee': True})
            QTimer.singleShot(3000, self.process.kill)
        self.thread_id = None
        self.editor.set_execution_line(0)
        for button in self.actions:
            button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def on_finished(self, *args):
        self.timeout.stop()
        self.finished = True
        self.configured = False
        self.thread_id = None
        for button in self.actions:
            button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.editor.set_execution_line(0)
        if self.status.text().startswith(('Stopping', 'Running', 'Starting', 'Paused')):
            self.status.setText('Debug session ended.')
        self.resources.close()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def done(self, result):
        # Escape and QDialog.reject() bypass closeEvent.
        self.shutdown()
        super().done(result)

    def shutdown(self):
        self.stop()
        if self.process.state() != QProcess.NotRunning:
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(1000)
        self.resources.close()
