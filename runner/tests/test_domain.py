"""Le domaine, teste sans la moindre QApplication.

C'est la garantie que la separation tient : si un import de ce fichier exige
Qt, c'est que la logique a fui dans l'interface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from runner.domain import parsing
from runner.domain.models import Kind, Reader, Status, worst
from runner.domain.tree import build_tree, collapse_single_class
from runner.domain.workspace import Workspace


def test_the_domain_does_not_import_qt():
    """Le point central de l'architecture, verifie plutot que promis."""
    import runner.domain.execution  # noqa: F401
    import runner.domain.models  # noqa: F401
    import runner.domain.tree  # noqa: F401
    import runner.domain.workspace  # noqa: F401

    charges = [nom for nom in sys.modules
               if nom.startswith(("PyQt5", "PySide"))
               and sys.modules[nom] is not None]
    # pytest-qt peut avoir charge Qt pour d'autres tests ; ce qui compte est
    # qu'aucun module du domaine ne le reference.
    for nom, module in list(sys.modules.items()):
        if nom.startswith("runner.domain") and module is not None:
            source = getattr(module, "__dict__", {})
            assert not any(
                getattr(v, "__module__", "").startswith(("PyQt5", "PySide"))
                for v in source.values()
            ), f"{nom} expose un objet Qt"
    assert charges is not None  # la presence de Qt ailleurs est sans importance


# ------------------------------------------------------------------- statuts

def test_the_worst_status_wins_for_a_group():
    """Un echec au fond d'une arborescence repliee doit se voir de la racine."""
    assert worst([Status.PASSED, Status.SKIPPED, Status.FAILED]) is Status.FAILED
    assert worst([Status.PASSED, Status.SKIPPED]) is Status.SKIPPED
    assert worst([]) is Status.PENDING


def test_an_error_outranks_a_failure():
    assert worst([Status.FAILED, Status.ERROR]) is Status.ERROR


# --------------------------------------------------------------------- arbre

def test_a_nodeid_becomes_folders_module_class_and_case():
    racines = build_tree(["a/b/test_x.py::TestC::test_f[cas]"])
    a = racines[0]
    assert (a.name, a.kind) == ("a", Kind.FOLDER)
    b = a.children[0]
    module = b.children[0]
    assert (module.name, module.kind) == ("test_x.py", Kind.MODULE)
    classe = module.children[0]
    assert (classe.name, classe.kind) == ("TestC", Kind.CLASS)
    fonction = classe.children[0]
    assert (fonction.name, fonction.kind) == ("test_f", Kind.TEST)
    cas = fonction.children[0]
    assert (cas.name, cas.kind) == ("[cas]", Kind.CASE)
    assert cas.nodeid == "a/b/test_x.py::TestC::test_f[cas]"


def test_only_the_leaf_carries_the_nodeid():
    """On execute une feuille, pas un dossier : lui donner un nodeid ferait
    lancer deux fois les memes tests."""
    racines = build_tree(["a/test_x.py::test_f"])
    assert racines[0].nodeid == ""
    assert list(racines[0].leaves())[0].nodeid == "a/test_x.py::test_f"


def test_parametrized_cases_share_their_function():
    racines = build_tree(["t.py::test_f[a]", "t.py::test_f[b]"])
    fonction = racines[0].children[0]
    assert fonction.name == "test_f"
    assert [c.name for c in fonction.children] == ["[a]", "[b]"]


def test_a_lone_class_is_collapsed_away():
    """Son nom reprend celui du fichier : le niveau ne distingue rien."""
    racines = collapse_single_class(build_tree(["t.py::TestOnly::test_f"]))
    assert [c.name for c in racines[0].children] == ["test_f"]


def test_several_classes_are_kept():
    """Sans elles, deux tests homonymes se retrouveraient cote a cote."""
    racines = collapse_single_class(
        build_tree(["t.py::TestA::test_f", "t.py::TestB::test_f"]))
    assert [c.name for c in racines[0].children] == ["TestA", "TestB"]


def test_collection_order_is_preserved():
    ids = ["z/test_z.py::test_1", "a/test_a.py::test_1"]
    assert [r.name for r in build_tree(ids)] == ["z", "a"]


# ------------------------------------------------------------------- parsing

