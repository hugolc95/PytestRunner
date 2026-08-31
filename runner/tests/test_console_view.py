"""Console, fiche de test et panneau de resultats, sans fenetre principale.

Tout se monte a la main : ces widgets ne connaissent que des donnees, jamais
un service. C'est ce qui permet de les eprouver ici en quelques lignes.
"""

from __future__ import annotations

import pytest

from runner.domain.console import Lens
from runner.domain.models import Reader, ReaderReport, Status
from runner.tests.test_console_domain import SORTIE
from runner.ui.console_view import ConsoleView
from runner.ui.detail_panel import DetailPanel
from runner.ui.results_panel import (
    ONGLET_DETAIL,
    ONGLET_LOGS,
    ONGLET_OUTPUT,
    ResultsPanel,
)

READERS = (Reader("Cosmo11Secured Reader", 0), Reader("Omnikey Reader", 1))

ECHEC = "test_demo.py::TestApdu::test_select_aid"
SUCCES = "test_demo.py::test_module_level"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def console(qapp):
    return ConsoleView()


# =========================================================================
# ConsoleView
# =========================================================================


def test_a_partial_line_waits_for_its_end(console):
    """Colorer un fragment sans attendre son `\\n` ferait sauter le rendu."""
    console.append("moitie")
    assert console.view.toPlainText() == ""
    console.append(" de ligne\n")
    assert console.view.toPlainText().splitlines() == ["moitie de ligne"]


def test_the_escape_codes_never_appear_in_the_document(console):
    console.append("\x1b[31mSW 9E EE\x1b[0m\n")
    texte = console.view.toPlainText()
    assert "SW 9E EE" in texte
    assert "\x1b" not in texte and "[31m" not in texte


def test_a_coloured_chunk_really_carries_its_colour(console):
    from PySide6.QtGui import QTextCursor

    from runner.ui import tokens as t

    console.append("\x1b[31mrouge\x1b[0m\n")
    curseur = QTextCursor(console.view.document())
    curseur.movePosition(QTextCursor.Start)
    curseur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
    couleur = curseur.charFormat().foreground().color().name()
    assert couleur == t.ANSI_COLORS["red"]


def test_windows_line_endings_do_not_double_the_lines(console):
    console.append("a\r\nb\r\n")
    assert console.view.toPlainText().splitlines() == ["a", "b"]


def test_a_lens_hides_lines_without_losing_them(console):
    console.append(SORTIE)
    complet = console.view.toPlainText()

    console.set_lens(Lens.PROBLEMS)
    filtre = console.view.toPlainText()

    assert len(filtre.splitlines()) < len(complet.splitlines())
    # Le tampon, lui, n'a pas bouge : c'est lui qu'on copie.
    assert "test_module_level PASSED" in console.text()
    assert "test_module_level PASSED" not in filtre


def test_going_back_to_all_restores_every_line(console):
    console.append(SORTIE)
    attendu = console.view.toPlainText()

    console.set_lens(Lens.OUTLINE)
    console.set_lens(Lens.ALL)
    assert console.view.toPlainText() == attendu


def test_the_counter_says_how_many_lines_are_hidden(console):
    console.append(SORTIE)
    assert "lines" in console.counter.text()
    assert " of " not in console.counter.text()

    console.set_lens(Lens.OUTLINE)
    assert " of " in console.counter.text()


def test_the_copied_text_has_no_escape_codes(console):
    console.append("\x1b[32mvert\x1b[0m\n")
    assert console.text() == "vert"


def test_scrolling_up_stops_the_console_from_jumping(console):
    """Une console qui saute a la fin pendant qu'on lit est inutilisable."""
    console.view.resize(400, 80)
    console.append("".join(f"ligne {i}\n" for i in range(400)))
    assert console.following()

    barre = console.view.verticalScrollBar()
    assert barre.maximum() > 0, "il faut de quoi defiler pour que le test ait un sens"
    barre.setValue(0)
    assert not console.following()

    # Ce qui arrive ensuite ne doit plus ramener la vue en bas.
    console.append("ligne 400\n")
    assert barre.value() == 0


def test_coming_back_to_the_bottom_starts_following_again(console):
    console.view.resize(400, 80)
    console.append("".join(f"ligne {i}\n" for i in range(400)))
    barre = console.view.verticalScrollBar()
    barre.setValue(0)
    assert not console.following()

    barre.setValue(barre.maximum())
    assert console.following()


def test_clearing_forgets_everything_including_the_partial_line(console):
    console.append("un debut sans fin")
    console.clear()
    console.append(" de ligne\n")
    assert console.view.toPlainText().splitlines() == [" de ligne"]


