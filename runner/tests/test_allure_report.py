"""Le bouton Allure : place dans la barre, et ce qu'il fait quand on clique.

Genere et ouvre un rapport a partir des resultats du DERNIER run demarre --
jamais rien s'il l'interpreteur n'a pas le plugin, jamais rien si l'outil
`allure` n'est pas sur le PATH. Les deux cas doivent le dire clairement
plutot que de planter ou de rester muets.

Un seul rapport pour tous les lecteurs d'un run : ce qui les distingue a
l'interieur est le parametre "Reader" que `reader_isolation.py` pose sur
chaque test (teste dans test_reader_isolation.py), pas un dossier separe.
La generation tourne sur un `QThread` (`AllureReportWorker`), aussi bien au
clic qu'automatiquement en fin de run -- les tests qui la declenchent
doivent donc laisser la boucle d'evenements Qt tourner le temps qu'elle
finisse.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from runner.domain import execution
from runner.domain import interpreter as interpreter_mod
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader, RunRequest
from runner.ui.main_window import _environnement_pour_allure, _GestionnaireAllure


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.domain import history as history_mod
    from runner.domain.workspace import Workspace
    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace(path=str(tmp_path), config_path="", settings={})
    # Sans ca, `f.history.racine` pointe sur le VRAI `~/.pytest_runner` de la
    # machine qui fait tourner la suite -- les rapports et l'historique
    # Allure generes par un test resteraient sur disque pour de vrai, et
    # pollueraient le test suivant (deux clics different sur le meme dossier
    # "latest", un historique deja present avant le premier test qui en a
    # besoin).
    f.history = history_mod.History(racine=tmp_path / "pytest_runner_history")
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _attendre_generation(fenetre, qapp, timeout_ms: int = 5000) -> None:
    """Laisse le worker Allure finir, et la boucle Qt livrer son signal.

    `AllureReportWorker` tourne dans son propre QThread : le signal `done`
    n'atteint `_sur_allure_genere` (sur le fil de la fenetre) qu'au prochain
    passage de la boucle d'evenements Qt."""
    worker = fenetre._allure_worker
    if worker is None:
        return
    worker.wait(timeout_ms)
    for _ in range(50):
        qapp.processEvents()
        if fenetre._allure_worker is None:
            return


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
    assert fenetre._allure_dir_for("python") == ""


def test_no_allure_dir_when_the_interpreter_was_never_probed(fenetre, monkeypatch):
    """Le probe tourne en fond : un run qui demarre avant qu'il finisse ne
    doit pas attendre, juste se passer d'Allure cette fois-ci."""
    monkeypatch.setattr(interpreter_mod, "cached_probe", lambda path: None)
    assert fenetre._allure_dir_for("python") == ""


def test_an_allure_dir_is_created_when_the_plugin_is_present(fenetre, monkeypatch):
    monkeypatch.setattr(interpreter_mod, "cached_probe",
                        lambda path: InterpreterInfo(path=path, has_allure=True))

    dossier = fenetre._allure_dir_for("python")

    assert dossier
    assert Path(dossier).is_dir()


def test_the_allure_dir_is_always_the_same_one_across_runs(fenetre, monkeypatch):
    """Le coeur du changement : pytest n'efface rien dans `--alluredir`, donc
    reutiliser TOUJOURS le meme dossier accumule les resultats de tous les
    runs passes -- c'est ce qui permet a Allure de montrer l'historique
    complet de chaque test dans son onglet Retries, pas seulement une
    tendance globale."""
    monkeypatch.setattr(interpreter_mod, "cached_probe",
                        lambda path: InterpreterInfo(path=path, has_allure=True))

    premier = fenetre._allure_dir_for("python")
    second = fenetre._allure_dir_for("python")

    assert premier == second


def test_two_real_runs_send_pytest_to_the_same_alluredir(fenetre, monkeypatch):
    """Meme verification, mais par le vrai chemin qu'un utilisateur emprunte
    (`run_selected` -> `_start`), pas par un appel direct a `_allure_dir_for`."""
    from runner.domain.execution import Collection

    fenetre._on_collected(Collection(nodeids=("t.py::test_a",)))
    fenetre.model.set_all_checked(True)
    monkeypatch.setattr(fenetre, "_require_interpreter", lambda: "python")
    monkeypatch.setattr(interpreter_mod, "cached_probe",
                        lambda path: InterpreterInfo(path=path, has_allure=True))
    demandes = []
    monkeypatch.setattr(fenetre.service, "start",
                        lambda requete, env: demandes.append(requete) or True)

    fenetre.run_selected()
    fenetre.run_selected()

    assert len(demandes) == 2
    assert demandes[0].allure_dir == demandes[1].allure_dir
    assert demandes[0].run_id != demandes[1].run_id, (
        "chaque run garde son propre identifiant d'historique, "
        "seul le dossier Allure est partage")


