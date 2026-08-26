"""Rejouer un test jusqu'a l'echec, ou exactement N fois.

`StressRunWorker.run()` est appele directement (pas `.start()`) : sa logique
ne depend pas de tourner sur un vrai fil, seul `AllureReportWorker` et les
autres worker Qt de l'appli ont besoin d'un vrai thread pour ne pas geler
l'interface -- ici on verifie juste l'enchainement des tentatives.
"""

from __future__ import annotations

import sys

import pytest

from runner.domain import execution
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.stress import MODE_N_TIMES, MODE_UNTIL_FAIL
from runner.services.stress_service import StressRunWorker

NODEID = "tests/test_authentication.py::test_login_timeout_retries"


class _FauxProcessus:
    def __init__(self, lignes: list[str]):
        self._lignes = list(lignes)
        self.returncode = 1 if any("FAILED" in l for l in lignes) else 0

    def readline(self):
        return self._lignes.pop(0) if self._lignes else ""

    def wait(self):
        pass

    def poll(self):
        return self.returncode

    def terminate(self):
        pass


def _popen_scripte(monkeypatch, sequence: list[str]):
    """Un Popen dont chaque appel rejoue le prochain statut de `sequence`."""
    appels = {"n": 0}

    def _faux_popen(commande, **kwargs):
        statut = sequence[appels["n"]]
        appels["n"] += 1
        processus = _FauxProcessus([f"{NODEID} {statut}\n"])
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _faux_popen)
    return appels


def _requete(tmp_path) -> RunRequest:
    return RunRequest(
        workspace=str(tmp_path), interpreter=sys.executable,
        nodeids=(NODEID,), readers=(Reader("", 0),),
    )


def test_until_fail_stops_at_the_first_failure(tmp_path, monkeypatch):
    _popen_scripte(monkeypatch, ["PASSED", "PASSED", "FAILED", "PASSED"])
    tentatives = []
    worker = StressRunWorker(_requete(tmp_path), Reader("", 0), {},
                             MODE_UNTIL_FAIL, cap=50)
    worker.attempt_done.connect(tentatives.append)
    resumes = []
    worker.finished_stress.connect(resumes.append)

    worker.run()

    assert [t.status for t in tentatives] == [Status.PASSED, Status.PASSED, Status.FAILED]
    resume = resumes[0]
    assert resume.ran == 3
    assert resume.passed == 2
    assert len(resume.failed_attempts) == 1
    assert resume.failed_attempts[0].number == 3
    assert not resume.cancelled


def test_until_fail_stops_at_the_cap_when_nothing_ever_fails(tmp_path, monkeypatch):
    _popen_scripte(monkeypatch, ["PASSED"] * 5)
    resumes = []
    worker = StressRunWorker(_requete(tmp_path), Reader("", 0), {},
                             MODE_UNTIL_FAIL, cap=5)
    worker.finished_stress.connect(resumes.append)

    worker.run()

    resume = resumes[0]
    assert resume.ran == 5
    assert resume.passed == 5
    assert resume.failed_attempts == []


def test_n_times_runs_to_completion_even_with_failures_in_between(tmp_path, monkeypatch):
    """Le coeur de la difference avec "until it fails" : un echec au milieu
    ne doit PAS arreter la serie, sous peine de fausser le taux de reussite."""
    _popen_scripte(monkeypatch, ["PASSED", "FAILED", "PASSED", "FAILED", "PASSED"])
    tentatives = []
    resumes = []
    worker = StressRunWorker(_requete(tmp_path), Reader("", 0), {},
                             MODE_N_TIMES, cap=5)
    worker.attempt_done.connect(tentatives.append)
    worker.finished_stress.connect(resumes.append)

    worker.run()

    assert len(tentatives) == 5
    resume = resumes[0]
    assert resume.ran == 5
    assert resume.passed == 3
    assert [t.number for t in resume.failed_attempts] == [2, 4]


def test_cancelling_stops_before_the_next_attempt(tmp_path, monkeypatch):
    _popen_scripte(monkeypatch, ["PASSED"] * 10)
    resumes = []
    worker = StressRunWorker(_requete(tmp_path), Reader("", 0), {},
                             MODE_N_TIMES, cap=10)
    worker.finished_stress.connect(resumes.append)

    numero_annulation = 3

    def _sur_tentative(tentative):
        if tentative.number == numero_annulation:
            worker.cancel()

    worker.attempt_done.connect(_sur_tentative)
    worker.run()

    resume = resumes[0]
    assert resume.ran == numero_annulation
    assert resume.cancelled
