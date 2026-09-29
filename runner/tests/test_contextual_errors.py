"""Real pytest subprocesses verify error ownership, including bootstrap failures."""
import os
import sys

import pytest

from runner.domain import diagnostics
from runner.domain.execution import ReaderRun, collect
from runner.domain.failures import failure_for, index_failures
from runner.domain.models import Reader, ReaderReport, RunRequest, Status


def run_suite(root, nodeids):
    request = RunRequest(str(root), sys.executable, tuple(nodeids), (Reader("", 0),))
    outcomes, lines = [], []
    report = ReaderRun(request, request.readers[0], dict(os.environ)).run(lines.append, outcomes.append)
    return report, outcomes, lines


def test_collection_only_shows_errors_from_all_files(tmp_path):
    (tmp_path / "test_a.py").write_text("import missing_component_a\n")
    (tmp_path / "test_b.py").write_text("raise ValueError('invalid product config')\n")
    (tmp_path / "test_ok.py").write_text("def test_ok(): pass\n")
    with pytest.raises(RuntimeError) as error:
        collect(str(tmp_path), sys.executable)
    message = str(error.value)
    assert "test_a.py" in message and "missing_component_a" in message
    assert "test_b.py" in message and "ValueError: invalid product config" in message
    assert "test_ok.py::" not in message
    assert "Traceback" not in message and "short test summary" not in message


def test_conftest_import_failure_is_a_collection_error(tmp_path):
    (tmp_path / "conftest.py").write_text("import absent_framework_xyz\n")
    with pytest.raises(RuntimeError, match="ModuleNotFoundError.*absent_framework_xyz") as error:
        collect(str(tmp_path), sys.executable)
    assert "import absent_framework_xyz" not in str(error.value)


@pytest.mark.parametrize("exception", ["ValueError", "RuntimeError", "ImportError", "TimeoutError"])
def test_any_exception_raised_by_a_test_belongs_in_details(tmp_path, exception):
    (tmp_path / "test_card.py").write_text(
        f"def test_card():\n    raise {exception}('card message')\n")
    nodeid = "test_card.py::test_card"
    assert nodeid in collect(str(tmp_path), sys.executable).nodeids
    report, outcomes, lines = run_suite(tmp_path, [nodeid])
    assert not report.issues
    assert outcomes[-1].status is Status.FAILED
    detail = failure_for(index_failures(report.output), nodeid)
    assert detail.phase == "call"
    assert detail.headline == f"{exception}: card message"
    assert not any(diagnostics.PREFIX in line for line in lines)


@pytest.mark.parametrize("phase", ["setup", "teardown"])
def test_fixture_exceptions_remain_attached_to_test(tmp_path, phase):
    fixture = "    raise RuntimeError('fixture failed')\n"
    if phase == "teardown":
        fixture = "    yield\n" + fixture
    (tmp_path / "test_card.py").write_text(
        "import pytest\n@pytest.fixture\ndef card():\n" + fixture +
        "def test_card(card): pass\n")
    nodeid = "test_card.py::test_card"
    report, outcomes, _ = run_suite(tmp_path, [nodeid])
    assert outcomes[-1].status is Status.ERROR
    assert not report.issues
    detail = failure_for(index_failures(report.output), nodeid)
    assert detail.phase == phase
    assert detail.headline == "RuntimeError: fixture failed"


def test_call_and_teardown_errors_are_both_retained(tmp_path):
    (tmp_path / "test_card.py").write_text(
        "import pytest\n@pytest.fixture\ndef card():\n"
        "    yield\n    raise RuntimeError('disconnect failed')\n"
        "def test_card(card):\n    raise ValueError('invalid response')\n")
    nodeid = "test_card.py::test_card"
    report, _, _ = run_suite(tmp_path, [nodeid])
    detail = failure_for(index_failures(report.output), nodeid)
    assert detail.phase == "call / teardown"
    assert "invalid response" in detail.body and "disconnect failed" in detail.body
    assert not report.issues


def test_homonymous_tests_have_exact_tracebacks(tmp_path):
    for suffix in ("a", "b"):
        (tmp_path / f"test_{suffix}.py").write_text(
            f"def test_card():\n    raise ValueError('{suffix} response')\n")
    ids = ["test_a.py::test_card", "test_b.py::test_card"]
    report, _, _ = run_suite(tmp_path, ids)
    for suffix, nodeid in zip(("a", "b"), ids):
        detail = failure_for(index_failures(report.output), nodeid)
        assert detail.headline == f"ValueError: {suffix} response"
        assert not detail.ambiguous


def test_runtime_collection_failure_is_global(tmp_path):
    nodeid = "test_card.py::test_card"
    (tmp_path / "test_card.py").write_text("def test_card(): pass\n")
    collect(str(tmp_path), sys.executable)
    (tmp_path / "test_card.py").write_text("import absent_runtime_xyz\n")
    report, outcomes, _ = run_suite(tmp_path, [nodeid])
    assert report.issues and "absent_runtime_xyz" in report.issues[0]
    assert not outcomes and not report.ok
    assert failure_for(index_failures(report.output), nodeid) is None


