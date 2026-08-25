"""L'interpreteur Python des tests : sa resolution, et le piege de l'exe fige.

Le bug que ce fichier existe pour empecher : une fois l'interface empaquetee
par PyInstaller, `sys.executable` pointe vers l'exe de l'INTERFACE, pas vers
un Python. Le lancer en sous-processus pour collecter les tests ne lance pas
pytest -- il relance une copie de l'interface. Une nouvelle fenetre s'ouvre,
sans le moindre arbre puisque aucune collecte n'a jamais eu lieu, et rien ne
dit pourquoi. C'est exactement la panne rapportee : "je fais Load, ca me
rouvre une instance de pytest runner et il n'y a aucun tree".
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from runner.domain import interpreter as interpreter_mod
from runner.domain.interpreter import InterpreterInfo, default, is_frozen, probe
from runner.domain.workspace import Workspace

FICHIER = textwrap.dedent('''\
    import pytest

    def test_atr():
        assert True
''')


# =========================================================================
# is_frozen / default -- le coeur du correctif
# =========================================================================


def test_not_frozen_uses_the_current_python(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not is_frozen()
    assert default() == sys.executable


def test_frozen_never_returns_the_apps_own_exe(monkeypatch):
    """Le coeur du bug : un exe fige ne doit JAMAIS se relancer lui-meme."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/fake/dist/PytestRunner.exe", raising=False)
    monkeypatch.setattr(interpreter_mod.shutil, "which",
                        lambda nom: "/usr/bin/python3" if nom == "python3" else None)

    resultat = default()

    assert resultat == "/usr/bin/python3"
    assert resultat != sys.executable


def test_frozen_without_any_python_on_the_path_admits_it(monkeypatch):
    """Pas de repli silencieux sur l'exe : une chaine vide, que l'appelant
    doit traiter comme "rien de configure", jamais comme un chemin valide."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(interpreter_mod.shutil, "which", lambda nom: None)

    assert default() == ""


def test_frozen_tries_python_then_python3_then_py(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    vus = []

    def which(nom):
        vus.append(nom)
        return "/usr/bin/py" if nom == "py" else None

    monkeypatch.setattr(interpreter_mod.shutil, "which", which)
    assert default() == "/usr/bin/py"
    assert vus == ["python", "python3", "py"]


# =========================================================================
# Workspace : la meme regle, exposee au reste de l'application
# =========================================================================


def test_a_workspace_without_a_declared_interpreter_uses_the_default(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert Workspace.load(str(tmp_path)).declared_interpreter == ""
    assert Workspace.load(str(tmp_path)).interpreter == sys.executable


def test_a_declared_interpreter_always_wins(tmp_path, monkeypatch):
    """L'interface peut tourner en 32 bits pendant que les tests chargent des
    DLL 64 bits : ce choix de projet ne doit jamais etre court-circuite."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    (tmp_path / "config.yml").write_text(
        "python_executable: /opt/py64/python\n", encoding="utf-8")

    ws = Workspace.load(str(tmp_path))
    assert ws.declared_interpreter == "/opt/py64/python"
    assert ws.interpreter == "/opt/py64/python"


