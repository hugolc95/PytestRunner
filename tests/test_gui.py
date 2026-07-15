import os, textwrap, time
from pathlib import Path
from PyQt5.QtCore import Qt
from gui_qt.test_tree_view import TestTreeView, STATUS_ROLE
from gui_qt.main_window import MainWindow, PytestWorker
from core.test_tree import build_test_tree
from core.test_discovery import collect_tests


def test_tree_selection_and_status(qtbot):
    nodeids=['tests/test_a.py::test_ok','tests/test_a.py::test_param[1]','tests/test_a.py::test_param[2]']
    tree=TestTreeView(); qtbot.addWidget(tree); tree.load_tree(build_test_tree(nodeids))
    assert sorted(tree.get_selected_nodeids())==sorted(nodeids)
    tree.set_all_checked(False); assert tree.get_selected_nodeids()==[]
    tree.set_all_checked(True); tree.update_single_test(nodeids[0], 'FAILED')
    assert tree._find_item_for_nodeid(nodeids[0]).data(STATUS_ROLE)=='FAILED'


def test_main_window_parses_results(qtbot):
    w=MainWindow(); qtbot.addWidget(w)
    w.workspace='.'
    w.tree.load_tree(build_test_tree(['test_a.py::test_ok','test_a.py::test_bad']))
    w._parse_pytest_output_line('collected 2 items')
    w._parse_pytest_output_line('test_a.py::test_ok PASSED [ 50%]')
    w._parse_pytest_output_line('test_a.py::test_bad FAILED [100%]')
    assert w.done_tests==2 and w.test_counts['PASSED']==1 and w.test_counts['FAILED']==1
    assert 'test_a.py::test_bad' in w.failed_nodeids


def test_worker_success_failure_skip_error(qtbot, tmp_path):
    (tmp_path/'test_all.py').write_text(textwrap.dedent('''
      import pytest
      def test_ok(): assert True
      def test_fail(): assert False
      @pytest.mark.skip(reason='demo')
      def test_skip(): pass
      @pytest.fixture
      def broken(): raise RuntimeError('boom')
      def test_error(broken): pass
    '''), encoding='utf-8')
    out=[]; result=[]
    worker=PytestWorker(['test_all.py'], str(tmp_path))
    worker.stdout_signal.connect(out.append); worker.finished_signal.connect(lambda c,s: result.append((c,s)))
    worker.start(); qtbot.waitUntil(lambda: bool(result), timeout=20000)
    text=''.join(out)
    assert result and result[0][0]==1
    for status in ('PASSED','FAILED','SKIPPED','ERROR'):
        assert status in text


def test_worker_stop(qtbot, tmp_path):
    (tmp_path/'test_slow.py').write_text('import time\ndef test_slow(): time.sleep(10)\n', encoding='utf-8')
    worker=PytestWorker(['test_slow.py'], str(tmp_path)); worker.start()
    qtbot.wait(500); worker.stop(); assert worker.wait(10000)


def test_single_parametrized_case_is_selectable_and_runs_alone(qtbot, tmp_path):
    """Un seul parametre peut etre coche puis execute via son nodeid pytest exact."""
    test_file = tmp_path / "test_parametrized.py"
    test_file.write_text(textwrap.dedent('''
        import pytest

        @pytest.mark.parametrize(
            ("value", "expected"),
            [
                pytest.param(1, 2, id="case_1"),
                pytest.param(2, 4, id="case_2"),
                pytest.param(3, 6, id="case_3"),
            ],
        )
        def test_double(value, expected):
            assert value * 2 == expected
    '''), encoding="utf-8")

    nodeids = collect_tests(str(tmp_path))
    assert nodeids == [
        "test_parametrized.py::test_double[case_1]",
        "test_parametrized.py::test_double[case_2]",
        "test_parametrized.py::test_double[case_3]",
    ]

    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(nodeids))
    tree.set_all_checked(False)

    selected_nodeid = "test_parametrized.py::test_double[case_2]"
    selected_item = tree._find_item_for_nodeid(selected_nodeid)
    assert selected_item is not None
    assert selected_item.text() == "[case_2]"

    selected_item.setCheckState(Qt.Checked)
    assert tree.get_selected_nodeids() == [selected_nodeid]

    output = []
    result = []
    worker = PytestWorker(tree.get_selected_nodeids(), str(tmp_path))
    worker.stdout_signal.connect(output.append)
    worker.finished_signal.connect(lambda code, stdout: result.append((code, stdout)))
    worker.start()
    qtbot.waitUntil(lambda: bool(result), timeout=20000)

    complete_output = "".join(output) + result[0][1]
    assert result[0][0] == 0
    assert "collected 1 item" in complete_output
    assert selected_nodeid in complete_output
    assert "test_double[case_1]" not in complete_output
    assert "test_double[case_3]" not in complete_output


def test_packaged_parametrized_cases_are_visible_and_individually_selectable(qtbot):
    """Régression: les exemples livrés doivent apparaître dans l'arbre du workspace racine."""
    project_root = Path(__file__).resolve().parents[1]
    nodeids = collect_tests(str(project_root))
    tree = TestTreeView()
    qtbot.addWidget(tree)
    tree.load_tree(build_test_tree(nodeids))
    tree.set_all_checked(False)

    target = "testSuite1/test_parametrized_selection.py::test_addition_parametree[medium]"
    item = tree._find_item_for_nodeid(target)
    assert item is not None
    assert item.text() == "[medium]"

    item.setCheckState(Qt.Checked)
    assert tree.get_selected_nodeids() == [target]