@pytest.mark.parametrize("ligne,attendu", [
    ("a/t.py::test_f PASSED [ 42%]", Status.PASSED),
    ("a/t.py::test_f FAILED [ 42%]", Status.FAILED),
    ("a/t.py::test_f[c] SKIPPED (no reason)", Status.SKIPPED),
    ("a/t.py::test_f ERROR", Status.ERROR),
])
def test_status_lines_are_read(ligne, attendu):
    resultat = parsing.parse_status_line(ligne)
    assert resultat is not None and resultat[1] is attendu


def test_xdist_output_is_read_too():
    resultat = parsing.parse_status_line("[gw2] [ 50%] FAILED a/t.py::test_f")
    assert resultat == ("a/t.py::test_f", Status.FAILED)


@pytest.mark.parametrize("ligne,nodeid,statut", [
    (
        ("tests/test_err_Put_Data_ECC_WrongDomain.py::TestSuitePutDataWrongPubKey::"
         "test_putDataECC_WrongB[PutData Curve = prime192v2-B = all_FF] "
         "PASSED [ 64%]"),
        ("tests/test_err_Put_Data_ECC_WrongDomain.py::TestSuitePutDataWrongPubKey::"
         "test_putDataECC_WrongB[PutData Curve = prime192v2-B = all_FF]"),
        Status.PASSED,
    ),
    (
        ("[gw2] [ 64%] PASSED tests/test_x.py::"
         "test_case[PutData Curve = prime192v2-B = all_FF]"),
        "tests/test_x.py::test_case[PutData Curve = prime192v2-B = all_FF]",
        Status.PASSED,
    ),
    (
        "tests/test_x.py::test_case[expected PASSED value] FAILED [ 64%]",
        "tests/test_x.py::test_case[expected PASSED value]",
        Status.FAILED,
    ),
    (
        "folder with spaces/test_x.py::test_case PASSED [ 64%]",
        "folder with spaces/test_x.py::test_case",
        Status.PASSED,
    ),
])
def test_nodeids_may_contain_spaces(ligne, nodeid, statut):
    """Pytest conserve les espaces des `id=` dans le nodeid affiche.

    Les perdre coupe toute la chaine de suivi : plus de verdict dans l'arbre,
    plus de compteur et plus de progression, alors que pytest continue.
    """
    assert parsing.parse_status_line(ligne) == (nodeid, statut)


def test_colored_pytest_status_is_read():
    ligne = ("tests/test_x.py::test_case "
             "\x1b[32mPASSED\x1b[0m\x1b[32m [ 68%]\x1b[0m")
    assert parsing.parse_status_line(ligne) == (
        "tests/test_x.py::test_case", Status.PASSED)


def test_internal_outcome_protocol_keeps_the_exact_nodeid():
    ligne = ("PYTESTRUNNER_OUTCOME\tPASSED\t"
             "tests/test_x.py::test_case[id with spaces]")
    assert parsing.is_outcome_protocol_line(ligne)
    assert parsing.parse_status_line(ligne) == (
        "tests/test_x.py::test_case[id with spaces]", Status.PASSED)


def test_a_status_word_inside_a_skip_reason_is_not_the_verdict():
    ligne = "tests/test_x.py::test_case SKIPPED (requires PASSED marker) [ 64%]"
    assert parsing.parse_status_line(ligne) == (
        "tests/test_x.py::test_case", Status.SKIPPED)


def test_an_expected_failure_is_not_a_failure():
    """XFAIL veut dire "echec attendu" : le compter en rouge ferait paniquer
    pour un test qui se comporte exactement comme prevu."""
    assert parsing.parse_status_line("a/t.py::test_f XFAIL")[1] is Status.SKIPPED
    assert parsing.parse_status_line("a/t.py::test_f XPASS")[1] is Status.PASSED


def test_ordinary_lines_are_ignored():
    assert parsing.parse_status_line("collecting ... collected 7 items") is None
    assert parsing.parse_status_line("") is None


def test_the_collected_count_is_read():
    assert parsing.parse_collected("collected 42 items") == 42
    assert parsing.parse_collected("nothing here") is None


def test_collect_only_keeps_nodeids_and_drops_the_summary():
    sortie = "a/t.py::test_1\na/t.py::test_2\n\n2 tests collected in 0.4s\n"
    assert parsing.parse_collect_only(sortie) == ["a/t.py::test_1", "a/t.py::test_2"]


