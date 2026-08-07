"""Collecte non reproductible d'un lancement a l'autre.

Quand les identifiants de parametres sont calcules a chaque collecte (valeurs
aleatoires, date, compteur), l'arbre etabli au chargement ne decrit plus ce que
pytest execute au lancement, puisqu'il recollecte.

L'arbre est donc complete au fil du run avec les tests reellement executes :
aucun resultat n'est perdu, et ce qui est affiche correspond a ce qui a tourne.
Le fait reste signale, car il implique que la selection faite avant le
lancement ne portait pas sur ces tests-la.
"""

import textwrap

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
    assert "ne figuraient pas" not in window.console.toPlainText()


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


def test_the_note_explains_the_cause_and_the_fix(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "ils y ont ete ajoutes" in message, "dire ce qui a ete fait"
    assert "reproductible" in message, "la cause doit etre nommee"
    assert "ids=" in message, "la correction doit etre montree"
    assert "test_x.py::test_f[7391]" in message, "l'exemple concret doit apparaitre"


def test_the_note_does_not_list_hundreds_of_examples(window):
    for i in range(50):
        window._on_test_status(f"test_x.py::test_f[{i}]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "et 47 autre(s)" in message
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
