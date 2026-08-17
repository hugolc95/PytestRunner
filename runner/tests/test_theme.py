"""Le theme, verifie sur des pixels et non sur le texte du QSS.

Une feuille de style peut etre parfaitement ecrite et ne rien peindre : Qt
ignore silencieusement ce qu'il ne sait pas appliquer. Les regles qui comptent
sont donc controlees sur le rendu.
"""

from __future__ import annotations

import pytest
from PyQt5.QtGui import QColor

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.ui import tokens as t
from runner.ui.results_panel import (
    ONGLET_DETAIL,
    ONGLET_LOGS,
    ONGLET_OUTPUT,
    ONGLET_SOURCE,
)
from runner.ui.theme import app_stylesheet
from runner.ui.tree_model import TestTreeModel

NODEIDS = ["suite/apdu/test_select.py::test_select_aid[A1]",
           "suite/apdu/test_select.py::test_select_aid[A2]"]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_a_translucent_colour_is_composed_the_way_qt_would():
    assert t.blend("#ffffff", "#000000", 0.5) == "#808080"
    assert t.blend("#ff0000", "#000000", 1.0) == "#ff0000"
    assert t.blend("#ff0000", "#00ff00", 0.0) == "#00ff00"


def test_the_selected_row_is_one_colour_from_edge_to_edge(qapp):
    """La colonne des branches ne doit pas trancher avec le reste de la ligne.

    Qt la peint separement et y ignore le canal alpha d'un `rgba()` : la ligne
    selectionnee commencait par un bloc bleu systeme, large de toute son
    indentation, qui n'appartenait a aucune palette du theme.
    """
    from PyQt5.QtWidgets import QHeaderView, QTreeView

    qapp.setStyleSheet(app_stylesheet())

    modele = TestTreeModel()
    modele.set_tree(build_tree(NODEIDS))
    modele.set_readers((Reader("R1", 0),))

    vue = QTreeView()
    vue.setModel(modele)
    # Comme dans la fenetre : sans cela la premiere colonne fait 4 px et le
    # test mesurerait le fond a cote de la ligne.
    vue.header().setStretchLastSection(False)
    vue.header().setSectionResizeMode(0, QHeaderView.Stretch)
    vue.expandAll()
    vue.resize(500, 240)
    vue.show()
    qapp.processEvents()

    index = modele.index_for_nodeid(NODEIDS[0])
    vue.setCurrentIndex(index)
    qapp.processEvents()

    rect = vue.visualRect(index)
    assert rect.width() > 100 and rect.left() > 40, (
        "la ligne doit etre indentee et large, sinon il n'y a rien a comparer")

    # `visualRect` est en coordonnees de la zone de defilement : capturer la
    # fenetre entiere decalerait tout de la hauteur de l'en-tete.
    milieu = rect.center().y()
    image = vue.viewport().grab().toImage()

    branche = image.pixelColor(rect.left() - 20, milieu)  # zone d'indentation
    item = image.pixelColor(rect.right() - 4, milieu)     # zone de l'item

    ecart = max(abs(branche.red() - item.red()),
                abs(branche.green() - item.green()),
                abs(branche.blue() - item.blue()))
    assert ecart <= 2, (
        f"la ligne selectionnee change de couleur en chemin : "
        f"{branche.name()} a gauche, {item.name()} a droite")


# ---------------------------------------------------------------------------
# Bascule clair / sombre
#
# Le theme est un etat GLOBAL au module : `set_theme()` rebinde les noms. Un
# test qui bascule et ne remet pas les choses en place contaminerait tous les
# suivants -- et l'ordre d'execution deciderait du resultat.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def theme_restaure():
    depart = t.current_theme()
    yield
    t.set_theme(depart)


def _luminance(couleur: str) -> float:
    """Luminance relative WCAG d'un `#rrggbb`."""
    canaux = []
    for i in (1, 3, 5):
        c = int(couleur[i:i + 2], 16) / 255
        canaux.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, v, b = canaux
    return 0.2126 * r + 0.7152 * v + 0.0722 * b


