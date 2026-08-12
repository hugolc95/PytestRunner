"""Reglages pytest lus dans la configuration du workspace.

Le defaut signale : une suite dont le conftest importe un module voisin
(`import imports_MaTestSuite`) se collectait dans VS Code et echouait dans
l'interface. La cause : l'interface imposait `--import-mode=importlib`, le seul
mode qui n'insere PAS le dossier du fichier de test dans sys.path.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from core.test_discovery import collect_tests
from core.workspace_config import (
    import_mode_args,
    import_mode_for,
    looks_absolute,
    pythonpath_for,
    pytest_env,
    setting_for,
)


@pytest.fixture
def suite_avec_imports(tmp_path):
    """Reproduit la structure signalee : un conftest qui importe un module voisin."""
    dossier = tmp_path / "TSu" / "JC_API" / "Int" / "BioLockTestSuite"
    dossier.mkdir(parents=True)

    (dossier / "imports_BiolockTestSuite.py").write_text(textwrap.dedent('''
        import os
        import sys

        module_dir = os.path.abspath(os.path.dirname(__file__))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
    '''), encoding="utf-8")
    (dossier / "conftest.py").write_text(
        "import imports_BiolockTestSuite\n", encoding="utf-8")
    (dossier / "test_biolock.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    return tmp_path


# ----------------------------------------------------------- le defaut de pytest

def test_no_import_mode_is_imposed(tmp_path):
    """Le point central : ne rien imposer, comme la ligne de commande et VS Code."""
    assert import_mode_args(str(tmp_path)) == []


def test_a_suite_importing_a_neighbour_module_collects(suite_avec_imports):
    """Sans --import-mode=importlib, pytest insere le dossier du fichier de test
    en tete de sys.path et l'import du module voisin aboutit."""
    nodeids = collect_tests(str(suite_avec_imports))
    assert nodeids == ["TSu/JC_API/Int/BioLockTestSuite/test_biolock.py::test_ok"]


def test_importlib_really_is_what_broke_it(suite_avec_imports):
    """Verifie la cause plutot que de la supposer."""
    sortie = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--import-mode=importlib"],
        cwd=str(suite_avec_imports), capture_output=True, text=True,
    )
    assert "No module named 'imports_BiolockTestSuite'" in sortie.stdout + sortie.stderr


# ------------------------------------------------- le workspace peut choisir

def test_a_workspace_can_ask_for_importlib(tmp_path):
    """L'echappatoire pour les projets aux noms de fichiers dupliques."""
    (tmp_path / "config.yml").write_text("import_mode: importlib\n", encoding="utf-8")
    assert import_mode_args(str(tmp_path)) == ["--import-mode=importlib"]


@pytest.mark.parametrize("mode", ["prepend", "append", "importlib"])
def test_every_pytest_mode_is_accepted(tmp_path, mode):
    (tmp_path / "config.yml").write_text(f"import_mode: {mode}\n", encoding="utf-8")
    assert import_mode_for(str(tmp_path)) == mode


def test_an_unknown_mode_is_ignored(tmp_path):
    """Transmis tel quel, pytest refuserait de demarrer et l'utilisateur verrait
    une erreur d'usage a la place de ses tests."""
    (tmp_path / "config.yml").write_text("import_mode: magique\n", encoding="utf-8")
    assert import_mode_args(str(tmp_path)) == []


def test_the_setting_is_found_in_a_config_with_another_name(tmp_path):
    """Meme angle mort que pour LOG_PATH : la configuration ne s'appelle pas
    toujours config.yml."""
    (tmp_path / "configWorkspace.yml").write_text("import_mode: append\n", encoding="utf-8")
    assert import_mode_for(str(tmp_path)) == "append"


def test_a_setting_inside_a_section_is_found(tmp_path):
    (tmp_path / "config.yml").write_text(
        "General:\n  import_mode: append\n", encoding="utf-8")
    assert import_mode_for(str(tmp_path)) == "append"


def test_the_chosen_config_file_comes_first(tmp_path):
    (tmp_path / "config.yml").write_text("import_mode: prepend\n", encoding="utf-8")
    choisi = tmp_path / "autre.yml"
    choisi.write_text("import_mode: importlib\n", encoding="utf-8")

    assert import_mode_for(str(tmp_path), str(choisi)) == "importlib"


def test_a_workspace_without_configuration_is_transparent(tmp_path):
    assert import_mode_args(str(tmp_path)) == []
    assert pythonpath_for(str(tmp_path)) == []
    assert setting_for(str(tmp_path), ("quoi_que_ce_soit",)) is None


# ----------------------------------------------------------------- PYTHONPATH