# =========================================================================
# DetailPanel
# =========================================================================


@pytest.fixture
def detail(qapp):
    return DetailPanel()


def _echecs(sortie: str, *indices: int) -> dict:
    from runner.domain import failures

    index = failures.index_failures(sortie)
    return {i: failures.failure_for(index, ECHEC) for i in indices}


def test_nothing_selected_shows_the_empty_state(detail):
    assert detail.stack.currentWidget() is detail.empty


def test_a_failing_test_shows_its_message_and_its_traceback(detail):
    detail.show_test(ECHEC, READERS,
                     {0: Status.FAILED, 1: Status.PASSED},
                     _echecs(SORTIE, 0, 1))

    corps = detail.body.toPlainText()
    assert "SW mismatch: expected 9000, got 9E EE" in corps
    assert "test_demo.py:7: in test_select_aid" in corps
    assert detail.stack.currentWidget() is not detail.empty


def test_only_the_readers_that_failed_get_a_traceback(detail):
    """Repeter la trace sous un lecteur qui a reussi ferait croire a un echec."""
    detail.show_test(ECHEC, READERS,
                     {0: Status.FAILED, 1: Status.PASSED},
                     _echecs(SORTIE, 0, 1))

    corps = detail.body.toPlainText()
    assert "COSMO11SECURED" in corps
    assert "OMNIKEY" not in corps


def test_the_path_and_the_name_are_separated(detail):
    detail.show_test(ECHEC, READERS, {0: Status.FAILED}, {0: None})
    assert detail.path_label.text() == "test_demo.py"
    assert "test_select_aid" in detail.name_label.text()
    assert "test_demo.py" not in detail.name_label.text()


def test_a_passing_test_says_so_instead_of_showing_an_empty_frame(detail):
    detail.show_test(SUCCES, READERS,
                     {0: Status.PASSED, 1: Status.PASSED}, {0: None, 1: None})
    assert "Passed on every reader" in detail.body.toPlainText()


def test_a_test_that_has_not_run_is_not_presented_as_a_success(detail):
    detail.show_test(SUCCES, READERS,
                     {0: Status.PENDING, 1: Status.PENDING}, {0: None, 1: None})
    corps = detail.body.toPlainText()
    assert "has not run yet" in corps
    assert "Passed" not in corps


def test_a_failure_without_a_traceback_is_explained(detail):
    """Run annule, sortie perdue : un cadre vide se lirait comme un bug."""
    detail.show_test(ECHEC, READERS, {0: Status.FAILED, 1: Status.PENDING},
                     {0: None, 1: None})
    assert "no traceback" in detail.body.toPlainText()


def test_a_homonym_is_signalled_rather_than_shown_silently(detail):
    from dataclasses import replace

    from runner.domain import failures

    bloc = failures.index_failures(SORTIE)["TestApdu.test_select_aid"]
    detail.show_test(ECHEC, READERS, {0: Status.FAILED}, {0: replace(bloc, ambiguous=True)})
    assert "same name" in detail.body.toPlainText()


def test_the_copy_button_is_off_when_there_is_nothing_to_copy(detail):
    detail.show_test(SUCCES, READERS, {0: Status.PASSED}, {0: None})
    assert not detail.copy_button.isEnabled()

    detail.show_test(ECHEC, READERS, {0: Status.FAILED}, _echecs(SORTIE, 0))
    assert detail.copy_button.isEnabled()


# =========================================================================
# ResultsPanel
# =========================================================================


@pytest.fixture
def panel(qapp):
    p = ResultsPanel()
    p.set_readers(READERS)
    return p


def test_the_detail_tab_is_the_one_that_opens(panel):
    """La console ne repond pas a la question posee ; la fiche, si."""
    assert panel.tabs.currentIndex() == ONGLET_DETAIL


def test_main_tabs_are_larger_than_reader_tabs(panel, qapp):
    """La navigation principale ne doit plus se confondre avec un filtre."""
    from runner.ui.theme import app_stylesheet

    qapp.setStyleSheet(app_stylesheet())
    panel.resize(900, 500)
    panel.show()
    qapp.processEvents()

    principaux = panel.tabs.tabBar()
    lecteurs = panel.output.tabs
    assert principaux.objectName() == "PrimaryTabs"
    assert lecteurs.objectName() == "ReaderTabs"
    assert principaux.tabRect(0).height() > lecteurs.tabRect(0).height()


