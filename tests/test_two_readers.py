"""Deux lecteurs, deux runs simultanes, une seule lecture.

Les tests sont les memes d'un lecteur a l'autre : les lister deux fois
obligerait a balayer deux arbres pour comparer. Une ligne par test, une colonne
de resultat par lecteur, et un filtre qui ne garde que les divergences.

Le lecteur ne peut pas etre ecrit dans config.yml au moment du run : deux
processus simultanes partagent ce fichier. Il passe donc par une variable
d'environnement, que les tests lisent.
"""

import textwrap
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings, Qt

from core.test_tree import build_test_tree
from core.workspace_config import DEFAULT_READER_ENV, reader_env, reader_env_var, readers_for
from gui_qt.status_icons import forget_status_icons
from gui_qt.styles import styles
from gui_qt.test_tree_view import STATUS_ROLE, TestTreeView

READERS = ["Infineon Reader 0", "Infineon Reader 1"]
NODEIDS = ["suite/test_x.py::test_f[cas1]", "suite/test_x.py::test_f[cas2]"]


@pytest.fixture(autouse=True)
def isolate_theme():
    styles.set_theme("light")
    forget_status_icons()
    yield
    styles.set_theme("light")
    forget_status_icons()


# ------------------------------------------------------ lecture de la configuration

def test_the_readers_are_read_from_the_configuration(tmp_path):
    (tmp_path / "config.yml").write_text(
        "Readers:\n  - Reader 0\n  - Reader 1\n", encoding="utf-8")
    assert readers_for(str(tmp_path)) == ["Reader 0", "Reader 1"]


def test_a_single_reader_key_still_works(tmp_path):
    """Une configuration existante ne declare qu'un `Reader` : elle doit rester
    valable, et donner une liste d'un element."""
    (tmp_path / "config.yml").write_text("Reader: Infineon 0\n", encoding="utf-8")
    assert readers_for(str(tmp_path)) == ["Infineon 0"]


def test_a_workspace_without_readers_is_transparent(tmp_path):
    assert readers_for(str(tmp_path)) == []


def test_a_duplicated_reader_is_ignored(tmp_path):
    """Deux fois le meme lecteur donnerait deux runs identiques et deux colonnes
    indiscernables."""
    (tmp_path / "config.yml").write_text(
        "Readers:\n  - Reader 0\n  - Reader 0\n  - Reader 1\n", encoding="utf-8")
    assert readers_for(str(tmp_path)) == ["Reader 0", "Reader 1"]


def test_the_reader_travels_by_environment_variable(tmp_path):
    """Deux processus simultanes partagent config.yml : y ecrire le lecteur du
    moment est impossible."""
    env = reader_env(str(tmp_path), "Infineon 1")
    assert env[DEFAULT_READER_ENV] == "Infineon 1"


def test_the_variable_name_can_be_chosen(tmp_path):
    """Pour coller au getter deja ecrit dans le workspace."""
    (tmp_path / "config.yml").write_text("reader_env: MON_READER\n", encoding="utf-8")

    assert reader_env_var(str(tmp_path)) == "MON_READER"
    assert reader_env(str(tmp_path), "Infineon 1")["MON_READER"] == "Infineon 1"


def test_the_pythonpath_still_reaches_the_tests(tmp_path):
    """L'environnement du lecteur complete celui du workspace, il ne le remplace pas."""
    (tmp_path / "config.yml").write_text(
        "pythonpath:\n  - /framework\nReaders:\n  - R0\n", encoding="utf-8")

    env = reader_env(str(tmp_path), "R0")
    assert env["PYTHONPATH"].startswith("/framework")
    assert env[DEFAULT_READER_ENV] == "R0"


# ----------------------------------------------------------- colonnes de l'arbre

@pytest.fixture
def tree(qtbot):
    vue = TestTreeView()
    qtbot.addWidget(vue)
    vue.load_tree(build_test_tree(NODEIDS))
    vue.set_readers(READERS)
    return vue


def test_each_reader_gets_its_column(tree):
    assert tree.model.columnCount() == 3
    entetes = [tree.model.headerData(c, Qt.Horizontal) for c in range(3)]
    assert entetes == ["Tests", "Reader 0", "Reader 1"]


def test_a_long_reader_name_is_shortened_in_the_header():
    """Ecrit en entier, l'en-tete imposait sa largeur a une colonne qui
    n'affiche qu'une icone, et le nom des tests se retrouvait tronque."""
    from gui_qt.test_tree_view import short_reader_label

    assert short_reader_label("Infineon CryptoWrapperTU Reader 0") == "Reader 0"
    assert short_reader_label("Reader 1") == "Reader 1"


def test_the_full_name_stays_in_the_tooltip(tree):
    assert tree.model.horizontalHeaderItem(1).toolTip() == READERS[0]


def test_the_test_name_column_takes_the_remaining_width(tree):
    from PyQt5.QtWidgets import QHeaderView

    assert tree.header().sectionResizeMode(0) == QHeaderView.Stretch


def test_a_single_reader_keeps_one_column(qtbot):
    """Un seul lecteur ne justifie pas une colonne : l'arbre reste comme avant."""
    vue = TestTreeView()
    qtbot.addWidget(vue)
    vue.load_tree(build_test_tree(NODEIDS))
    vue.set_readers(["Infineon 0"])

    assert vue.model.columnCount() == 1
    assert vue.reader_column(0) == 0


def test_each_reader_writes_in_its_own_column(tree):
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)

    item = tree._find_item_for_nodeid(NODEIDS[0])
    assert tree._status_cell(item, 1).data(STATUS_ROLE) == "PASSED"
    assert tree._status_cell(item, 2).data(STATUS_ROLE) == "FAILED"


