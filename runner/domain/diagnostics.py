"""Structured pytest diagnostics, classified by context rather than exception type."""

from __future__ import annotations

import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from runner.domain.ansi import strip_ansi

ENV_OUT = "PYTESTRUNNER_DIAGNOSTICS_OUT"
PREFIX = "PYTESTRUNNER_DIAGNOSTIC\t"
MODULE = "runner_diagnostic_probe"

# This standalone plugin runs in the selected test interpreter, including x86.
_SOURCE = r'''
import json
import os
import pytest

def _write(kind, nodeid, phase, detail):
    # xdist forwards reports to the controller; only it writes the shared file.
    if "PYTEST_XDIST_WORKER" in os.environ:
        return
    target = os.environ.get("PYTESTRUNNER_DIAGNOSTICS_OUT", "")
    if not target:
        return
    crash = getattr(detail, "reprcrash", None)
    payload = dict(kind=kind, nodeid=nodeid, phase=phase,
                   message=str(getattr(crash, "message", "") or detail),
                   body=str(detail))
    try:
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except OSError:
        pass

@pytest.hookimpl(trylast=True)
def pytest_collectreport(report):
    if report.failed:
        _write("collection", report.nodeid, "collection", report.longrepr)

@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    if report.failed:
        _write("test", report.nodeid, report.when, report.longrepr)

def pytest_internalerror(excrepr, excinfo):
    _write("execution", "", "internal", excrepr)

def pytest_keyboard_interrupt(excinfo):
    _write("execution", "", "interrupted", excinfo.getrepr(style="short"))
'''


@contextmanager
def diagnostic_probe():
    with tempfile.TemporaryDirectory(prefix="runner_diagnostics_") as directory:
        root = Path(directory)
        (root / f"{MODULE}.py").write_text(_SOURCE, encoding="utf-8")
        yield ["-p", MODULE], directory, str(root / "diagnostics.jsonl")


def read_diagnostics(path: str) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    result = []
    for line in lines:
        try:
            item = json.loads(line)
            if isinstance(item, dict) and all(isinstance(item.get(k), str)
                                             for k in ("kind", "nodeid", "phase", "message", "body")):
                result.append(item)
        except (ValueError, TypeError):
            continue
    return result


def format_errors(items: list[dict]) -> str:
    """Show only the location and exception message, not collection chatter."""
    return "\n\n".join(dict.fromkeys(
        (f"{item['nodeid']}\n" if item["nodeid"] else "") + (
            fallback_error(item["body"], 2) if item["message"] == item["body"]
            and item["kind"] == "collection" else item["message"])
        for item in items))


def fallback_error(output: str, code: int) -> str:
    """Fallback for failures before the plugin loads, usage errors and native crashes."""
    lines = strip_ansi(output or "").splitlines()
    exception_lines = [line.strip()[1:].strip() for line in lines
                       if re.match(r"^\s*E\s+", line)]
    if exception_lines:
        return "\n".join(dict.fromkeys(exception_lines))
    errors = [line.strip().removeprefix("E ").strip() for line in lines
              if re.match(r"^\s*(?:E\s+)?[\w.]+(?:Error|Exception):", line)
              or line.lstrip().startswith(("ERROR:", "INTERNALERROR>"))]
    if errors:
        return "\n".join(dict.fromkeys(errors))
    # No assumptions about custom exception names in bootstrap failures.
    if any("Traceback (most recent call last)" in line for line in lines):
        nonempty = [line.strip() for line in lines if line.strip()]
        if nonempty:
            return nonempty[-1]
    return f"Pytest stopped without a test result (exit code {code})."