def test_collect_only_ignores_warnings_and_duplicates():
    sortie = ("a/t.py::test_1\n"
              "a/t.py::test_1\n"
              "<Module a/t.py>\n"
              "warning summary here\n")
    assert parsing.parse_collect_only(sortie) == ["a/t.py::test_1"]


# ----------------------------------------------------------------- workspace

def test_readers_put_the_main_one_first(tmp_path):
    """`Reader` est celui que les tests lisent ; `Readers` ceux qu'on ajoute."""
    (tmp_path / "config.yml").write_text(
        "Reader: A\nReaders:\n  - B\n  - C\n", encoding="utf-8")
    ws = Workspace.load(str(tmp_path))
    assert [r.name for r in ws.readers] == ["A", "B", "C"]
    assert [r.index for r in ws.readers] == [0, 1, 2]


def test_a_reader_listed_twice_appears_once(tmp_path):
    """Deux colonnes indiscernables pour un seul lecteur n'aideraient personne."""
    (tmp_path / "config.yml").write_text(
        "Reader: A\nReaders:\n  - A\n  - B\n", encoding="utf-8")
    assert [r.name for r in Workspace.load(str(tmp_path)).readers] == ["A", "B"]


def test_a_workspace_without_readers_has_none(tmp_path):
    (tmp_path / "config.yml").write_text("Mode: PERSO\n", encoding="utf-8")
    assert Workspace.load(str(tmp_path)).readers == ()


def test_a_setting_at_the_root_beats_one_in_a_section(tmp_path):
    (tmp_path / "config.yml").write_text(
        "Reader: racine\nDebug:\n  Reader: section\n", encoding="utf-8")
    assert Workspace.load(str(tmp_path)).readers[0].name == "racine"


def test_a_config_file_with_another_name_is_found(tmp_path):
    (tmp_path / "configWorkspace.yml").write_text("Reader: A\n", encoding="utf-8")
    ws = Workspace.load(str(tmp_path))
    assert ws.config_path.endswith("configWorkspace.yml")
    assert ws.readers[0].name == "A"


def test_a_config_file_in_a_workspace_subfolder_is_found(tmp_path):
    campagne = tmp_path / ".Campaign"
    campagne.mkdir()
    config = campagne / "campaign.yml"
    config.write_text("Reader: Nested Reader\n", encoding="utf-8")

    ws = Workspace.load(str(tmp_path))

    assert Path(ws.config_path) == config
    assert ws.readers[0].name == "Nested Reader"


def test_config_discovery_skips_virtual_environments(tmp_path):
    parasite = tmp_path / ".venv"
    parasite.mkdir()
    (parasite / "config.yml").write_text("Reader: Wrong\n", encoding="utf-8")

    assert Workspace.load(str(tmp_path)).config_path == ""


def test_a_relative_log_path_is_anchored_to_the_workspace(tmp_path):
    (tmp_path / "config.yml").write_text("LOG_PATH: traces\n", encoding="utf-8")
    assert Workspace.load(str(tmp_path)).log_root == tmp_path / "traces"


def test_an_absolute_log_path_is_left_alone(tmp_path):
    (tmp_path / "config.yml").write_text("LOG_PATH: /var/logs\n", encoding="utf-8")
    assert str(Workspace.load(str(tmp_path)).log_root) == "/var/logs"


def test_the_interpreter_falls_back_to_the_current_one(tmp_path):
    assert Workspace.load(str(tmp_path)).interpreter == sys.executable


def test_a_workspace_can_pin_its_own_interpreter(tmp_path):
    """L'interface peut tourner en 32 bits pendant que les tests chargent des
    DLL 64 bits."""
    (tmp_path / "config.yml").write_text(
        "python_executable: /opt/py64/python\n", encoding="utf-8")
    assert Workspace.load(str(tmp_path)).interpreter == "/opt/py64/python"


def test_a_broken_config_does_not_crash_the_load(tmp_path):
    (tmp_path / "config.yml").write_text("cle: [non fermee\n", encoding="utf-8")
    ws = Workspace.load(str(tmp_path))
    assert ws.readers == ()


# -------------------------------------------------------------------- lecteur

def test_a_reader_drops_the_generic_word_for_its_column():
    assert Reader("Cosmo11Secured Reader", 0).short_name == "Cosmo11Secured"
    assert Reader("Lecteur", 0).short_name == "Lecteur"
