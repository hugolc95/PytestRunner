import sys

from runner.domain.execution import ReaderRun, collect
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.tree import build_tree
from runner.ui.tree_model import TestTreeModel


def _make_suite(root, suite_name: str, import_name: str, test_name: str):
    suite = root / "TSu" / "JC_API" / "Int" / suite_name
    tests = suite / "Tests"
    tests.mkdir(parents=True)

    # Reproduit l'organisation reelle : conftest.py importe par nom court un
    # fichier imports_<suite>.py situe juste a cote de lui.
    (suite / f"{import_name}.py").write_text(
        f'SUITE_NAME = "{suite_name}"\n', encoding="utf-8")
    (suite / "conftest.py").write_text(
        f"import {import_name}\n", encoding="utf-8")
    (tests / "test_nominal.py").write_text(
        f"from {import_name} import SUITE_NAME\n\n"
        f"def {test_name}():\n"
        f"    assert SUITE_NAME == {suite_name!r}\n",
        encoding="utf-8",
    )
    return tests


def test_same_test_module_name_in_two_suites_keeps_results_on_the_right_suite(tmp_path):
    """Each TestSuite keeps its own imports, nodeids and final UI result."""
    _make_suite(
        tmp_path, "BioLockTestSuite", "imports_BiolockTestSuite", "test_biolock")
    _make_suite(
        tmp_path, "CVCertificateV3", "imports_CVcertificateV3", "test_certificate")

    nodeids = (
        "TSu/JC_API/Int/BioLockTestSuite/Tests/test_nominal.py::test_biolock",
        "TSu/JC_API/Int/CVCertificateV3/Tests/test_nominal.py::test_certificate",
    )

    # La collecte doit fonctionner meme avec --import-mode=importlib : les
    # dossiers des conftest sont explicitement exposes pour leurs imports_*.py.
    collection = collect(str(tmp_path), sys.executable, {})
    assert set(collection.nodeids) == set(nodeids)

    request = RunRequest(
        workspace=str(tmp_path),
        interpreter=sys.executable,
        nodeids=nodeids,
        readers=(),
    )

    outcomes = []
    report = ReaderRun(request, Reader("", 0), {}).run(
        on_line=lambda _line: None,
        on_outcome=outcomes.append,
    )

    assert report.exit_code == 0, report.output
    assert "ModuleNotFoundError" not in report.output
    assert "import file mismatch" not in report.output
    assert [(outcome.nodeid, outcome.status) for outcome in outcomes] == [
        (nodeids[0], Status.PASSED),
        (nodeids[1], Status.PASSED),
    ]

    # Meme chemin que l'UI reelle : les icones et compteurs viennent des
    # resultats effectivement rattaches aux feuilles de l'arbre.
    model = TestTreeModel()
    model.set_tree(build_tree(nodeids))
    for outcome in outcomes:
        assert model.apply_outcome(outcome.nodeid, outcome.status, outcome.reader_index)

    assert model.done() == 2
    assert model.status_counts() == {Status.PASSED: 2}
    assert model.statuses_for_nodeid(nodeids[0])[0] is Status.PASSED
    assert model.statuses_for_nodeid(nodeids[1])[0] is Status.PASSED