def _contraste(avant: str, arriere: str) -> float:
    a, b = _luminance(avant), _luminance(arriere)
    clair, sombre = max(a, b), min(a, b)
    return (clair + 0.05) / (sombre + 0.05)


def test_the_two_palettes_define_exactly_the_same_names():
    """Une clef absente d'une palette garderait la valeur de l'autre.

    `set_theme()` rebinde par `globals().update()` : il ecrase, il n'efface
    pas. Un `TEXT` oublie dans LIGHT laisserait donc le gris clair du theme
    sombre en place, sur un fond devenu blanc -- invisible, et sans la moindre
    erreur pour le signaler.
    """
    assert set(t.DARK) == set(t.LIGHT)


def test_switching_rebinds_the_names_the_whole_interface_reads():
    t.set_theme("dark")
    sombre = (t.TEXT, t.BG_APP, t.status_color(Status.PASSED))

    t.set_theme("light")
    clair = (t.TEXT, t.BG_APP, t.status_color(Status.PASSED))

    assert sombre != clair
    assert t.TEXT == t.LIGHT["TEXT"]
    assert t.current_theme() == "light" and not t.is_dark()


def test_an_unknown_theme_name_falls_back_to_the_dark_one():
    """Le reglage vient de QSettings : un fichier edite a la main, une version
    plus ancienne, et le nom peut etre n'importe quoi. Mieux vaut un theme
    connu qu'une palette a moitie reliee."""
    t.set_theme("solarise-du-mardi")
    assert t.current_theme() == "dark" and t.TEXT == t.DARK["TEXT"]


@pytest.mark.parametrize("nom", ["dark", "light"])
def test_every_text_colour_stays_readable_on_its_own_background(nom):
    """Le piege deja rencontre deux fois : une couleur juste, mais invisible.

    Verifie sur le contraste WCAG, pas a l'oeil. 4.5 pour le texte courant,
    3.0 pour ce qui est volontairement discret ou de grande taille.
    """
    t.set_theme(nom)

    exigences = [
        (t.TEXT, t.BG_SURFACE, 4.5, "texte courant"),
        (t.TEXT, t.BG_APP, 4.5, "texte sur le fond de l'application"),
        (t.TEXT_MUTED, t.BG_SURFACE, 3.0, "texte secondaire"),
        (t.TEXT_FAINT, t.BG_SURFACE, 2.0, "texte tres discret"),
        (t.ON_ACCENT, t.ACCENT, 4.0, "libelle du bouton d'action"),
        (t.ON_RUN, t.RUN, 4.0, "libelle du bouton Run"),
        (t.GUTTER_TEXT, t.GUTTER_BG, 2.0, "numeros de ligne"),
    ]
    for statut in Status:
        if statut is Status.PENDING:
            continue  # en attente : discret par construction
        exigences.append((t.status_color(statut), t.BG_SURFACE, 3.0,
                          f"statut {statut.name}"))
    for role in t.SYNTAX:
        exigences.append((t.syntax_color(role), t.BG_INPUT, 3.0,
                          f"coloration {role}"))
    for index in range(len(t.READER_COLORS)):
        exigences.append((t.reader_color(index), t.BG_SURFACE, 2.5,
                          f"lecteur {index}"))
    for table, vive in ((t.ANSI_COLORS, False), (t.ANSI_BRIGHT, True)):
        for cle in table:
            exigences.append((t.ansi_color(cle, vive), t.BG_INPUT, 2.5,
                              f"ansi {cle}{' vif' if vive else ''}"))

    illisibles = [
        f"{quoi} : {avant} sur {arriere} = {_contraste(avant, arriere):.2f}"
        f" (minimum {seuil})"
        for avant, arriere, seuil, quoi in exigences
        if _contraste(avant, arriere) < seuil
    ]
    assert not illisibles, "theme " + nom + " :\n" + "\n".join(illisibles)


