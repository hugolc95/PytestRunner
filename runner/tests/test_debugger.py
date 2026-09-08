"""Real DAP/pytest round trip; debugpy is optional for regular GUI installs."""
import sys

import pytest
from PySide6.QtCore import QProcess

from runner.domain.models import Reader, RunRequest
from runner.ui.debug_dialog import DebugDialog
from runner.ui.source_panel import SourcePanel


def test_breakpoints_follow_the_source_file(qapp, tmp_path):
    first = tmp_path / 'test_a.py'
    second = tmp_path / 'test_b.py'
    first.write_text('def test_a():\n    assert True\n')
    second.write_text('def test_b():\n    assert True\n')
    panel = SourcePanel()
    panel.show_file(first, 'test_a.py::test_a')
    panel.editor.toggle_breakpoint(2)
    panel.show_file(second, 'test_b.py::test_b')
    assert panel.editor.breakpoints == set()
    panel.show_file(first, 'test_a.py::test_a')
    assert panel.editor.breakpoints == {2}
    assert panel.debug_button.isEnabled()
    panel.clear()
    assert not panel.debug_button.isEnabled()


def test_real_breakpoint_step_variables_and_finish(qtbot, tmp_path):
    pytest.importorskip('debugpy')
    source = tmp_path / 'test_debug_sample.py'
    source.write_text('def test_sample():\n    number = 40\n    number += 2\n    assert number == 42\n')
    request = RunRequest(str(tmp_path), sys.executable,
                         ('test_debug_sample.py::test_sample',), ())
    dialog = DebugDialog(request, Reader('', 0), {}, {str(source): {3}})
    qtbot.addWidget(dialog)
    dialog.start()
    try:
        qtbot.waitUntil(lambda: dialog.editor.execution_line == 3, timeout=30000)
        qtbot.waitUntil(lambda: dialog.variables.topLevelItemCount() > 0)
        values = {dialog.variables.topLevelItem(i).text(0): dialog.variables.topLevelItem(i).text(1)
                  for i in range(dialog.variables.topLevelItemCount())}
        assert values['number'] == '40'
        dialog.resume('next')
        qtbot.waitUntil(lambda: dialog.editor.execution_line == 4, timeout=10000)
        dialog.resume('continue')
        qtbot.waitUntil(lambda: dialog.finished, timeout=10000)
        assert '1 passed' in dialog.output.toPlainText()
    finally:
        dialog.close()


def test_escape_terminates_paused_session(qtbot, tmp_path):
    pytest.importorskip('debugpy')
    source = tmp_path / 'test_stop.py'
    source.write_text('def test_stop():\n    assert True\n')
    dialog = DebugDialog(RunRequest(str(tmp_path), sys.executable,
        ('test_stop.py::test_stop',), ()), Reader('', 0), {}, {str(source): {2}})
    qtbot.addWidget(dialog)
    dialog.start()
    try:
        qtbot.waitUntil(lambda: dialog.editor.execution_line == 2, timeout=30000)
        dialog.reject()
        assert dialog.process.state() == QProcess.NotRunning
        assert dialog.finished
    finally:
        dialog.close()
