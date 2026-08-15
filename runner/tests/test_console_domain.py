"""Lecture de la sortie pytest : couleurs, blocs d'echec, lentilles.

La sortie de reference n'est pas inventee : c'est celle d'un vrai run
`pytest -v --tb=short` sur une suite qui echoue de trois facons differentes
(assertion, assertion parametree, erreur de fixture). Un echantillon ecrit a
la main aurait valide mes regex contre mes propres suppositions.
"""

from __future__ import annotations

import pytest

from runner.domain import console, failures
from runner.domain.ansi import Style, contient_ansi, parse_ansi, strip_ansi
from runner.domain.console import Lens

SORTIE = """\
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- /usr/local/bin/python
rootdir: /home/user/ws
plugins: qt-4.5.0, xdist-3.8.0
collecting ... collected 6 items

test_demo.py::TestApdu::test_select_aid FAILED                           [ 16%]
test_demo.py::TestApdu::test_read_record[0] PASSED                       [ 33%]
test_demo.py::TestApdu::test_read_record[1] FAILED                       [ 50%]
test_demo.py::test_module_level PASSED                                   [ 66%]
test_demo.py::test_needs_reader ERROR                                    [ 83%]
test_demo.py::test_skipped SKIPPED (no card)                             [100%]

==================================== ERRORS ====================================
_____________________ ERROR at setup of test_needs_reader ______________________
test_demo.py:20: in broken
    raise RuntimeError("reader not connected")
E   RuntimeError: reader not connected
=================================== FAILURES ===================================
___________________________ TestApdu.test_select_aid ___________________________
test_demo.py:7: in test_select_aid
    assert sw == 0x9000, "SW mismatch: expected 9000, got 9E EE"
E   AssertionError: SW mismatch: expected 9000, got 9E EE
E   assert 40686 == 36864
_________________________ TestApdu.test_read_record[1] _________________________
test_demo.py:11: in test_read_record
    assert i == 0
E   assert 1 == 0
=========================== short test summary info ============================
FAILED test_demo.py::TestApdu::test_select_aid - AssertionError: SW mismatch:...
FAILED test_demo.py::TestApdu::test_read_record[1] - assert 1 == 0
ERROR test_demo.py::test_needs_reader - RuntimeError: reader not connected
=============== 2 failed, 2 passed, 1 skipped, 1 error in 0.02s ================
"""

LIGNES = SORTIE.splitlines()


# =========================================================================
# Sequences ANSI
# =========================================================================


def test_a_plain_line_comes_back_untouched():
    assert parse_ansi("hello") == [("hello", Style())]
    assert not contient_ansi("hello")


def test_the_escape_codes_never_reach_the_text():
    texte = "\x1b[31mSW 9E EE\x1b[0m ok"
    assert strip_ansi(texte) == "SW 9E EE ok"
    assert "\x1b" not in strip_ansi(texte)
    assert "[31m" not in strip_ansi(texte)


def test_a_colour_applies_until_it_is_reset():
    morceaux = parse_ansi("\x1b[32mgreen\x1b[0mplain")
    assert morceaux == [("green", Style(couleur="green")), ("plain", Style())]


@pytest.mark.parametrize("texte, attendu", [
    ("\x1b[91mvif\x1b[0m", Style(couleur="red", vive=True)),
    ("\x1b[1;34mgras\x1b[0m", Style(couleur="blue", gras=True)),
    ("\x1b[38;5;46mcube\x1b[0m", Style(couleur="#00ff00")),
    ("\x1b[38;2;255;128;0mvraie\x1b[0m", Style(couleur="#ff8000")),
])
def test_every_colour_mode_is_understood(texte, attendu):
    assert parse_ansi(texte)[0][1] == attendu


def test_a_cursor_move_is_removed_without_leaving_its_letters():
    # Une sequence sans couleur ne doit pas s'afficher en toutes lettres.
    assert strip_ansi("a\x1b[2Kb") == "ab"


def test_a_background_code_changes_nothing():
    # Repeindre le fond d'une ligne dans un theme choisi la rendrait illisible.
    assert parse_ansi("\x1b[41mrouge\x1b[0m")[0][1] == Style()


# =========================================================================
# Blocs d'echec
# =========================================================================


def test_every_failure_block_is_found_once():
    titres = [f.title for f in failures.split_failures(SORTIE)]
    assert titres == [
        "test_needs_reader",
        "TestApdu.test_select_aid",
        "TestApdu.test_read_record[1]",
    ]


def test_an_underscore_in_the_test_name_does_not_break_the_header():
    """Le separateur des en-tetes est le caractere le plus courant d'un nom.

    `____ TestApdu.test_select_aid ____` : une regle qui interdit le
    separateur au milieu du titre ne reconnait plus aucun en-tete reel.
    """
    titres = [f.title for f in failures.split_failures(SORTIE)]
    assert "TestApdu.test_select_aid" in titres
    assert "TestApdu.test_read_record[1]" in titres


def test_a_setup_error_keeps_the_phase_that_produced_it():
    bloc = failures.split_failures(SORTIE)[0]
    assert (bloc.kind, bloc.phase) == ("error", "setup")


def test_the_headline_is_the_first_exception_line():
    index = failures.index_failures(SORTIE)
    bloc = index["TestApdu.test_select_aid"]
    assert bloc.headline == "AssertionError: SW mismatch: expected 9000, got 9E EE"
    # La seconde ligne `E` reste dans le corps : elle explique la premiere.
    assert "assert 40686 == 36864" in bloc.body


def test_the_body_stops_before_the_next_header():
    index = failures.index_failures(SORTIE)
    assert "test_read_record" not in index["TestApdu.test_select_aid"].body