def test_global_hook_failure_is_global_even_with_passing_tests(tmp_path):
    (tmp_path / "conftest.py").write_text(
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    raise RuntimeError('global cleanup failed')\n")
    (tmp_path / "test_card.py").write_text("def test_card(): pass\n")
    report, outcomes, _ = run_suite(tmp_path, ["test_card.py::test_card"])
    assert outcomes[-1].status is Status.PASSED
    assert "global cleanup failed" in report.issues[0]
    assert not report.ok


def test_native_process_crash_is_global(tmp_path):
    (tmp_path / "test_card.py").write_text(
        "import os\ndef test_card(): os._exit(17)\n")
    report, _, _ = run_suite(tmp_path, ["test_card.py::test_card"])
    assert report.exit_code == 17
    assert "exit code 17" in report.issues[0]


def test_missing_interpreter_is_global(tmp_path):
    request = RunRequest(str(tmp_path), str(tmp_path / "absent_python"),
                         ("test_card.py::test_card",), (Reader("", 0),))
    report = ReaderRun(request, request.readers[0], {}).run(lambda line: None, lambda item: None)
    assert report.issues and "Could not start" in report.issues[0]


def test_cancel_does_not_create_global_alert(tmp_path):
    (tmp_path / "test_card.py").write_text("def test_card(): pass\n")
    request = RunRequest(str(tmp_path), sys.executable, ("test_card.py::test_card",), ())
    run = ReaderRun(request, Reader("", 0), {})
    run.cancel()
    report = run.run(lambda line: None, lambda item: None)
    assert report.cancelled and not report.issues


def test_structured_test_failures_survive_history_roundtrip(tmp_path):
    (tmp_path / "test_card.py").write_text("def test_card(): raise ImportError('test import')\n")
    nodeid = "test_card.py::test_card"
    report, _, _ = run_suite(tmp_path, [nodeid])
    saved = tmp_path / "output.log"
    saved.write_text(report.output)
    assert failure_for(index_failures(saved.read_text()), nodeid).headline == "ImportError: test import"


def test_global_failure_is_not_an_ok_reader_report():
    assert not ReaderReport(Reader("", 0), exit_code=3).ok


def test_popup_is_scrollable_and_shows_errors_immediately(qtbot, monkeypatch):
    from runner.ui.widgets import ErrorDialog
    from PySide6.QtWidgets import QPushButton
    snapshots = []
    def inspect(dialog):
        snapshots.append((dialog.detail_view.isHidden(), dialog.detail_view.toPlainText(),
                          [button.text() for button in dialog.findChildren(QPushButton)]))
    monkeypatch.setattr(ErrorDialog, "exec", inspect)
    ErrorDialog.show_diagnostics(None, "Collection failed", "test_card.py\nImportError: framework")
    hidden, text, buttons = snapshots[0]
    assert not hidden
    assert text == "test_card.py\nImportError: framework"
    assert "Copy errors" in buttons and "Close" in buttons


def test_global_popup_offers_console(qtbot, monkeypatch):
    from runner.ui.widgets import ErrorDialog
    from PySide6.QtWidgets import QPushButton
    opened = []
    def inspect(dialog):
        button = next(button for button in dialog.findChildren(QPushButton)
                      if button.text() == "Show console")
        button.click()
    monkeypatch.setattr(ErrorDialog, "exec", inspect)
    ErrorDialog.show_diagnostics(None, "Execution error", "Process exited: 17", lambda: opened.append(True))
    assert opened == [True]


def test_custom_exception_during_collection_has_no_console_noise(tmp_path):
    (tmp_path / "test_card.py").write_text(
        "class CardFault(Exception): pass\nraise CardFault('invalid card')\n")
    with pytest.raises(RuntimeError) as error:
        collect(str(tmp_path), sys.executable)
    assert str(error.value) == "test_card.py\ntest_card.CardFault: invalid card"


def test_xdist_failures_are_attached_to_exact_nodeids(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -n 2\n")
    (tmp_path / "test_card.py").write_text(
        "import pytest\n@pytest.mark.parametrize('value', [1, 2])\n"
        "def test_card(value): raise ImportError('card %s' % value)\n")
    ids = [f"test_card.py::test_card[{value}]" for value in (1, 2)]
    report, _, _ = run_suite(tmp_path, ids)
    assert not report.issues
    for value, nodeid in zip((1, 2), ids):
        assert failure_for(index_failures(report.output), nodeid).headline == f"ImportError: card {value}"


def test_run_completion_only_alerts_for_global_errors(qtbot, monkeypatch):
    from runner.ui.main_window import MainWindow
    from runner.ui.widgets import ErrorDialog
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    for method in ("_archiver", "_notifier_fin_de_run", "_show_failure_actions"):
        monkeypatch.setattr(window, method, lambda *args: None)
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics", lambda *args: popups.append(args))
    window._on_run_finished([ReaderReport(Reader("", 0), exit_code=1, counts={Status.FAILED: 1})])
    assert not popups
    window._on_run_finished([ReaderReport(Reader("", 0), exit_code=3,
                                        issues=["RuntimeError: global hook failed"])])
    assert len(popups) == 1
    assert "global hook failed" in popups[0][2]
    assert "All tests passed" not in window.status_label.text()


def test_diagnostic_transport_is_hidden_in_console_and_clipboard(qtbot):
    from runner.ui.console_view import ConsoleView
    view = ConsoleView()
    qtbot.addWidget(view)
    view.set_text("ValueError: card response\n" + diagnostics.PREFIX + '{}\n')
    assert diagnostics.PREFIX not in view.view.toPlainText()
    assert view.text() == "ValueError: card response"
