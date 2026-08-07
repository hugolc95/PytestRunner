"""Theme clair / sombre.

Le piege principal : les couleurs sont posees directement sur les widgets et sur
les items de l'arbre. Changer de palette ne suffit donc pas, il faut repeindre.
Ces tests verifient que la palette change bien ET que les elements deja colores
suivent.
"""

import pytest
from PyQt5.QtCore import Qt

from core.test_tree import build_test_tree
from gui_qt.status_icons import STATUS_COLORS, forget_status_icons, status_icon
from gui_qt.styles import styles
from gui_qt.test_tree_view import TestTreeView, STATUS_ROLE


@pytest.fixture(autouse=True)
def isolate_theme():
    """Le theme est un etat global du module, et MainWindow applique celui qui
    est memorise dans QSettings. Sans remise a zero AVANT chaque test, l'ordre
    d'execution et les reglages de la machine influenceraient le resultat."""
    styles.set_theme("light")
    forget_status_icons()
    yield
    styles.set_theme("light")
    forget_status_icons()


def test_selecting_light_gives_the_light_palette():
    assert styles.current_theme() == "light"
    assert not styles.is_dark()
    assert styles.palette() is styles.LIGHT


def test_the_saved_theme_is_applied_at_startup(qtbot):
    """Le choix doit survivre a la fermeture de l'application."""
    from PyQt5.QtCore import QSettings
    from gui_qt.main_window import MainWindow

    settings = QSettings("MyCompany", "PyTestRunner")
    precedent = settings.value("theme", "light", type=str)
    try:
        settings.setValue("theme", "dark")
        fenetre = MainWindow()
        qtbot.addWidget(fenetre)
        assert styles.is_dark()
    finally:
        settings.setValue("theme", precedent)


def test_the_toggle_button_switches_and_persists(qtbot):
    from PyQt5.QtCore import QSettings
    from gui_qt.main_window import MainWindow

    settings = QSettings("MyCompany", "PyTestRunner")
    precedent = settings.value("theme", "light", type=str)
    try:
        settings.setValue("theme", "light")
        fenetre = MainWindow()
        qtbot.addWidget(fenetre)

        fenetre.toggle_theme()
        assert styles.is_dark()
        assert settings.value("theme", type=str) == "dark"

        fenetre.toggle_theme()
        assert not styles.is_dark()
        assert settings.value("theme", type=str) == "light"
    finally:
        settings.setValue("theme", precedent)


def test_the_button_shows_the_theme_it_switches_to(qtbot):
    from PyQt5.QtCore import QSettings
    from gui_qt.main_window import MainWindow

    settings = QSettings("MyCompany", "PyTestRunner")
    precedent = settings.value("theme", "light", type=str)
    try:
        settings.setValue("theme", "light")
        fenetre = MainWindow()
        qtbot.addWidget(fenetre)

        lune = fenetre.theme_button.text()
        assert "sombre" in fenetre.theme_button.toolTip()

        fenetre.toggle_theme()
        assert fenetre.theme_button.text() != lune
        assert "clair" in fenetre.theme_button.toolTip()
    finally:
        settings.setValue("theme", precedent)


def test_the_button_sits_in_the_top_right_corner(qtbot):
    from PyQt5.QtCore import Qt
    from gui_qt.main_window import MainWindow

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    assert fenetre.menuBar().cornerWidget(Qt.TopRightCorner) is fenetre.theme_button


def test_switching_to_dark_changes_the_palette():
    clair = styles.palette()["background"]
    styles.set_theme("dark")
    assert styles.is_dark()
    assert styles.palette()["background"] != clair


def test_an_unknown_theme_falls_back_to_light():
    styles.set_theme("fluo")
    assert styles.current_theme() == "light"


def test_both_palettes_define_the_same_keys():
    """Une cle manquante ferait planter une feuille de style au changement."""
    assert set(styles.LIGHT) == set(styles.DARK)


def test_every_color_is_a_valid_hex_value():
    for nom, palette in (("light", styles.LIGHT), ("dark", styles.DARK)):
        for cle, valeur in palette.items():
            if cle == "name" or not isinstance(valeur, str):
                continue
            assert valeur.startswith("#") and len(valeur) in (4, 7), f"{nom}.{cle} = {valeur}"


def test_status_colors_differ_between_themes():
    """Un vert fonce lisible sur blanc devient illisible sur fond sombre."""
    clair = styles.status_color("PASSED")
    styles.set_theme("dark")
    assert styles.status_color("PASSED") != clair


def test_status_colors_mapping_follows_the_theme():
    clair = STATUS_COLORS["FAILED"].name()
    styles.set_theme("dark")
    assert STATUS_COLORS["FAILED"].name() != clair
    assert "FAILED" in STATUS_COLORS
    assert STATUS_COLORS.get("INCONNU") is None


def test_card_colors_exist_for_every_status():
    for theme in ("light", "dark"):
        styles.set_theme(theme)
        for status in ("PASSED", "FAILED", "SKIPPED", "ERROR"):
            base, strong = styles.card_colors(status)
            assert base.startswith("#") and strong.startswith("#")


def test_stylesheets_are_generated_for_both_themes():
    for theme in ("light", "dark"):
        styles.set_theme(theme)
        for maker in (styles.app_stylesheet, styles.tree_style, styles.console_style,
                      styles.primary_button, styles.toolbar_button, styles.theme_toggle_button):
            produit = maker()
            assert produit.strip()
            assert "{" in produit


def test_icon_cache_is_cleared_between_themes(qtbot):
    """Sans purge, les icones garderaient les couleurs de l'ancienne palette."""
    premiere = status_icon("PASSED")
    assert status_icon("PASSED") is premiere  # mise en cache

    styles.set_theme("dark")
    forget_status_icons()
    assert status_icon("PASSED") is not premiere


def test_tree_recolors_already_displayed_statuses(qtbot):
    nodeids = ["a/test_x.py::test_un", "a/test_x.py::test_deux"]
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(nodeids))
    tree.update_single_test(nodeids[0], "FAILED")

    item = tree._find_item_for_nodeid(nodeids[0])
    couleur_claire = item.foreground().color().name()

    styles.set_theme("dark")
    forget_status_icons()
    tree.recolor_statuses()

    assert item.foreground().color().name() != couleur_claire
    # Le statut lui-meme ne doit pas etre perdu au passage.
    assert item.data(STATUS_ROLE) == "FAILED"


def test_recoloring_leaves_checkboxes_alone(qtbot):
    nodeids = ["a/test_x.py::test_un", "a/test_x.py::test_deux"]
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(nodeids))
    tree.set_all_checked(False)
    tree._nodeid_to_item[nodeids[0]].setCheckState(Qt.Checked)

    avant = tree.get_selected_nodeids()
    styles.set_theme("dark")
    tree.recolor_statuses()

    assert tree.get_selected_nodeids() == avant
