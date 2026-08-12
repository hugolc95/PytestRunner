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
