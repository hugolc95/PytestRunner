"""Couleurs ANSI des logs.

Beaucoup de conftest colorent leurs traces pour la console (`ESC[31m`). Sans
les interpreter, une zone de texte Qt affiche ces sequences en toutes lettres
au milieu de chaque ligne, et la couleur est perdue.
"""

import pytest
from PyQt5.QtCore import QSettings

from core.ansi import Style, contient_ansi, parse_ansi, strip_ansi

ESC = "\x1b"


# -------------------------------------------------------------- analyse du texte

def test_plain_text_is_left_alone():
    assert parse_ansi("rien de special") == [("rien de special", Style())]
    assert not contient_ansi("rien de special")


def test_a_coloured_run_is_isolated():
    morceaux = parse_ansi(f"avant {ESC}[31mrouge{ESC}[0m apres")
    assert [t for t, _ in morceaux] == ["avant ", "rouge", " apres"]
    assert morceaux[1][1].couleur == "red"
    assert morceaux[0][1].neutre and morceaux[2][1].neutre


def test_the_escape_sequences_never_reach_the_screen():
    """Le defaut visible : `[31m` ecrit en toutes lettres dans le log."""
    texte = f"{ESC}[1;32mOK{ESC}[0m fin"
    assert "[31m" not in strip_ansi(texte)
    assert ESC not in strip_ansi(texte)
    assert strip_ansi(texte) == "OK fin"


def test_bold_and_colour_combine():
    (_, style), = parse_ansi(f"{ESC}[1;31mx")
    assert style.couleur == "red" and style.gras


def test_bright_colours_are_marked_as_such():
    (_, style), = parse_ansi(f"{ESC}[92mx")
    assert style.couleur == "green" and style.vive


def test_a_reset_clears_everything():
    morceaux = parse_ansi(f"{ESC}[1;4;31ma{ESC}[0mb")
    assert morceaux[1][1].neutre


def test_default_foreground_keeps_the_other_attributes():
    """`39` remet la couleur par defaut, sans annuler le gras."""
    morceaux = parse_ansi(f"{ESC}[1;31ma{ESC}[39mb")
    assert morceaux[1][1].couleur is None
    assert morceaux[1][1].gras


def test_256_colour_mode():
    (_, style), = parse_ansi(f"{ESC}[38;5;196mx")
    assert style.couleur.startswith("#")


def test_true_colour_mode():
    (_, style), = parse_ansi(f"{ESC}[38;2;18;52;86mx")
    assert style.couleur == "#123456"


def test_background_codes_are_ignored():
    """Reecrire le fond d'une ligne la rendrait illisible des qu'il jure avec
    le theme choisi."""
    (_, style), = parse_ansi(f"{ESC}[41mx")
    assert style.neutre


def test_non_colour_sequences_are_removed_too():
    """Un effacement de ligne ou un deplacement de curseur ne colore rien mais
    s'afficherait en toutes lettres."""
    assert strip_ansi(f"a{ESC}[2Kb{ESC}[1;5Hc") == "abc"


def test_a_style_spans_several_lines_until_reset():
    morceaux = parse_ansi(f"{ESC}[31mligne1\nligne2{ESC}[0m")
    assert morceaux[0][0] == "ligne1\nligne2"
    assert morceaux[0][1].couleur == "red"


def test_an_empty_text_gives_nothing():
    assert parse_ansi("") == []


# ------------------------------------------------------- traduction en couleurs

def test_ansi_colours_follow_the_theme():
    """Le rouge vif d'un terminal passe sous le seuil de lisibilite sur fond
    clair : chaque theme a ses propres teintes."""
    from gui_qt.styles import styles

    styles.set_theme("light")
    clair = styles.ansi_color("red")
    styles.set_theme("dark")
    sombre = styles.ansi_color("red")

    assert clair != sombre
    styles.set_theme("light")


def test_an_explicit_hex_colour_is_used_as_is():
    from gui_qt.styles import styles

    assert styles.ansi_color("#123456") == "#123456"


# ---------------------------------------------------------------- panneau Log

@pytest.fixture
def panel(qtbot, tmp_path):
    from gui_qt.detail_panel import DetailPanel

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "module").mkdir()
    (tmp_path / "module" / "test_exemple.py").write_text(
        "def test_cible():\n    pass\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("log_directory: logs\n", encoding="utf-8")

    widget = DetailPanel()
    qtbot.addWidget(widget)
    widget.set_workspace(str(tmp_path))
    return widget, tmp_path


def _ecrire_log(tmp_path, contenu):
    dossier = tmp_path / "logs" / "20260813" / "module"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "test_cible.log").write_text(contenu, encoding="utf-8")


def test_a_coloured_log_shows_no_escape_sequences(panel):
    widget, tmp_path = panel
    _ecrire_log(tmp_path, f"{ESC}[32mVerdict : OK{ESC}[0m\nligne suivante\n")

    widget.show_for("module/test_exemple.py::test_cible",
                    "module/test_exemple.py::test_cible")

    affiche = widget.log_view.toPlainText()
    assert "Verdict : OK" in affiche
    assert "[32m" not in affiche and ESC not in affiche


def test_a_coloured_log_really_gets_its_colour(panel):
    widget, tmp_path = panel
    _ecrire_log(tmp_path, f"neutre {ESC}[31mrouge{ESC}[0m\n")

    widget.show_for("module/test_exemple.py::test_cible",
                    "module/test_exemple.py::test_cible")

    from gui_qt.styles import styles
    from PyQt5.QtGui import QTextCursor

    curseur = widget.log_view.textCursor()
    curseur.movePosition(QTextCursor.Start)
    # Se placer dans le mot "rouge" (apres "neutre ").
    curseur.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, 9)
    couleur = curseur.charFormat().foreground().color().name()

    assert couleur == styles.ansi_color("red")


def test_a_plain_log_keeps_the_keyword_highlighter(panel):
    """Sans couleur ANSI, c'est le coloriseur par mots-cles qui renseigne."""
    widget, tmp_path = panel
    _ecrire_log(tmp_path, "2026-08-13 19:10:13,886 - INFO - APDU Status : 9000\n")

    widget.show_for("module/test_exemple.py::test_cible",
                    "module/test_exemple.py::test_cible")

    assert widget.log_highlighters[0].document() is widget.log_view.document()


def test_the_keyword_highlighter_steps_aside_for_ansi(panel):
    """Deux coloriseurs superposes donnent un resultat que personne n'a choisi :
    le programme qui ecrit le log a deja dit quoi colorer."""
    widget, tmp_path = panel
    _ecrire_log(tmp_path, f"{ESC}[31mINFO rouge malgre le mot-cle{ESC}[0m\n")

    widget.show_for("module/test_exemple.py::test_cible",
                    "module/test_exemple.py::test_cible")

    assert widget.log_highlighters[0].document() is None
