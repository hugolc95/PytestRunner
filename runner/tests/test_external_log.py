"""Tests de l'ouverture du log sans dependance vers l'ancienne interface."""

import pytest

from runner.ui.external_log import (
    find_notepad_plus_plus,
    open_in_notepad_plus_plus,
)
from runner.ui.widgets import ErrorDialog


def test_windows_log_folder_uses_explorer_with_complete_path(tmp_path, monkeypatch):
    from runner.ui import external_log
    folder = tmp_path / "logs with spaces" / "Run_0414"
    folder.mkdir(parents=True)
    opened = []
    monkeypatch.setattr(external_log.sys, "platform", "win32")
    monkeypatch.setattr(external_log.os, "startfile",
                        lambda path, verb: opened.append((path, verb)), raising=False)
    monkeypatch.setattr(external_log.QDesktopServices, "openUrl",
                        lambda *_: pytest.fail("Native Explorer opening should suffice"))
    external_log.open_log_folder(folder)
    assert opened == [(str(folder), "explore")]


def test_windows_folder_open_falls_back_to_qt_and_reports_both_failures(tmp_path, monkeypatch):
    from runner.ui import external_log
    monkeypatch.setattr(external_log.sys, "platform", "win32")
    def fail_native(*_):
        raise OSError("Explorer access denied")
    monkeypatch.setattr(external_log.os, "startfile", fail_native, raising=False)
    opened = []
    monkeypatch.setattr(external_log.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toLocalFile()) or True)
    external_log.open_log_folder(tmp_path)
    assert opened == [str(tmp_path)]
    monkeypatch.setattr(external_log.QDesktopServices, "openUrl", lambda *_: False)
    with pytest.raises(OSError, match="Explorer access denied"):
        external_log.open_log_folder(tmp_path)


def test_folder_removed_before_opening_reports_its_path(tmp_path):
    from runner.ui.external_log import open_log_folder
    missing = tmp_path / "Run_0414"
    with pytest.raises(FileNotFoundError, match="Run_0414"):
        open_log_folder(missing)


def test_notepad_plus_plus_is_found_in_program_files(tmp_path, monkeypatch):
    executable = tmp_path / "Notepad++" / "notepad++.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"")
    monkeypatch.setattr("runner.ui.external_log.shutil.which", lambda command: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMW6432", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert find_notepad_plus_plus() == executable


def test_notepad_plus_plus_receives_the_complete_log_path(tmp_path, monkeypatch):
    executable = tmp_path / "notepad++.exe"
    executable.write_bytes(b"")
    log = tmp_path / "complete.log"
    log.write_text("complete", encoding="utf-8")
    launched = []
    monkeypatch.setattr(
        "runner.ui.external_log.find_notepad_plus_plus", lambda: executable
    )
    monkeypatch.setattr(
        "runner.ui.external_log.subprocess.Popen", lambda command: launched.append(command)
    )

    assert open_in_notepad_plus_plus(None, log)
    assert launched == [[str(executable), str(log)]]


def test_a_missing_log_reports_through_error_dialog_not_a_bare_message_box(
        tmp_path, monkeypatch):
    """`QMessageBox.warning()` ouvrait une vraie fenetre native independante,
    qui peut apparaitre un instant sans le style de l'appli sous Windows.
    `ErrorDialog.show_error()` est le chemin d'erreur unifie que
    `runtime_polish.py` sait rediriger vers le bandeau integre a la fenetre
    principale plutot que vers un dialogue a part."""
    appels = []
    monkeypatch.setattr(
        ErrorDialog, "show_error",
        classmethod(lambda cls, *args, **kwargs: appels.append(args)))

    ok = open_in_notepad_plus_plus(None, tmp_path / "does-not-exist.log")

    assert ok is False
    assert appels
