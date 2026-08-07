"""Collecte non reproductible d'un lancement a l'autre.

Quand les identifiants de parametres sont calcules a chaque collecte (valeurs
aleatoires, date, compteur), l'arbre etabli au chargement ne decrit plus ce que
pytest execute au lancement, puisqu'il recollecte. Les resultats arrivent alors
avec des nodeids inconnus de l'arbre.

Aucun rattrapage cote interface ne peut corriger cela : les tests executes sont
reellement d'autres tests. Ce qui est en notre pouvoir, c'est de le detecter et
de le dire clairement plutot que de laisser croire a un affichage fiable.
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


def test_matching_results_raise_no_warning(window):
    for nodeid in NODEIDS:
        window._on_test_status(nodeid, "PASSED")

    assert window._unmatched_results == []
    window._warn_about_unmatched_results()
    window._flush_console_output()
    assert "ATTENTION" not in window.console.toPlainText()


def test_unknown_results_are_collected(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._on_test_status("test_x.py::test_f[2048]", "FAILED")

    assert window._unmatched_results == [
        "test_x.py::test_f[7391]", "test_x.py::test_f[2048]",
    ]


def test_the_warning_explains_the_cause_and_the_fix(window):
    window._on_test_status("test_x.py::test_f[7391]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "ATTENTION" in message
    assert "aleatoires" in message, "la cause doit etre nommee"
    assert "ids=" in message, "la correction doit etre montree"
    assert "test_x.py::test_f[7391]" in message, "l'exemple concret doit apparaitre"


def test_the_warning_does_not_list_hundreds_of_examples(window):
    for i in range(50):
        window._on_test_status(f"test_x.py::test_f[{i}]", "PASSED")
    window._warn_about_unmatched_results()
    window._flush_console_output()

    message = window.console.toPlainText()
    assert "et 45 autre(s)" in message
    assert message.count("test_x.py::test_f[") <= 6


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