def test_a_frozen_workspace_never_leaks_the_apps_exe(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/fake/dist/PytestRunner.exe", raising=False)
    monkeypatch.setattr(interpreter_mod.shutil, "which",
                        lambda nom: "/usr/bin/python3" if nom == "python3" else None)

    ws = Workspace.load(str(tmp_path))
    assert ws.interpreter == "/usr/bin/python3"


# =========================================================================
# probe() : verifier un interpreteur avant de s'en servir
# =========================================================================


def test_probing_the_current_python_finds_pytest():
    """Le Python qui fait tourner cette suite a forcement pytest : c'est le
    cas le plus simple qui doit marcher."""
    info = probe(sys.executable, use_cache=False)
    assert info.ok
    assert info.pytest_version
    assert info.bits in (32, 64)


def test_probing_a_missing_path_reports_it_without_raising():
    info = probe("/definitely/not/a/real/interpreter", use_cache=False)
    assert not info.ok
    assert "not found" in info.error.lower()


def test_probing_an_empty_path_reports_it_without_raising():
    info = probe("", use_cache=False)
    assert not info.ok


def test_the_probe_is_cached(monkeypatch, tmp_path):
    """Un probe lance un vrai processus : le repeter a chaque lancement de
    tests gelerait l'interface."""
    faux = tmp_path / "faux_python"
    faux.write_text("#!/bin/sh\necho appele\n", encoding="utf-8")
    faux.chmod(0o755)

    appels = []
    original = interpreter_mod._run_probe

    def compte(path, timeout):
        appels.append(path)
        return original(path, timeout)

    monkeypatch.setattr(interpreter_mod, "_run_probe", compte)

    probe(str(faux))
    probe(str(faux))
    assert len(appels) == 1


def test_use_cache_false_always_re_runs():
    probe(sys.executable, use_cache=True)
    interpreter_mod.forget_probe()
    a = probe(sys.executable, use_cache=False)
    b = probe(sys.executable, use_cache=False)
    assert a.ok and b.ok


def test_a_summary_says_when_pytest_is_missing():
    info = InterpreterInfo(path="/usr/bin/python3", version="3.11.0", bits=64)
    assert "MISSING" in info.summary()


def test_probe_detects_allure_pytest_when_installed(tmp_path):
    """Le vrai `_run_probe` lance un sous-processus : un faux interpreteur qui
    imite sa sortie verifie le parsing sans avoir besoin d'allure-pytest
    reellement installe dans l'environnement de la suite."""
    faux = tmp_path / "faux_python"
    faux.write_text("#!/bin/sh\nprintf '3.11.0\\n64\\n7.0.0\\nyes\\nyes\\n'\n",
                    encoding="utf-8")
    faux.chmod(0o755)

    info = probe(str(faux), use_cache=False)
    assert info.has_allure


def test_probe_says_allure_is_missing_when_the_import_fails(tmp_path):
    faux = tmp_path / "faux_python"
    faux.write_text("#!/bin/sh\nprintf '3.11.0\\n64\\n7.0.0\\nyes\\n\\n'\n",
                    encoding="utf-8")
    faux.chmod(0o755)

    info = probe(str(faux), use_cache=False)
    assert not info.has_allure


def test_forgetting_one_path_does_not_clear_the_others(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b""), b.write_bytes(b"")
    monkeypatch.setattr(interpreter_mod, "_run_probe",
                        lambda path, timeout: InterpreterInfo(path=path, version="3.11"))

    probe(str(a))
    probe(str(b))
    interpreter_mod.forget_probe(str(a))

    assert interpreter_mod.cached_probe(str(a)) is None
    assert interpreter_mod.cached_probe(str(b)) is not None


# =========================================================================
# La fenetre : priorite, garde-fou, dialogue
# =========================================================================


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path, monkeypatch):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    monkeypatch.delattr(sys, "frozen", raising=False)
    (tmp_path / "test_demo.py").write_text(FICHIER, encoding="utf-8")

    w = MainWindow()
    w.workspace = Workspace.load(str(tmp_path))
    return w


def test_with_nothing_configured_the_window_falls_back_to_default(fenetre):
    assert fenetre._effective_interpreter() == default()


def test_the_global_override_is_used_when_the_workspace_declares_nothing(fenetre):
    fenetre._interpreter_override = "/opt/custom/python"
    assert fenetre._effective_interpreter() == "/opt/custom/python"


def test_the_workspace_declaration_beats_the_global_override(fenetre, tmp_path):
    """Le reglage global est une commodite ; la configuration d'un projet
    precis ne doit jamais s'effacer devant lui par accident."""
    (tmp_path / "config.yml").write_text(
        "python_executable: /opt/py64/python\n", encoding="utf-8")
    fenetre.workspace = Workspace.load(str(tmp_path))
    fenetre._interpreter_override = "/opt/other/python"

    assert fenetre._effective_interpreter() == "/opt/py64/python"


def test_without_a_workspace_the_override_still_applies(fenetre):
    fenetre.workspace = None
    fenetre._interpreter_override = "/opt/custom/python"
    assert fenetre._effective_interpreter() == "/opt/custom/python"


def test_require_interpreter_explains_itself_instead_of_spawning_garbage(
        fenetre, monkeypatch):
    """Le point precis du bug rapporte : sans interpreteur resolu, rien ne
    doit etre lance -- ni pytest, ni, pire, l'exe lui-meme."""
    monkeypatch.setattr(fenetre, "_effective_interpreter", lambda: "")

    lance = []
    monkeypatch.setattr("runner.ui.main_window.ErrorDialog.show_error",
                        staticmethod(lambda *a, **k: lance.append(a)))

    assert fenetre._require_interpreter() == ""
    assert lance, "aucune explication n'a ete montree"
    assert "interpreter" in lance[0][2].lower()


def test_loading_a_workspace_without_an_interpreter_never_starts_a_collector(
        fenetre, monkeypatch):
    monkeypatch.setattr(fenetre, "_require_interpreter", lambda: "")
    fenetre.workspace_combo.setCurrentText(fenetre.workspace.path)

    demarres = []
    from runner.services.run_service import CollectWorker

    monkeypatch.setattr(CollectWorker, "start", lambda self: demarres.append(1))
    fenetre.load_workspace()

    assert demarres == []


def test_running_without_an_interpreter_never_starts_the_service(fenetre, monkeypatch):
    from runner.domain.tree import build_tree

    fenetre.model.set_tree(build_tree(["test_demo.py::test_atr"]))
    monkeypatch.setattr(fenetre, "_require_interpreter", lambda: "")

    lances = []
    fenetre.service.start = lambda requete, env: lances.append(requete) or True

    fenetre._start(["test_demo.py::test_atr"])
    assert lances == []


