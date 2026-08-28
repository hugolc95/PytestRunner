""""Run until it fails" / "Run N times" declenches depuis la fenetre :
demarrage, badge sur l'arbre, barre de statut, panneau Detail, et retour a la
normale une fois fini.

`subprocess.Popen` est remplace, comme dans test_allure_report.py et
test_stress_service.py : aucun vrai pytest ne tourne, seule l'orchestration
est testee.
"""

from __future__ import annotations

import sys

import pytest
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QApplication, QDialog

from runner.domain import execution
from runner.domain.history import History
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
    # Historique isole : les tentatives de stress-test s'y archivent
    # maintenant reellement, il ne doit pas ecrire dans le vrai dossier
    # utilisateur.
    f.history = History(tmp_path / "history")
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


def test_until_fail_disables_run_and_shows_the_running_status(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED"] * 3 + ["FAILED"])

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=50)

    assert fenetre._stress_worker is not None
    assert not fenetre.run_button.isEnabled()
    assert "stress-testing" in fenetre.status_label.text().lower()
    # Stop est desormais le MEME bouton que pour un run normal.
    assert fenetre.stop_button.isEnabled()

    _attendre(fenetre, qapp)


def test_until_fail_stops_and_shows_the_failed_status(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED", "PASSED", "FAILED"])

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=50)
    _attendre(fenetre, qapp)

    assert fenetre._stress_worker is None
    assert fenetre.run_button.isEnabled()
    assert "failed" in fenetre.status_label.text().lower()
    assert fenetre.results.detail._dernier_stress is not None


def test_until_fail_reaching_the_cap_shows_a_neutral_done_status(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED"] * 5)

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=5)
    _attendre(fenetre, qapp)

    assert "never failed" in fenetre.status_label.text().lower()


def test_the_tree_row_carries_a_compact_badge_while_it_runs(fenetre, monkeypatch, qapp):
    """Le badge vit sur la ligne du test dans l'arbre -- pas dans un widget a
    part qu'il faut associer mentalement au bon test."""
    _popen_scripte(monkeypatch, ["PASSED"] * 3 + ["FAILED"])

    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=50)

    index = fenetre.model.index_for_nodeid(NODEID)
    assert "1/50" in fenetre.model.data(index, Qt.DisplayRole)

    _attendre(fenetre, qapp)


def test_the_tree_badge_keeps_the_final_tally_once_done(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED", "FAILED", "PASSED", "FAILED", "PASSED"])

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=5)
    _attendre(fenetre, qapp)

    index = fenetre.model.index_for_nodeid(NODEID)
    assert "5/5" in fenetre.model.data(index, Qt.DisplayRole)


def test_starting_a_normal_run_clears_a_leftover_stress_badge(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED"] * 5)
    fenetre._lancer_stress(NODEID, MODE_UNTIL_FAIL, cap=5)
    _attendre(fenetre, qapp)

    from runner.domain.models import RunRequest

    fenetre._on_run_started(RunRequest(
        workspace=str(fenetre.workspace.path), interpreter=sys.executable,
        nodeids=(NODEID,), readers=(Reader("", 0),)))

    index = fenetre.model.index_for_nodeid(NODEID)
    assert fenetre.model.data(index, Qt.DisplayRole) == "test_atr"


def test_n_times_runs_to_completion_and_reports_the_tally(fenetre, monkeypatch, qapp):
    _popen_scripte(monkeypatch, ["PASSED", "FAILED", "PASSED", "FAILED", "PASSED"])

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=5)
    _attendre(fenetre, qapp)

    assert fenetre._stress_worker is None
    _, resume = fenetre.results.detail._dernier_stress
    assert resume.ran == 5
    assert resume.passed == 3
    assert len(resume.failed_attempts) == 2


def test_each_attempt_lands_in_history(fenetre, monkeypatch, qapp):
    """Le coeur du reproche : "Run N times" ne laissait RIEN dans l'onglet
    History. Chaque tentative doit y devenir sa propre entree, retrouvable et
    rejouable comme n'importe quel autre run."""
    _popen_scripte(monkeypatch, ["PASSED", "FAILED", "PASSED", "FAILED", "PASSED"])

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=5)
    _attendre(fenetre, qapp)

    entrees = fenetre.history.entries()
    assert len(entrees) == 5
    assert all(e.nodeids == (NODEID,) for e in entrees)
    assert [e.ok for e in entrees] == [True, False, True, False, True]


def test_a_multi_reader_stress_run_archives_one_entry_per_reader(
        fenetre, monkeypatch, qapp, tmp_path):
    """Coche sur deux lecteurs, chaque tentative doit tourner -- et
    s'archiver -- sur CHACUN d'eux, pas seulement le premier."""
    from runner.domain.execution import Collection

    (tmp_path / "config.yml").write_text("Reader: A\nReaders:\n  - B\n", encoding="utf-8")
    fenetre.workspace = Workspace.load(str(tmp_path))
    fenetre._on_collected(Collection(nodeids=(NODEID,)))

    _popen_scripte(monkeypatch, ["PASSED"] * 6)  # 3 tentatives x 2 lecteurs

    fenetre._lancer_stress(NODEID, MODE_N_TIMES, cap=3)
    _attendre(fenetre, qapp)

    entrees = fenetre.history.entries()
    assert len(entrees) == 6
    assert sorted({e.reader for e in entrees}) == ["A", "B"]


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


def test_the_stop_button_cancels_a_running_stress_series(fenetre, monkeypatch, qapp):
    """Le meme bouton Stop que pour un run normal -- plus de bouton dedie
    dans un widget a part qu'il faut d'abord retrouver."""
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

    assert fenetre.stop_button.isEnabled()
    fenetre.stop_run()
    poursuivre.set()
    _attendre(fenetre, qapp)

    _, resume = fenetre.results.detail._dernier_stress
    assert resume.cancelled
    assert "stopped" in fenetre.status_label.text().lower()
