"""Markers cote v1 : releve, comptage, expressions, et la barre qui les pilote.

Les regles sont les memes qu'en v2, mais l'implementation est independante
(core/ ne doit rien devoir a runner/, il est empaquete seul par PyInstaller) :
elle merite donc ses propres tests plutot que la confiance.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from core import markers as m
from core.test_discovery import collect_details as collect
from core.markers import (
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
# Le bouton et son panneau
# =========================================================================


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


TROIS = [Marker("smoke", "quick checks", 3),
         Marker("perso", "personalisation", 2),
         Marker("slow", "", 1)]

BEAUCOUP = [Marker(f"marker_{i:02d}", f"famille {i}", 30 - i) for i in range(30)]


@pytest.fixture
def bouton(qapp):
    from gui_qt.marker_bar import MarkerFilter

    b = MarkerFilter()
    b.set_markers(TROIS)
    return b


def test_a_suite_without_markers_hides_the_button(qapp):
    from gui_qt.marker_bar import MarkerFilter

    b = MarkerFilter()
    b.set_markers([])
    assert b.isHidden()

    b.set_markers(TROIS)
    assert not b.isHidden()


def test_thirty_markers_do_not_widen_the_toolbar(qapp):
    """La regression qui a motive ce panneau.

    En rangee de puces, trente markers reclamaient 2892 px : Qt comprimait les
    puces en moignons d'un caractere et la largeur minimale du panneau gauche
    suivait, ecrasant tout le reste de la fenetre. Un bouton ne grandit pas
    avec le nombre de markers.
    """
    from gui_qt.marker_bar import MarkerFilter
    from gui_qt.styles import styles

    # La feuille de style decide de la taille d'un bouton, et l'application
    # est partagee par toute la session de tests : sans la poser ici, la
    # mesure dependrait de l'ordre des fichiers.
    qapp.setStyleSheet(styles.app_stylesheet())

    b = MarkerFilter()
    b.set_markers(TROIS)
    etroit = b.sizeHint().width()

    b.set_markers(BEAUCOUP)
    assert b.sizeHint().width() == etroit
    assert b.sizeHint().width() < 160


def test_the_popup_never_grows_past_its_bounds(bouton):
    """Il se pose par-dessus l'arbre : il ne doit pas couvrir la fenetre."""
    from gui_qt.marker_bar import HAUTEUR_LISTE, LARGEUR_PANNEAU

    bouton.set_markers(BEAUCOUP)
    popup = bouton.popup
    popup.adjustSize()

    assert popup.width() == LARGEUR_PANNEAU
    assert 0 < popup.scroll.maximumHeight() <= HAUTEUR_LISTE
    assert popup.height() < 500


def test_the_list_stops_on_a_whole_row(bouton):
    """Une derniere ligne coupee en deux se lit comme un defaut d'affichage."""
    bouton.set_markers(BEAUCOUP)
    popup = bouton.popup
    ligne = next(iter(popup._rows.values())).height()
    assert ligne > 0
    assert popup.scroll.maximumHeight() % ligne == 0


def test_a_short_list_is_not_padded_with_empty_space(bouton):
    """Trois markers ne doivent pas ouvrir un panneau de dix lignes."""
    popup = bouton.popup
    ligne = next(iter(popup._rows.values())).height()
    assert popup.scroll.maximumHeight() == 3 * ligne


def test_every_marker_has_a_row_even_when_the_list_scrolls(bouton):
    bouton.set_markers(BEAUCOUP)
    assert len(bouton.popup._boxes) == 30


def test_searching_narrows_the_list(bouton):
    bouton.set_markers(BEAUCOUP)
    popup = bouton.popup

    popup.search.setText("marker_1")
    visibles = [n for n, l in popup._rows.items() if not l.isHidden()]
    assert visibles == [f"marker_1{i}" for i in range(10)]
    assert popup.empty.isHidden()


def test_a_search_that_matches_nothing_says_so(bouton):
    bouton.popup.search.setText("zzz")
    assert not any(not l.isHidden() for l in bouton.popup._rows.values())
    assert not bouton.popup.empty.isHidden()


def test_clearing_the_search_brings_every_marker_back(bouton):
    popup = bouton.popup
    popup.search.setText("smoke")
    popup.search.setText("")
    assert all(not l.isHidden() for l in popup._rows.values())


def test_ticking_boxes_writes_the_expression(bouton):
    bouton.popup._boxes["smoke"].setChecked(True)
    assert bouton.expression() == "smoke"

    bouton.popup._boxes["perso"].setChecked(True)
    assert bouton.expression() == "smoke or perso"


def test_typing_a_union_ticks_the_matching_boxes(bouton):
    bouton.popup.field.setText("perso or slow")
    assert not bouton.popup._boxes["smoke"].isChecked()
    assert bouton.popup._boxes["perso"].isChecked()
    assert bouton.popup._boxes["slow"].isChecked()


def test_a_custom_expression_leaves_every_box_off(bouton):
    """Les cases ne savent ecrire qu'une union : les laisser cochees sur un
    `and not` mentirait sur ce qui est selectionne."""
    bouton.popup.field.setText("smoke and not slow")
    assert not any(c.isChecked() for c in bouton.popup._boxes.values())
    assert bouton.is_valid()


