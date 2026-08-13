"""Collecte non reproductible d'un lancement a l'autre.

Quand les identifiants de parametres sont calcules a chaque collecte (valeurs
aleatoires, date, compteur), l'arbre etabli au chargement ne decrit plus ce que
pytest execute au lancement, puisqu'il recollecte.

L'arbre est donc complete au fil du run avec les tests reellement executes, et
les cas de la collecte perimee qu'ils remplacent en sont retires : aucun
resultat n'est perdu, et ce qui est affiche correspond a ce qui a tourne.
Le fait reste signale, car il implique que la selection faite avant le
lancement ne portait pas sur ces tests-la.
"""

import textwrap
from types import SimpleNamespace

import pytest

from core.test_tree import build_test_tree
from gui_qt.main_window import MainWindow
from gui_qt.test_tree_view import TestTreeView

NODEIDS = ["test_x.py::test_f[cas_1]", "test_x.py::test_f[cas_2]"]


@pytest.fixture
def window(qtbot):
    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = "."
    fenetre.tree.load_tree(build_test_tree(NODEIDS))
    fenetre._on_collected(len(NODEIDS))
    return fenetre


def test_the_tree_reports_whether_it_matched_a_result(qtbot):
    """C'est ce retour qui permet de compter les resultats orphelins."""
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(NODEIDS))

    assert tree.update_single_test(NODEIDS[0], "PASSED") is True
    assert tree.update_single_test("test_x.py::test_f[valeur_aleatoire]", "PASSED") is False


def test_matching_results_raise_no_note(window):
    for nodeid in NODEIDS:
        window._on_test_status(nodeid, "PASSED")

    assert window._unmatched_results == []
    window._warn_about_unmatched_results()
    window._flush_console_output()
    assert "were not in the tree" not in window.console.toPlainText()


def test_unknown_results_are_collected(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._on_test_status("test_x.py::test_f[2048]", "FAILED")

    assert window._unmatched_results == [
        "test_x.py::test_f[7391]", "test_x.py::test_f[2048]",
    ]


def test_an_executed_test_is_added_to_the_tree(window):
    """Le point central : ce qui a tourne doit se retrouver dans l'arbre."""
    from gui_qt.test_tree_view import STATUS_ROLE

    inconnu = "test_x.py::test_f[7391]"
    window._on_test_status(inconnu, "PASSED")

    item = window.tree._find_item_for_nodeid(inconnu)
    assert item is not None, "le test execute doit apparaitre dans l'arbre"
    assert item.data(STATUS_ROLE) == "PASSED", "avec son resultat"


def test_the_added_test_joins_the_existing_branch(window):
    """Sans fusion, chaque test ajoute recreerait toute la hierarchie."""
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._on_test_status("test_x.py::test_f[2048]", "FAILED")

    assert window.tree.model.rowCount() == 1, "un seul fichier a la racine"
    assert len(window.tree._nodeid_to_item) == len(NODEIDS) + 2


def test_the_stale_cases_leave_the_tree(window):
    """Le reproche de l'utilisateur : l'arbre semblait non mis a jour.

    Les cas de l'ancienne collecte restaient affiches, sans resultat, au-dessus
    de ceux qui venaient de tourner. On ne voyait donc qu'une minorite de lignes
    colorees et l'arbre paraissait fige.
    """
    from gui_qt.test_tree_view import STATUS_ROLE

    window.tree.start_run()
    for nodeid in ("test_x.py::test_f[7391]", "test_x.py::test_f[2048]"):
        window._on_test_status(nodeid, "PASSED")

    assert window.tree.prune_replaced_cases() == len(NODEIDS)

    fonction = window.tree._find_item_for_nodeid("test_x.py::test_f[7391]").parent()
    cas = [fonction.child(row) for row in range(fonction.rowCount())]
    assert [c.text() for c in cas] == ["[7391]", "[2048]"]
    assert all(c.data(STATUS_ROLE) == "PASSED" for c in cas), "tout est colore"
    assert window.tree._nodeid_to_item.keys() == {
        "test_x.py::test_f[7391]", "test_x.py::test_f[2048]",
    }


def test_the_selection_count_follows_the_pruning(qtbot):
    """Le compteur 'X / Y selected' comptait encore les cas disparus."""
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(NODEIDS))

    comptes = []
    tree.selection_changed.connect(lambda s, t: comptes.append((s, t)))

    tree.update_single_test("test_x.py::test_f[7391]", "PASSED", create_missing=True)
    tree.prune_replaced_cases()

    assert comptes[-1] == (1, 1)


