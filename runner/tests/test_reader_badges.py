"""Badges des lecteurs en tete des colonnes de statut de l'arbre.

Chaque colonne prenait la largeur du nom complet du lecteur : ~210 px pour
"OnmikeyCardman 3x21 Reader 0", soit ~840 px pour 4 lecteurs. Le badge ne
garde que ce qui distingue le lecteur -- son nom entier s'il est seul -- et
le nom complet reste dans l'infobulle.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from runner.domain.models import Reader
from runner.domain.reader_labels import badge_labels
from runner.domain.tree import build_tree

MEME_MODELE = [f"OnmikeyCardman 3x21 Reader {i}" for i in range(4)]
SANS_RAPPORT = ["OMNIKEY CardMan 3x21 0", "Cosmo11SecuredSLC27G",
                "OTR V4 ISO_SPI Reader", "OTReader ISO_SWP Reader"]


# ------------------------------------------------------------------ libelles

def test_readers_of_the_same_model_keep_only_their_number():
    assert badge_labels(MEME_MODELE) == ["0", "1", "2", "3"]


def test_unrelated_names_get_short_distinct_abbreviations():
    assert badge_labels(SANS_RAPPORT) == ["OMNI", "COSM", "OTRV", "OTRE"]


def test_a_single_reader_keeps_its_full_name():
    assert badge_labels(["OnmikeyCardman 3x21 Reader 0"]) == ["OnmikeyCardman 3x21 Reader 0"]


def test_a_shared_word_prefix_is_dropped():
    assert badge_labels(["Reader A", "Reader B"]) == ["A", "B"]


def test_identical_names_are_told_apart_by_position():
    assert badge_labels(["X", "X"]) == ["X1", "X2"]


# ------------------------------------------------------------------ fenetre

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp):
    from PySide6.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.model.set_tree(build_tree(["s/test_a.py::test_x"]))
    yield f
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _colonnes(fenetre, noms):
    lecteurs = tuple(Reader(n, i) for i, n in enumerate(noms))
    fenetre.model.set_readers(lecteurs)
    fenetre._size_reader_columns()
    entete = fenetre.tree.header()
    return [entete.sectionSize(c) for c in range(1, fenetre.model.columnCount())]


def test_the_model_serves_the_badge_and_keeps_the_full_name_in_the_tooltip(fenetre):
    from runner.ui.tree_model import BADGE_ROLE

    _colonnes(fenetre, MEME_MODELE)
    assert fenetre.model.headerData(1, Qt.Horizontal, BADGE_ROLE) == "0"
    assert fenetre.model.headerData(1, Qt.Horizontal, Qt.ToolTipRole) == MEME_MODELE[0]


def test_four_readers_of_the_same_model_take_little_room(fenetre):
    largeurs = _colonnes(fenetre, MEME_MODELE)
    assert all(l <= 60 for l in largeurs)
    assert sum(largeurs) < 260


def test_a_single_reader_column_fits_its_full_name(fenetre):
    [largeur] = _colonnes(fenetre, ["OnmikeyCardman 3x21 Reader 0"])
    assert largeur == max(fenetre.tree.header().badge_width(1) + 16, 40)
    assert largeur > 150


def test_the_profile_tree_follows_its_readers(qapp):
    from runner.ui.live_profile_model import LiveProfileModel
    from runner.ui.tree_model import BADGE_ROLE

    modele = LiveProfileModel()
    modele.set_readers(tuple(Reader(n, i) for i, n in enumerate(SANS_RAPPORT)))
    assert [modele.headerData(c, Qt.Horizontal, BADGE_ROLE) for c in range(1, 5)] == \
        ["OMNI", "COSM", "OTRV", "OTRE"]