def test_the_status_ring_of_a_group_stays_visible_on_its_background():
    """L'anneau des dossiers est compose a 75 % vers le fond.

    C'est exactement la ou qtawesome peignait du noir : la couleur passee
    n'etait pas une couleur valide, et le dossier semblait ne rien recevoir de
    ses enfants. Le resultat de la composition doit rester distinguable.
    """
    for nom in ("dark", "light"):
        t.set_theme(nom)
        for statut in (Status.PASSED, Status.FAILED, Status.ERROR):
            compose = t.blend(t.status_color(statut), t.BG_SURFACE, 0.75)
            assert compose.startswith("#") and len(compose) == 7
            assert _contraste(compose, t.BG_SURFACE) >= 1.8, (
                f"{nom}/{statut.name} : anneau {compose} noye dans "
                f"{t.BG_SURFACE}")


def test_a_glyph_keeps_one_file_per_colour():
    """Qt met en cache les images d'`url()` en les indexant sur le CHEMIN.

    Un nom de fichier fixe aurait donc garde le dessin de l'ancien theme apres
    bascule, bien que le fichier ait ete reecrit.
    """
    from runner.ui import glyphs

    t.set_theme("dark")
    sombre = glyphs.check(t.ACCENT)
    t.set_theme("light")
    clair = glyphs.check(t.ACCENT)

    assert sombre and clair and sombre != clair


def test_an_icon_is_repainted_when_the_palette_changes(qapp):
    """Le cache des icones est indexe sur la couleur RESOLUE.

    Avec la couleur par defaut resolue apres le cache, les deux themes
    partageaient la meme clef et la bascule rendait l'icone de l'ancien.
    """
    from runner.ui import icons

    if not icons.available():
        pytest.skip("qtawesome absent")

    t.set_theme("dark")
    sombre = icons.icon("mdi.magnify").pixmap(16, 16).toImage()
    t.set_theme("light")
    clair = icons.icon("mdi.magnify").pixmap(16, 16).toImage()

    assert sombre != clair, "l'icone est restee celle du theme precedent"


def test_a_group_status_icon_is_never_painted_black(qapp):
    """Verifie le rendu, pas la couleur demandee : c'est le pixel qui manquait."""
    from runner.ui import icons

    if not icons.available():
        pytest.skip("qtawesome absent")

    for nom in ("dark", "light"):
        t.set_theme(nom)
        image = icons.status_icon(Status.PASSED, group=True).pixmap(16, 16).toImage()
        peints = [image.pixelColor(x, y)
                  for x in range(image.width()) for y in range(image.height())
                  if image.pixelColor(x, y).alpha() > 128]
        assert peints, f"{nom} : l'anneau n'a rien peint du tout"

        fond = QColor(t.BG_SURFACE)
        visibles = [c for c in peints
                    if max(abs(c.red() - fond.red()), abs(c.green() - fond.green()),
                           abs(c.blue() - fond.blue())) > 20]
        assert visibles, f"{nom} : l'anneau se confond avec {t.BG_SURFACE}"


# ---------------------------------------------------------------------------
# Ce que la feuille de style globale ne repeint pas
#
# Regenerer le QSS suffit pour tout ce qui lit un jeton au moment de l'appel.
# Restent les couleurs FIGEES a la construction : une icone deja teintee, un
# format de coloration, une feuille posee sur un widget. Ce sont elles que les
# `restyle()` doivent rejouer -- et elles qui, oubliees, laissent des ilots de
# l'ancien theme.
# ---------------------------------------------------------------------------

def test_the_search_bar_keeps_exactly_one_magnifier(qapp):
    """`addAction` AJOUTE : rejoue a chaque bascule, il empile les loupes.

    Trois allers-retours entre les themes affichaient trois loupes cote a
    cote, poussant le champ de saisie vers la droite.
    """
    from runner.ui.widgets import SearchBar

    barre = SearchBar()
    depart = len(barre.field.actions())

    for nom in ("light", "dark", "light"):
        t.set_theme(nom)
        barre.restyle()

    assert len(barre.field.actions()) == depart, (
        f"{len(barre.field.actions())} icones dans le champ au lieu de {depart}")


