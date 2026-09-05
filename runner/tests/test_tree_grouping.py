"""Regroupement hierarchique des etapes d'une sequence, pour l'affichage.

Cocher un test lourdement parametre, toute une classe, ou un dossier entier
peut selectionner des milliers de nodeids d'un coup. Sans regroupement,
chacun devient sa propre ligne ailleurs (la sequence d'un profil d'execution,
en particulier) -- ces fonctions decident SEULEMENT du regroupement, sans
rien connaitre de Qt ni de l'endroit ou le resultat sera affiche.

Le regroupement remonte toujours au plus haut ancetre commun qui couvre
EXACTEMENT et sans trou la selection : monter plus haut ne coute jamais une
ligne de plus des qu'un seul ancetre englobe deja tout, donc autant remonter
le plus loin possible. Deux selections qui ne partagent aucun ancetre (deux
dossiers distincts, par exemple) restent forcement deux groupes."""

from __future__ import annotations

from runner.domain.models import Kind
from runner.domain.tree import group_hierarchically


def test_a_single_nodeid_is_its_own_group():
    groupes = group_hierarchically(["suite/test_x.py::test_f"])
    assert len(groupes) == 1
    assert groupes[0].nodeids == ("suite/test_x.py::test_f",)
    assert groupes[0].name == "suite/test_x.py::test_f"


def test_every_case_of_one_function_collapses_to_one_group():
    """Rien d'autre n'accompagne ces cas dans ce lot : le module ne fait que
    menerd'un trait a `test_f`, donc le groupe redescend jusqu'a la fonction
    elle-meme plutot que de s'arreter au module -- son compte reste "500
    parameter cases", pas "500 tests" : ce sont 500 prises du MEME test."""
    nodeids = [f"test_x.py::test_f[{i}]" for i in range(500)]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 1
    assert groupes[0].kind is Kind.TEST
    assert groupes[0].name == "test_x.py::test_f"
    assert groupes[0].nodeids == tuple(nodeids)


def test_two_unrelated_selections_never_merge():
    """Deux chemins qui ne partagent aucun prefixe restent deux groupes,
    meme ajoutes dans le meme lot : rien ne les rattache l'un a l'autre."""
    nodeids = (
        [f"suite_a/test_x.py::test_f[{i}]" for i in range(3)]
        + [f"suite_b/test_y.py::test_g[{i}]" for i in range(3)]
    )
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 2
    assert groupes[0].name == "suite_a/test_x.py::test_f"
    assert groupes[1].name == "suite_b/test_y.py::test_g"


def test_every_method_of_one_class_redescends_to_the_class():
    """Le module ne contient que `TestC` dans ce lot : le groupe redescend
    jusqu'a la classe, plus parlante qu'un module qui ne ferait que la
    contenir seule."""
    nodeids = [
        "test_x.py::TestC::test_a",
        "test_x.py::TestC::test_b",
        "test_x.py::TestC::test_c[1]",
        "test_x.py::TestC::test_c[2]",
    ]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 1
    assert groupes[0].kind is Kind.CLASS
    assert groupes[0].name == "test_x.py::TestC"
    assert groupes[0].nodeids == tuple(nodeids)


def test_a_whole_folder_collapses_to_one_group():
    """Ici le dossier contient reellement deux modules distincts : rien de
    plus specifique ne couvre exactement la meme selection, le dossier reste
    donc le niveau le plus parlant."""
    nodeids = [
        "suite/test_x.py::test_a",
        "suite/test_y.py::test_b",
        "suite/test_y.py::test_c",
    ]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 1
    assert groupes[0].kind is Kind.FOLDER
    assert groupes[0].name == "suite"
    assert groupes[0].nodeids == tuple(nodeids)


def test_nested_subfolders_redescend_to_the_deepest_shared_one():
    """`suite/` ne menes qu'a `security/` dans ce lot (rien d'autre a cote) :
    le groupe redescend jusqu'a ce sous-dossier, le niveau le plus specifique
    qui couvre encore exactement les deux tests."""
    nodeids = [
        "suite/security/test_x.py::test_a",
        "suite/security/pin/test_y.py::test_b",
    ]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 1
    assert groupes[0].kind is Kind.FOLDER
    assert groupes[0].name == "suite/security"
    assert groupes[0].nodeids == tuple(nodeids)