def test_the_body_stops_at_the_summary_banner():
    index = failures.index_failures(SORTIE)
    assert "short test summary" not in index["TestApdu.test_read_record[1]"].body


@pytest.mark.parametrize("nodeid, attendu", [
    ("test_demo.py::TestApdu::test_select_aid", "TestApdu.test_select_aid"),
    ("test_demo.py::TestApdu::test_read_record[1]", "TestApdu.test_read_record[1]"),
    ("a/b/test_demo.py::test_needs_reader", "test_needs_reader"),
    ("test_demo.py", "test_demo.py"),
])
def test_a_nodeid_maps_to_the_title_pytest_prints(nodeid, attendu):
    assert failures.title_for_nodeid(nodeid) == attendu


def test_a_test_that_passed_has_no_block():
    index = failures.index_failures(SORTIE)
    assert failures.failure_for(index, "test_demo.py::test_module_level") is None


def test_two_tests_of_the_same_name_are_flagged_rather_than_guessed():
    """pytest n'imprime pas le fichier dans ses en-tetes.

    Deux `test_login` dans deux fichiers donnent le meme titre : montrer la
    trace de l'un pour l'autre serait pire que de le signaler.
    """
    doublon = SORTIE + (
        "=================================== FAILURES ===================================\n"
        "___________________________ TestApdu.test_select_aid ___________________________\n"
        "other.py:3: in test_select_aid\n"
        "E   AssertionError: something else\n"
        "=============================== 1 failed =====================================\n"
    )
    bloc = failures.index_failures(doublon)["TestApdu.test_select_aid"]
    assert bloc.ambiguous
    # Le premier bloc est conserve : on n'ecrase pas ce qu'on savait deja.
    assert "SW mismatch" in bloc.headline


def test_setup_and_teardown_errors_of_one_test_are_joined():
    texte = (
        "==================================== ERRORS ====================================\n"
        "_____________________ ERROR at setup of test_thing ______________________\n"
        "E   RuntimeError: no reader\n"
        "____________________ ERROR at teardown of test_thing ____________________\n"
        "E   RuntimeError: still busy\n"
        "============================== 1 error =======================================\n"
    )
    bloc = failures.index_failures(texte)["test_thing"]
    assert not bloc.ambiguous
    assert "no reader" in bloc.body and "still busy" in bloc.body


def test_an_output_without_any_failure_yields_nothing():
    assert failures.split_failures("== 3 passed in 0.1s ==") == []
    assert failures.split_failures("") == []


@pytest.mark.parametrize("ligne, nature", [
    ("E   AssertionError: boom", "exception"),
    (">       assert x == 1", "code"),
    ("test_demo.py:7: in test_select_aid", "frame"),
    ("------------------ Captured stdout call ------------------", "section"),
    ("    raise RuntimeError('x')", "text"),
])
def test_each_kind_of_traceback_line_is_recognised(ligne, nature):
    assert failures.classify_line(ligne) == nature


def test_a_coloured_traceback_line_is_classified_on_its_text():
    assert failures.classify_line("\x1b[31mE   AssertionError\x1b[0m") == "exception"


# =========================================================================
# Lentilles
# =========================================================================


def test_all_shows_the_output_untouched():
    assert console.apply_lens(LIGNES, Lens.ALL) == LIGNES


def test_problems_drops_the_verdicts_the_tree_already_shows():
    retenues = console.apply_lens(LIGNES, Lens.PROBLEMS)
    assert "test_demo.py::TestApdu::test_read_record[0] PASSED                       [ 33%]" not in retenues
    # Un echec, lui, reste : c'est par la qu'on entre dans la trace.
    assert any("test_select_aid FAILED" in l for l in retenues)


def test_problems_keeps_the_failing_statement_even_without_a_marker():
    """Avec `--tb=short`, la ligne de code fautive n'a aucun marqueur.

    Elle est simplement indentee sous son cadre. Une regle sans memoire la
    jetterait avec le reste du bruit, et il ne resterait de la trace que le
    message d'exception -- sans le code qui l'a produit.
    """
    retenues = console.apply_lens(LIGNES, Lens.PROBLEMS)
    assert '    assert sw == 0x9000, "SW mismatch: expected 9000, got 9E EE"' in retenues
    assert "    raise RuntimeError(\"reader not connected\")" in retenues


def test_problems_hides_much_more_than_it_keeps_on_a_real_run():
    retenues = console.apply_lens(LIGNES, Lens.PROBLEMS)
    assert len(retenues) < len(LIGNES)


def test_outline_keeps_only_the_shape_of_the_run():
    retenues = console.apply_lens(LIGNES, Lens.OUTLINE)
    assert any("collected 6 items" in l for l in retenues)
    assert any("2 failed, 2 passed" in l for l in retenues)
    assert any(l.startswith("FAILED test_demo.py") for l in retenues)
    # Ni verdicts ligne a ligne, ni contenu de trace.
    assert not any("PASSED" in l and "::" in l for l in retenues)
    assert not any(l.startswith("E   ") for l in retenues)


def test_outline_is_short_enough_to_read_at_a_glance():
    assert len(console.apply_lens(LIGNES, Lens.OUTLINE)) <= 12


def test_the_filter_forgets_its_section_when_it_is_reset():
    """Un rendu qui repart du debut du tampon doit repartir du bon etat.

    Sans remise a zero, une console figee dans `FAILURES` garderait toutes les
    lignes du run suivant.
    """
    filtre = console.LensFilter(Lens.PROBLEMS)
    filtre.keep("=================================== FAILURES ===================================")
    assert filtre.keep("    du bruit quelconque")
    filtre.reset()
    assert not filtre.keep("    du bruit quelconque")
