"""Lecture des resultats dans la sortie de pytest -v.

Quand un workspace affiche ses logs en direct (log_cli = true dans pytest.ini,
reglage courant pour du test materiel), pytest coupe la ligne de resultat en
deux : le nodeid, puis les enregistrements de log, puis le statut seul.

    test_carte.py::test_pso[nom-RSA-...-tc0]
    ----------------------------- live log call -----------------------------
    INFO     apdu APDU >> 00A4040007A0000000041010
    PASSED                                                          [ 16%]

L'analyse ligne par ligne ne voyait alors aucun resultat, donc aucun test ne se
colorait dans l'arbre, alors que les compteurs restaient justes puisqu'ils sont
relus dans le resume final de pytest.
"""

import subprocess
import sys
import textwrap

from core.pytest_executor import PytestOutputParser, parse_test_status_line


def feed_all(lignes):
    parser = PytestOutputParser()
    return [r for r in (parser.feed(l) for l in lignes) if r]


# ------------------------------------------------- format sur une seule ligne

def test_a_complete_line_is_read():
    assert parse_test_status_line("a/test_x.py::test_f PASSED [ 50%]") == ("a/test_x.py::test_f", "PASSED")


def test_the_parser_also_reads_complete_lines():
    assert feed_all(["a/test_x.py::test_f[cas] FAILED  [100%]"]) == [("a/test_x.py::test_f[cas]", "FAILED")]


def test_the_xdist_format_is_read():
    ligne = "[gw2] [ 33%] PASSED a/test_x.py::test_f[cas]"
    assert feed_all([ligne]) == [("a/test_x.py::test_f[cas]", "PASSED")]


# ----------------------------------------------------- statut sur une autre ligne

def test_a_status_separated_by_live_logs_is_attached_to_its_test():
    lignes = [
        "a/test_x.py::test_pso[nom-RSA-tc0] ",
        "-------------------------------- live log call ---------------------------------",
        "INFO     apdu:test_x.py:6 APDU >> 00A4040007A0000000041010",
        "INFO     apdu:test_x.py:7 APDU << 9000",
        "PASSED                                                                   [ 16%]",
    ]
    assert feed_all(lignes) == [("a/test_x.py::test_pso[nom-RSA-tc0]", "PASSED")]


def test_several_tests_in_a_row_keep_their_own_status():
    lignes = []
    for i, statut in enumerate(("PASSED", "FAILED", "SKIPPED")):
        lignes += [
            f"a/test_x.py::test_pso[tc{i}] ",
            "INFO     apdu APDU >> 00A4",
            f"{statut}                       [ {(i + 1) * 33}%]",
        ]

    assert feed_all(lignes) == [
        ("a/test_x.py::test_pso[tc0]", "PASSED"),
        ("a/test_x.py::test_pso[tc1]", "FAILED"),
        ("a/test_x.py::test_pso[tc2]", "SKIPPED"),
    ]


def test_a_status_without_a_pending_test_is_ignored():
    assert feed_all(["PASSED   [ 50%]"]) == []


def test_a_status_is_consumed_only_once():
    lignes = [
        "a/test_x.py::test_f ",
        "PASSED  [ 50%]",
        "PASSED  [100%]",   # sans nouveau nodeid : rien a rattacher
    ]
    assert feed_all(lignes) == [("a/test_x.py::test_f", "PASSED")]


# ------------------------------------------------------------- faux positifs

def test_the_final_summary_is_not_mistaken_for_a_result():
    """Le resume final commence aussi par un statut, mais porte son propre
    nodeid : l'attribuer au test en attente inventerait un resultat."""
    lignes = [
        "a/test_x.py::test_en_cours ",
        "=========================== short test summary info ============================",
        "FAILED b/test_autre.py::test_casse - assert 1 == 2",
    ]
    assert feed_all(lignes) == []


def test_an_error_summary_line_is_not_mistaken_for_a_result():
    lignes = [
        "a/test_x.py::test_en_cours ",
        "ERROR b/test_autre.py::test_casse - fixture manquante",
    ]
    assert feed_all(lignes) == []


def test_a_log_line_mentioning_passed_is_ignored():
    lignes = [
        "a/test_x.py::test_f ",
        "INFO     apdu Le test PASSED sur la carte",
    ]
    assert feed_all(lignes) == []


def test_a_separator_line_is_not_a_nodeid():
    assert feed_all(["____________ test_f[cas] ____________", "PASSED [ 50%]"]) == []


# ------------------------------------------------------- verification reelle

def test_a_real_run_with_live_logs_is_fully_read(tmp_path):
    """Bout en bout : c'est la configuration exacte qui ne colorait rien."""
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nlog_cli = true\nlog_cli_level = INFO\n", encoding="utf-8"
    )
    (tmp_path / "test_carte.py").write_text(textwrap.dedent('''
        import logging
        import pytest

        log = logging.getLogger("apdu")

        @pytest.mark.parametrize("cas", [f"nom-RSA-mod2048-tg1-tc{i}" for i in range(6)])
        def test_pso(cas):
            log.info("APDU >> 00A4040007A0000000041010")
            log.info("APDU << 9000")
            assert "tc5" not in cas
    '''), encoding="utf-8")

    sortie = subprocess.run(
        [sys.executable, "-u", "-m", "pytest", "-v", "--tb=short"],
        cwd=str(tmp_path), capture_output=True, text=True,
    ).stdout

    resultats = feed_all(sortie.splitlines())
    statuts = [s for _, s in resultats]

    assert len(resultats) == 6, f"6 resultats attendus, obtenu {resultats}"
    assert statuts.count("PASSED") == 5
    assert statuts.count("FAILED") == 1
    assert all("::test_pso[" in nodeid for nodeid, _ in resultats)


def test_a_real_run_without_live_logs_still_works(tmp_path):
    """La correction ne doit pas casser le cas normal."""
    (tmp_path / "test_simple.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('v', range(4))\n"
        "def test_x(v):\n    assert v < 3\n",
        encoding="utf-8",
    )

    sortie = subprocess.run(
        [sys.executable, "-u", "-m", "pytest", "-v", "--tb=short"],
        cwd=str(tmp_path), capture_output=True, text=True,
    ).stdout

    resultats = feed_all(sortie.splitlines())
    assert len(resultats) == 4
    assert [s for _, s in resultats].count("FAILED") == 1