def test_a_configured_path_reaches_the_tests(tmp_path):
    """L'equivalent du PYTHONPATH que VS Code compose pour la decouverte."""
    (tmp_path / "config.yml").write_text(
        "pythonpath:\n  - C:\\Projets\\SmartCardFramework\n", encoding="utf-8")

    env = pytest_env(str(tmp_path))
    assert env["PYTHONPATH"].startswith("C:\\Projets\\SmartCardFramework")


def test_a_relative_path_is_resolved_from_the_workspace(tmp_path):
    (tmp_path / "config.yml").write_text("pythonpath:\n  - lib\n", encoding="utf-8")
    assert pythonpath_for(str(tmp_path)) == [str(tmp_path / "lib")]


@pytest.mark.parametrize("chemin", [
    "C:\\Projets\\Framework", "C:/Projets/Framework", "/opt/framework",
    "\\\\serveur\\partage\\framework",
])
def test_an_absolute_path_is_left_alone(tmp_path, chemin):
    """Path.is_absolute() dependant de la plateforme, un chemin Windows relu
    sous Linux se retrouvait colle derriere le workspace."""
    assert looks_absolute(chemin)
    (tmp_path / "config.yml").write_text(f"pythonpath:\n  - {chemin}\n", encoding="utf-8")
    assert pythonpath_for(str(tmp_path)) == [chemin]


def test_a_single_string_can_hold_several_paths(tmp_path):
    import os

    valeur = os.pathsep.join(["/un", "/deux"])
    (tmp_path / "config.yml").write_text(f'pythonpath: "{valeur}"\n', encoding="utf-8")
    assert pythonpath_for(str(tmp_path)) == ["/un", "/deux"]


def test_the_existing_pythonpath_is_kept_behind(tmp_path, monkeypatch):
    """Un workspace doit pouvoir imposer sa version d'un framework, sans effacer
    ce que l'environnement apportait."""
    import os

    monkeypatch.setenv("PYTHONPATH", "/deja/present")
    (tmp_path / "config.yml").write_text("pythonpath:\n  - /prioritaire\n", encoding="utf-8")

    assert pytest_env(str(tmp_path))["PYTHONPATH"].split(os.pathsep) == [
        "/prioritaire", "/deja/present",
    ]


def test_without_configuration_the_environment_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/deja/present")
    assert pytest_env(str(tmp_path))["PYTHONPATH"] == "/deja/present"


def test_a_configured_path_is_importable_by_the_tests(tmp_path):
    """Bout en bout : un module hors du workspace devient importable."""
    framework = tmp_path / "framework"
    framework.mkdir()
    (framework / "faux_smartcard.py").write_text("VALEUR = 42\n", encoding="utf-8")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "config.yml").write_text(
        f"pythonpath:\n  - {framework}\n", encoding="utf-8")
    (workspace / "test_import.py").write_text(
        "import faux_smartcard\n\ndef test_ok():\n    assert faux_smartcard.VALEUR == 42\n",
        encoding="utf-8")

    assert collect_tests(str(workspace)) == ["test_import.py::test_ok"]


# --------------------------------------------- l'interpreteur suit la meme regle

def test_the_interpreter_is_read_from_any_config_name(tmp_path):
    """Meme angle mort : python_executable n'etait lu que dans config.yml."""
    from core.python_interpreter import interpreter_from_config

    (tmp_path / "configWorkspace.yml").write_text(
        "python_executable: C:\\Python313x32\\python.exe\n", encoding="utf-8")

    assert interpreter_from_config(str(tmp_path)) == "C:\\Python313x32\\python.exe"


# ------------------------------------------------- longueur des lignes console

from core.pytest_executor import compact_output_line, compact_path  # noqa: E402

LIGNE = ("TSu/JC_API/Int/BioLockTestSuite/test_BioLockTestSuite.py::TestSuiteBioLock::"
         "test_ComputeHash[datalen==2048_bytes] PASSED [ 12%]")


def test_a_test_line_keeps_its_suite_but_loses_the_climb():
    """Le reproche : avec une arborescence profonde, le chemin occupe
    l'essentiel de la ligne et se repete a chaque test."""
    court = compact_output_line(LIGNE)

    assert court.startswith("…/BioLockTestSuite/test_BioLockTestSuite.py::")
    assert "TSu/JC_API/Int" not in court
    assert court.endswith("PASSED [ 12%]"), "le statut reste intact"
    assert len(court) < len(LIGNE)