# ------------------------------------------------- JAVA_HOME mal renseignee

def test_java_home_with_a_single_valid_path_is_untouched(monkeypatch, tmp_path):
    jdk = tmp_path / "jdk11"
    jdk.mkdir()
    monkeypatch.setenv("JAVA_HOME", str(jdk))

    assert _environnement_pour_allure()["JAVA_HOME"] == str(jdk)


def test_java_home_with_several_paths_keeps_the_first_valid_one(monkeypatch, tmp_path):
    """Le cas reel rapporte : plusieurs JDK installes au fil du temps ont
    chacun ajoute leur chemin a JAVA_HOME au lieu de le remplacer."""
    jdk11 = tmp_path / "jdk11"
    jdk11.mkdir()
    jdk8 = tmp_path / "jdk8"
    jdk8.mkdir()
    monkeypatch.setenv("JAVA_HOME", f"{jdk11}{os.pathsep}{jdk8}")

    assert _environnement_pour_allure()["JAVA_HOME"] == str(jdk11)


def test_java_home_skips_a_listed_path_that_does_not_exist(monkeypatch, tmp_path):
    jdk8 = tmp_path / "jdk8"
    jdk8.mkdir()
    disparu = tmp_path / "jamais_installe"
    monkeypatch.setenv("JAVA_HOME", f"{disparu}{os.pathsep}{jdk8}")

    assert _environnement_pour_allure()["JAVA_HOME"] == str(jdk8)


def test_java_home_is_left_alone_when_nothing_listed_exists(monkeypatch, tmp_path):
    """Aucun des chemins listes n'existe : on laisse la vraie erreur d'allure
    remonter plutot que de la masquer avec une valeur tout aussi fausse."""
    valeur = f"{tmp_path / 'a'}{os.pathsep}{tmp_path / 'b'}"
    monkeypatch.setenv("JAVA_HOME", valeur)

    assert _environnement_pour_allure()["JAVA_HOME"] == valeur


def test_no_java_home_at_all_does_not_crash(monkeypatch):
    monkeypatch.delenv("JAVA_HOME", raising=False)

    env = _environnement_pour_allure()

    assert env.get("JAVA_HOME", "") == ""


# -------------------------------------------- la commande pytest reelle

class _FauxProcessus:
    """Assez d'un Popen pour que `ReaderRun.run()` aille jusqu'au bout sans
    jamais lancer de vrai pytest."""

    returncode = 0

    def readline(self):
        return ""

    def wait(self):
        pass


def _lancer_avec_popen_capture(monkeypatch, tmp_path, allure_dir: str,
                               readers: tuple = (Reader("", 0),),
                               lecteur: Reader | None = None) -> list:
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
        nodeids=("t.py::test_a",), readers=readers,
        allure_dir=allure_dir,
    )
    execution.ReaderRun(requete, lecteur or readers[0], {}).run(
        lambda l: None, lambda o: None)
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


def test_two_readers_share_the_same_alluredir(monkeypatch, tmp_path):
    """Un seul rapport pour tout le run : deux lecteurs ecrivent au meme
    endroit. Les fichiers allure-pytest sont nommes par UUID, ils ne
    s'ecrasent donc jamais -- ce qui les distingue DANS le rapport commun
    est le parametre "Reader" pose par reader_isolation.py, pas le dossier."""
    base = tmp_path / "allure-results"
    lecteur_a = Reader("Cosmo11Secured Reader", 0)
    lecteur_b = Reader("TestBiosWrapperTU Reader", 1)

    commande_a = _lancer_avec_popen_capture(
        monkeypatch, tmp_path, str(base), readers=(lecteur_a, lecteur_b),
        lecteur=lecteur_a)
    commande_b = _lancer_avec_popen_capture(
        monkeypatch, tmp_path, str(base), readers=(lecteur_a, lecteur_b),
        lecteur=lecteur_b)

    assert f"--alluredir={base}" in commande_a
    assert f"--alluredir={base}" in commande_b


def test_a_lone_named_reader_still_writes_directly_to_the_base_dir(monkeypatch, tmp_path):
    """Le cas courant : un seul lecteur, meme nomme, ecrit directement dans
    le dossier de base -- pas de sous-dossier a chercher pour lui non plus."""
    base = tmp_path / "allure-results"
    lecteur = Reader("Cosmo11Secured Reader", 0)

    commande = _lancer_avec_popen_capture(
        monkeypatch, tmp_path, str(base), readers=(lecteur,), lecteur=lecteur)

    assert f"--alluredir={base}" in commande


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


