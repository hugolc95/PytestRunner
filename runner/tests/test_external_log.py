"""Tests de l'ouverture du log sans dependance vers l'ancienne interface."""

from runner.ui.external_log import (
    find_notepad_plus_plus,
    open_in_notepad_plus_plus,
)


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
