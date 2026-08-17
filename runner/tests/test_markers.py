"""Markers : relevé, comptage, expressions, et la barre qui les pilote."""

from __future__ import annotations

import sys
import textwrap

import pytest

from runner.domain import markers as m
from runner.domain.execution import collect
from runner.domain.markers import (
    ExpressionError,
    Marker,
    compile_expression,
    matches,
    names_of_union,
    summarize,
    union_expression,
)

RELEVE = "\n".join([
    "D\tsmoke: quick sanity checks on a card",
    "D\tperso: personalisation phase",
    "D\tslow(reason): takes more than 10s",
    "D\tjamais_utilise: declared but nobody uses it",
    "M\ttest_a.py::test_atr\tsmoke",
    "M\ttest_a.py::test_keygen[ECDSA]\tparametrize,perso,smoke",
    "M\ttest_a.py::test_keygen[MLDSA]\tparametrize,perso,smoke",
    "M\ttest_a.py::test_secure\tslow",
    "M\ttest_a.py::test_nu\t",
])


@pytest.fixture
def releve(tmp_path):
    fichier = tmp_path / "markers.tsv"
    fichier.write_text(RELEVE, encoding="utf-8")
    return m.read_probe(str(fichier))


# =========================================================================
# Relevé
# =========================================================================


def test_the_probe_file_gives_markers_per_test(releve):
    par_nodeid, _ = releve
    assert par_nodeid["test_a.py::test_atr"] == ("smoke",)
    assert par_nodeid["test_a.py::test_keygen[ECDSA]"] == (
        "parametrize", "perso", "smoke")


def test_a_test_without_any_marker_is_kept_with_an_empty_tuple(releve):
    """Il doit rester selectionnable par `not smoke` : l'oublier le rendrait
    invisible a toute expression negative."""
    par_nodeid, _ = releve
    assert par_nodeid["test_a.py::test_nu"] == ()


def test_a_parameterised_marker_keeps_only_its_name(releve):
    _, descriptions = releve
    assert descriptions["slow"] == "takes more than 10s"


def test_a_missing_probe_file_is_not_an_error():
    """La collecte a pu aboutir sans que le plugin n'ecrive : l'arbre reste
    utilisable, seules les puces disparaissent."""
    assert m.read_probe("/definitely/not/here.tsv") == ({}, {})


# =========================================================================
# Comptage
# =========================================================================


def test_only_the_markers_actually_used_become_chips(releve):
    par_nodeid, descriptions = releve
    noms = [x.name for x in summarize(par_nodeid, descriptions)]
    # `jamais_utilise` est declare mais ne selectionnerait aucun test.
    assert "jamais_utilise" not in noms


def test_pytest_mechanisms_are_not_offered_as_categories(releve):
    """`parametrize` est porte par la moitie d'une suite et ne veut rien dire
    comme filtre."""
    par_nodeid, descriptions = releve
    noms = [x.name for x in summarize(par_nodeid, descriptions)]
    assert "parametrize" not in noms
    assert set(noms) == {"perso", "smoke", "slow"}


def test_chips_are_sorted_by_count_then_alphabetically(releve):
    par_nodeid, descriptions = releve
    resultat = [(x.name, x.count) for x in summarize(par_nodeid, descriptions)]
    assert resultat == [("smoke", 3), ("perso", 2), ("slow", 1)]


def test_a_chip_carries_its_declared_description(releve):
    par_nodeid, descriptions = releve
    smoke = summarize(par_nodeid, descriptions)[0]
    assert "quick sanity checks" in smoke.tooltip
    assert "3 tests" in smoke.tooltip


def test_a_marker_with_one_test_says_test_not_tests():
    assert Marker("slow", "", 1).tooltip == "1 test"


# =========================================================================
# Expressions
# =========================================================================


@pytest.mark.parametrize("expression, markers, attendu", [
    ("smoke", {"smoke"}, True),
    ("smoke", {"perso"}, False),
    ("smoke or perso", {"perso"}, True),
    ("smoke and perso", {"perso"}, False),
    ("smoke and perso", {"smoke", "perso"}, True),
    ("not slow", {"smoke"}, True),
    ("not slow", {"slow"}, False),
    ("smoke and not slow", {"smoke"}, True),
    ("smoke and not slow", {"smoke", "slow"}, False),
    ("(smoke or perso) and not slow", {"perso"}, True),
    ("(smoke or perso) and not slow", {"perso", "slow"}, False),
])
def test_an_expression_selects_the_way_pytest_would(expression, markers, attendu):
    assert matches(expression, markers) is attendu


