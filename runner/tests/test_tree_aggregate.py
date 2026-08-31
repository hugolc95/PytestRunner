"""Le statut des dossiers, et le cache qui le rend tenable.

Le statut d'un regroupement est le pire de ses descendants. Qt le redemande a
chaque redessin, pour chaque ligne visible et chaque colonne : le recalculer
par un parcours du sous-arbre coutait 291 ms par resultat sur une suite de
2000 tests, ce qui saturait le fil de l'interface -- les resultats
n'apparaissaient plus au fur et a mesure mais par paquets.

Il est donc retenu. Un cache est exactement le genre de chose qui ment en
silence : ces tests existent pour l'attraper quand il le fera.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QModelIndex

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.ui.tree_model import TestTreeModel

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
    "suite/perso/test_cert.py::test_chr",
]
READERS = (Reader("Reader A", 0), Reader("Reader B", 1))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def model(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree(NODEIDS))
    m.set_readers(READERS)
    return m


def _ligne(model, nom: str):
    """Retrouve une ligne par son libelle, a n'importe quelle profondeur."""
    def descendre(parent):
        for r in range(model.rowCount(parent)):
            index = model.index(r, 0, parent)
            if model.data(index) == nom:
                return index.internalPointer()
            trouve = descendre(index)
            if trouve is not None:
                return trouve
        return None

    return descendre(QModelIndex())


def _statut(model, nom: str, lecteur: int = 0) -> Status:
    return model.status_for(_ligne(model, nom), lecteur)


# =========================================================================
# La regle : un dossier montre le pire de ce qu'il contient
# =========================================================================


def test_everything_starts_pending(model):
    for nom in ("suite", "apdu", "test_select.py"):
        assert _statut(model, nom) is Status.PENDING


def test_a_failure_climbs_all_the_way_to_the_root(model):
    """Un echec au fond d'une arborescence repliee doit se voir depuis la
    racine, sinon on ne sait pas qu'il faut deplier."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)

    assert _statut(model, "test_select.py") is Status.FAILED
    assert _statut(model, "apdu") is Status.FAILED
    assert _statut(model, "suite") is Status.FAILED


def test_a_success_next_to_a_failure_does_not_erase_it(model):
    """Le piege du cache incrementiel : un PASSED qui arrive apres un FAILED
    ne doit pas repeindre le dossier en vert."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    model.apply_outcome("suite/apdu/test_select.py::test_aid", Status.PASSED, 0)

    assert _statut(model, "test_select.py") is Status.FAILED
    assert _statut(model, "suite") is Status.FAILED


def test_the_worst_wins_whatever_the_order(model):
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.PASSED, 0)
    model.apply_outcome("suite/apdu/test_select.py::test_aid", Status.ERROR, 0)
    assert _statut(model, "apdu") is Status.ERROR


def test_a_sibling_branch_is_left_alone(model):
    """`perso` n'a rien a voir avec l'echec de `apdu`."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)

    assert _statut(model, "perso") is Status.PENDING
    assert _statut(model, "suite") is Status.FAILED


# =========================================================================
# Le cache ne doit pas survivre a ce qui l'invalide
# =========================================================================


def test_clearing_resets_the_folders_too(model):
    """Sans purge du cache, un dossier resterait rouge alors que le run
    suivant vient de tout remettre a zero."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    assert _statut(model, "suite") is Status.FAILED

    model.clear_statuses()

    assert _statut(model, "suite") is Status.PENDING
    assert _statut(model, "apdu") is Status.PENDING
    assert _statut(model, "test_select.py") is Status.PENDING


def test_a_second_run_does_not_inherit_the_first(model):
    """Le cas qui compte vraiment : rouge, puis on corrige, puis on relance."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    model.clear_statuses()

    for nodeid in NODEIDS:
        model.apply_outcome(nodeid, Status.PASSED, 0)

    assert _statut(model, "suite") is Status.PASSED
    assert _statut(model, "apdu") is Status.PASSED


def test_the_cache_stays_in_step_with_the_leaves_across_a_reader_change(model):
    """Agregats et statuts de feuilles sont ranges par le MEME index de
    lecteur : changer la liste les perime ensemble, jamais l'un sans l'autre.
    C'est ce qui permet de ne pas purger dans `set_readers`."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    assert _statut(model, "suite", 0) is Status.FAILED

    model.set_readers((Reader("Reader Z", 0),))

    feuille = model._by_nodeid["suite/apdu/test_select.py::test_atr"]  # noqa: SLF001
    assert feuille.statuses.get(0) is Status.FAILED
    assert _statut(model, "suite", 0) is Status.FAILED


def test_reloading_the_tree_starts_from_nothing(model):
    """`set_tree` reconstruit les lignes : les agregats disparaissent avec
    elles, sans purge explicite."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    model.set_tree(build_tree(NODEIDS))
    assert _statut(model, "suite") is Status.PENDING


# =========================================================================
# Chaque lecteur a son propre agregat
# =========================================================================


def test_two_readers_do_not_share_a_folder_status(model):
    """C'est toute la raison d'etre des colonnes : voir qu'un dossier casse
    sur un lecteur et pas sur l'autre."""
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.PASSED, 1)

    assert _statut(model, "suite", 0) is Status.FAILED
    assert _statut(model, "suite", 1) is Status.PASSED