def test_the_test_name_carries_the_worst_of_the_readers(tree):
    """Une divergence doit se voir sans comparer les colonnes une a une."""
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)

    item = tree._find_item_for_nodeid(NODEIDS[0])
    assert item.data(STATUS_ROLE) == "FAILED"


def test_one_reader_does_not_erase_the_other(tree):
    """Le piege du multi-run : deux resultats pour la meme ligne."""
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)

    item = tree._find_item_for_nodeid(NODEIDS[0])
    assert tree._status_cell(item, 1).data(STATUS_ROLE) == "PASSED"
    assert tree._status_cell(item, 2).data(STATUS_ROLE) == "FAILED"


def test_divergences_are_listed(tree):
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)
    tree.update_single_test(NODEIDS[1], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[1], "PASSED", reader_index=1)

    assert tree.divergent_nodeids() == [NODEIDS[0]]


def test_a_test_only_one_reader_has_reached_counts_as_divergent(tree):
    """En cours de run, un test vu par un seul lecteur n'est pas encore un accord."""
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    assert tree.divergent_nodeids() == [NODEIDS[0]]


def test_the_filter_hides_what_the_readers_agree_on(tree):
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)
    tree.update_single_test(NODEIDS[1], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[1], "PASSED", reader_index=1)

    tree.filter_divergences(True)

    divergent = tree._find_item_for_nodeid(NODEIDS[0])
    accord = tree._find_item_for_nodeid(NODEIDS[1])
    assert not tree.isRowHidden(divergent.row(), divergent.parent().index())
    assert tree.isRowHidden(accord.row(), accord.parent().index())


def test_the_filter_keeps_the_branch_that_leads_to_a_divergence(tree):
    """Cacher le parent cacherait l'enfant qu'on veut justement voir."""
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)
    tree.filter_divergences(True)

    fichier = tree.model.item(0).child(0)
    assert not tree.isRowHidden(0, tree.model.invisibleRootItem().index())
    assert not tree.isRowHidden(fichier.row(), tree.model.item(0).index())


def test_turning_the_filter_off_shows_everything_again(tree):
    tree.update_single_test(NODEIDS[0], "PASSED", reader_index=0)
    tree.filter_divergences(True)
    tree.filter_divergences(False)

    accord = tree._find_item_for_nodeid(NODEIDS[1])
    assert not tree.isRowHidden(accord.row(), accord.parent().index())


def test_a_new_run_clears_the_previous_columns(tree):
    """Un statut oublie ferait croire a une divergence avec un lecteur qui n'a
    pas encore repondu."""
    tree.update_single_test(NODEIDS[0], "FAILED", reader_index=1)
    tree.reset_result_colors()

    item = tree._find_item_for_nodeid(NODEIDS[0])
    assert tree._status_cell(item, 2).data(STATUS_ROLE) is None
    assert tree.divergent_nodeids() == []


# ------------------------------------------------------------------ deux consoles

@pytest.fixture
def window(qtbot, tmp_path):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "config.yml").write_text(
        "Readers:\n" + "".join(f"  - {r}\n" for r in READERS), encoding="utf-8")
    # Le test note le lecteur qu'il a recu : pytest capture les print, un
    # fichier temoin est plus sur que la console pour verifier l'environnement.
    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import os
        import pathlib

        def test_f():
            lecteur = os.environ.get("PYTESTRUNNER_READER", "aucun")
            pathlib.Path(__file__).with_name("vu_" + lecteur.replace(" ", "_")).touch()
            assert True
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_the_readers_appear_in_the_action_bar(window):
    assert [c.text() for c in window.reader_checkboxes] == READERS
    assert window.diff_button.isVisible() or not window.isVisible()


def test_a_workspace_without_readers_shows_no_control(qtbot, tmp_path):
    from gui_qt.main_window import MainWindow

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.refresh_readers()

    assert window_controls_hidden(fenetre)


def window_controls_hidden(fenetre) -> bool:
    return not fenetre.reader_checkboxes and not fenetre.diff_button.isVisible()


def test_unchecking_a_reader_leaves_the_other(window):
    window.reader_checkboxes[1].setChecked(False)
    assert window.selected_readers() == [READERS[0]]


def test_each_reader_gets_its_console(window):
    window.details.set_readers(READERS)

    assert len(window.details.consoles) >= 2
    assert window.details.console_for(0) is not window.details.console_for(1)
    assert window.details.console_headers[0].text() == READERS[0]


def test_output_reaches_the_right_console(window):
    window.details.set_readers(READERS)

    window._on_stdout("ligne du lecteur 0\n", 0)
    window._on_stdout("ligne du lecteur 1\n", 1)
    window._flush_console_output()

    assert "lecteur 0" in window.details.console_for(0).toPlainText()
    assert "lecteur 0" not in window.details.console_for(1).toPlainText()
    assert "lecteur 1" in window.details.console_for(1).toPlainText()


def test_two_processes_really_run_with_different_readers(window, qtbot):
    """Bout en bout : deux pytest simultanes, chacun avec son lecteur."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        assert len(window.workers) == 2
        assert [w.reader for w in window.workers] == READERS

        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=60000)

        temoins = sorted(p.name for p in Path(window.workspace).glob("vu_*"))
        assert temoins == ["vu_Infineon_Reader_0", "vu_Infineon_Reader_1"]
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_each_reader_writes_its_own_junit_report(window):
    """Un seul chemin verrait les deux processus s'ecraser l'un l'autre."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        chemins = [w.junit_xml_path for w in window.workers]
        assert len(set(chemins)) == 2
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_the_summary_covers_both_readers(window, qtbot):
    """Deux lecteurs sur un test, c'est deux resultats attendus."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        assert window.total_tests == 2
        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=60000)
        assert window.test_counts["PASSED"] == 2
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)
