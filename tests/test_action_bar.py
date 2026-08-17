"""Barre d'actions : composition, disposition et style des boutons.

Trois defauts signales a l'usage : la case "Parallel" n'etait pas voulue, les
boutons s'etiraient sur toute la largeur de la fenetre au lieu de rester
groupes a gauche, et leur apparence ne hierarchisait rien.
"""

import pytest
from PyQt5.QtCore import QSettings

from gui_qt.status_icons import forget_status_icons
from gui_qt.styles import styles


@pytest.fixture(autouse=True)
def isolate_theme():
    styles.set_theme("light")
    forget_status_icons()
    yield
    styles.set_theme("light")
    forget_status_icons()


@pytest.fixture
def window(qtbot):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.resize(1500, 700)
    fenetre.show()
    qtbot.wait(10)
    return fenetre


# ------------------------------------------------------- la case Parallel part

def test_the_parallel_checkbox_is_gone(window):
    assert not hasattr(window, "parallel_checkbox")


def test_the_campaign_panel_has_no_parallel_checkbox_either(window):
    assert not hasattr(window.campaign_panel, "parallel_checkbox")


def test_a_run_can_still_be_launched(window, tmp_path):
    """Retirer la case ne doit pas casser le lancement."""
    (tmp_path / "test_x.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")
    window.workspace = str(tmp_path)

    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        assert window.worker.isRunning() or window.worker.isFinished()
        assert window.worker.parallel is False
    finally:
        window.worker.stop()
        window.worker.wait(5000)


# ----------------------------------------------------- les boutons a gauche

@pytest.mark.parametrize("nom", ["run_button", "stop_button", "rerun_failed_button"])
def test_a_button_keeps_its_natural_width(window, nom):
    """Sans espace final, la barre repartissait toute la largeur entre les
    boutons : chacun faisait 250 px et l'ensemble flottait au milieu."""
    bouton = getattr(window, nom)
    assert bouton.width() <= bouton.sizeHint().width() + 12, (
        f"{nom} fait {bouton.width()} px pour un contenu de "
        f"{bouton.sizeHint().width()} px"
    )


def test_the_three_buttons_stay_grouped(window):
    """Colles les uns aux autres, pas eparpilles sur la largeur."""
    gauches = [b.x() for b in (window.run_button, window.stop_button,
                               window.rerun_failed_button)]
    droites = [b.x() + b.width() for b in (window.run_button, window.stop_button,
                                           window.rerun_failed_button)]
    for precedent, suivant in zip(droites, gauches[1:]):
        assert suivant - precedent <= 12, "les boutons doivent rester colles"


def test_widening_the_window_leaves_the_buttons_alone(window, qtbot):
    """La marque de l'espace extensible en fin de barre : agrandir la fenetre
    ne doit ni deplacer ni etirer les boutons.

    Mesurer une position absolue ne dirait rien : la largeur d'un bouton depend
    de la police du systeme, et le groupe finit bien plus loin sous Windows que
    sous Linux sans que rien ne soit etire pour autant.
    """
    avant = [(b.x(), b.width()) for b in (window.run_button, window.stop_button,
                                          window.rerun_failed_button)]

    window.resize(window.width() + 700, window.height())
    qtbot.wait(10)

    apres = [(b.x(), b.width()) for b in (window.run_button, window.stop_button,
                                          window.rerun_failed_button)]
    assert apres == avant


# ------------------------------------------------------------ style des boutons

@pytest.mark.parametrize("theme", ["light", "dark"])
def test_only_one_button_of_the_run_group_is_filled(theme, window):
    """Une barre ou tout est plein ne hierarchise rien : l'oeil ne sait pas ou
    aller et le rouge de l'arret crie meme quand il ne sert pas."""
    styles.set_theme(theme)
    window.restyle()

    pleins = [
        b for b in (window.run_button, window.stop_button, window.rerun_failed_button)
        if "background-color: transparent" not in b.styleSheet()
    ]
    assert [b is window.run_button for b in pleins] == [True]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fabrique", ["primary_button", "success_button"])
def test_a_filled_button_keeps_its_label_readable(theme, fabrique):
    """Le vert clair du theme sombre avec du texte blanc tombait a 2,3:1."""
    styles.set_theme(theme)
    feuille = getattr(styles, fabrique)()

    fond = _premiere_valeur(feuille, "background-color")
    texte = _premiere_valeur(feuille, "color")
    mesure = _contraste(fond, texte)
    assert mesure >= 4.5, f"{theme}/{fabrique} : {mesure:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fabrique", ["neutral_button", "danger_button", "info_button"])
def test_an_outline_button_keeps_its_label_readable(theme, fabrique):
    styles.set_theme(theme)
    feuille = getattr(styles, fabrique)()

    texte = _premiere_valeur(feuille, "color")
    mesure = _contraste(styles.palette()["background"], texte)
    assert mesure >= 3.0, f"{theme}/{fabrique} : {mesure:.2f}:1"


@pytest.mark.parametrize("fabrique", ["primary_button", "success_button", "neutral_button",
                                      "danger_button", "info_button", "toolbar_button"])
def test_every_button_reacts_to_the_mouse(fabrique):
    """L'ancienne feuille demandait le survol avec `opacity`, propriete que Qt
    ignore : aucun bouton ne reagissait, ce qui les faisait paraitre morts."""
    feuille = getattr(styles, fabrique)()
    assert ":hover" in feuille and "opacity" not in feuille
    assert ":pressed" in feuille
    assert ":disabled" in feuille


def test_hover_actually_changes_the_background():
    """Declarer :hover ne suffit pas s'il repose la meme couleur."""
    feuille = styles.success_button()
    fonds = _toutes_valeurs(feuille, "background-color")
    assert len(set(fonds)) > 1, "le survol doit changer quelque chose"


# ------------------------------------------------------------------ outillage

def _premiere_valeur(feuille: str, propriete: str) -> str:
    for ligne in feuille.splitlines():
        ligne = ligne.strip()
        if ligne.startswith(propriete + ":"):
            return ligne.split(":", 1)[1].strip().rstrip(";")
    raise AssertionError(f"{propriete} absent de la feuille de style")


def _toutes_valeurs(feuille: str, propriete: str) -> list[str]:
    return [
        ligne.strip().split(":", 1)[1].strip().rstrip(";")
        for ligne in feuille.splitlines()
        if ligne.strip().startswith(propriete + ":")
    ]


def _luminance(couleur: str) -> float:
    couleur = couleur.lstrip("#")
    canaux = [int(couleur[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineaire = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lineaire[0] + 0.7152 * lineaire[1] + 0.0722 * lineaire[2]


def _contraste(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