def test_an_unknown_marker_is_false_rather_than_an_error():
    """pytest se comporte ainsi, et cela permet de taper une expression
    caractere par caractere sans qu'elle passe son temps en erreur."""
    assert matches("jamais_vu", {"smoke"}) is False
    assert matches("smoke or jamais_vu", {"smoke"}) is True


def test_a_test_without_markers_matches_a_negation():
    assert matches("not slow", set()) is True


@pytest.mark.parametrize("expression", [
    "",
    "   ",
    "smoke and",
    "(smoke",
    "smoke &&perso",
])
def test_a_broken_expression_is_refused(expression):
    with pytest.raises(ExpressionError):
        compile_expression(expression)


@pytest.mark.parametrize("expression, indice", [
    ("smoke && perso", "and / or"),
    ("(smoke or perso", "parenthes"),
])
def test_the_error_message_names_the_mistake(expression, indice):
    with pytest.raises(ExpressionError) as capture:
        compile_expression(expression)
    assert indice.lower() in str(capture.value).lower()


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo pwned')",
    "open('/etc/passwd').read()",
    "smoke.__class__",
    "1 + 1",
    "[x for x in ()]",
    "smoke == perso",
])
def test_an_expression_can_never_execute_anything(expression):
    """Le champ est evalue : il ne doit accepter que des noms et and/or/not."""
    with pytest.raises(ExpressionError):
        compile_expression(expression)


def test_a_quoted_string_is_not_a_marker_name():
    with pytest.raises(ExpressionError):
        compile_expression("'smoke'")


# ------------------------------------------------------- puces <-> expression


def test_chips_write_a_union():
    assert union_expression(["smoke", "perso"]) == "smoke or perso"
    assert union_expression([]) == ""
    assert union_expression(["smoke", "smoke"]) == "smoke"


@pytest.mark.parametrize("expression, attendu", [
    ("smoke", ("smoke",)),
    ("smoke or perso", ("smoke", "perso")),
    ("smoke and perso", None),
    ("not smoke", None),
    # Un `or` dont un membre n'est pas un simple nom : la forme est bien une
    # union, son contenu non. Les puces ne peuvent pas l'ecrire.
    ("smoke or not slow", None),
    ("(smoke or perso) and not slow", None),
    ("", None),
])
def test_only_a_pure_union_can_light_the_chips(expression, attendu):
    """Des que l'expression fait autre chose, les puces ne savent plus la
    representer : les laisser allumees mentirait sur ce qui est selectionne."""
    assert names_of_union(expression) == attendu


def test_selected_nodeids_keeps_the_collection_order():
    par_nodeid = {
        "t.py::a": ("smoke",),
        "t.py::b": ("slow",),
        "t.py::c": ("smoke", "slow"),
    }
    retenus = m.selected_nodeids(par_nodeid, compile_expression("smoke and not slow"))
    assert retenus == ["t.py::a"]


# =========================================================================
# Bout en bout : la collecte reelle
# =========================================================================


@pytest.fixture
def suite_marquee(tmp_path):
    """Une suite dont un marker est pose DYNAMIQUEMENT par le conftest."""
    (tmp_path / "pytest.ini").write_text(textwrap.dedent("""\
        [pytest]
        markers =
            smoke: quick sanity checks
            perso: personalisation phase
    """), encoding="utf-8")
    (tmp_path / "conftest.py").write_text(textwrap.dedent('''
        import pytest

        def pytest_collection_modifyitems(items):
            for item in items:
                if "secure" in item.nodeid:
                    item.add_marker(pytest.mark.slow)
    '''), encoding="utf-8")
    (tmp_path / "test_suite.py").write_text(textwrap.dedent('''
        import pytest

        @pytest.mark.smoke
        def test_atr(): pass

        @pytest.mark.smoke
        @pytest.mark.perso
        @pytest.mark.parametrize("algo", ["ECDSA", "MLDSA"])
        def test_keygen(algo): pass

        def test_secure_channel(): pass
    '''), encoding="utf-8")
    return tmp_path


