"""Quand tout un dossier ou tout un fichier est selectionne, on passe son chemin
a pytest plutot que d'enumerer chacun de ses tests.

Enumerer les nodeids coute cher : pytest apparie chaque argument contre les
items collectes. Mesure dans l'interface sur 6000 tests, un run complet passe de
6,80 s (6000 arguments) a 4,76 s (6 arguments), pour un resultat identique.

La selection doit rester exacte au test pres : un sous-arbre partiellement coche
est parcouru, jamais replie.
"""

import subprocess
import sys

import pytest
from PyQt5.QtCore import Qt

from core.test_tree import build_test_tree
from gui_qt.test_tree_view import TestTreeView


# Basenames uniques dans tout l'arbre : sans __init__.py, deux fichiers de test
# de meme nom font echouer la collecte pytest, ce qui rendrait le test de bout
# en bout vide et donc trompeur.
NODEIDS = [
    f"module_{d}/test_m{d}_f{f}.py::test_fonction_{t}[{p}]"
    for d in range(2)
    for f in range(2)
    for t in range(2)
    for p in range(2)
]


@pytest.fixture
def tree(qtbot):
    view = TestTreeView()
    qtbot.addWidget(view)
    view.load_tree(build_test_tree(NODEIDS))
    return view


def test_everything_selected_collapses_to_root_folders(tree):
    assert tree.get_selected_targets() == ["module_0", "module_1"]


def test_nothing_selected_gives_no_target(tree):
    tree.set_all_checked(False)
    assert tree.get_selected_targets() == []


def test_a_single_case_is_not_collapsed(tree):
    tree.set_all_checked(False)
    tree._nodeid_to_item[NODEIDS[0]].setCheckState(Qt.Checked)
    assert tree.get_selected_targets() == [NODEIDS[0]]


def test_a_partially_selected_folder_is_walked(tree):
    """Deselectionner un seul cas doit empecher le repliage du dossier entier."""
    tree._nodeid_to_item[NODEIDS[0]].setCheckState(Qt.Unchecked)

    targets = tree.get_selected_targets()
    assert "module_0" not in targets, "un dossier incomplet ne doit jamais etre replie"
    assert "module_1" in targets, "l'autre dossier reste complet, donc replie"
    assert NODEIDS[0] not in targets


def test_a_fully_selected_file_collapses_to_the_file(tree):
    tree.set_all_checked(False)
    for nodeid in NODEIDS:
        if nodeid.startswith("module_0/test_m0_f0.py"):
            tree._nodeid_to_item[nodeid].setCheckState(Qt.Checked)

    assert tree.get_selected_targets() == ["module_0/test_m0_f0.py"]


def test_a_fully_selected_parametrized_function_collapses_to_the_function(tree):
    tree.set_all_checked(False)
    for nodeid in NODEIDS:
        if nodeid.startswith("module_0/test_m0_f0.py::test_fonction_0"):
            tree._nodeid_to_item[nodeid].setCheckState(Qt.Checked)

    assert tree.get_selected_targets() == ["module_0/test_m0_f0.py::test_fonction_0"]


def test_classes_are_collapsible_too(qtbot):
    ids = [f"test_a.py::MaClasse::test_{i}" for i in range(3)]
    view = TestTreeView()
    qtbot.addWidget(view)
    view.load_tree(build_test_tree(ids))

    assert view.get_selected_targets() == ["test_a.py"]

    view._nodeid_to_item[ids[0]].setCheckState(Qt.Unchecked)
    assert view.get_selected_targets() == ids[1:]


def build_real_workspace(tmp_path):
    for d in range(2):
        folder = tmp_path / f"module_{d}"
        folder.mkdir()
        for f in range(2):
            source = "import pytest\n"
            for t in range(2):
                source += (
                    "@pytest.mark.parametrize('p', range(2))\n"
                    f"def test_fonction_{t}(p):\n    assert True\n"
                )
            (folder / f"test_m{d}_f{f}.py").write_text(source, encoding="utf-8")


def run_pytest(workspace, args) -> set[str]:
    """Ensemble des nodeids reellement executes par pytest pour ces arguments."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-v", "--tb=short"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    executed = set()
    for line in result.stdout.splitlines():
        if "::" in line and " PASSED" in line:
            executed.add(line.split(" PASSED")[0].strip().replace("\\", "/"))
    return executed


def test_collapsed_targets_run_exactly_the_same_tests(tmp_path, qtbot):
    """La propriete qui compte : replier ne doit ni ajouter ni retirer un test."""
    build_real_workspace(tmp_path)

    view = TestTreeView()
    qtbot.addWidget(view)
    view.load_tree(build_test_tree(NODEIDS))

    # On deselectionne un cas pour sortir du cas trivial "tout est selectionne".
    view._nodeid_to_item[NODEIDS[0]].setCheckState(Qt.Unchecked)

    par_nodeids = run_pytest(tmp_path, view.get_selected_nodeids())
    par_cibles = run_pytest(tmp_path, view.get_selected_targets())

    # Verifie d'abord que pytest a reellement tourne : deux ensembles vides
    # seraient egaux sans rien prouver.
    assert len(par_cibles) == len(NODEIDS) - 1
    assert par_nodeids == par_cibles