def test_a_traceback_line_keeps_its_full_path():
    """C'est le chemin complet qui permet de retrouver le fichier fautif."""
    ligne = "TSu/RA/Int/FlexiDep/test_flexi.py:34: AssertionError"
    assert compact_output_line(ligne) == ligne


def test_a_collection_error_keeps_its_full_path():
    ligne = "ERROR collecting TSu/JC_API/Int/BioLockTestSuite"
    assert compact_output_line(ligne) == ligne


def test_the_rootdir_header_is_untouched():
    ligne = "rootdir: C:\\Projets\\COSMO11_ADD_TST_CI\\testEnv\\test_insi"
    assert compact_output_line(ligne) == ligne


def test_the_summary_line_is_shortened_too():
    ligne = "FAILED TSu/RA/Int/FlexiDep/test_flexi.py::TestFlexi::test_deploy[cas-3] - Err"
    court = compact_output_line(ligne)
    assert court.startswith("FAILED …/FlexiDep/test_flexi.py::")


@pytest.mark.parametrize("niveaux, attendu", [
    (0, "…/test_x.py"),
    (1, "…/BioLockTestSuite/test_x.py"),
    (2, "…/Int/BioLockTestSuite/test_x.py"),
])
def test_the_number_of_kept_folders_is_adjustable(niveaux, attendu):
    assert compact_path("TSu/JC_API/Int/BioLockTestSuite/test_x.py", niveaux) == attendu


def test_the_original_line_can_be_kept_whole():
    assert compact_output_line(LIGNE, -1, show_classes=True) == LIGNE


def test_the_class_is_dropped_by_default():
    """Dans ces suites, la classe reprend le nom du fichier : trois fois le meme
    mot sur une ligne."""
    court = compact_output_line(LIGNE)
    assert "::TestSuiteBioLock::" not in court
    assert "::test_ComputeHash[datalen==2048_bytes]" in court


def test_the_class_can_be_kept():
    assert "::TestSuiteBioLock::" in compact_output_line(LIGNE, show_classes=True)


def test_a_test_without_class_is_unaffected():
    ligne = "…/suite/test_x.py::test_ok PASSED"
    assert compact_output_line(ligne, 1) == ligne


def test_a_short_path_is_left_alone():
    """Rien a gagner, et une ellipse serait un mensonge."""
    ligne = "test_x.py::test_ok PASSED"
    assert compact_output_line(ligne) == ligne
    assert compact_path("dossier/test_x.py", 1) == "dossier/test_x.py"


def test_windows_separators_survive():
    assert compact_path("TSu\\Int\\Suite\\test_x.py", 1) == "…\\Suite\\test_x.py"


def test_the_workspace_chooses_the_level(tmp_path):
    (tmp_path / "config.yml").write_text("console_path_levels: 0\n", encoding="utf-8")
    from core.workspace_config import console_path_levels
    assert console_path_levels(str(tmp_path)) == 0


@pytest.mark.parametrize("valeur, attendu", [("full", -1), ("complet", -1), ("short", 0), ("3", 3)])
def test_the_level_accepts_words_as_well_as_numbers(tmp_path, valeur, attendu):
    (tmp_path / "config.yml").write_text(f'console_path_levels: "{valeur}"\n', encoding="utf-8")
    from core.workspace_config import console_path_levels
    assert console_path_levels(str(tmp_path)) == attendu


def test_an_unreadable_level_falls_back_to_the_default(tmp_path):
    """Mieux vaut le defaut qu'une information qui disparait."""
    (tmp_path / "config.yml").write_text("console_path_levels: beaucoup\n", encoding="utf-8")
    from core.workspace_config import DEFAULT_CONSOLE_PATH_LEVELS, console_path_levels
    assert console_path_levels(str(tmp_path)) == DEFAULT_CONSOLE_PATH_LEVELS


def test_the_raw_output_survives_for_traces_and_history(qtbot, tmp_path):
    """Le raccourcissement ne concerne QUE l'affichage : la trace d'echec et
    l'historique se lisent dans la sortie brute, ou les chemins sont entiers."""
    from gui_qt.main_window import PytestWorker

    suite = tmp_path / "TSu" / "JC_API" / "Int" / "MaSuite"
    suite.mkdir(parents=True)
    (suite / "test_x.py").write_text("def test_ko():\n    assert False\n", encoding="utf-8")

    worker = PytestWorker(nodeids=[], workspace=str(tmp_path), targets=["."])
    affiche: list[str] = []
    brut: list[str] = []
    worker.stdout_signal.connect(affiche.append)
    worker.finished_signal.connect(lambda code, sortie: brut.append(sortie))

    worker.run()

    console = "".join(affiche)
    sortie = brut[0]
    assert "…/MaSuite/test_x.py::test_ko" in console, "l'affichage est raccourci"
    assert "TSu/JC_API/Int/MaSuite/test_x.py::test_ko" in sortie.replace("\\", "/"), \
        "la sortie brute garde le chemin complet"