def test_the_button_says_when_a_filter_is_on(bouton):
    """Le panneau se referme : sans ce rappel, un filtre actif serait
    invisible et on chercherait pourquoi l'arbre est a moitie decoche."""
    assert bouton.text() == "Markers"
    assert not bouton.isChecked()

    bouton.popup._boxes["smoke"].setChecked(True)
    assert bouton.text() == "Markers · 1"
    assert bouton.isChecked()

    bouton.popup._boxes["perso"].setChecked(True)
    assert bouton.text() == "Markers · 2"
    assert "smoke, perso" in bouton.toolTip()


def test_the_button_never_spells_out_the_whole_expression(bouton):
    """Un libelle qui s'allonge deformerait la barre d'outils."""
    bouton.popup.field.setText("gpki and not slow or prepersonalisation")
    assert bouton.text() == "Markers · ƒ"
    assert len(bouton.text()) < 20


def test_a_custom_expression_is_signalled_on_the_button(bouton):
    """Aucune case n'est cochee, mais un filtre s'applique bien."""
    bouton.popup.field.setText("smoke and not slow")
    assert bouton.isChecked()
    assert "smoke and not slow" in bouton.toolTip()


def test_an_invalid_expression_is_signalled_and_selects_nothing(bouton):
    bouton.popup.field.setText("smoke &&")
    assert bouton.matcher() is None
    assert not bouton.is_valid()
    assert bouton.popup.message.text()
    # v1 pose ses styles widget par widget : le champ porte le rouge du theme.
    from gui_qt.styles import styles

    assert styles.palette()["danger"].lower() in bouton.popup.field.styleSheet().lower()


def test_an_unknown_marker_is_a_note_not_an_error(bouton):
    bouton.popup.field.setText("smoke or jamais_vu")
    assert bouton.is_valid()
    assert "jamais_vu" in bouton.popup.message.text()


def test_an_empty_field_asks_for_nothing(bouton):
    """Effacer le filtre ne doit pas balayer une selection faite a la main."""
    bouton.popup.field.setText("smoke")
    assert bouton.matcher() is not None
    bouton.popup.field.setText("")
    assert bouton.matcher() is None


def test_the_clear_button_wipes_the_filter(bouton):
    bouton.popup.field.setText("smoke or perso")
    assert bouton.popup.clear_button.isEnabled()

    bouton.popup.clear_button.click()
    assert bouton.expression() == ""
    assert not any(c.isChecked() for c in bouton.popup._boxes.values())
    assert not bouton.popup.clear_button.isEnabled()


def test_the_popup_counts_what_the_expression_retains(bouton):
    bouton.set_markers(BEAUCOUP)
    bouton.popup.field.setText("marker_00 or marker_01")
    assert "2 of 30" in bouton.popup.count.text()


def test_loading_another_workspace_resets_the_filter(bouton):
    bouton.popup.field.setText("smoke and not slow")
    bouton.set_markers([Marker("autre", "", 4)])

    assert bouton.expression() == ""
    assert set(bouton.popup._boxes) == {"autre"}
    assert bouton.text() == "Markers"


def test_the_filter_emits_once_per_change(bouton):
    coups = []
    bouton.filter_changed.connect(lambda: coups.append(1))
    bouton.popup.field.setText("smoke")
    assert len(coups) == 1


# =========================================================================
# L'arbre v1 : cocher exactement une liste
# =========================================================================


@pytest.fixture
def arbre(qtbot):
    from core.test_tree import build_test_tree
    from gui_qt.test_tree_view import TestTreeView

    vue = TestTreeView()
    qtbot.addWidget(vue)
    vue.load_tree(build_test_tree([
        "suite/apdu/test_select.py::test_atr",
        "suite/apdu/test_select.py::test_secure",
        "suite/perso/test_cert.py::test_chr",
    ], show_classes=True))
    vue.expandAll()
    return vue


def test_checking_a_list_leaves_everything_else_unchecked(arbre):
    coches = arbre.set_checked_nodeids(["suite/apdu/test_select.py::test_atr"])
    assert coches == 1
    assert arbre.get_selected_nodeids() == ["suite/apdu/test_select.py::test_atr"]


def test_a_partly_checked_folder_shows_it(arbre):
    """Un dossier coche a moitie doit se distinguer d'un dossier coche : sinon
    l'arbre ment sur ce qui va tourner."""
    from PyQt5.QtCore import Qt

    arbre.set_checked_nodeids(["suite/apdu/test_select.py::test_atr"])

    etats = {}
    racine = arbre.model.item(0)
    pile = [racine]
    while pile:
        item = pile.pop()
        etats[item.text()] = item.checkState()
        for row in range(item.rowCount()):
            pile.append(item.child(row))

    assert etats["test_select.py"] == Qt.PartiallyChecked
    assert etats["test_cert.py"] == Qt.Unchecked


def test_an_unknown_nodeid_is_simply_ignored(arbre):
    """Un marker peut porter sur un test que l'arbre n'a pas : ne rien cocher
    vaut mieux que de lever."""
    assert arbre.set_checked_nodeids(["jamais/vu.py::test_x"]) == 0
    assert arbre.get_selected_nodeids() == []


def test_the_selection_counter_follows(arbre):
    recu = []
    arbre.selection_changed.connect(lambda s, t: recu.append((s, t)))
    arbre.set_checked_nodeids(["suite/apdu/test_select.py::test_atr",
                               "suite/perso/test_cert.py::test_chr"])
    assert recu[-1] == (2, 3)