def _generation_simulee(commande, **kwargs):
    """Remplace `allure generate` : ecrit un vrai index.html et un dossier
    history/ la ou `-o` le demande, pour verifier que le serveur local sert
    vraiment le premier et que le second est bien recupere ensuite -- pas
    seulement que la bonne commande a ete construite."""
    rapport = Path(commande[commande.index("-o") + 1])
    rapport.mkdir(parents=True, exist_ok=True)
    (rapport / "index.html").write_text("<html>rapport</html>", encoding="utf-8")
    (rapport / "history").mkdir(exist_ok=True)
    (rapport / "history" / "history-trend.json").write_text("[]", encoding="utf-8")
    return subprocess.CompletedProcess(commande, 0, stdout="", stderr="")


def test_a_successful_generation_opens_the_report(fenetre, monkeypatch, tmp_path, qapp):
    """L'ouverture directe de index.html en file:// bloque tous ses appels
    AJAX (CORS) et reste sur "Loading…" -- le rapport doit passer par le
    petit serveur HTTP local, jamais par une URL de fichier."""
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")

    appels = []
    monkeypatch.setattr(
        "runner.services.allure_service.subprocess.run",
        lambda commande, **kwargs: appels.append((commande, kwargs)) or
        _generation_simulee(commande, **kwargs))

    ouverts = []
    monkeypatch.setattr(
        "runner.ui.main_window.QDesktopServices.openUrl",
        lambda url: ouverts.append(url.toString()))

    fenetre.open_allure_report()
    _attendre_generation(fenetre, qapp)

    assert appels
    commande, kwargs = appels[0]
    assert commande[0] == "/usr/bin/allure"
    assert commande[1] == "generate"
    # Le vrai appel passe bien par la correction de JAVA_HOME (`env=`), pas
    # seulement la fonction testee en isolation ci-dessus.
    assert "env" in kwargs

    assert len(ouverts) == 1
    assert re.fullmatch(r"http://127\.0\.0\.1:\d+/index\.html", ouverts[0]), ouverts[0]

    # Le serveur sert vraiment le fichier -- pas juste une URL qui y ressemble.
    contenu = urllib.request.urlopen(ouverts[0], timeout=3).read()
    assert b"rapport" in contenu


def test_the_handler_never_touches_stderr(monkeypatch):
    """Le point precis du bug, isole de tout le reste : `log_message()` ne
    doit jamais chercher a ecrire quoi que ce soit."""
    monkeypatch.setattr(sys, "stderr", None)
    # Ne doit lever aucune exception, meme avec sys.stderr a None.
    _GestionnaireAllure.log_message(object(), "%s", "peu importe")


def test_the_server_survives_a_console_less_build(fenetre, monkeypatch, tmp_path, qapp):
    """Cas reel rapporte : le rapport s'ouvrait mais restait vide, chaque
    autre onglet en 404 -- le navigateur affichait ERR_EMPTY_RESPONSE.

    PytestRunner.spec construit l'appli avec `console=False` : sous Windows,
    `sys.stderr` y vaut `None`. Le gestionnaire HTTP par defaut journalise
    CHAQUE requete sur `sys.stderr`, DEPUIS `send_response()` -- donc avant
    d'ecrire le moindre octet. L'exception qui en resulte coupe la reponse
    a cet instant precis : le navigateur voit une connexion fermee sans
    aucune donnee, symptome identique a ce qui a ete rapporte.
    """
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr("runner.services.allure_service.subprocess.run", _generation_simulee)
    ouverts = []
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: ouverts.append(url.toString()))

    ancien_stderr = sys.stderr
    sys.stderr = None
    try:
        fenetre.open_allure_report()
        _attendre_generation(fenetre, qapp)
        contenu = urllib.request.urlopen(ouverts[0], timeout=3).read()
    finally:
        sys.stderr = ancien_stderr

    assert b"rapport" in contenu


def test_reopening_the_report_reuses_the_same_server(fenetre, monkeypatch, tmp_path, qapp):
    """Un serveur par session suffit : le rapport change de contenu sous le
    meme dossier a chaque clic, pas besoin d'en relancer un a chaque fois --
    et en relancer un occuperait un nouveau port a chaque clic, pour rien."""
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr("runner.services.allure_service.subprocess.run", _generation_simulee)
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: None)

    fenetre.open_allure_report()
    _attendre_generation(fenetre, qapp)
    premier_serveur = fenetre._allure_server
    assert premier_serveur is not None

    fenetre.open_allure_report()
    _attendre_generation(fenetre, qapp)

    assert fenetre._allure_server is premier_serveur


def test_closing_the_window_shuts_the_server_down(fenetre, monkeypatch, tmp_path, qapp):
    """Un serveur HTTP oublie en arriere-plan survivrait a la fermeture de la
    fenetre -- le port resterait occupe tant que le processus tourne."""
    from PyQt5.QtGui import QCloseEvent

    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr("runner.services.allure_service.subprocess.run", _generation_simulee)
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: None)

    fenetre.open_allure_report()
    _attendre_generation(fenetre, qapp)
    serveur = fenetre._allure_server
    assert serveur is not None

    fenetre.closeEvent(QCloseEvent())

    assert serveur.socket.fileno() == -1, "le socket du serveur n'a pas ete ferme"