# =========================================================================
# Le chemin paresseux : lire un agregat jamais calcule
# =========================================================================


def test_reading_a_folder_before_any_result_computes_it(model):
    """Qt peut demander le statut d'un dossier avant le moindre resultat --
    au premier affichage. Le cache est alors vide et doit se remplir seul."""
    for ligne in [r for r in model._roots] :  # noqa: SLF001
        assert ligne.agg == {}

    assert _statut(model, "suite") is Status.PENDING
    assert _ligne(model, "suite").agg  # rempli par la lecture


def test_the_cached_value_matches_a_full_recomputation(model):
    """Le filet de securite : quoi qu'il arrive au cache, il doit dire la
    meme chose qu'un parcours complet du sous-arbre."""
    from runner.domain.models import worst

    model.apply_outcome("suite/apdu/test_select.py::test_atr", Status.FAILED, 0)
    model.apply_outcome("suite/apdu/test_select.py::test_aid", Status.SKIPPED, 0)
    model.apply_outcome("suite/perso/test_cert.py::test_chr", Status.PASSED, 0)

    def sans_cache(ligne, lecteur):
        if ligne.is_leaf:
            return ligne.statuses.get(lecteur, Status.PENDING)
        return worst(sans_cache(e, lecteur) for e in ligne.children)

    for nom in ("suite", "apdu", "perso", "test_select.py", "test_cert.py"):
        ligne = _ligne(model, nom)
        assert model.status_for(ligne, 0) == sans_cache(ligne, 0), nom


# =========================================================================
# Le cout, qui est la raison d'etre du cache
# =========================================================================


def test_reading_a_folder_twice_does_not_walk_the_tree_twice(qapp):
    """La mesure qui justifie tout ce fichier : sans cache, Qt refaisait le
    parcours a chaque redessin."""
    gros = [f"suite/m{i // 100:02d}/test_f{i // 10:03d}.py::test_{i:04d}"
            for i in range(1000)]
    m = TestTreeModel()
    m.set_tree(build_tree(gros))
    m.set_readers((Reader("R", 0),))

    racine = m._roots[0]  # noqa: SLF001
    visites = []
    vrai_status_for = m.status_for

    def compte(ligne, lecteur):
        visites.append(ligne)
        return vrai_status_for(ligne, lecteur)

    m.status_for = compte
    m.status_for(racine, 0)
    premier = len(visites)

    visites.clear()
    m.status_for(racine, 0)

    assert premier > 500, "le premier calcul doit bien parcourir l'arbre"
    assert len(visites) == 1, "le second doit se contenter du cache"


# =========================================================================
# Le statut d'un dossier doit se VOIR
# =========================================================================


@pytest.mark.parametrize("status", [
    Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR,
])
def test_a_folder_icon_is_painted_in_its_status_colour(qapp, status):
    """Le calcul peut etre juste et l'affichage muet.

    L'icone des regroupements etait teintee avec une chaine `rgba(...)` :
    valide en QSS, mais pas comme QColor. qtawesome retombait sur du noir, et
    sur le fond sombre de l'arbre les dossiers ne montraient qu'un anneau
    invisible -- ils semblaient ne rien recevoir de leurs enfants.
    """
    from runner.ui import icons
    from runner.ui import tokens as t

    if not icons.available():
        pytest.skip("qtawesome absent : rien n'est dessine")

    image = icons.status_icon(status, group=True).pixmap(16, 16).toImage()
    pixels = [image.pixelColor(x, y)
              for x in range(16) for y in range(16)
              if image.pixelColor(x, y).alpha() > 150]
    assert pixels, "l'icone ne dessine rien"

    dessine = pixels[len(pixels) // 2]
    attendu = t.blend(t.status_color(status), t.BG_SURFACE, 0.75)

    from PySide6.QtGui import QColor

    cible = QColor(attendu)
    ecart = max(abs(dessine.red() - cible.red()),
                abs(dessine.green() - cible.green()),
                abs(dessine.blue() - cible.blue()))
    assert ecart <= 2, f"attendu ~{attendu}, dessine {dessine.name()}"

    # Et surtout : pas du noir, qui serait invisible sur le fond de l'arbre.
    assert dessine.lightness() > 40, "icone quasi noire, donc invisible"


def test_a_folder_icon_differs_from_a_leaf_icon(qapp):
    """Un dossier ne porte pas de verdict propre : il montre le pire de ce
    qu'il contient. Le meme pictogramme plein qu'une feuille laisserait croire
    a un resultat qui lui appartient."""
    from runner.ui import icons

    if not icons.available():
        pytest.skip("qtawesome absent")

    feuille = icons.status_icon(Status.FAILED, group=False).pixmap(16, 16).toImage()
    dossier = icons.status_icon(Status.FAILED, group=True).pixmap(16, 16).toImage()
    assert feuille != dossier
