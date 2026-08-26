""""Run until it fails" / "Run N times" declenches depuis la fenetre :
demarrage, bandeau, panneau Detail, et retour a la normale une fois fini.

`subprocess.Popen` est remplace, comme dans test_allure_report.py et
test_stress_service.py : aucun vrai pytest ne tourne, seule l'orchestration
est testee.
"""

from __future__ import annotations

import sys

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QDialog

from runner.domain import execution
from runner.domain.models import Reader
from runner.domain.stress import MODE_N_TIMES, MODE_UNTIL_FAIL
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.run_n_times_dialog import RunNTimesDialog

NODEID = "suite/apdu/test_select.py::test_atr"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace.load(str(tmp_path))
    f.model.set_tree(build_tree([NODEID]))
    f.model.set_readers((Reader("", 0),))
    f.results.set_readers((Reader("", 0),))
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


class _FauxProcessus:
    def __init__(self, statut: str):
        self._lignes = [f"{NODEID} {statut}\n"]
        self.returncode = 1 if statut == "FAILED" else 0

    def readline(self):
        return self._lignes.pop(0) if self._lignes else ""

    def wait(self):
        pass

    def poll(self):
        return self.returncode

    def terminate(self):
        pass


def _popen_scripte(monkeypatch, sequence: list[str]):
    appels = {"n": 0}

    def _faux_popen(commande, **kwargs):
        statut = sequence[min(appels["n"], len(sequence) - 1)]
        appels["n"] += 1
        processus = _FauxProcessus(statut)
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _faux_popen)
    return appels


def _attendre(fenetre, qapp, timeout_ms=3000):
    worker = fenetre._stress_worker
    if worker is None:
        return
    worker.wait(timeout_ms)
    for _ in range(50):
        qapp.processEvents()
        if fenetre._stress_worker is None:
            return


def test_until_fail_disables_run_and_shows_the_running_banner(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED"] * 3 + ["FAILED"])

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=50)

    assert fenetre._stress_worker is not None
    assert not fenetre.run_button.isEnabled()
    assert "stress-testing" in fenetre.stress_banner._titre.text().lower()
    assert fenetre.stress_banner.stop_button.isEnabled()

    _attendre(fenetre, qapp)


def test_until_fail_stops_and_shows_the_failed_banner(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED", "PASSED", "FAILED"])

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=50)
    _attendre(fenetre, qapp)

    assert fenetre._stress_worker is None
    assert fenetre.run_button.isEnabled()
    assert "failed" in fenetre.stress_banner._titre.text().lower()
    assert fenetre.results.detail._dernier_stress is not None


def test_until_fail_reaching_the_cap_shows_a_neutral_done_banner(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED"] * 5)

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=5)
    _attendre(fenetre, qapp)

    assert "never failed" in fenetre.stress_banner._titre.text().lower()


def test_n_times_runs_to_completion_and_reports_the_tally(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED", "FAILED", "PASSED", "FAILED", "PASSED"])

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=5)
    _attendre(fenetre, qapp)

    assert fenetre._stress_worker is None
    _, resume = fenetre.results.detail._dernier_stress
    assert resume.ran == 5
    assert resume.passed == 3
    assert len(resume.failed_attempts) == 2


def test_the_n_times_dialog_feeds_the_chosen_count(fenetre, monkeypatch, qapp):
    monkeypatch.setattr(RunNTimesDialog, "exec_", lambda self: QDialog.Accepted)
    monkeypatch.setattr(RunNTimesDialog, "count", lambda self: 7)
    appels = []
    monkeypatch.setattr(fenetre, "_lancer_stress",
                        lambda nodeid, mode, cap: appels.append((nodeid, mode, cap)))

    fenetre._demander_run_n_fois(NODEID)

    assert appels == [(NODEID, MODE_N_TIMES, 7)]


def test_cancelling_the_n_times_dialog_launches_nothing(fenetre, monkeypatch, qapp):
    monkeypatch.setattr(RunNTimesDialog, "exec_", lambda self: QDialog.Rejected)
    appels = []
    monkeypatch.setattr(fenetre, "_lancer_stress",
                        lambda *a: appels.append(a))

    fenetre._demander_run_n_fois(NODEID)

    assert appels == []


def test_stop_button_on_the_banner_cancels_the_series(fenetre, monkeypatch, qapp):
    demarre = __import__("threading").Event()
    poursuivre = __import__("threading").Event()

    def _popen_lent(commande, **kwargs):
        demarre.set()
        poursuivre.wait(5)
        processus = _FauxProcessus("PASSED")
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _popen_lent)

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=50)
    assert demarre.wait(2)

    fenetre.stress_banner.stop_button.click()
    poursuivre.set()
    _attendre(fenetre, qapp)

    _, resume = fenetre.results.detail._dernier_stress
    assert resume.cancelled
    assert "stopped" in fenetre.stress_banner._titre.text().lower()
