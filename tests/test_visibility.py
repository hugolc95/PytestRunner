"""Lisibilite des reperes visuels dans les deux themes.

Deux defauts signales a l'usage : la surbrillance de ligne courante se voyait
mal selon le theme, et les fleches de deploiement de l'arbre disparaissaient sur
fond sombre. Ces tests mesurent le contraste plutot que de s'en remettre a
l'oeil, pour qu'un futur ajustement de palette ne les fasse pas resortir.
"""

import pytest

from gui_qt.status_icons import forget_status_icons
from gui_qt.styles import styles


@pytest.fixture(autouse=True)
def isolate_theme():
    styles.set_theme("light")
    forget_status_icons()
    yield
    styles.set_theme("light")
    forget_status_icons()


def luminance(couleur: str) -> float:
    couleur = couleur.lstrip("#")
    canaux = [int(couleur[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineaire = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lineaire[0] + 0.7152 * lineaire[1] + 0.0722 * lineaire[2]


def contraste(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    haut, bas = max(la, lb), min(la, lb)
    return (haut + 0.05) / (bas + 0.05)


# Un rapport de 1.0 signifie deux couleurs identiques, donc invisible.
SEUIL_SURBRILLANCE = 1.15
# Une fleche doit se detacher franchement du fond de l'arbre.
SEUIL_FLECHE = 2.5
# Seuil usuel pour du texte lisible.
SEUIL_TEXTE = 4.5


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_current_line_is_visible(theme):
    styles.set_theme(theme)
    palette = styles.palette()
    mesure = contraste(palette["console_bg"], palette["current_line"])
    assert mesure >= SEUIL_SURBRILLANCE, (
        f"surbrillance trop discrete en theme {theme} : {mesure:.2f}"
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_stays_readable_on_the_current_line(theme):
    """Une surbrillance trop appuyee rendrait le code illisible."""
    styles.set_theme(theme)
    palette = styles.palette()
    mesure = contraste(palette["console_text"], palette["current_line"])
    assert mesure >= SEUIL_TEXTE, f"texte peu lisible en theme {theme} : {mesure:.1f}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_current_line_number_stands_out(theme):
    styles.set_theme(theme)
    palette = styles.palette()
    assert contraste(palette["gutter_current"], palette["gutter_bg"]) >= SEUIL_TEXTE


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_branch_arrows_are_visible(theme):
    styles.set_theme(theme)
    palette = styles.palette()
    mesure = contraste(palette["branch_arrow"], palette["tree_bg"])
    assert mesure >= SEUIL_FLECHE, f"fleche peu visible en theme {theme} : {mesure:.2f}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_hovered_arrows_are_visible_too(theme):
    styles.set_theme(theme)
    palette = styles.palette()
    assert contraste(palette["branch_arrow_hover"], palette["tree_bg"]) >= 2.0


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_status_colors_are_readable_on_the_tree_background(theme):
    """Le vert d'un test reussi doit rester lisible sur le fond de l'arbre."""
    styles.set_theme(theme)
    fond = styles.palette()["tree_bg"]
    for statut in ("PASSED", "FAILED", "SKIPPED", "ERROR"):
        mesure = contraste(styles.status_color(statut), fond)
        assert mesure >= 3.0, f"{statut} peu lisible en theme {theme} : {mesure:.1f}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_output_colors_are_readable_in_the_console(theme):
    styles.set_theme(theme)
    fond = styles.palette()["console_bg"]
    for role in ("passed", "failed", "skipped", "error", "nodeid", "info", "warning"):
        mesure = contraste(styles.output_color(role), fond)
        assert mesure >= 3.0, f"{role} peu lisible en theme {theme} : {mesure:.1f}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_syntax_colors_are_readable_in_the_editor(theme):
    styles.set_theme(theme)
    fond = styles.palette()["console_bg"]
    for role in ("keyword", "builtin", "string", "comment", "number",
                 "decorator", "function", "classname", "self", "docstring"):
        mesure = contraste(styles.syntax_color(role), fond)
        assert mesure >= 3.0, f"{role} peu lisible en theme {theme} : {mesure:.1f}"


def test_the_tree_draws_its_own_arrows(qtbot):
    """Les fleches du style natif de Qt sont sombres et disparaissent sur fond
    sombre : l'arbre doit donc les dessiner lui-meme."""
    from gui_qt.campaign_window import CampaignTreeView
    from gui_qt.test_tree_view import TestTreeView

    for classe in (TestTreeView, CampaignTreeView):
        vue = classe()
        qtbot.addWidget(vue)
        assert "drawBranches" in vars(classe), f"{classe.__name__} n'a pas sa propre methode"


# ---------------------------------------------- texte selectionne a la souris

@pytest.mark.parametrize("theme", ["light", "dark"])
def test_selected_text_stays_readable(theme):
    """Le defaut signale : selectionner du texte dans la console le faisait
    disparaitre. La feuille de style fixait le fond de selection sans la couleur
    du texte, donc Qt gardait le blanc de sa palette systeme : blanc sur le bleu
    tres pale du theme clair, soit un rapport de 1,1:1."""
    styles.set_theme(theme)
    palette = styles.palette()
    mesure = contraste(palette["tree_selected_text"], palette["tree_selected"])
    assert mesure >= SEUIL_TEXTE, f"{theme} : {mesure:.2f}:1 sur une selection"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_selection_background_sets_its_text_color(theme):
    """La regle qui manquait : declarer l'un sans l'autre laisse Qt choisir."""
    styles.set_theme(theme)
    for feuille in (styles.app_stylesheet(), styles.console_style(), styles.tree_style()):
        assert feuille.count("selection-background-color") \
            <= feuille.count("selection-color"), \
            "un fond de selection est declare sans couleur de texte"
