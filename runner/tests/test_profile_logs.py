"""Profile logs must stay attached to their occurrence, reader and attempt."""
import json
import shutil
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from runner.domain import history
from runner.domain.execution_profile import ExecutionOptions, ExecutionProfile
from runner.domain.logs import find_test_log
from runner.domain.models import Reader, ReaderReport, RunRequest, Status
from runner.domain.profile_logs import ProfileLogIndex
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.results_panel import ONGLET_LOGS

NODE = "TSu/PACE/Int/PaceInfo/Tests/perso/test_initCard_loadPrepersoAppCap.py::TestSuite_SampleClass::test_GenericPerso"
READER = Reader("simuSCR700U1132 Reader", 0)


def write_log(root, name="test_GenericPerso.log", text="first card trace", reader=READER.name, build=414):
    path = root / "Cosmo11" / "20261013" / f"Run_{build:04d}" / reader / "TSu/PACE/Int/PaceInfo/Tests/perso" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("incremental", [False, True])
def test_numbered_parameter_logs_match_current_build_not_another_run(tmp_path, incremental):
    node = "test_card.py::test_read[SHA512]"
    directory = tmp_path / "20261013" / (READER.name if incremental else "Run_0414" + "/" + READER.name)
    directory.mkdir(parents=True)
    stem = "test_read[SHA512]" + ("_B0414" if incremental else "")
    first = directory / (stem + "_001.log" if incremental else stem + ".log")
    second = directory / (stem + "_002.log")
    first.write_text("first")
    second.write_text("second")
    wrong = write_log(tmp_path, "test_read[SHA512].log", "another build", build=415)
    (tmp_path / "last_run_index.json").write_text(json.dumps({node: str(wrong)}))
    assert find_test_log(tmp_path, node, READER.name, build_number=414,
                         excluded=frozenset({first})) == second
    assert find_test_log(tmp_path, node, READER.name, build_number=416) is None


def test_captured_occurrences_ignore_later_manifest_changes_and_other_readers(tmp_path):
    index = ProfileLogIndex(tmp_path, 414)
    first = write_log(tmp_path)
    index.capture("0:0", NODE, READER, True)
    second = write_log(tmp_path, "test_GenericPerso_002.log", "retry card trace")
    (tmp_path / "last_run_index.json").write_text(json.dumps({NODE: str(second)}))
    index.capture("0:1", NODE, READER, True)
    other = Reader("Other Reader", 2)
    other_log = write_log(tmp_path, text="other card trace", reader=other.name)
    index.capture("0:0", NODE, other, True)
    index.capture("1:0", NODE, READER, True)  # No new log: don't borrow an earlier one.
    assert index.for_execution("0:0", (READER, other)) == {0: first, 2: other_log}
    assert index.for_execution("0:1", (READER, other)) == {0: second, 2: None}
    assert index.for_execution("1:0", (READER,)) == {0: None}
    assert index.for_execution("2:0", (READER,)) == {0: None}


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    QSettings(ORG, APP).clear()
    w = MainWindow()
    qtbot.addWidget(w)
    w.workspace = Workspace(str(tmp_path), settings={"LOG_PATH": str(tmp_path / "logs"), "Reader": READER.name})
    yield w
    w.close()
    QSettings(ORG, APP).clear()


def start_inspection(window, repetitions=2, config=""):
    window._running_execution_profile = ExecutionProfile(
        name="Card diagnostics", sequence=[NODE], configuration_name="", configuration_text="",
        execution=ExecutionOptions(repetitions=repetitions))
    window._on_run_started(RunRequest(window.workspace.path, sys.executable,
                                     (NODE,) * repetitions, (READER,),
                                     config_path=config, build_number=414))


def test_profile_log_tab_opens_each_occurrence_and_retry_without_changing_classic_logs(window, qtbot):
    start_inspection(window)
    root = window.workspace.log_root
    first = write_log(root)
    window._on_profile_execution(0, 0, 0, NODE, Status.FAILED)
    window._on_profile_batch_report(0, 1, 0, ReaderReport(READER))
    retry = write_log(root, "test_GenericPerso_002.log", "retry succeeded")
    window._on_profile_execution(0, 1, 0, NODE, Status.PASSED)
    window._on_profile_batch_report(0, 1, 1, ReaderReport(READER))
    second = write_log(root, "test_GenericPerso_003.log", "second repetition")
    window._on_profile_execution(1, 0, 0, NODE, Status.PASSED)
    window._on_profile_batch_report(1, 1, 0, ReaderReport(READER))
    assert window.profile_results.tabs.isTabEnabled(ONGLET_LOGS)
    qtbot.waitUntil(lambda: window.profile_results.logs.path_at(0) == first)
    for key, path in (("0:0", first), ("0:1", retry), ("1:0", second)):
        window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid(key))
        window.profile_results.show_tab(ONGLET_LOGS)
        assert window.profile_results.tabs.currentIndex() == ONGLET_LOGS
        assert window.profile_results.logs.path_at(0) == path
        assert path.read_text() in window.profile_results.logs.views[0].text()
    assert window.results._log_files is None
    window.profile_tree.setCurrentIndex(window.profile_tree.model().index(0, 0))
    assert window.profile_results.logs.path_at(0) is None
    assert "first card trace" not in window.profile_results.logs.views[0].text()