def test_a_partial_run_with_stable_ids_prunes_nothing(qtbot):
    """La garde essentielle : ne pas effacer ce que l'utilisateur n'a pas lance.

    Sans cas inconnu, aucune fonction n'est suspecte, donc les cas non joues
    restent en place.
    """
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(NODEIDS))
    tree.start_run()

    tree.update_single_test(NODEIDS[0], "PASSED", create_missing=True)

    assert tree.prune_replaced_cases() == 0
    assert len(tree._nodeid_to_item) == len(NODEIDS)


def test_only_the_affected_function_is_pruned(qtbot):
    """Une autre fonction du meme fichier n'a pas a perdre ses cas."""
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(NODEIDS + ["test_x.py::test_g[stable]"]))
    tree.start_run()

    tree.update_single_test("test_x.py::test_f[7391]", "PASSED", create_missing=True)
    tree.prune_replaced_cases()

    assert tree._find_item_for_nodeid("test_x.py::test_g[stable]") is not None


def _terminer_run(window, arrete: bool, exit_code: int):
    """Rejoue la fin d'un run sans laisser de trace dans l'historique."""
    window.worker = SimpleNamespace(stopped=arrete)
    window.history_manager.add_run = lambda **kwargs: None
    window._on_finished(exit_code, "")


def test_an_interrupted_run_keeps_its_cases(window):
    """Un run arrete laisse forcement des cas sans resultat : ils sont legitimes."""
    window.tree.start_run()
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")

    _terminer_run(window, arrete=True, exit_code=-1)

    assert window.tree._find_item_for_nodeid("test_x.py::test_f[cas_1]") is not None
    assert window._replaced_cases == 0


def test_the_end_of_a_run_prunes_the_tree(window):
    """Le nettoyage doit etre branche sur la fin du run, pas seulement disponible."""
    window.tree.start_run()
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")

    _terminer_run(window, arrete=False, exit_code=0)

    assert window._replaced_cases == len(NODEIDS)
    assert window.tree._find_item_for_nodeid("test_x.py::test_f[cas_1]") is None


def test_the_note_mentions_the_replacement(window):
    window.tree.start_run()
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._replaced_cases = window.tree.prune_replaced_cases()
    window._warn_about_unmatched_results()
    window._flush_console_output()

    assert "in place of the 2 case(s)" in window.console.toPlainText()


def test_the_note_explains_the_cause_and_the_fix(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "added to the tree" in message, "dire ce qui a ete fait"
    assert "reproducible" in message, "la cause doit etre nommee"
    assert "ids=" in message, "la correction doit etre montree"
    assert "test_x.py::test_f[7391]" in message, "l'exemple concret doit apparaitre"


def test_the_note_does_not_list_hundreds_of_examples(window):
    for i in range(50):
        window._on_test_status(f"test_x.py::test_f[{i}]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "and 47 more" in message
    assert message.count("test_x.py::test_f[") <= 4


def test_the_count_resets_between_runs(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    assert window._unmatched_results

    window._launch_worker(NODEIDS, "run\n")
    assert window._unmatched_results == []
    window.worker.stop()
    window.worker.wait(5000)


def test_random_parameters_really_produce_different_nodeids(tmp_path):
    """Verifie la cause reelle plutot que de la supposer : deux collectes
    successives du meme fichier ne donnent pas les memes nodeids."""
    import subprocess
    import sys

    (tmp_path / "test_alea.py").write_text(textwrap.dedent('''
        import random
        import pytest

        @pytest.mark.parametrize("valeur", [random.randint(0, 10**6) for _ in range(5)])
        def test_f(valeur):
            assert valeur >= 0
    '''), encoding="utf-8")

    def collecter():
        sortie = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(tmp_path), capture_output=True, text=True,
        ).stdout
        return {l.strip() for l in sortie.splitlines() if "::" in l}

    assert collecter() != collecter()


def test_stable_ids_make_collection_reproducible(tmp_path):
    """La correction proposee dans le message fonctionne."""
    import subprocess
    import sys

    (tmp_path / "test_stable.py").write_text(textwrap.dedent('''
        import random
        import pytest

        @pytest.mark.parametrize(
            "valeur",
            [random.randint(0, 10**6) for _ in range(5)],
            ids=[f"cas_{i}" for i in range(5)],
        )
        def test_f(valeur):
            assert valeur >= 0
    '''), encoding="utf-8")

    def collecter():
        sortie = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(tmp_path), capture_output=True, text=True,
        ).stdout
        return {l.strip() for l in sortie.splitlines() if "::" in l}

    assert collecter() == collecter()
