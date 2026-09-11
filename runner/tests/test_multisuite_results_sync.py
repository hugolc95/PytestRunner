import sys

from runner.domain.execution import ReaderRun
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.tree import build_tree
from runner.ui.tree_model import TestTreeModel


def test_same_test_module_name_in_two_suites_keeps_results_on_the_right_suite(tmp_path):
    """Regression: the first suite must not stay cached for the next one.

    Pytest's default ``prepend`` import mode registers a non-package test module
    by its short name. Two suites containing ``test_nominal.py`` therefore used
    to reuse the first imported module and the second suite ended in an import
    mismatch. The UI then received no matching outcomes: counters stayed low and
    the corresponding rows had no result icon.
    """
    biolock = tmp_path / "TSu" / "JC_API" / "Int" / "BioLockTestSuite" / "Tests"
    cvcert = tmp_path / "TSu" / "JC_API" / "Int" / "CVCertificateV3" / "Tests"
    biolock.mkdir(parents=True)
    cvcert.mkdir(parents=True)

    (biolock / "test_nominal.py").write_text(
        "def test_biolock():\n    assert True\n", encoding="utf-8")
    (cvcert / "test_nominal.py").write_text(
        "def test_certificate():\n    assert True\n", encoding="utf-8")

    nodeids = (
        "TSu/JC_API/Int/BioLockTestSuite/Tests/test_nominal.py::test_biolock",
        "TSu/JC_API/Int/CVCertificateV3/Tests/test_nominal.py::test_certificate",
    )
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
    assert "import file mismatch" not in report.output
    assert [(outcome.nodeid, outcome.status) for outcome in outcomes] == [
        (nodeids[0], Status.PASSED),
        (nodeids[1], Status.PASSED),
    ]

    # Same path used by the real UI: an outcome must update the tree first;
    # counters are then derived from that exact tree state.
    model = TestTreeModel()
    model.set_tree(build_tree(nodeids))
    for outcome in outcomes:
        assert model.apply_outcome(outcome.nodeid, outcome.status, outcome.reader_index)

    assert model.done() == 2
    assert model.status_counts() == {Status.PASSED: 2}
    assert model.statuses_for_nodeid(nodeids[0])[0] is Status.PASSED
    assert model.statuses_for_nodeid(nodeids[1])[0] is Status.PASSED
