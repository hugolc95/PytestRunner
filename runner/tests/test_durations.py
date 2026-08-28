"""Duree de chaque test, relue depuis le `--durations=0` que pytest calcule
deja tout seul -- rien ici ne chronometre quoi que ce soit.
"""

from __future__ import annotations

import sys

import pytest

from runner.domain import execution, parsing
from runner.domain.models import Reader, RunRequest

SORTIE_REELLE = """\
============================= test session starts ==============================
collected 2 items

test_probe.py::test_fast PASSED                                          [ 50%]
test_probe.py::test_slow PASSED                                          [100%]

============================== slowest durations ===============================
0.05s call     test_probe.py::test_slow

(5 durations < 0.005s hidden.  Use -vv to show these durations.)
============================== 2 passed in 0.06s ===============================
"""


def test_parses_a_real_durations_block():
    durees = parsing.parse_durations(SORTIE_REELLE)
    assert durees == {"test_probe.py::test_slow": 0.05}


def test_hidden_fast_tests_are_simply_absent_not_zero():
    durees = parsing.parse_durations(SORTIE_REELLE)
    assert "test_probe.py::test_fast" not in durees


def test_setup_call_and_teardown_are_summed_per_nodeid():
    sortie = (
        "0.10s setup    tests/test_x.py::test_slow_fixture\n"
        "0.20s call     tests/test_x.py::test_slow_fixture\n"
        "0.01s teardown tests/test_x.py::test_slow_fixture\n"
    )
    assert parsing.parse_durations(sortie) == {
        "tests/test_x.py::test_slow_fixture": pytest.approx(0.31)
    }


def test_no_durations_section_gives_an_empty_dict():
    assert parsing.parse_durations("2 passed in 0.01s\n") == {}


def test_ansi_colored_lines_still_parse():
    coloree = "\x1b[32m0.12s\x1b[0m call     tests/test_x.py::test_y\n"
    assert parsing.parse_durations(coloree) == {"tests/test_x.py::test_y": 0.12}


# --------------------------------------------- integration avec ReaderRun

class _FauxProcessus:
    def __init__(self, lignes: list[str]):
        self._lignes = list(lignes)
        self.returncode = 0

    def readline(self):
        return self._lignes.pop(0) if self._lignes else ""

    def wait(self):
        pass


def test_durations_flag_reaches_the_real_pytest_command(monkeypatch, tmp_path):
    captures = []

    def _faux_popen(commande, **kwargs):
        captures.append(commande)
        processus = _FauxProcessus([])
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _faux_popen)
    requete = RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                        nodeids=("t.py::test_a",), readers=(Reader("", 0),))

    execution.ReaderRun(requete, Reader("", 0), {}).run(lambda l: None, lambda o: None)

    assert "--durations=0" in captures[0]


def test_the_report_carries_the_parsed_durations(monkeypatch, tmp_path):
    def _faux_popen(commande, **kwargs):
        processus = _FauxProcessus([
            "t.py::test_a PASSED\n",
            "0.42s call     t.py::test_a\n",
        ])
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _faux_popen)
    requete = RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                        nodeids=("t.py::test_a",), readers=(Reader("", 0),))

    rapport = execution.ReaderRun(requete, Reader("", 0), {}).run(
        lambda l: None, lambda o: None)

    assert rapport.durations == {"t.py::test_a": 0.42}