def test_the_markers_come_from_the_same_collection_as_the_nodeids(suite_marquee):
    """Une seconde passe de pytest doublerait l'attente -- et sur un conftest
    qui parle au materiel, elle la doublerait pour de bon."""
    collection = collect(str(suite_marquee), sys.executable)

    assert len(collection.nodeids) == 4
    assert collection.markers["test_suite.py::test_atr"] == ("smoke",)


def test_a_marker_added_by_a_conftest_is_seen(suite_marquee):
    """Un `grep @pytest.mark` ne verrait jamais celui-la : c'est tout l'interet
    de faire relever les markers par pytest lui-meme."""
    collection = collect(str(suite_marquee), sys.executable)
    assert collection.markers["test_suite.py::test_secure_channel"] == ("slow",)

    noms = [x.name for x in collection.marker_list()]
    assert "slow" in noms


def test_the_declared_descriptions_travel_with_the_collection(suite_marquee):
    collection = collect(str(suite_marquee), sys.executable)
    smoke = next(x for x in collection.marker_list() if x.name == "smoke")
    assert smoke.description == "quick sanity checks"


def test_a_suite_without_markers_offers_no_chip(tmp_path):
    (tmp_path / "test_nu.py").write_text("def test_un(): pass\n", encoding="utf-8")
    collection = collect(str(tmp_path), sys.executable)
    assert collection.nodeids
    assert collection.marker_list() == []


def test_the_probe_never_invents_a_test(suite_marquee):
    """Le releve ne fait autorite que sur ce que la collecte a liste."""
    collection = collect(str(suite_marquee), sys.executable)
    assert set(collection.markers) <= set(collection.nodeids)


# =========================================================================
# La barre
# =========================================================================


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def barre(qapp):
    from runner.ui.marker_bar import MarkerBar

    b = MarkerBar()
    b.set_markers([Marker("smoke", "quick checks", 3),
                   Marker("perso", "personalisation", 2),
                   Marker("slow", "", 1)])
    return b


def test_a_suite_without_markers_hides_the_bar_entirely(qapp):
    """Une rangee vide au-dessus de l'arbre serait de la place prise pour rien."""
    from runner.ui.marker_bar import MarkerBar

    b = MarkerBar()
    b.set_markers([])
    assert b.isHidden()

    b.set_markers([Marker("smoke", "", 1)])
    assert not b.isHidden()


def test_clicking_chips_writes_the_expression(barre):
    barre._chips["smoke"].setChecked(True)
    barre._chips["smoke"].clicked.emit()
    assert barre.expression() == "smoke"

    barre._chips["perso"].setChecked(True)
    barre._chips["perso"].clicked.emit()
    assert barre.expression() == "smoke or perso"


def test_typing_a_union_lights_the_matching_chips(barre):
    barre.field.setText("perso or slow")
    assert not barre._chips["smoke"].isChecked()
    assert barre._chips["perso"].isChecked()
    assert barre._chips["slow"].isChecked()


def test_a_custom_expression_leaves_every_chip_off(barre):
    """Les puces ne savent ecrire qu'une union : les laisser allumees sur un
    `and not` mentirait sur ce qui est selectionne."""
    barre.field.setText("smoke and not slow")
    assert not any(p.isChecked() for p in barre._chips.values())
    assert barre.is_valid()


def test_an_invalid_expression_is_signalled_and_selects_nothing(barre):
    barre.field.setText("smoke &&")
    assert barre.matcher() is None
    assert not barre.is_valid()
    assert barre.message.text()
    assert barre.field.property("invalid")


def test_an_unknown_marker_is_a_note_not_an_error(barre):
    """pytest l'accepte : il ne selectionne simplement rien. Le dire evite de
    chercher pourquoi la selection est vide."""
    barre.field.setText("smoke or jamais_vu")
    assert barre.is_valid()
    assert "jamais_vu" in barre.message.text()


def test_an_empty_field_asks_for_nothing(barre):
    """Effacer le filtre ne doit pas balayer une selection faite a la main."""
    barre.field.setText("smoke")
    assert barre.matcher() is not None
    barre.field.setText("")
    assert barre.matcher() is None


def test_loading_another_workspace_resets_the_filter(barre):
    barre.field.setText("smoke and not slow")
    barre.set_markers([Marker("autre", "", 4)])
    assert barre.expression() == ""
    assert set(barre._chips) == {"autre"}


def test_the_bar_emits_once_per_change(barre):
    coups = []
    barre.filter_changed.connect(lambda: coups.append(1))
    barre.field.setText("smoke")
    assert len(coups) == 1
