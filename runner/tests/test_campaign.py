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


def _campaign_avec_dossiers(workspace: Path) -> Path:
    """Une campagne qui liste des DOSSIERS et un FICHIER entier, comme le
    fait un vrai campaign.yaml : plus court a ecrire, et un test ajoute au
    dossier plus tard y entre sans toucher au YAML."""
    path = workspace / "flexiPQC" / "Campaigns" / "campaign.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """\
campaign:
  - config: ../Tests/00_CardConfig/test_001_SetConfig.py
    tests:
      - ../Tests/02_MLDSA_flexicoded
      - ../Tests/00_CardConfig/test_999_single_file.py
""",
        encoding="utf-8",
    )
    return path


def test_a_folder_or_whole_file_under_tests_expands_to_every_test_it_contains(
    tmp_path,
):
    """Le YAML n'a pas toujours un nodeid precis sous `tests:` : parfois un
    dossier entier, parfois un fichier .py entier -- comme les scripts de
    `config:`, relatifs au fichier Campaign lui-meme, `..` compris.
    """
    _campaign_avec_dossiers(tmp_path)
    collected = (
        "flexiPQC/Tests/02_MLDSA_flexicoded/test_foo.py::test_a",
        "flexiPQC/Tests/02_MLDSA_flexicoded/test_foo.py::test_b",
        "flexiPQC/Tests/00_CardConfig/test_999_single_file.py::test_x",
        # Un dossier voisin qui ne doit PAS etre couvert : sans cela, le test
        # ne prouverait pas que seul le dossier nomme est retenu.
        "flexiPQC/Tests/03_MLKEM_activated/test_bar.py::test_c",
    )

    found = discover_campaigns(str(tmp_path), collected)

    assert len(found) == 1
    assert set(found[0].nodeids) == {
        "flexiPQC/Tests/02_MLDSA_flexicoded/test_foo.py::test_a",
        "flexiPQC/Tests/02_MLDSA_flexicoded/test_foo.py::test_b",
        "flexiPQC/Tests/00_CardConfig/test_999_single_file.py::test_x",
    }


def test_an_empty_folder_under_tests_is_dropped_rather_than_kept_verbatim(
    tmp_path,
):
    """Un chemin qui ne couvre rien (dossier vide, faute de frappe) ne doit
    pas laisser un identifiant litteral dans les nodeids : ce dernier ne
    correspondrait a aucun test de l'arbre, et la campagne resterait invisible
    sans qu'aucune erreur ne le signale."""
    _campaign_avec_dossiers(tmp_path)
    collected = ("flexiPQC/Tests/00_CardConfig/test_999_single_file.py::test_x",)

    found = discover_campaigns(str(tmp_path), collected)

    assert len(found) == 1
    assert "../Tests/02_MLDSA_flexicoded" not in found[0].nodeids
    assert all("::" in nodeid for nodeid in found[0].nodeids)


def test_the_campaign_badge_follows_the_theme_instead_of_painting_black():
    """`QColor(rgba(...))` echoue en silence et rend un noir opaque -- invisible
    sur le fond sombre de l'arbre, mais un pave noir plaque sur son fond clair.
    Verifie sur le PIXEL peint, pas sur la couleur demandee : c'est justement
    ce que `QColor` peut refuser sans le dire.
    """
    from PyQt5.QtCore import QSettings
    from PyQt5.QtWidgets import QApplication

    from runner.ui.main_window import APP, ORG, MainWindow
    from runner.ui.tree_model import CAMPAIGN_ROLE

    qapp = QApplication.instance() or QApplication([])
    QSettings(ORG, APP).clear()
    nodeids = ("Suite/test_x.py::test_a", "Suite/test_x.py::test_b")

    fenetre = MainWindow()
    fenetre.model.set_tree(build_tree(nodeids))
    fenetre.model.set_campaigns({n: "campaign.yml" for n in nodeids})
    fenetre.left_stack.setCurrentWidget(fenetre.tree)
    fenetre.tree.expandAll()
    fenetre.resize(900, 300)

    try:
        for nom in ("dark", "light"):
            fenetre.apply_theme(nom)
            fenetre.show()
            qapp.processEvents()

            # Le badge n'est pas sur une feuille mais sur l'ancetre commun
            # (voir `_rebuild_campaign_roots`) : on le retrouve comme le fait
            # deja `test_marks_only_the_common_campaign_suite`, plutot que de
            # deviner sa position dans l'arbre.
            marquees = []
            pile = [fenetre.model.index(r, 0) for r in range(fenetre.model.rowCount())]
            while pile:
                index = pile.pop()
                if index.data(CAMPAIGN_ROLE):
                    marquees.append(index)
                pile.extend(fenetre.model.index(r, 0, index)
                           for r in range(fenetre.model.rowCount(index)))
            assert len(marquees) == 1, f"{nom} : {len(marquees)} ligne(s) marquee(s)"

            rect = fenetre.tree.visualRect(marquees[0])
            # Meme geometrie que `CampaignBadgeDelegate.paint()` : la pastille
            # (76x20) est ancree a 8px du bord droit de la colonne. On prend un
            # pixel pres du bord interieur, loin du texte centre.
            x = rect.right() - 80
            y = rect.center().y() - 7

            pixel = fenetre.tree.viewport().grab().toImage().pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue()) != (0, 0, 0), (
                f"{nom} : la pastille Campaign est peinte en noir opaque")
    finally:
        fenetre.hide()


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