def test_a_subfolder_can_stay_its_own_group_next_to_an_unrelated_file():
    """Un sous-dossier complet et un fichier sans rapport, ajoutes ensemble,
    ne partagent aucun ancetre commun : deux groupes, pas un. `security/`
    ne menant qu'a `test_a.py` dans ce lot, le premier groupe redescend
    jusqu'au module."""
    nodeids = [
        "security/test_a.py::test_1",
        "security/test_a.py::test_2",
        "test_b.py::test_3",
    ]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 2
    assert groupes[0].kind is Kind.MODULE
    assert groupes[0].name == "security/test_a.py"
    assert groupes[0].nodeids == (
        "security/test_a.py::test_1", "security/test_a.py::test_2")
    assert groupes[1].nodeids == ("test_b.py::test_3",)


def test_an_unrelated_test_in_between_breaks_the_group():
    nodeids = [
        "test_x.py::TestC::test_a",
        "test_y.py::test_other",
        "test_x.py::TestC::test_b",
    ]
    groupes = group_hierarchically(nodeids)
    assert [groupe.nodeids for groupe in groupes] == [
        ("test_x.py::TestC::test_a",),
        ("test_y.py::test_other",),
        ("test_x.py::TestC::test_b",),
    ]


def test_two_deliberate_repeats_of_a_plain_test_stay_two_separate_groups():
    """Un profil peut vouloir rejouer deux fois d'affilee le meme test :
    `build_tree()` fusionnerait un nodeid repete en une seule feuille, donc
    regrouper au travers d'une repetition perdrait cette repetition voulue."""
    nodeids = ["test_x.py::test_f", "test_x.py::test_f"]
    groupes = group_hierarchically(nodeids)
    assert [groupe.nodeids for groupe in groupes] == [
        ("test_x.py::test_f",),
        ("test_x.py::test_f",),
    ]


def test_two_deliberate_repeats_of_the_same_parameter_stay_separate():
    nodeid = "test_x.py::test_f[admin]"
    groupes = group_hierarchically([nodeid, nodeid])
    assert [groupe.nodeids for groupe in groupes] == [(nodeid,), (nodeid,)]


def test_a_repeat_stays_isolated_and_nothing_is_lost():
    """La repetition de `test_a` ne doit ni disparaitre, ni fusionner avec ce
    qui l'entoure -- et rien de la sequence ne doit se perdre en route."""
    nodeids = [
        "test_x.py::TestC::test_a",
        "test_x.py::TestC::test_b",
        "test_x.py::TestC::test_a",  # rejoue
        "test_y.py::test_c",
        "test_y.py::test_d",
    ]
    groupes = group_hierarchically(nodeids)
    assert groupes[0].nodeids == (
        "test_x.py::TestC::test_a", "test_x.py::TestC::test_b")
    assert ("test_x.py::TestC::test_a",) in [g.nodeids for g in groupes]
    assert [nodeid for groupe in groupes for nodeid in groupe.nodeids] == nodeids


def test_an_interleaved_sequence_never_loses_or_duplicates_a_nodeid():
    """Une sequence enregistree peut avoir ete reordonnee a la main d'une
    facon qui casse toute structure d'arbre coherente -- le regroupement doit
    alors s'effacer proprement (pas de ligne par ligne compacte), jamais
    perdre ou dedoubler un nodeid."""
    nodeids = [
        "test_x.py::TestC::test_a",
        "test_y.py::test_other",
        "test_x.py::TestC::test_b",
    ]
    groupes = group_hierarchically(nodeids)
    assert [nodeid for groupe in groupes for nodeid in groupe.nodeids] == nodeids


def test_flattening_every_group_back_reproduces_the_original_order():
    nodeids = (
        [f"test_x.py::test_f[{i}]" for i in range(50)]
        + ["autre/test_y.py::TestC::test_h", "autre/test_y.py::TestC::test_i"]
    )
    groupes = group_hierarchically(nodeids)
    assert [nodeid for groupe in groupes for nodeid in groupe.nodeids] == nodeids


def test_an_empty_selection_groups_to_nothing():
    assert group_hierarchically([]) == []


def test_a_bracket_inside_the_parameter_value_does_not_confuse_grouping():
    """Un id personnalise peut contenir un crochet (`id="a[b]"`) : seul le
    DERNIER `]` ferme le cas, pas le premier."""
    nodeids = [
        "test_x.py::test_f[a[b]-c]",
        "test_x.py::test_f[d]",
    ]
    groupes = group_hierarchically(nodeids)
    assert len(groupes) == 1
    assert groupes[0].kind is Kind.TEST
    assert groupes[0].name == "test_x.py::test_f"
