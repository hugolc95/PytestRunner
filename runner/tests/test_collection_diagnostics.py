"""The failed pytest collection reaches both the error dialog and Console."""
import subprocess
import sys
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QPushButton

from runner.domain import diagnostics, execution, history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.services.run_service import CollectWorker
from runner.ui.main_window import MainWindow
from runner.ui.widgets import ErrorDialog


def test_collection_keeps_all_tracebacks_locations_and_process_context(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --tb=no\n")
    helper = tmp_path / "card_dependency.py"
    helper.write_text("def initialize():\n    raise RuntimeError('card initialization failed')\n")
    (tmp_path / "test_import.py").write_text("from card_dependency import initialize\ninitialize()\n")
    (tmp_path / "test_syntax.py").write_text("def test_broken(:\n    pass\n")
    # Pas de fichier sain ici : avec un test valide, la collecte devient
    # partielle (voir test_partial_collection_durations.py).
    with pytest.raises(diagnostics.CollectionError) as raised:
        execution.collect(str(tmp_path), sys.executable)
    error = raised.value
    assert len(error.reports) == 2
    assert error.exit_code == 2
    assert "card_dependency.py:2" in error.details
    assert "card initialization failed" in error.details
    assert "test_syntax.py:1" in error.details
    assert "def test_broken(:" in error.details
    assert "raise RuntimeError" in error.details
    assert "Traceback:" in error.details
    assert "SyntaxError" in error.details
    syntax = next(item for item in error.reports if "SyntaxError" in item["message"])
    assert diagnostics.diagnostic_location(syntax).endswith("test_syntax.py:1")
    assert "2 collection errors" in error.headline
    assert str(tmp_path) in error.details and sys.executable in error.details
    assert "--collect-only" in error.details
    assert error.stdout and "test_syntax.py" in error.stdout


def test_conftest_bootstrap_keeps_import_trace_and_source_line(tmp_path):
    (tmp_path / "conftest.py").write_text("import absent_collection_framework_xyz\n")
    with pytest.raises(diagnostics.CollectionError) as raised:
        execution.collect(str(tmp_path), sys.executable)
    error = raised.value
    assert "ModuleNotFoundError" in error.details
    assert "conftest.py:1" in error.details
    assert "import absent_collection_framework_xyz" in error.details
    assert error.stderr


def test_timeout_keeps_partial_output_and_python_trace(tmp_path, monkeypatch):
    def expire(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"],
                                        output="Connecting to card…".encode(),
                                        stderr=b"Importing conftest.py\n")
    monkeypatch.setattr(execution.subprocess, "run", expire)
    with pytest.raises(diagnostics.CollectionError) as raised:
        execution.collect(str(tmp_path), sys.executable, timeout=3)
    error = raised.value
    assert "timed out after 3s" in error.details
    assert "Connecting to card…" in error.details
    assert "Importing conftest.py" in error.details
    assert "Traceback (most recent call last)" in error.details
    assert error.exit_code is None


def test_worker_preserves_unexpected_failure_trace_and_legacy_message(qapp, tmp_path, monkeypatch):
    def broken_probe(*args, **kwargs):
        raise ValueError("diagnostic probe could not be prepared")
    monkeypatch.setattr(execution, "collect", broken_probe)
    worker = CollectWorker(str(tmp_path), sys.executable, {})
    failures, messages = [], []
    worker.diagnostic_failed.connect(failures.append)
    worker.failed.connect(messages.append)
    worker.run()
    assert len(failures) == 1 and len(messages) == 1
    assert isinstance(failures[0], diagnostics.CollectionError)
    assert "broken_probe" in failures[0].details
    assert "ValueError: diagnostic probe could not be prepared" in failures[0].details
    assert "Traceback (most recent call last)" in failures[0].details
    assert "ValueError" in messages[0]


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()


def test_real_collection_error_is_visible_in_popup_and_error_console(window, qtbot, tmp_path, monkeypatch):
    (tmp_path / "test_card.py").write_text("import missing_card_diagnostic_xyz\n")
    console = window.preferences.console
    console.pause.setChecked(True)
    console.search.setText("old search")
    console.kind.setCurrentIndex(console.kind.findData("commands"))
    snapshots = []
    def inspect(dialog):
        snapshots.append(dialog.detail_view.toPlainText())
        assert not dialog.detail_view.isHidden()
        button = next(button for button in dialog.findChildren(QPushButton)
                      if button.text() == "Show console")
        button.click()
        return 0
    monkeypatch.setattr(ErrorDialog, "exec", inspect)
    window.workspace_combo.setCurrentText(str(tmp_path))
    window.load_workspace()
    qtbot.waitUntil(lambda: bool(snapshots), timeout=15000)
    qtbot.waitUntil(lambda: not window._collector.isRunning())
    assert len(snapshots) == 1
    assert "test_card.py:1" in snapshots[0]
    assert "import missing_card_diagnostic_xyz" in snapshots[0]
    assert "ModuleNotFoundError" in snapshots[0]
    assert window.pages.currentWidget() is window.console_page
    assert console.kind.currentData() == "errors" and not console.paused
    assert console.search.text() == ""
    assert "missing_card_diagnostic_xyz" in console.text.toPlainText()
    assert "Traceback:" in console.text.toPlainText()
    assert window.load_button.isEnabled() and not window.progress.isVisible()
    assert len([event for event in console.events if event[1] == "errors"
                and "Collection failed" in event[2]]) == 1
    assert any(kind == "output" and "ModuleNotFoundError" in text
               for _, kind, text in console.events)


def test_draft_collection_error_reaches_shared_console_with_run_context(window, monkeypatch, tmp_path):
    draft = window.run_tabs.new_run()
    draft._pending_run_name = "Card configuration B"
    error = diagnostics.CollectionError("ImportError: framework missing", workspace=str(tmp_path),
                                        interpreter=sys.executable,
                                        stderr="conftest.py:4\nImportError: framework missing")
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics", lambda *args, **kwargs: popups.append((args, kwargs)))
    draft._on_collect_failed(error)
    assert len(popups) == 1
    assert "framework missing" in popups[0][0][2]
    window.preferences.console.refresh()
    assert "framework missing" in window.preferences.console.text.toPlainText()
    assert "[Card configuration B]" in window.preferences.console.text.toPlainText()


def test_popup_headline_has_useful_location_and_cause(qtbot, monkeypatch):
    seen = []
    def inspect(dialog):
        from PySide6.QtWidgets import QLabel
        seen.append([label.text() for label in dialog.findChildren(QLabel)])
    monkeypatch.setattr(ErrorDialog, "exec", inspect)
    ErrorDialog.show_diagnostics(None, "Collection failed", "Full traceback body",
                                 summary="test_card.py:12\nImportError: card framework")
    assert "test_card.py:12\nImportError: card framework" in seen[0]


def test_process_error_with_empty_output_still_has_useful_console_details(window):
    from runner.domain.models import Reader, ReaderReport
    report = ReaderReport(Reader("Card reader", 0), exit_code=3,
                          issues=["ImportError: test framework was not loaded"])
    window.preferences.reader_finished(report)
    window.preferences.show_errors()
    assert "ImportError: test framework was not loaded" in window.preferences.console.text.toPlainText()
