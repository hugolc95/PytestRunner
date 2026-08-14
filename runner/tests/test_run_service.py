"""Le service de run, sur une vraie suite pytest, sans fenetre.

Ces tests lancent de vrais processus : ils sont lents, mais ce sont les seuls
qui prouvent que la chaine complete tient -- collecte, execution parallele,
isolation des lecteurs, remontee des resultats.
"""

from __future__ import annotations

import textwrap

import pytest
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication

from runner.domain.models import Reader, RunRequest, Status
from runner.domain.workspace import Workspace
from runner.services.run_service import CollectWorker, RunService


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def suite(tmp_path):
    """Une suite dont UN test depend du lecteur : c'est ce qui rend la
    divergence observable."""
    (tmp_path / "config.yml").write_text(
        "Reader: Reader A\nReaders:\n  - Reader B\n", encoding="utf-8")
    (tmp_path / "test_suite.py").write_text(textwrap.dedent('''
        import pathlib
        import pytest
        import yaml

        def lecteur():
            texte = pathlib.Path(__file__).with_name("config.yml").read_text(
                encoding="utf-8")
            return yaml.safe_load(texte)["Reader"]

        def test_toujours_vert():
            assert True

        def test_depend_du_lecteur():
            assert lecteur() == "Reader A"

        def test_ignore():
            pytest.skip("pas encore supporte")
    '''), encoding="utf-8")
    return tmp_path


def _attendre(condition, timeout_ms: int = 60000) -> bool:
    """Fait tourner la boucle Qt jusqu'a ce que la condition soit vraie."""
    ecoule = 0
    while not condition() and ecoule < timeout_ms:
        boucle = QEventLoop()
        QTimer.singleShot(25, boucle.quit)
        boucle.exec_()
        ecoule += 25
    return condition()


# ------------------------------------------------------------------ collecte

def test_collection_runs_off_the_ui_thread(qapp, suite):
    resultats = []
    worker = CollectWorker(str(suite), Workspace.load(str(suite)).interpreter,
                           Workspace.load(str(suite)).env)
    worker.collected.connect(resultats.append)
    worker.start()

    assert _attendre(lambda: bool(resultats)), "la collecte n'a jamais rendu la main"
    worker.wait(5000)
    assert len(resultats[0]) == 3


def test_a_broken_workspace_reports_a_readable_error(qapp, tmp_path):
    """Pas de stacktrace brute : l'interface affiche ce message tel quel."""
    erreurs = []
    worker = CollectWorker(str(tmp_path), "/definitely/not/python", {})
    worker.failed.connect(erreurs.append)
    worker.start()

    assert _attendre(lambda: bool(erreurs), 20000)
    worker.wait(5000)
    assert "not found" in erreurs[0].lower()


# ----------------------------------------------------------------------- run

@pytest.fixture
def lance(qapp, suite):
    """Joue la suite sur les deux lecteurs et rend (service, resultats)."""
    ws = Workspace.load(str(suite))
    service = RunService()

    outcomes: list = []
    rapports: list = []
    service.outcome.connect(outcomes.append)
    service.finished.connect(rapports.extend)

    requete = RunRequest(
        workspace=ws.path, interpreter=ws.interpreter,
        nodeids=("test_suite.py::test_toujours_vert",
                 "test_suite.py::test_depend_du_lecteur",
                 "test_suite.py::test_ignore"),
        readers=ws.readers, config_path=ws.config_path,
    )
    assert service.start(requete, ws.env)
    assert _attendre(lambda: bool(rapports)), "le run ne s'est jamais termine"
    service.wait(5000)
    return service, outcomes, rapports


def test_every_reader_produces_its_own_results(lance):
    _, outcomes, rapports = lance
    assert len(rapports) == 2
    assert {r.reader.name for r in rapports} == {"Reader A", "Reader B"}
    assert len(outcomes) == 6, "3 tests x 2 lecteurs"


def test_each_reader_really_sees_its_own_reader_value(lance):
    """Le coeur du multi-lecteur : le meme test ne rend pas le meme verdict
    d'un lecteur a l'autre. S'ils etaient identiques, l'isolation ne marcherait
    pas et personne ne s'en apercevrait."""
    _, outcomes, _ = lance
    par_lecteur = {
        o.reader_index: o.status
        for o in outcomes if o.nodeid.endswith("test_depend_du_lecteur")
    }
    assert par_lecteur[0] is Status.PASSED
    assert par_lecteur[1] is Status.FAILED


def test_results_carry_the_index_of_their_reader(lance):
    _, outcomes, _ = lance
    assert {o.reader_index for o in outcomes} == {0, 1}


def test_the_reports_come_back_in_column_order(lance):
    """Ils arrivent dans l'ordre ou les lecteurs finissent : un bilan qui
    change de disposition d'un run a l'autre serait illisible."""
    _, _, rapports = lance
    assert [r.reader.index for r in rapports] == [0, 1]


def test_a_skipped_test_is_not_counted_as_failed(lance):
    _, _, rapports = lance
    assert all(r.counts.get(Status.SKIPPED, 0) == 1 for r in rapports)


def test_the_failing_reader_is_the_only_one_reported_as_bad(lance):
    _, _, rapports = lance
    par_nom = {r.reader.name: r for r in rapports}
    assert par_nom["Reader A"].ok
    assert not par_nom["Reader B"].ok


def test_a_second_run_is_refused_while_one_is_going(qapp, suite):
    """Deux suites qui se disputent le meme materiel n'ont aucun sens."""
    ws = Workspace.load(str(suite))
    service = RunService()
    requete = RunRequest(
        workspace=ws.path, interpreter=ws.interpreter,
        nodeids=("test_suite.py::test_toujours_vert",),
        readers=ws.readers, config_path=ws.config_path,
    )
    assert service.start(requete, ws.env) is True
    assert service.start(requete, ws.env) is False, "le second doit etre refuse"

    service.cancel()
    service.wait(10000)


def test_progress_counts_every_reader(qapp, suite):
    """Le total est le nombre de tests MULTIPLIE par le nombre de lecteurs."""
    ws = Workspace.load(str(suite))
    requete = RunRequest(
        workspace=ws.path, interpreter=ws.interpreter,
        nodeids=("test_suite.py::test_toujours_vert",),
        readers=ws.readers, config_path=ws.config_path,
    )
    assert requete.total_tests == 2

    service = RunService()
    vus: list = []
    service.progress.connect(lambda faits, total: vus.append((faits, total)))
    fini: list = []
    service.finished.connect(fini.append)

    service.start(requete, ws.env)
    assert _attendre(lambda: bool(fini))
    service.wait(5000)
    assert vus[-1] == (2, 2)