def test_a_failed_generation_shows_allures_own_error(fenetre, monkeypatch, tmp_path, qapp):
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr(
        "runner.services.allure_service.subprocess.run",
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
    _attendre_generation(fenetre, qapp)

    assert len(messages) == 1
    assert "boom" in messages[0][3]
    assert ouverts == []


# --------------------------------------------- generation automatique et file d'attente

def test_a_finished_run_regenerates_the_report_on_its_own(fenetre, monkeypatch, tmp_path, qapp):
    """Le coeur de la demande : l'utilisateur ne doit jamais avoir a cliquer
    sur le bouton Allure juste pour rafraichir le HTML apres un run."""
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    appels = []
    monkeypatch.setattr(
        "runner.services.allure_service.subprocess.run",
        lambda commande, **kwargs: appels.append(commande) or
        _generation_simulee(commande, **kwargs))
    ouverts = []
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: ouverts.append(url))

    fenetre._on_run_finished([])
    _attendre_generation(fenetre, qapp)

    assert appels, "la generation doit partir toute seule a la fin du run"
    assert ouverts == [], "mais rien ne doit s'ouvrir sans que l'utilisateur ait clique"


def test_a_run_finishing_without_allure_results_does_not_try_to_generate(fenetre, monkeypatch, tmp_path):
    """Interpreteur sans allure-pytest : `_last_allure_dir` reste vide, la
    fin du run ne doit rien tenter de generer."""
    fenetre._last_allure_dir = ""
    appels = []
    monkeypatch.setattr("runner.services.allure_service.subprocess.run",
                        lambda commande, **kwargs: appels.append(commande))

    fenetre._on_run_finished([])

    assert appels == []
    assert fenetre._allure_worker is None


def test_clicking_while_a_generation_is_already_running_does_not_start_a_second_one(
        fenetre, monkeypatch, tmp_path, qapp):
    """Cas reel : l'auto-regeneration vient de partir en fin de run, et
    l'utilisateur clique tout de suite sur Allure. Il ne doit pas y avoir
    deux `allure generate` concurrents sur le meme dossier -- juste une
    ouverture des que celui deja en cours finit."""
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")

    demarre = threading.Event()
    poursuivre = threading.Event()

    def _generation_lente(commande, **kwargs):
        demarre.set()
        poursuivre.wait(5)
        return _generation_simulee(commande, **kwargs)

    monkeypatch.setattr("runner.services.allure_service.subprocess.run", _generation_lente)
    ouverts = []
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: ouverts.append(url.toString()))

    fenetre._lancer_generation_allure(ouvrir_apres=False)  # l'auto-regeneration
    assert demarre.wait(2), "la generation n'a jamais demarre"
    premier_worker = fenetre._allure_worker
    assert premier_worker is not None and premier_worker.isRunning()

    fenetre.open_allure_report()  # le clic pendant qu'elle tourne encore

    assert fenetre._allure_worker is premier_worker, "un second worker a ete lance"
    assert fenetre._allure_open_en_attente is True

    poursuivre.set()
    _attendre_generation(fenetre, qapp)

    assert len(ouverts) == 1


# ------------------------------------------------------- l'historique Allure

def test_history_is_stashed_after_a_successful_generation(fenetre, monkeypatch, tmp_path, qapp):
    """Le coeur de l'autre demande : sans ca, chaque generation reparlait
    d'une tendance vide -- jamais d'historique visible entre deux builds."""
    resultats = tmp_path / "allure-results"
    resultats.mkdir()
    (resultats / "result.json").write_text("{}", encoding="utf-8")
    fenetre._last_allure_dir = str(resultats)

    monkeypatch.setattr("runner.ui.main_window.shutil.which",
                        lambda name: "/usr/bin/allure")
    monkeypatch.setattr("runner.services.allure_service.subprocess.run", _generation_simulee)
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: None)

    fenetre.open_allure_report()
    _attendre_generation(fenetre, qapp)

    stash = fenetre._allure_history_stash()
    assert (stash / "history-trend.json").is_file()


def test_the_stashed_history_is_restored_into_the_next_run(fenetre, tmp_path):
    stash = fenetre._allure_history_stash()
    stash.mkdir(parents=True)
    (stash / "history-trend.json").write_text('["build precedent"]', encoding="utf-8")

    resultats = tmp_path / "allure-results"
    resultats.mkdir()

    fenetre._restaurer_historique_allure(resultats)

    assert (resultats / "history" / "history-trend.json").read_text() \
        == '["build precedent"]'
