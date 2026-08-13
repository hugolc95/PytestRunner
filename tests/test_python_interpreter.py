import sys

import pytest

from core.python_interpreter import (
    cached_probe,
    check_ready_to_run,
    default_interpreter,
    forget_probe,
    interpreter_from_config,
    interpreter_source,
    probe_interpreter,
    resolve_interpreter,
    subprocess_flags,
)
from core.test_discovery import collect_tests


@pytest.fixture(autouse=True)
def clean_probe_cache():
    """Le cache de probes est un etat global du module : on l'isole entre tests."""
    forget_probe()
    yield
    forget_probe()


def write_config(tmp_path, content: str):
    (tmp_path / "config.yaml").write_text(content, encoding="utf-8")


def test_default_interpreter_is_current_python_when_not_frozen():
    assert default_interpreter() == sys.executable


def test_default_interpreter_looks_on_path_when_frozen(monkeypatch):
    """Fige: sys.executable pointe vers le .exe du GUI, pas vers un Python.
    L'utiliser relancerait l'interface au lieu de pytest."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        "core.python_interpreter.shutil.which",
        lambda name: "/usr/bin/python3" if name in ("python", "python3") else None,
    )
    assert default_interpreter() == "/usr/bin/python3"


def test_default_interpreter_empty_when_frozen_and_nothing_on_path(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("core.python_interpreter.shutil.which", lambda name: None)
    assert default_interpreter() == ""


def test_resolve_falls_back_to_current_python(tmp_path):
    assert resolve_interpreter(workspace=str(tmp_path)) == sys.executable


def test_configured_value_wins_over_default(tmp_path):
    assert resolve_interpreter(configured="/opt/py64/python", workspace=str(tmp_path)) == "/opt/py64/python"


def test_blank_configured_value_is_ignored(tmp_path):
    assert resolve_interpreter(configured="   ", workspace=str(tmp_path)) == sys.executable


def test_workspace_config_wins_over_configured_value(tmp_path):
    write_config(tmp_path, "python_executable: C:/Py313-64/python.exe\n")
    resolved = resolve_interpreter(configured="/opt/py64/python", workspace=str(tmp_path))
    assert resolved == "C:/Py313-64/python.exe"


def test_python_alias_accepted_in_workspace_config(tmp_path):
    write_config(tmp_path, "python: /usr/bin/python3.13\n")
    assert interpreter_from_config(str(tmp_path)) == "/usr/bin/python3.13"


def test_broken_config_file_does_not_crash_resolution(tmp_path):
    write_config(tmp_path, "python_executable: [unclosed\n")
    assert resolve_interpreter(workspace=str(tmp_path)) == sys.executable


def test_config_without_the_key_is_transparent(tmp_path):
    write_config(tmp_path, "log_directory: logs\n")
    assert interpreter_from_config(str(tmp_path)) is None


def test_interpreter_source_reports_where_the_value_came_from(tmp_path):
    assert interpreter_source(workspace=str(tmp_path)) == "current Python"
    assert interpreter_source(configured="/opt/py", workspace=str(tmp_path)) == "application setting"

    write_config(tmp_path, "python_executable: /opt/py64\n")
    assert interpreter_source(configured="/opt/py", workspace=str(tmp_path)) == "workspace configuration"


def test_probe_reports_version_bitness_and_pytest():
    info = probe_interpreter(sys.executable)
    assert info.ok, info.error
    assert info.version.startswith(str(sys.version_info.major))
    assert info.bits in (32, 64)
    assert info.pytest_version  # pytest tourne, il est forcement importable


def test_probe_reports_missing_interpreter():
    info = probe_interpreter("/definitely/not/a/python")
    assert not info.ok
    assert "not found" in info.error


def test_probe_rejects_a_non_python_executable(tmp_path):
    fake = tmp_path / "fake"
    fake.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    fake.chmod(0o755)
    info = probe_interpreter(str(fake))
    assert not info.ok


def test_probe_result_is_cached():
    assert cached_probe(sys.executable) is None
    first = probe_interpreter(sys.executable)
    assert cached_probe(sys.executable) is not None
    # Deuxieme appel : meme objet, donc aucun processus relance.
    assert probe_interpreter(sys.executable) is first


def test_probe_can_bypass_the_cache():
    first = probe_interpreter(sys.executable)
    assert probe_interpreter(sys.executable, use_cache=False) is not first


def test_forgetting_a_probe_empties_the_cache():
    probe_interpreter(sys.executable)
    forget_probe(sys.executable)
    assert cached_probe(sys.executable) is None


def test_ui_thread_check_never_spawns_a_process(monkeypatch):
    """Garantie centrale : appele depuis le thread UI, check_ready_to_run ne doit
    JAMAIS lancer de processus, sinon l'interface gele a chaque lancement."""
    def explode(*args, **kwargs):
        raise AssertionError("check_ready_to_run a lance un processus")

    monkeypatch.setattr("core.python_interpreter.subprocess.run", explode)

    assert check_ready_to_run(sys.executable) == ""
    assert check_ready_to_run(sys.executable, parallel=True) == ""