def test_the_marker_popup_keeps_exactly_one_magnifier(qapp):
    from runner.ui.marker_bar import MarkerFilter

    barre = MarkerFilter()
    champ = barre.popup.search
    depart = len(champ.actions())

    for nom in ("light", "dark", "light"):
        t.set_theme(nom)
        barre.restyle()

    assert len(champ.actions()) == depart


def test_the_console_forgets_the_ansi_colours_of_the_previous_theme(qapp):
    """Les formats ANSI sont mis en cache par style, couleurs deja resolues.

    Sans purge, une console remplie en sombre gardait son rouge clair sur le
    fond blanc du theme clair.
    """
    from runner.ui.console_view import ConsoleView

    t.set_theme("dark")
    vue = ConsoleView()
    vue.append("\x1b[31mFAILED test_atr\x1b[0m\n")
    assert vue._formats, "rien n'a ete mis en cache : le test ne prouve rien"
    avant = {style: fmt.foreground().color().name()
             for style, fmt in vue._formats.items()}

    t.set_theme("light")
    vue.restyle()
    vue.append("\x1b[31mFAILED test_aid\x1b[0m\n")

    apres = {style: fmt.foreground().color().name()
             for style, fmt in vue._formats.items()}
    communs = set(avant) & set(apres)
    assert communs, "aucun style commun a comparer"
    assert any(avant[s] != apres[s] for s in communs), (
        "la console a garde les couleurs du theme precedent")


def test_the_code_editor_recolours_its_syntax(qapp):
    """Les formats du surligneur sont batis une fois, a la construction."""
    from runner.ui.code_editor import CodeEditor

    t.set_theme("dark")
    editeur = CodeEditor()
    editeur.setPlainText("def test_atr():\n    assert True\n")

    def couleurs() -> list[str]:
        return [fmt.foreground().color().name()
                for _, fmt, _ in editeur.highlighter._regles]

    avant = couleurs()
    t.set_theme("light")
    editeur.restyle()

    assert couleurs() != avant


def test_the_traceback_tints_are_read_at_call_time(qapp):
    """Figee au niveau du module, la table aurait garde les couleurs de l'import."""
    from runner.ui.detail_panel import _teinte

    t.set_theme("dark")
    sombre = (_teinte("exception"), _teinte("code"), _teinte("frame"))
    t.set_theme("light")
    clair = (_teinte("exception"), _teinte("code"), _teinte("frame"))

    assert sombre != clair


def test_a_status_pill_follows_the_palette(qapp):
    """Sa teinte vient du statut, pas de la feuille globale : elle ne suit pas
    toute seule."""
    from runner.ui.widgets import StatusPill

    t.set_theme("dark")
    pastille = StatusPill(Status.FAILED)
    pastille.set_value(3)
    avant = pastille._dot.styleSheet()

    t.set_theme("light")
    pastille.restyle()

    assert pastille._dot.styleSheet() != avant
    assert t.LIGHT["STATUS_COLORS"][Status.FAILED] in pastille._dot.styleSheet()


# ---------------------------------------------------------------------------
# La bascule dans la fenetre
# ---------------------------------------------------------------------------

@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.model.set_tree(build_tree(NODEIDS))
    f.model.set_readers((Reader("Reader A", 0),))
    yield f
    f.settings.clear()


def test_the_button_offers_the_theme_you_are_not_in(fenetre):
    """Le pictogramme annonce la destination, pas l'etat courant : un soleil
    dans le noir veut dire « aller vers le clair »."""
    fenetre.apply_theme("dark")
    assert "light" in fenetre.theme_button.toolTip()

    fenetre.toggle_theme()
    assert t.current_theme() == "light"
    assert "dark" in fenetre.theme_button.toolTip()

    fenetre.toggle_theme()
    assert t.current_theme() == "dark"