def test_profile_uses_launch_yaml_log_path_and_keeps_pending_execution_empty(window, tmp_path):
    config = tmp_path / "profile.yaml"
    config.write_text("LOG_PATH: profile-logs\n")
    start_inspection(window, config=str(config))
    assert window.profile_results._log_root == tmp_path / "profile-logs"
    write_log(tmp_path / "profile-logs", text="old run", build=413)
    write_log(window.workspace.log_root, text="wrong configuration")
    window._on_profile_execution(0, 0, 0, NODE, Status.ERROR)
    window._on_profile_batch_report(0, 1, 0, ReaderReport(READER))
    window._refresh_profile_selection()
    assert window.profile_results.logs.path_at(0) is None
    assert "old run" not in window.profile_results.logs.views[0].text()
    assert "wrong configuration" not in window.profile_results.logs.views[0].text()
    correct = write_log(tmp_path / "profile-logs", text="correct configuration")
    window._on_profile_execution(1, 0, 0, NODE, Status.PASSED)
    window._on_profile_batch_report(1, 1, 0, ReaderReport(READER))
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid("1:0"))
    assert window.profile_results.logs.path_at(0) == correct


def test_retry_batch_without_collected_tests_does_not_attach_a_previous_log(window):
    start_inspection(window)
    write_log(window.workspace.log_root, text="unrelated execution")
    # A collection error can finish a retry batch without emitting an
    # execution signal, so that retry has no row in the profile model.
    window._on_profile_batch_report(0, 1, 1, ReaderReport(READER, exit_code=2))
    window._on_profile_batch_report(0, 1, 0, ReaderReport(READER, exit_code=2))
    window._refresh_profile_selection()
    assert window.profile_results.logs.path_at(0) is None
    assert "unrelated execution" not in window.profile_results.logs.views[0].text()


@pytest.mark.parametrize("background", [False, True])
def test_history_archives_launch_log_root_even_after_yaml_and_workspace_change(
        window, qtbot, tmp_path, monkeypatch, background):
    from runner.domain.models import Outcome
    if background:
        from runner.ui import end_run_feedback
        for name in ("_on_run_started", "_on_outcome", "_on_progress", "_on_run_finished"):
            monkeypatch.setattr(MainWindow, name, getattr(MainWindow, name))
        end_run_feedback.install()
    config = tmp_path / "launch.yaml"
    config.write_text("LOG_PATH: launch-logs\n")
    window._run_id = "recorded-log-root"
    window._build_number = 414
    start_inspection(window, repetitions=1, config=str(config))
    window._on_outcome(Outcome(NODE, Status.PASSED, READER.index))
    # Editable run settings must not change the already-launched run's metadata.
    config.write_text("LOG_PATH: changed-logs\n")
    window.workspace = Workspace(str(tmp_path), settings={"LOG_PATH": "other-logs"})
    monkeypatch.setattr(window, "_notifier_fin_de_run", lambda *_: None)
    window._on_run_finished([ReaderReport(READER, counts={Status.PASSED: 1})])
    if background:
        qtbot.waitUntil(lambda: window._archive_worker is None)
    entry = window.history.find("recorded-log-root")
    assert entry.log_root == str(tmp_path / "launch-logs")


def test_real_profile_keeps_all_four_logs_generated_by_workspace_logging(window, qtbot, tmp_path, monkeypatch):
    # Use the repository's actual exclusive file naming, with real pytest
    # invocations: a duplicate nodeid starts a separate batch each time.
    shutil.copyfile(Path(__file__).parents[2] / "testSuite1/log.py", tmp_path / "log.py")
    (tmp_path / "test_card.py").write_text("def test_GenericPerso():\n    assert True\n")
    (tmp_path / "conftest.py").write_text('''
import logging
import os
from pathlib import Path
import pytest
from log import setup_logging

@pytest.fixture(autouse=True)
def card_log(request):
    root = Path(__file__).parent
    logger = logging.getLogger('card')
    path, handler = setup_logging(
        test_file=request.node.path, test_name=request.node.name,
        log_directory=root / 'logs', session_datestamp='20261013',
        workspace_root=root, reader='simuSCR700U1132 Reader',
        build_number=int(os.environ['PYTEST_RUNNER_BUILD_NUMBER']),
        incremental_log=False, logger=logger)
    logger.info('Card exchange in %s', path.name)
    yield
    logger.removeHandler(handler)
    handler.close()
''')
    node = "test_card.py::test_GenericPerso"
    window.model.set_tree(build_tree([node]))
    monkeypatch.setattr(window, "_require_interpreter", lambda: sys.executable)
    monkeypatch.setattr(window.history, "next_build_number", lambda: 414)
    monkeypatch.setattr(window, "_notifier_fin_de_run", lambda *_: None)
    profile = ExecutionProfile(name="Four card executions", sequence=[node], configuration_name="", configuration_text="",
                               execution=ExecutionOptions(repetitions=4))
    window._start_profile(profile)
    qtbot.waitUntil(lambda: not window.service.busy, timeout=30000)
    paths = []
    for position in range(4):
        window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid(f"{position}:0"))
        path = window.profile_results.logs.path_at(0)
        assert path is not None
        assert f"Card exchange in {path.name}" in window.profile_results.logs.views[0].text()
        assert window.profile_results._statuses[0] is Status.PASSED
        paths.append(path.name)
    assert paths == ["test_GenericPerso.log", "test_GenericPerso_002.log",
                     "test_GenericPerso_003.log", "test_GenericPerso_004.log"]
