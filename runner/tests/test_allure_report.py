"""Le bouton Allure : place dans la barre, et ce qu'il fait quand on clique.

Genere et ouvre un rapport a partir des resultats du DERNIER run demarre --
jamais rien s'il l'interpreteur n'a pas le plugin, jamais rien si l'outil
`allure` n'est pas sur le PATH. Les deux cas doivent le dire clairement
plutot que de planter ou de rester muets.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from runner.domain import execution
from runner.domain import interpreter as interpreter_mod
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader, RunRequest


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.domain.workspace import Workspace
    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace(path=str(tmp_path), config_path="", settings={})
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


# --------------------------------------------------------------- la barre

def test_the_allure_button_sits_next_to_history(fenetre):
    barre = fenetre.history_button.parentWidget().layout()
    dans_la_barre = [barre.itemAt(i).widget() for i in range(barre.count())]
    assert fenetre.allure_button in dans_la_barre
    assert (dans_la_barre.index(fenetre.allure_button)
           == dans_la_barre.index(fenetre.history_button) + 1)


# ------------------------------------------------- ou ecrire les resultats

def test_no_allure_dir_when_the_interpreter_lacks_the_plugin(fenetre, monkeypatch):
    monkeypatch.setattr(interpreter_mod, "cached_probe",
                        lambda path: InterpreterInfo(path=path, has_allure=False))
    assert fenetre._allure_dir_for("python", "run123") == ""


def test_no_allure_dir_when_the_interpreter_was_never_probed(fenetre, monkeypatch):
    """Le probe tourne en fond : un run qui demarre avant qu'il finisse ne
    doit pas attendre, juste se passer d'Allure cette fois-ci."""
    monkeypatch.setattr(interpreter_mod, "cached_probe", lambda path: None)
    assert fenetre._allure_dir_for("python", "run123") == ""


def test_an_allure_dir_is_created_when_the_plugin_is_present(fenetre, monkeypatch):
    monkeypatch.setattr(interpreter_mod, "cached_probe",
                        lambda path: InterpreterInfo(path=path, has_allure=True))

    dossier = fenetre._allure_dir_for("python", "run123")

    assert dossier
    assert "run123" in dossier
    from pathlib import Path
    assert Path(dossier).is_dir()


# -------------------------------------------- la commande pytest reelle

class _FauxProcessus:
    """Assez d'un Popen pour que `ReaderRun.run()` aille jusqu'au bout sans
    jamais lancer de vrai pytest."""

    returncode = 0

    def readline(self):
        return ""

    def wait(self):
        pass


def _lancer_avec_popen_capture(monkeypatch, tmp_path, allure_dir: str) -> list:
    """Rejoue un `ReaderRun.run()` complet, Popen remplace, et rend la
    commande reellement construite."""
    captures: list = []

    def _faux_popen(commande, **kwargs):
        captures.append(commande)
        processus = _FauxProcessus()
        processus.stdout = processus
        return processus

    monkeypatch.setattr(execution.subprocess, "Popen", _faux_popen)

    requete = RunRequest(
        workspace=str(tmp_path), interpreter=sys.executable,
        nodeids=("t.py::test_a",), readers=(Reader("", 0),),
        allure_dir=allure_dir,
    )
    execution.ReaderRun(requete, Reader("", 0), {}).run(lambda l: None, lambda o: None)
    return captures[0]


def test_alluredir_reaches_the_real_pytest_command(monkeypatch, tmp_path):
    """Le coeur du dispositif : sans cette ligne, --alluredir n'atteint
    jamais pytest, quoi que dise le reste de la fonctionnalite."""
    commande = _lancer_avec_popen_capture(
        monkeypatch, tmp_path, str(tmp_path / "allure-results"))

    assert f"--alluredir={tmp_path / 'allure-results'}" in commande


def test_no_alluredir_flag_when_allure_is_not_configured(monkeypatch, tmp_path):
    commande = _lancer_avec_popen_capture(monkeypatch, tmp_path, "")

    assert not any(morceau.startswith("--alluredir=") for morceau in commande)


# ------------------------------------------------------------- le clic

def test_clicking_with_no_prior_run_explains_why(fenetre, monkeypatch):
    """Rien n'a encore tourne : `_last_allure_dir` est vide, le clic doit le
    dire plutot que planter sur un chemin qui n'existe pas."""
    messages = []
    monkeypatch.setattr(
        "runner.ui.main_window.ErrorDialog.show_error",
        lambda *args, **kwargs: messages.append(args))

    fenetre.open_allure_report()

    assert len(messages) == 1
    assert "No Allure results" in messages[0][1]


def test_clicking_with_empty_results_explains_why(fenetre, monkeypatch, tmp_path):
    """Le dossier existe (le run a demarre) mais pytest n'a encore rien
    ecrit dedans -- pas different d'une absence de resultats pour l'utilisateur."""
    vide = tmp_path / "allure-results"
    vide.mkdir()
    fenetre._last_allure_dir = str(vide)

    messages = []
    monkeypatch.setattr(
        "runner.ui.main_window.ErrorDialog.show_error",
        lambda *args, **kwargs: messages.append(args))

    fenetre.open_allure_report()

    assert len(messages) == 1
    assert "No Allure results" in messages[0][1]


def test_clicking_without_the_allure_cli_explains_why(fenetre, monkeypatch, tmp_path):
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which", lambda name: None)
    messages = []
    monkeypatch.setattr(
        "runner.ui.main_window.ErrorDialog.show_error",
        lambda *args, **kwargs: messages.append(args))

    fenetre.open_allure_report()

    assert len(messages) == 1
    assert "not found" in messages[0][1].lower()


def test_a_successful_generation_opens_the_report(fenetre, monkeypatch, tmp_path):
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")

    appels = []
    monkeypatch.setattr(
        "runner.ui.main_window.subprocess.run",
        lambda commande, **kwargs: appels.append(commande) or
        subprocess.CompletedProcess(commande, 0, stdout="", stderr=""))

    ouverts = []
    monkeypatch.setattr(
        "runner.ui.main_window.QDesktopServices.openUrl",
        lambda url: ouverts.append(url.toLocalFile()))

    fenetre.open_allure_report()

    assert appels and appels[0][0] == "/usr/bin/allure"
    assert appels[0][1] == "generate"
    assert len(ouverts) == 1
    assert ouverts[0].endswith("index.html")


def test_a_failed_generation_shows_allures_own_error(fenetre, monkeypatch, tmp_path):
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr(
        "runner.ui.main_window.subprocess.run",
        lambda commande, **kwargs: subprocess.CompletedProcess(
            commande, 1, stdout="", stderr="boom"))

    messages = []
    monkeypatch.setattr(
        "runner.ui.main_window.ErrorDialog.show_error",
        lambda *args, **kwargs: messages.append(args))
    ouverts = []
    monkeypatch.setattr(
        "runner.ui.main_window.QDesktopServices.openUrl",
        lambda url: ouverts.append(url))

    fenetre.open_allure_report()

    assert len(messages) == 1
    assert "boom" in messages[0][3]
    assert ouverts == []