def test_accepting_the_dialog_persists_the_override(fenetre, monkeypatch):
    from runner.ui.interpreter_dialog import InterpreterDialog
    from runner.ui.main_window import K_INTERPRETER

    class FausseDialogue:
        Accepted = InterpreterDialog.Accepted

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return self.Accepted

        def interpreter_path(self):
            return "/opt/pinned/python"

    monkeypatch.setattr("runner.ui.main_window.InterpreterDialog", FausseDialogue)
    monkeypatch.setattr(fenetre, "load_workspace", lambda: None)

    fenetre.open_interpreter_dialog()

    assert fenetre._interpreter_override == "/opt/pinned/python"
    assert fenetre.settings.value(K_INTERPRETER) == "/opt/pinned/python"


def test_cancelling_the_dialog_changes_nothing(fenetre, monkeypatch):
    from runner.ui.interpreter_dialog import InterpreterDialog

    class FausseDialogue:
        Accepted = InterpreterDialog.Accepted

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return 0  # Rejected

        def interpreter_path(self):
            return "/should/not/be/used"

    monkeypatch.setattr("runner.ui.main_window.InterpreterDialog", FausseDialogue)
    fenetre._interpreter_override = "/opt/kept/python"

    fenetre.open_interpreter_dialog()
    assert fenetre._interpreter_override == "/opt/kept/python"


def test_changing_the_interpreter_reloads_an_open_workspace(fenetre, monkeypatch):
    """Un arbre collecte avec l'ancien interpreteur peut ne plus correspondre
    a ce que le nouveau verrait -- l'utilisateur ne doit pas avoir a y penser."""
    from runner.ui.interpreter_dialog import InterpreterDialog

    class FausseDialogue:
        Accepted = InterpreterDialog.Accepted

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return self.Accepted

        def interpreter_path(self):
            return "/opt/new/python"

    monkeypatch.setattr("runner.ui.main_window.InterpreterDialog", FausseDialogue)
    recharge = []
    monkeypatch.setattr(fenetre, "load_workspace", lambda: recharge.append(1))

    fenetre.open_interpreter_dialog()
    assert recharge == [1]


def test_the_dialog_does_not_reload_when_the_workspace_pins_its_own(
        fenetre, tmp_path, monkeypatch):
    """Le workspace a deja gagne la priorite : changer le reglage global ne
    changera rien pour lui, recharger serait un travail pour rien."""
    (tmp_path / "config.yml").write_text(
        "python_executable: /opt/pinned/python\n", encoding="utf-8")
    fenetre.workspace = Workspace.load(str(tmp_path))

    from runner.ui.interpreter_dialog import InterpreterDialog

    class FausseDialogue:
        Accepted = InterpreterDialog.Accepted

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return self.Accepted

        def interpreter_path(self):
            return "/opt/other/python"

    monkeypatch.setattr("runner.ui.main_window.InterpreterDialog", FausseDialogue)
    recharge = []
    monkeypatch.setattr(fenetre, "load_workspace", lambda: recharge.append(1))

    fenetre.open_interpreter_dialog()
    assert recharge == []


# =========================================================================
# Le dialogue lui-meme
# =========================================================================


@pytest.fixture
def dialogue(qapp):
    from runner.ui.interpreter_dialog import InterpreterDialog

    d = InterpreterDialog(current="", declared_by_workspace="")
    yield d
    # Le probe lance un vrai processus : sans attendre sa fin, detruire la
    # fenetre pendant qu'il tourne encore fait planter le programme (QThread
    # detruit en plein travail).
    d.wait_for_probe()


def test_opening_the_dialog_probes_the_default_interpreter(dialogue, qapp):
    from PyQt5.QtCore import QEventLoop, QTimer

    boucle = QEventLoop()
    QTimer.singleShot(3000, boucle.quit)
    if dialogue._probe is not None:
        dialogue._probe.done.connect(boucle.quit)
    boucle.exec_()
    dialogue.wait_for_probe()

    assert dialogue.status_label.text()
    assert "Checking" not in dialogue.status_label.text()


def test_a_workspace_override_is_shown_as_a_note(qapp):
    """`isVisible()` repond toujours faux tant que la fenetre n'a pas ete
    montree, meme apres un `setVisible(True)` explicite : c'est `isHidden()`
    qu'il faut lire pour ce test, comme partout ailleurs dans ce depot."""
    from runner.ui.interpreter_dialog import InterpreterDialog

    d = InterpreterDialog(current="", declared_by_workspace="/opt/pinned/python")
    try:
        assert not d.override_label.isHidden()
        assert "/opt/pinned/python" in d.override_label.text()
    finally:
        d.wait_for_probe()


def test_no_workspace_override_hides_the_note(dialogue):
    assert dialogue.override_label.isHidden()