def test_reader_names_keep_the_same_colour_in_output_logs_and_compare(panel):
    from runner.ui import tokens as t

    for vues in (panel.output, panel.logs):
        for position, lecteur in enumerate(READERS):
            couleur = t.reader_color(lecteur.index)
            assert couleur in vues._tab_labels[position].styleSheet()
            assert couleur in vues.headers[position].styleSheet()


def test_clearing_a_run_keeps_reader_names_above_compared_consoles(panel):
    panel.output.compare.setChecked(True)
    panel.begin_run()

    assert [header.text() for header in panel.output.headers[:2]] == [
        lecteur.short_name for lecteur in READERS]


def test_log_compare_highlights_the_meaningful_error_not_durations(panel):
    left = "INFO - Duration : 2.53 ms\nINFO - Expected Status : 9EEE\n"
    right = ("INFO - Duration : 0.26 ms\nINFO - Expected Status : 9EEE\n"
             "ERRO - Wrong Status Word, received: 6FEE ; authorized : {'9EEE'}\n")
    panel.logs.set_text(0, left)
    panel.logs.set_text(1, right)

    panel.logs.compare.setChecked(True)

    left_highlights = panel.logs.views[0].view.extraSelections()
    right_highlights = panel.logs.views[1].view.extraSelections()
    assert left_highlights == []
    assert [item.cursor.block().text() for item in right_highlights] == [
        "ERRO - Wrong Status Word, received: 6FEE ; authorized : {'9EEE'}"]

    panel.logs.compare.setChecked(False)
    assert panel.logs.views[1].view.extraSelections() == []


def test_selecting_a_reader_emphasises_it_without_losing_its_colour(panel):
    from runner.ui import tokens as t

    panel.output.tabs.setCurrentIndex(1)
    libelle = panel.output._tab_labels[1]

    assert t.reader_color(READERS[1].index) in libelle.styleSheet()
    assert "font-weight: 700" in libelle.styleSheet()


def test_starting_a_run_does_not_steal_the_current_tab(panel):
    """L'avancement se lit dans l'arbre : la console n'a pas a s'imposer.

    L'onglet choisi ici n'est pas la console, justement : un panneau qui
    basculerait dessus au lancement passerait inapercu autrement.
    """
    panel.show_tab(ONGLET_LOGS)
    panel.begin_run()
    assert panel.tabs.currentIndex() == ONGLET_LOGS


def test_a_report_feeds_the_traceback_of_the_selected_test(panel):
    panel.show_test(ECHEC, {0: Status.FAILED, 1: Status.PASSED})
    assert "no traceback" in panel.detail.body.toPlainText()

    panel.set_report(ReaderReport(reader=READERS[0], output=SORTIE))
    assert "SW mismatch" in panel.detail.body.toPlainText()


def test_a_result_arriving_during_the_run_updates_the_open_card(panel):
    panel.set_report(ReaderReport(reader=READERS[0], output=SORTIE))
    panel.show_test(ECHEC, {0: Status.PENDING, 1: Status.PENDING})
    assert "has not run yet" in panel.detail.body.toPlainText()

    panel.update_statuses(ECHEC, {0: Status.FAILED, 1: Status.PASSED})
    assert "SW mismatch" in panel.detail.body.toPlainText()


def test_a_result_for_another_test_leaves_the_card_alone(panel):
    panel.set_report(ReaderReport(reader=READERS[0], output=SORTIE))
    panel.show_test(SUCCES, {0: Status.PASSED, 1: Status.PASSED})
    panel.update_statuses(ECHEC, {0: Status.FAILED, 1: Status.FAILED})
    assert "Passed on every reader" in panel.detail.body.toPlainText()


def test_loading_another_workspace_drops_the_previous_selection(panel):
    panel.set_report(ReaderReport(reader=READERS[0], output=SORTIE))
    panel.show_test(ECHEC, {0: Status.FAILED})
    panel.set_readers((Reader("Autre Reader", 0),))
    assert panel.detail.stack.currentWidget() is panel.detail.empty


def test_the_output_console_offers_lenses_but_the_logs_do_not(panel):
    """Une lentille faite pour la sortie pytest n'a aucun sens sur un log.

    `isVisibleTo` et non `isVisible` : rien n'est reellement affiche tant que
    la fenetre n'est pas montree, et `isVisible` repondrait faux partout.
    """
    assert panel.output.views[0].lens_bar.isVisibleTo(panel.output)
    assert not panel.logs.views[0].lens_bar.isVisibleTo(panel.logs)


def test_the_output_of_each_reader_stays_in_its_own_console(panel):
    panel.append_output(0, "premier lecteur\n")
    panel.append_output(1, "second lecteur\n")
    assert "premier" in panel.output.views[0].text()
    assert "premier" not in panel.output.views[1].text()
