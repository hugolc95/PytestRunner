"""Organisation des logs par build et mode incremental."""

import io
import logging
import re
from pathlib import Path

from gui_qt.config.config_loader import find_logs_for_build
from testSuite1.log import next_available_build_number, setup_logging


def _create_log(tmp_path, *, incremental: bool, build: int = 42):
    workspace = tmp_path / "workspace"
    test_file = workspace / "TSu" / "JC_API_ID" / "Int" / "CVcertificateV3" / "test_signature.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_verify_signature():\n    pass\n", encoding="utf-8")

    logger = logging.getLogger(f"build-log-{incremental}-{build}-{id(tmp_path)}")
    path, handler = setup_logging(
        test_file=test_file,
        test_name="test_verify_signature[P256]",
        log_directory=workspace / "logs",
        session_datestamp="20260819",
        workspace_root=workspace,
        reader="HID OMNIKEY",
        build_number=build,
        incremental_log=incremental,
        logger=logger,
    )
    logger.info("preuve")
    logger.removeHandler(handler)
    handler.close()
    return workspace, path


def test_normal_mode_uses_a_build_directory_and_workspace_tree(tmp_path):
    workspace, path = _create_log(tmp_path, incremental=False)

    assert path.relative_to(workspace / "logs").parts == (
        "20260819", "Run_0042", "HID OMNIKEY", "TSu", "JC_API_ID", "Int",
        "CVcertificateV3", "test_verify_signature[P256].log",
    )
    assert "preuve" in path.read_text(encoding="utf-8")


def test_normal_mode_never_overwrites_a_reused_build(tmp_path):
    _, first = _create_log(tmp_path, incremental=False)
    _, second = _create_log(tmp_path, incremental=False)

    assert first.name == "test_verify_signature[P256].log"
    assert second.name == "test_verify_signature[P256]_002.log"
    assert first.is_file() and second.is_file()


def test_incremental_mode_stays_in_the_same_place_and_numbers_files(tmp_path):
    workspace, first = _create_log(tmp_path, incremental=True)
    _, second = _create_log(tmp_path, incremental=True)

    expected_parent = (
        workspace / "logs" / "20260819" / "HID OMNIKEY" / "TSu"
        / "JC_API_ID" / "Int" / "CVcertificateV3"
    )
    assert first.parent == expected_parent
    assert "Run_0042" not in first.parts
    assert first.name == "test_verify_signature[P256]_B0042_001.log"
    assert second.name == "test_verify_signature[P256]_B0042_002.log"


def test_manual_build_fallback_sees_both_log_modes(tmp_path):
    workspace, _ = _create_log(tmp_path, incremental=False, build=7)
    _create_log(tmp_path, incremental=True, build=11)

    assert next_available_build_number(workspace / "logs", "20260819") == 12


def test_console_has_no_timestamp_but_log_file_keeps_it(tmp_path):
    console_output = io.StringIO()
    console_handler = logging.StreamHandler(console_output)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger = logging.getLogger(f"console-format-{id(tmp_path)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.addHandler(console_handler)

    workspace = tmp_path / "workspace"
    test_file = workspace / "tests" / "test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_example():\n    pass\n", encoding="utf-8")

    log_path, file_handler = setup_logging(
        test_file=test_file,
        test_name="test_example",
        log_directory=workspace / "logs",
        session_datestamp="20260819",
        workspace_root=workspace,
        reader="Reader",
        build_number=42,
        incremental_log=False,
        logger=logger,
    )
    logger.info("message test")

    logger.removeHandler(file_handler)
    file_handler.close()
    logger.removeHandler(console_handler)

    assert console_output.getvalue() == "INFO - message test\n"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - INFO - message test\n",
        log_path.read_text(encoding="utf-8"),
    )


def test_run_history_lookup_finds_normal_and_incremental_builds(tmp_path):
    workspace, normal = _create_log(tmp_path, incremental=False, build=20)
    _, incremental = _create_log(tmp_path, incremental=True, build=21)
    (workspace / "config.yaml").write_text("log_directory: logs\n", encoding="utf-8")

    assert find_logs_for_build(str(workspace), 20, reader="HID OMNIKEY") == [normal]
    assert find_logs_for_build(str(workspace), 21, reader="HID OMNIKEY") == [incremental]
    assert find_logs_for_build(str(workspace), 21, reader="Another reader") == []
