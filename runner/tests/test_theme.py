"""Le theme, verifie sur des pixels et non sur le texte du QSS.

Une feuille de style peut etre parfaitement ecrite et ne rien peindre : Qt
ignore silencieusement ce qu'il ne sait pas appliquer. Les regles qui comptent
sont donc controlees sur le rendu.
"""

from __future__ import annotations

import pytest

from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.ui import tokens as t
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