def test_the_chosen_theme_survives_a_restart(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    premiere = MainWindow()
    premiere.apply_theme("light")

    seconde = MainWindow()
    try:
        assert t.current_theme() == "light"
        assert "dark" in seconde.theme_button.toolTip()
    finally:
        seconde.settings.clear()


def test_the_window_really_repaints_in_the_new_theme(fenetre, qapp):
    """Le QSS peut etre juste et n'etre applique nulle part : on regarde le fond."""
    fenetre.resize(900, 600)
    fenetre.show()

    def fond():
        qapp.processEvents()
        return fenetre.grab().toImage().pixelColor(4, 4)

    fenetre.apply_theme("dark")
    sombre = fond()
    fenetre.apply_theme("light")
    clair = fond()

    assert clair != sombre
    assert clair.lightness() > sombre.lightness() + 60, (
        f"le theme clair n'eclaircit rien : {sombre.name()} -> {clair.name()}")
    fenetre.hide()


def _remplir(fenetre, tmp_path, onglet: int) -> None:
    """Met la fenetre dans l'etat ou on la regarde vraiment : un test choisi,
    sa source affichee, une trace dans la console.

    Sans cela, mesurer le rendu ne prouve rien : une fenetre vierge n'a aucune
    couleur figee a garder de l'ancien theme, et un `restyle()` supprime
    passerait inapercu.
    """
    # A l'emplacement que le nodeid designe : le panneau ira l'y chercher tout
    # seul, comme lors d'un vrai clic dans l'arbre.
    fichier = tmp_path / "suite" / "apdu" / "test_select.py"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(
        '"""Un module de test."""\n\n'
        "import pytest\n\n\n"
        "@pytest.mark.smoke\n"
        "def test_select_aid(aid):\n"
        "    assert aid == 0x9000, f\"SW {aid:04X}\"\n",
        encoding="utf-8")

    fenetre.results.append_output(
        0, "\x1b[31mFAILED\x1b[0m suite/apdu/test_select.py::test_select_aid\n"
           "E   assert 0x9EEE == 0x9000\n")
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    fenetre.results.show_test(NODEIDS[0], {0: Status.FAILED}, str(tmp_path))
    fenetre.results.show_tab(onglet)
    assert fenetre.results.source.editor.toPlainText().strip(), (
        "la source n'a pas ete chargee : il n'y aurait rien a mesurer")

    fenetre.resize(1000, 650)
    fenetre.show()


def _couleurs_a_l_ecran(widget) -> set:
    """Toutes les couleurs reellement peintes, en `#rrggbb`."""
    image = widget.grab().toImage()
    return {image.pixelColor(x, y).name()
            for x in range(image.width()) for y in range(image.height())}


@pytest.mark.parametrize("onglet", [ONGLET_DETAIL, ONGLET_SOURCE, ONGLET_OUTPUT])
def test_no_background_stays_dark_under_the_light_theme(fenetre, qapp, tmp_path,
                                                        onglet):
    """Les FONDS viennent de la feuille globale : ce test surveille sa portee.

    Un widget que le QSS ne couvre pas garde son fond sombre et se voit comme
    un trou. Il ne dit en revanche rien des couleurs de premier plan, qui ne
    passent pas par la feuille -- c'est le test suivant qui s'en charge.
    """
    _remplir(fenetre, tmp_path, onglet)
    fenetre.apply_theme("dark")
    qapp.processEvents()
    fenetre.apply_theme("light")
    qapp.processEvents()

    image = fenetre.grab().toImage()
    sombres = total = 0
    for x in range(0, image.width(), 4):
        for y in range(0, image.height(), 4):
            total += 1
            if image.pixelColor(x, y).lightness() < 60:
                sombres += 1

    fenetre.hide()
    assert total and sombres / total < 0.02, (
        f"{100 * sombres / total:.1f} % du rendu est reste sombre apres "
        "le passage au theme clair")


def _teintes(palette: dict) -> set:
    """Toutes les couleurs `#rrggbb` d'une palette, tables imbriquees comprises."""
    trouvees = set()
    for valeur in palette.values():
        if isinstance(valeur, str) and valeur.startswith("#"):
            trouvees.add(valeur)
        elif isinstance(valeur, dict):
            trouvees.update(v for v in valeur.values() if v.startswith("#"))
        elif isinstance(valeur, tuple):
            trouvees.update(v for v in valeur if v.startswith("#"))
    return trouvees


def _fenetre_peuplee(qapp, tmp_path, depart: str, bascules: tuple, onglet: int):
    """Une fenetre garnie, nee dans `depart`, puis basculee dans `bascules`."""
    from PyQt5.QtCore import QSettings

    from runner.domain.failures import Failure
    from runner.ui.main_window import APP, K_THEME, ORG, MainWindow

    reglages = QSettings(ORG, APP)
    reglages.clear()
    reglages.setValue(K_THEME, depart)   # lu par le constructeur

    fenetre = MainWindow()
    fenetre.model.set_tree(build_tree(NODEIDS))
    lecteur = Reader("Reader A", 0)
    fenetre.model.set_readers((lecteur,))
    _remplir(fenetre, tmp_path, onglet)
    fenetre.results.detail.show_test(
        NODEIDS[0], (lecteur,), {0: Status.FAILED},
        {0: Failure("AssertionError: SW 9EEE",
                    "suite/apdu/test_select.py:7: in test_select_aid\n"
                    "    assert sw == 0x9000\nE   AssertionError: SW 9EEE\n")})

    for nom in bascules:
        fenetre.apply_theme(nom)
        qapp.processEvents()
    qapp.processEvents()
    return fenetre


@pytest.mark.parametrize("onglet", [ONGLET_DETAIL, ONGLET_SOURCE, ONGLET_OUTPUT,
                                    ONGLET_LOGS])
def test_a_switched_window_shows_what_one_born_in_the_theme_shows(qapp, tmp_path,
                                                                  onglet):
    """La vraie trace d'un `restyle()` oublie : une couleur de PREMIER PLAN.

    Elles sont figees a la construction -- formats du surligneur, formats ANSI,
    icones deja teintees, HTML d'une trace -- et la feuille globale ne les
    touche pas. Un panneau oublie garde donc le violet des mots-cles du theme
    sombre sur son fond devenu blanc, sans qu'aucun fond ne trahisse rien.

    La reference est une fenetre NEE dans le theme clair, jamais passee par le
    sombre. Comparer a la seule palette sombre donnait de fausses alertes : Qt
    delave lui-meme l'icone d'un bouton desactive, et le gris obtenu tombe
    parfois pile sur une teinte du theme sombre.
    """
    basculee = _fenetre_peuplee(qapp, tmp_path, "dark", ("light",), onglet)
    native = _fenetre_peuplee(qapp, tmp_path, "light", (), onglet)

    propres_au_sombre = ({v.lower() for v in _teintes(t.DARK)}
                         - {v.lower() for v in _teintes(t.LIGHT)})
    vues = _couleurs_a_l_ecran(basculee) & propres_au_sombre
    admises = _couleurs_a_l_ecran(native) & propres_au_sombre

    basculee.hide()
    native.hide()
    assert not (vues - admises), (
        "des couleurs du theme sombre survivent a la bascule, absentes d'une "
        "fenetre nee claire : " + ", ".join(sorted(vues - admises)))


def test_the_reference_window_would_notice_a_forgotten_restyle(qapp, tmp_path):
    """Garde-fou du test precedent : sans rejeu, l'ecart doit bien apparaitre.

    Une comparaison entre deux fenetres identiques passe aussi quand elle ne
    regarde rien ; on verifie donc qu'un theme change SANS `restyle()` laisse
    des traces detectables.
    """
    fenetre = _fenetre_peuplee(qapp, tmp_path, "dark", (), ONGLET_SOURCE)
    propres_au_sombre = ({v.lower() for v in _teintes(t.DARK)}
                         - {v.lower() for v in _teintes(t.LIGHT)})

    # La feuille globale seule, sans faire redescendre le changement.
    t.set_theme("light")
    qapp.setStyleSheet(app_stylesheet())
    qapp.processEvents()
    oublie = _couleurs_a_l_ecran(fenetre) & propres_au_sombre

    fenetre.apply_theme("light")
    qapp.processEvents()
    rejoue = _couleurs_a_l_ecran(fenetre) & propres_au_sombre
    fenetre.hide()

    assert oublie - rejoue, (
        "un theme applique sans rejeu ne laisse aucune trace mesurable : "
        "le test de reference ne prouverait rien")
