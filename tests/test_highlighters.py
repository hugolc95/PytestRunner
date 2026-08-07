"""Coloration du code source, de la sortie pytest et des logs.

La coloration est appliquee a l'affichage, pas via --color=yes : les codes ANSI
de pytest se retrouveraient sinon dans la sortie brute qui sert a l'historique,
a l'extraction des traces d'echec et a la detection des statuts. Ces tests
verrouillent ce principe autant que le rendu.
"""

import pytest
from PyQt5.QtGui import QTextDocument

from gui_qt.highlighters import (
    MAX_HIGHLIGHT_LENGTH,
    LogHighlighter,
    PythonHighlighter,
    PytestOutputHighlighter,
)
from gui_qt.status_icons import forget_status_icons
from gui_qt.styles import styles


@pytest.fixture(autouse=True)
def isolate_theme():
    styles.set_theme("light")
    forget_status_icons()
    yield
    styles.set_theme("light")
    forget_status_icons()


def colors_of(highlighter_class, texte: str, ligne: int = 0) -> dict[str, str]:
    """Couleur appliquee a chaque caractere de la ligne demandee, indexee par
    le fragment de texte concerne."""
    document = QTextDocument()
    document.setPlainText(texte)
    highlighter_class(document)

    bloc = document.findBlockByNumber(ligne)
    resultat = {}
    for plage in bloc.layout().formats():
        fragment = bloc.text()[plage.start:plage.start + plage.length]
        couleur = plage.format.foreground().color().name()
        resultat[fragment] = couleur
    return resultat


# ------------------------------------------------------------------ sortie pytest

def test_passed_and_failed_get_different_colors():
    passed = colors_of(PytestOutputHighlighter, "a/test_x.py::test_f PASSED [ 50%]")
    failed = colors_of(PytestOutputHighlighter, "a/test_x.py::test_f FAILED [ 50%]")

    assert passed["PASSED"] == styles.output_color("passed")
    assert failed["FAILED"] == styles.output_color("failed")
    assert passed["PASSED"] != failed["FAILED"]


def test_skipped_has_its_own_color():
    colore = colors_of(PytestOutputHighlighter, "a/test_x.py::test_f SKIPPED [ 50%]")
    assert colore["SKIPPED"] == styles.output_color("skipped")


def test_assertion_lines_of_a_traceback_are_marked():
    colore = colors_of(PytestOutputHighlighter, "E       assert 1 == 2")
    assert any(couleur == styles.output_color("traceback") for couleur in colore.values())


def test_separators_are_dimmed():
    colore = colors_of(PytestOutputHighlighter, "=========== short test summary info ===========")
    assert any(couleur == styles.output_color("separator") for couleur in colore.values())


def test_an_ordinary_line_is_left_alone():
    assert colors_of(PytestOutputHighlighter, "collecting ... ") == {}


# ------------------------------------------------------------------ code Python

def test_keywords_are_colored():
    colore = colors_of(PythonHighlighter, "def test_f():")
    assert colore["def"] == styles.syntax_color("keyword")


def test_the_function_name_is_colored_apart_from_the_keyword():
    colore = colors_of(PythonHighlighter, "def test_addition():")
    assert colore.get("test_addition") == styles.syntax_color("function")


def test_class_names_are_colored():
    colore = colors_of(PythonHighlighter, "class TestSuite:")
    assert colore.get("TestSuite") == styles.syntax_color("classname")


def test_strings_are_colored():
    colore = colors_of(PythonHighlighter, 'valeur = "attendu"')
    assert colore['"attendu"'] == styles.syntax_color("string")


def test_comments_are_colored():
    colore = colors_of(PythonHighlighter, "x = 1  # explication")
    assert colore["# explication"] == styles.syntax_color("comment")


def test_decorators_are_colored():
    colore = colors_of(PythonHighlighter, "@pytest.mark.parametrize")
    assert colore["@pytest.mark.parametrize"] == styles.syntax_color("decorator")


def test_numbers_are_colored():
    colore = colors_of(PythonHighlighter, "taille = 2048")
    assert colore["2048"] == styles.syntax_color("number")


def test_a_docstring_spanning_lines_stays_colored(qtbot):
    source = 'def f():\n    """Ligne un\n    Ligne deux"""\n    return 1\n'
    milieu = colors_of(PythonHighlighter, source, ligne=2)
    assert any(couleur == styles.syntax_color("docstring") for couleur in milieu.values())


def test_code_after_a_docstring_is_colored_normally():
    source = 'def f():\n    """Doc"""\n    return 1\n'
    apres = colors_of(PythonHighlighter, source, ligne=2)
    assert apres.get("return") == styles.syntax_color("keyword")


# ------------------------------------------------------------------------- logs

def test_log_levels_are_colored():
    colore = colors_of(LogHighlighter, "2026-08-07 09:51:11,494 - INFO - APDU >> 00A4")
    assert colore["INFO"] == styles.output_color("info")


def test_error_level_stands_out():
    colore = colors_of(LogHighlighter, "2026-08-07 09:51:11 - ERROR - carte absente")
    assert colore["ERROR"] == styles.output_color("failed")


def test_the_timestamp_is_dimmed():
    colore = colors_of(LogHighlighter, "2026-08-07 09:51:11,494 - INFO - message")
    assert any(couleur == styles.output_color("timestamp") for couleur in colore.values())


def test_apdu_frames_are_highlighted():
    colore = colors_of(LogHighlighter, "APDU >> 00A4040007A0000000041010")
    assert colore.get("00A4040007A0000000041010") == styles.output_color("nodeid")


# -------------------------------------------------------------------- garde-fous

def test_an_enormous_line_is_left_uncolored():
    """Analyser une ligne demesuree couterait cher sur le thread de l'interface
    pour un gain visuel nul."""
    ligne = "PASSED " + "A" * (MAX_HIGHLIGHT_LENGTH + 10)
    assert colors_of(PytestOutputHighlighter, ligne) == {}


def test_colors_follow_the_theme():
    clair = colors_of(PytestOutputHighlighter, "a/test_x.py::test_f PASSED")["PASSED"]
    styles.set_theme("dark")
    sombre = colors_of(PytestOutputHighlighter, "a/test_x.py::test_f PASSED")["PASSED"]
    assert clair != sombre


def test_refresh_rebuilds_the_colors_after_a_theme_change():
    document = QTextDocument()
    document.setPlainText("a/test_x.py::test_f PASSED")
    highlighter = PytestOutputHighlighter(document)

    def couleur_passed():
        bloc = document.findBlockByNumber(0)
        for plage in bloc.layout().formats():
            if bloc.text()[plage.start:plage.start + plage.length] == "PASSED":
                return plage.format.foreground().color().name()
        return None

    avant = couleur_passed()
    styles.set_theme("dark")
    highlighter.refresh()
    assert couleur_passed() != avant
