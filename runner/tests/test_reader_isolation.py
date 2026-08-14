"""Chaque processus doit voir SON lecteur, et lui seul.

Le mecanisme est le point le plus delicat du multi-lecteur : s'il echoue en
silence, tous les lecteurs jouent la meme valeur et les resultats se
ressemblent sans que rien ne le signale.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from runner.domain.reader_isolation import (
    ENV_CONFIG,
    ENV_READER,
    PLUGIN_MODULE,
    reader_plugin,
)


def test_without_a_config_file_the_plugin_stays_out_of_the_way():
    with reader_plugin("") as (args, dossier):
        assert args == [] and dossier == ""


def test_the_plugin_is_written_and_cleaned_up(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Reader: A\n", encoding="utf-8")

    with reader_plugin(str(config)) as (args, dossier):
        assert args == ["-p", PLUGIN_MODULE]
        assert (Path(dossier) / f"{PLUGIN_MODULE}.py").is_file()

    assert not Path(dossier).exists(), "rien ne doit rester dans le temporaire"


def _run_pytest(tmp_path, config, reader, corps_du_test):
    """Lance un vrai pytest avec le plugin, et rend son code de sortie."""
    (tmp_path / "test_reader.py").write_text(corps_du_test, encoding="utf-8")

    with reader_plugin(str(config)) as (args, dossier):
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": dossier,
            ENV_READER: reader,
            ENV_CONFIG: str(config),
        }
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *args, "test_reader.py"],
            cwd=tmp_path, capture_output=True, text=True, env=env, timeout=90,
        )


@pytest.mark.parametrize("lecteur", ["Reader A", "Reader B"])
def test_the_test_code_reads_the_reader_it_was_given(tmp_path, lecteur):
    """Bout en bout : le code de test lit `Reader` dans le fichier, sans savoir
    que quoi que ce soit a ete detourne."""
    config = tmp_path / "config.yml"
    config.write_text("Reader: valeur d'origine\nMode: PERSO\n", encoding="utf-8")

    corps = textwrap.dedent(f'''
        import pathlib, yaml

        def getConfigReader():
            texte = pathlib.Path(__file__).with_name("config.yml").read_text(
                encoding="utf-8")
            return yaml.safe_load(texte)["Reader"]

        def test_reader():
            assert getConfigReader() == {lecteur!r}
    ''')
    assert _run_pytest(tmp_path, config, lecteur, corps).returncode == 0


def test_a_getter_that_enriches_the_value_keeps_its_own_logic(tmp_path):
    """Le defaut d'une approche par remplacement de fonction : tout traitement
    que le workspace ajoute par-dessus la cle disparaitrait avec elle."""
    config = tmp_path / "config.yml"
    config.write_text("Reader: origine\n", encoding="utf-8")

    corps = textwrap.dedent('''
        import pathlib, yaml

        def getConfigReader():
            texte = pathlib.Path(__file__).with_name("config.yml").read_text(
                encoding="utf-8")
            return "hub:" + yaml.safe_load(texte)["Reader"]

        def test_reader():
            assert getConfigReader() == "hub:Reader A"
    ''')
    assert _run_pytest(tmp_path, config, "Reader A", corps).returncode == 0


def test_the_real_file_on_disk_is_never_modified(tmp_path):
    """Deux processus simultanes s'ecraseraient l'un l'autre s'il l'etait."""
    config = tmp_path / "config.yml"
    origine = "Reader: intouchable\nMode: PERSO\n"
    config.write_text(origine, encoding="utf-8")

    corps = "def test_ok():\n    assert True\n"
    _run_pytest(tmp_path, config, "Reader A", corps)

    assert config.read_text(encoding="utf-8") == origine


def test_comments_and_key_order_survive_the_substitution(tmp_path):
    """L'edition est faite a la ligne : un yaml.safe_dump reordonnerait les
    cles et effacerait les commentaires du fichier vu par les tests."""
    config = tmp_path / "config.yml"
    config.write_text(
        "# entete\nMode: PERSO\nReader: origine  # le lecteur\nRSAkey: 3072\n",
        encoding="utf-8")

    corps = textwrap.dedent('''
        import pathlib

        def test_reader():
            texte = pathlib.Path(__file__).with_name("config.yml").read_text(
                encoding="utf-8")
            assert "# entete" in texte
            assert "# le lecteur" in texte
            assert texte.index("Mode:") < texte.index("Reader:") < texte.index("RSAkey:")
            assert "Reader: Reader A" in texte
    ''')
    assert _run_pytest(tmp_path, config, "Reader A", corps).returncode == 0


def test_a_config_without_a_reader_key_fails_loudly(tmp_path):
    """Continuer ferait tourner tous les lecteurs sur la meme valeur, sans que
    rien ne le signale. Mieux vaut un run rouge qu'un resultat faux."""
    config = tmp_path / "config.yml"
    config.write_text("Mode: PERSO\n", encoding="utf-8")

    resultat = _run_pytest(tmp_path, config, "Reader A",
                           "def test_ok():\n    assert True\n")
    assert resultat.returncode != 0
    assert "Could not pin reader" in (resultat.stdout + resultat.stderr)


@pytest.mark.parametrize("lecture", [
    'open(chemin, encoding="utf-8").read()',
    'pathlib.Path(chemin).read_text(encoding="utf-8")',
    'pathlib.Path(chemin).read_bytes().decode("utf-8")',
])
def test_every_way_of_reading_the_file_is_covered(tmp_path, lecture):
    """Un workspace lit sa configuration comme il veut : `open()`, `read_text`
    ou `read_bytes`. En couvrir deux sur trois laisse une porte ouverte par
    laquelle le vrai lecteur passe sans etre remplace."""
    config = tmp_path / "config.yml"
    config.write_text("Reader: origine\n", encoding="utf-8")

    corps = textwrap.dedent(f'''
        import pathlib, yaml

        def test_reader():
            chemin = str(pathlib.Path(__file__).with_name("config.yml"))
            texte = {lecture}
            assert yaml.safe_load(texte)["Reader"] == "Reader A"
    ''')
    assert _run_pytest(tmp_path, config, "Reader A", corps).returncode == 0
