from pathlib import Path

from PyQt5.QtCore import Qt

from runner.domain.campaign import build_runs, discover_campaigns, memberships
from runner.domain.execution import ReaderRun
from runner.domain.models import (
    CampaignPhase,
    CampaignRun,
    PhaseReport,
    Reader,
    ReaderReport,
    RunRequest,
    Status,
)
from runner.domain.tree import build_tree
from runner.ui.results_panel import ResultsPanel
from runner.ui.tree_model import CAMPAIGN_ROLE, TestTreeModel


def _campaign(workspace: Path) -> Path:
    path = workspace / "TestSuiteCCC" / ".Campaign" / "campaign.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """\
name: CCC configurations
workspace: ../../
scenarios:
  - name: Configuration A
    setup: setup_a.py
    tests:
      - Tests/test_crypto.py::test_checksum[AES]
      - Tests/test_crypto.py::test_put_data
  - name: Configuration B
    setup: setup_b.py
    tests:
      - Tests/test_crypto.py::test_checksum[AES]
      - Tests/test_crypto.py::test_put_data
""",
        encoding="utf-8",
    )
    return path


def test_discovers_nested_campaign_and_resolves_collected_nodeids(tmp_path):
    _campaign(tmp_path)
    collected = (
        "TestSuiteCCC/Tests/test_crypto.py::test_checksum[AES]",
        "TestSuiteCCC/Tests/test_crypto.py::test_put_data",
    )

    found = discover_campaigns(str(tmp_path), collected)

    assert len(found) == 1
    assert found[0].name == "CCC configurations"
    assert found[0].nodeids == collected
    assert found[0].scenarios[0].setup == "setup_a.py"


def test_marks_only_the_common_campaign_suite(tmp_path):
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    _campaign(tmp_path)
    collected = (
        "TestSuiteCCC/Tests/test_crypto.py::test_checksum[AES]",
        "TestSuiteCCC/Tests/test_crypto.py::test_put_data",
        "OtherSuite/test_regular.py::test_regular",
    )
    campaigns = discover_campaigns(str(tmp_path), collected)
    model = TestTreeModel()
    model.set_tree(build_tree(collected))
    model.set_campaigns(memberships(campaigns))

    campaign_rows = []
    stack = [model.index(row, 0) for row in range(model.rowCount())]
    while stack:
        index = stack.pop()
        if index.data(CAMPAIGN_ROLE):
            campaign_rows.append(index)
        stack.extend(model.index(row, 0, index)
                     for row in range(model.rowCount(index)))

    assert len(campaign_rows) == 1
    assert campaign_rows[0].data(Qt.DisplayRole) == "TestSuiteCCC"
    assert app is not None


def test_run_tests_routes_the_same_test_through_every_configuration(tmp_path):
    import sys

    suite = tmp_path / "TestSuiteCCC"
    tests = suite / "Tests"
    tests.mkdir(parents=True)
    (tests / "test_crypto.py").write_text(
        "from pathlib import Path\n"
        "def test_active_configuration():\n"
        "    assert (Path(__file__).parents[1] / 'active.txt').read_text() in {'A', 'B'}\n",
        encoding="utf-8",
    )
    (suite / "setup_a.py").write_text(
        "from pathlib import Path\nPath(__file__).with_name('active.txt').write_text('A')\n",
        encoding="utf-8",
    )
    (suite / "setup_b.py").write_text(
        "from pathlib import Path\nPath(__file__).with_name('active.txt').write_text('B')\n",
        encoding="utf-8",
    )
    campaign_path = suite / ".Campaign" / "campaign.yml"
    campaign_path.parent.mkdir()
    campaign_path.write_text(
        """\
name: Crypto configurations
workspace: ../../
scenarios:
  - name: Configuration A
    setup: TestSuiteCCC/setup_a.py
    tests: [TestSuiteCCC/Tests/test_crypto.py::test_active_configuration]
  - name: Configuration B
    setup: TestSuiteCCC/setup_b.py
    tests: [TestSuiteCCC/Tests/test_crypto.py::test_active_configuration]
""",
        encoding="utf-8",
    )
    nodeid = "TestSuiteCCC/Tests/test_crypto.py::test_active_configuration"
    campaigns = discover_campaigns(str(tmp_path), (nodeid,))
    runs, regular = build_runs(campaigns, (nodeid,))
    request = RunRequest(
        workspace=str(tmp_path), interpreter=sys.executable,
        nodeids=(nodeid,), readers=(Reader("", 0),),
        regular_nodeids=regular, campaigns=runs,
    )
    outcomes = []

    report = ReaderRun(request, Reader("", 0), {}).run(
        on_line=lambda _line: None, on_outcome=outcomes.append)

    assert [outcome.phase_name for outcome in outcomes] == [
        "Configuration A", "Configuration B"]
    assert all(outcome.status is Status.PASSED for outcome in outcomes)
    assert report.counts == {Status.PASSED: 2}
    assert [phase.name for phase in report.phases] == [
        "Configuration A", "Configuration B"]
    assert "===== Crypto configurations · Configuration A =====" in report.output


def test_configuration_selector_filters_output_detail_and_logs(qapp, tmp_path):
    nodeid = "CryptoSuite/Tests/test_crypto.py::test_secure_channel"
    reader = Reader("Reader A", 0)
    phases = (
        CampaignPhase("0:0", "Configuration A", None, (nodeid,)),
        CampaignPhase("0:1", "Configuration B", None, (nodeid,)),
    )
    request = RunRequest(
        workspace=str(tmp_path), interpreter="python", nodeids=(nodeid,),
        readers=(reader,), campaigns=(CampaignRun(
            "Crypto campaign", "campaign.yml", str(tmp_path), phases),),
    )
    report = ReaderReport(
        reader=reader, output="A output\nB output\n",
        phases=[
            PhaseReport("0:0", "Configuration A", "Crypto campaign",
                        "A output\n", {nodeid: Status.PASSED}, True,
                        {nodeid: "INFO - OK\n"}, {nodeid: "a.log"}),
            PhaseReport("0:1", "Configuration B", "Crypto campaign",
                        "B output\n", {nodeid: Status.FAILED}, True,
                        {nodeid: "ERRO - Wrong Status Word\n"}, {nodeid: "b.log"}),
        ],
    )
    panel = ResultsPanel()
    panel.set_readers((reader,))
    panel.set_log_root(tmp_path)
    panel.begin_run(request)
    panel.set_report(report)
    panel.show_test(nodeid, {0: Status.FAILED}, str(tmp_path))

    panel.phase_tabs.setCurrentIndex(2)

    assert not panel.phase_bar.isHidden()
    assert panel.output.views[0].text() == "B output"
    assert panel.detail._dernier[2] == {0: Status.FAILED}
    assert panel.logs.views[0].text() == "ERRO - Wrong Status Word"


def test_tree_keeps_the_worst_result_across_campaign_configurations(qapp):
    nodeid = "Suite/test_file.py::test_case"
    model = TestTreeModel()
    model.set_tree(build_tree((nodeid,)))

    assert model.apply_outcome(nodeid, Status.FAILED, 0, aggregate=True)
    assert model.apply_outcome(nodeid, Status.PASSED, 0, aggregate=True)

    assert model.statuses_for_nodeid(nodeid) == {0: Status.FAILED}
