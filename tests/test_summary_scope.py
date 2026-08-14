"""Les pastilles de bas de fenetre suivent le lecteur qu'on regarde.

Avec plusieurs lecteurs, un total agrege ne dit pas lequel a echoue : regarder
la console du lecteur B en lisant les compteurs de A+B+C n'apprend rien sur B.
Les pastilles suivent donc l'onglet de console, et un bouton ramene au total.
"""

import pytest
from PyQt5.QtCore import QSettings

from core.test_tree import build_test_tree

NODEIDS = ["test_x.py::test_a", "test_x.py::test_b"]


@pytest.fixture
def window(qtbot, tmp_path):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.tree.load_tree(build_test_tree(NODEIDS))
    return fenetre


def _deux_lecteurs(window):
    """Prepare l'etat d'un run a deux lecteurs, sans lancer pytest."""
    window._current_readers = ["Lecteur A", "Lecteur B"]
    window._counts_by_reader = [{k: 0 for k in window.test_counts} for _ in range(2)]
    window.test_counts = {k: 0 for k in window.test_counts}
    window.total_tests = 4  # 2 tests x 2 lecteurs
    window.details.set_readers(["Lecteur A", "Lecteur B"])
    window.tree.set_readers(["Lecteur A", "Lecteur B"])
    window.set_summary_scope(None)


def _valeur(carte) -> int:
    return carte._value


def test_a_single_reader_hides_the_scope_button(window):
    window.set_summary_scope(None)
    assert not window.scope_button.isVisible()


def test_counters_start_on_the_total(window):
    _deux_lecteurs(window)
    window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._on_test_status("test_x.py::test_a", "FAILED", 1)
    window._refresh_summary_cards()

    assert _valeur(window.card_passed) == 1
    assert _valeur(window.card_failed) == 1
    assert window.scope_button.text() == "All readers"


def test_scoping_to_a_reader_shows_only_its_own_result(window):
    _deux_lecteurs(window)
    window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._on_test_status("test_x.py::test_b", "PASSED", 0)
    window._on_test_status("test_x.py::test_a", "FAILED", 1)

    window.set_summary_scope(1)
    assert _valeur(window.card_passed) == 0, "Lecteur B n'a rien fait passer"
    assert _valeur(window.card_failed) == 1

    window.set_summary_scope(0)
    assert _valeur(window.card_passed) == 2
    assert _valeur(window.card_failed) == 0


def test_the_scope_button_names_the_reader_being_shown(window):
    _deux_lecteurs(window)
    window.set_summary_scope(1)
    assert "Lecteur B" in window.scope_button.text()


def test_the_scope_button_goes_back_to_the_total(window):
    _deux_lecteurs(window)
    window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._on_test_status("test_x.py::test_b", "PASSED", 1)

    window.set_summary_scope(0)
    assert _valeur(window.card_passed) == 1

    window.scope_button.click()
    assert window._summary_scope is None
    assert _valeur(window.card_passed) == 2


def test_clicking_a_console_tab_scopes_the_counters(window):
    """Le geste attendu : on clique l'onglet d'un lecteur, les compteurs
    suivent -- sans avoir a toucher au bouton de portee."""
    _deux_lecteurs(window)
    window._on_test_status("test_x.py::test_a", "FAILED", 1)

    window.details.console_tabs.setCurrentIndex(1)

    assert window._summary_scope == 1
    assert _valeur(window.card_failed) == 1


def test_an_out_of_range_scope_falls_back_to_the_total(window):
    _deux_lecteurs(window)
    window.set_summary_scope(7)
    assert window._summary_scope is None


def test_a_new_run_goes_back_to_the_total(window):
    _deux_lecteurs(window)
    window.set_summary_scope(1)
    window._launch_worker(NODEIDS, "run\n")
    try:
        assert window._summary_scope is None
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


# ---------------------------------------------- pastille des tests restants

def test_the_remaining_card_counts_down_as_tests_finish(window):
    """La barre de progression montre une proportion ; elle ne dit pas combien
    de tests il reste encore a passer."""
    _deux_lecteurs(window)
    assert _valeur(window.card_remaining) == 4

    window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._refresh_summary_cards()
    assert _valeur(window.card_remaining) == 3

    window._on_test_status("test_x.py::test_b", "FAILED", 0)
    window._refresh_summary_cards()
    assert _valeur(window.card_remaining) == 2


def test_the_remaining_card_follows_the_scope(window):
    """Ramenee a un lecteur, elle compte ce qu'il reste A CE lecteur."""
    _deux_lecteurs(window)
    window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._on_test_status("test_x.py::test_b", "PASSED", 0)

    window.set_summary_scope(0)
    assert _valeur(window.card_remaining) == 0, "Lecteur A a tout passe"

    window.set_summary_scope(1)
    assert _valeur(window.card_remaining) == 2, "Lecteur B n'a rien passe"


def test_the_remaining_card_never_goes_negative(window):
    """Un test peut etre rapporte plus de fois que prevu (cas parametres
    remplaces en cours de collecte) : un nombre negatif n'aurait aucun sens."""
    _deux_lecteurs(window)
    for _ in range(10):
        window._on_test_status("test_x.py::test_a", "PASSED", 0)
    window._refresh_summary_cards()

    assert _valeur(window.card_remaining) == 0


def test_the_remaining_card_does_not_filter_the_tree(window):
    """"Restant" n'est pas un statut : cliquer la pastille ne doit pas vider
    l'arbre en cherchant des tests dont le statut serait "remaining"."""
    _deux_lecteurs(window)
    window.card_remaining.clicked.emit("remaining")

    assert window.active_summary_filter is None