def test_ui_thread_check_reports_a_cached_failure():
    probe_interpreter("/definitely/not/a/python")
    message = check_ready_to_run("/definitely/not/a/python")
    assert "not found" in message


def test_ui_thread_check_reports_cached_missing_xdist(monkeypatch):
    from core import python_interpreter

    info = python_interpreter.probe_interpreter(sys.executable)
    info.has_xdist = False

    assert python_interpreter.check_ready_to_run(sys.executable, parallel=False) == ""
    assert "pytest-xdist" in python_interpreter.check_ready_to_run(sys.executable, parallel=True)


def test_check_ready_accepts_the_current_interpreter():
    assert check_ready_to_run(sys.executable, cached_only=False) == ""


def test_check_ready_explains_an_empty_configuration():
    message = check_ready_to_run("")
    assert "No Python interpreter" in message


def test_check_ready_explains_a_bad_path():
    message = check_ready_to_run("/definitely/not/a/python", cached_only=False)
    assert "not found" in message


def test_check_ready_flags_missing_xdist(monkeypatch):
    """Parallel a besoin de pytest-xdist dans l'interpreteur des TESTS,
    pas dans celui de l'interface."""
    from core import python_interpreter

    real_probe = python_interpreter.probe_interpreter

    def probe_without_xdist(path, timeout=15.0):
        info = real_probe(path, timeout)
        info.has_xdist = False
        return info

    monkeypatch.setattr(python_interpreter, "probe_interpreter", probe_without_xdist)

    assert python_interpreter.check_ready_to_run(sys.executable, parallel=False, cached_only=False) == ""
    message = python_interpreter.check_ready_to_run(sys.executable, parallel=True, cached_only=False)
    assert "pytest-xdist" in message


def test_subprocess_flags_are_zero_off_windows(monkeypatch):
    monkeypatch.setattr("core.python_interpreter.os.name", "posix")
    assert subprocess_flags() == 0


def test_collect_tests_accepts_an_explicit_interpreter(tmp_path):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    nodeids = collect_tests(str(tmp_path), interpreter=sys.executable)
    assert nodeids == ["test_sample.py::test_ok"]


def test_collect_tests_reports_a_bad_interpreter_clearly(tmp_path):
    with pytest.raises(RuntimeError) as excinfo:
        collect_tests(str(tmp_path), interpreter="/definitely/not/a/python")
    assert "not found" in str(excinfo.value)


def test_collect_tests_refuses_to_run_without_an_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr("core.test_discovery.resolve_interpreter", lambda **kwargs: "")
    with pytest.raises(RuntimeError) as excinfo:
        collect_tests(str(tmp_path))
    assert "No Python interpreter" in str(excinfo.value)
