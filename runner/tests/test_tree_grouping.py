"""Regroupement des cas parametres d'un meme test, pour l'affichage.

Cocher un test lourdement parametre (ou tout un dossier) peut selectionner
des milliers de nodeids d'un coup. Sans regroupement, chacun devient sa
propre ligne ailleurs (la sequence d'un profil d'execution, en particulier) --
ces fonctions decident SEULEMENT du regroupement, sans rien connaitre de Qt
ni de l'endroit ou le resultat sera affiche.
"""

from __future__ import annotations

from runner.domain.tree import group_consecutive_parameters, parameter_base


def test_a_non_parametrized_nodeid_is_its_own_base():
    assert parameter_base("suite/test_x.py::test_f") == "suite/test_x.py::test_f"


def test_the_case_is_stripped_from_a_parametrized_nodeid():
    assert (parameter_base("suite/test_x.py::test_f[cas-1]")
            == "suite/test_x.py::test_f")


def test_a_bracket_inside_the_case_itself_does_not_confuse_the_base():
    """Un id personnalise peut contenir un crochet (`id="a[b]"`) : seul le
    DERNIER `]` ferme le cas, pas le premier."""
    assert (parameter_base("suite/test_x.py::test_f[a[b]-c]")
            == "suite/test_x.py::test_f")


def test_the_base_still_carries_the_class_when_there_is_one():
    assert (parameter_base("suite/test_x.py::TestC::test_f[cas]")
            == "suite/test_x.py::TestC::test_f")


def test_every_case_of_the_same_function_becomes_one_group():
    nodeids = [f"suite/test_x.py::test_f[{i}]" for i in range(500)]
    groupes = group_consecutive_parameters(nodeids)
    assert groupes == [tuple(nodeids)]


def test_a_different_test_in_between_starts_a_new_group():
    nodeids = [
        "suite/test_x.py::test_f[1]",
        "suite/test_x.py::test_f[2]",
        "suite/test_x.py::test_g",
        "suite/test_x.py::test_f[3]",
    ]
    groupes = group_consecutive_parameters(nodeids)
    assert groupes == [
        ("suite/test_x.py::test_f[1]", "suite/test_x.py::test_f[2]"),
        ("suite/test_x.py::test_g",),
        ("suite/test_x.py::test_f[3]",),
    ]


def test_two_deliberate_repeats_of_a_plain_test_stay_two_separate_groups():
    """Un profil peut vouloir rejouer deux fois d'affilee le meme test, non
    parametre : sa "base" est lui-meme, donc le regrouper avec son voisin
    effacerait cette repetition voulue."""
    nodeids = ["suite/test_x.py::test_f", "suite/test_x.py::test_f"]
    groupes = group_consecutive_parameters(nodeids)
    assert groupes == [("suite/test_x.py::test_f",),
                       ("suite/test_x.py::test_f",)]


def test_two_deliberate_repeats_of_the_same_parameter_stay_separate():
    """Meme chose pour un cas parametre repete a l'identique : le regrouper
    avec lui-meme donnerait "2 parameter cases" alors qu'il n'y en a qu'un,
    repete deux fois."""
    nodeid = "suite/test_x.py::test_f[admin]"
    groupes = group_consecutive_parameters([nodeid, nodeid])
    assert groupes == [(nodeid,), (nodeid,)]


def test_flattening_every_group_back_reproduces_the_original_order():
    nodeids = (
        [f"suite/test_x.py::test_f[{i}]" for i in range(50)]
        + ["suite/test_x.py::test_g"]
        + [f"suite/test_y.py::test_h[{i}]" for i in range(50)]
    )
    groupes = group_consecutive_parameters(nodeids)
    assert [nodeid for groupe in groupes for nodeid in groupe] == nodeids


def test_an_empty_selection_groups_to_nothing():
    assert group_consecutive_parameters([]) == []