# ------------------------------------------------- le niveau de classe dans l'arbre

from core.test_tree import build_test_tree  # noqa: E402


def noms(noeuds):
    return [n.name for n in noeuds]


def test_a_lone_class_disappears_from_the_tree():
    """Elle ne distingue rien et reprend souvent le nom du fichier."""
    arbre = build_test_tree(["suite/test_x.py::TestSuiteX::test_a",
                             "suite/test_x.py::TestSuiteX::test_b"])
    fichier = arbre[0].children[0]

    assert fichier.name == "test_x.py"
    assert noms(fichier.children) == ["test_a", "test_b"]


def test_several_classes_keep_their_level():
    """La garde essentielle : sans elle, deux tests de meme nom se retrouveraient
    cote a cote sans plus rien pour les distinguer."""
    arbre = build_test_tree(["suite/test_x.py::TestA::test_f",
                             "suite/test_x.py::TestB::test_f"])
    fichier = arbre[0].children[0]

    assert noms(fichier.children) == ["TestA", "TestB"]


def test_a_class_beside_module_level_tests_keeps_its_level():
    arbre = build_test_tree(["suite/test_x.py::test_f",
                             "suite/test_x.py::TestA::test_f"])
    fichier = arbre[0].children[0]

    assert "TestA" in noms(fichier.children)


def test_nested_lone_classes_are_all_removed():
    arbre = build_test_tree(["suite/test_x.py::TestA::TestB::test_f"])
    fichier = arbre[0].children[0]

    assert noms(fichier.children) == ["test_f"]


def test_parametrized_cases_keep_their_function_level():
    """Seule la classe part : la fonction reste, elle regroupe ses cas."""
    arbre = build_test_tree(["suite/test_x.py::TestSuiteX::test_f[cas1]",
                             "suite/test_x.py::TestSuiteX::test_f[cas2]"])
    fichier = arbre[0].children[0]

    assert noms(fichier.children) == ["test_f"]
    assert noms(fichier.children[0].children) == ["[cas1]", "[cas2]"]


def test_the_target_still_names_the_class():
    """L'affichage change, pas ce qui est passe a pytest."""
    arbre = build_test_tree(["suite/test_x.py::TestSuiteX::test_f[cas1]"])
    fonction = arbre[0].children[0].children[0]

    assert fonction.target == "suite/test_x.py::TestSuiteX::test_f"
    assert fonction.children[0].nodeid == "suite/test_x.py::TestSuiteX::test_f[cas1]"


def test_the_class_can_be_kept_in_the_tree():
    arbre = build_test_tree(["suite/test_x.py::TestSuiteX::test_a"], show_classes=True)
    fichier = arbre[0].children[0]

    assert noms(fichier.children) == ["TestSuiteX"]


def test_a_test_added_during_a_run_lands_at_the_same_level(qtbot):
    """Un cas inconnu ajoute en cours de run ne doit pas recreer la classe que
    l'arbre a masquee, sinon la meme fonction apparaitrait deux fois."""
    from gui_qt.test_tree_view import TestTreeView

    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(["suite/test_x.py::TestSuiteX::test_f[cas1]"]))

    tree.update_single_test("suite/test_x.py::TestSuiteX::test_f[cas2]",
                            "PASSED", create_missing=True)

    fichier = tree.model.item(0).child(0)
    assert [fichier.child(r).text() for r in range(fichier.rowCount())] == ["test_f"]
    fonction = fichier.child(0)
    assert [fonction.child(r).text() for r in range(fonction.rowCount())] == ["[cas1]", "[cas2]"]


def test_a_run_respects_a_tree_that_shows_its_classes(qtbot):
    """Quand l'arbre affiche ses classes, l'ajout doit s'y ranger aussi."""
    from gui_qt.test_tree_view import TestTreeView

    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(["suite/test_x.py::TestA::test_f[cas1]",
                                    "suite/test_x.py::TestB::test_g"]))

    tree.update_single_test("suite/test_x.py::TestA::test_f[cas2]",
                            "PASSED", create_missing=True)

    fichier = tree.model.item(0).child(0)
    classes = [fichier.child(r).text() for r in range(fichier.rowCount())]
    assert classes == ["TestA", "TestB"]
    fonction = fichier.child(0).child(0)
    assert [fonction.child(r).text() for r in range(fonction.rowCount())] == ["[cas1]", "[cas2]"]
