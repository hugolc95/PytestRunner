from PySide6.QtCore import Qt

from runner.domain.history import History, RunEntry
from runner.ui.history_dashboard import HistoryWindow
from runner.ui.history_execution_tree import HistoryExecutionModel
from runner.ui.tree_model import NODEID_ROLE


def test_repeated_profile_executions_keep_separate_results(qtbot, tmp_path):
    results = (('suite/test_a.py::test_one', 'FAILED'),
               ('other/test_b.py::test_two', 'SKIPPED'),
               ('suite/test_a.py::test_one', 'PASSED'))
    history = History(tmp_path)
    history.add(RunEntry(id='profile', timestamp=1, workspace='', run_kind='profile',
                        profile_name='Smoke', nodeids=tuple(n for n, _ in results), executions=results))
    saved = History(tmp_path).entries()[0]
    assert saved.executions == results
    model = HistoryExecutionModel()
    model.set_entry(saved)
    for i, (nodeid, status) in enumerate(results, 1):
        index = model.index_for_nodeid(str(i))
        assert model.data(index, NODEID_ROLE) == nodeid
        assert model.data(index.siblingAtColumn(1)) == status
        assert model.data(index, Qt.CheckStateRole) is None
    assert model.rowCount() == 3


def test_reader_selection_changes_overview(qtbot, tmp_path):
    history = History(tmp_path)
    nodeid = 'suite/test_a.py::test_one'
    for reader, status in [('A', 'PASSED'), ('B', 'ERROR')]:
        history.add(RunEntry(id='run', timestamp=1, workspace='', reader=reader,
                            nodeids=(nodeid,), counts={status: 1},
                            executions=((nodeid, status),)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    assert window.tabs.tabText(0) == 'Overview'
    assert window.tabs.tabText(1).startswith('Failed')
    assert window.reader_selector.currentData() == -1
    root = window.execution_model.index_for_nodeid('1')
    assert window.execution_model.data(root.siblingAtColumn(1)) == 'ERROR'
    assert not window.execution_tree.isExpanded(root)
    assert window.execution_model.rowCount(root) == 2
    window.reader_selector.setCurrentIndex(1)
    index = window.execution_model.index_for_nodeid('1').siblingAtColumn(1)
    assert window.execution_model.data(index) == 'PASSED'
    window.reader_selector.setCurrentIndex(2)
    index = window.execution_model.index_for_nodeid('1').siblingAtColumn(1)
    assert window.execution_model.data(index) == 'ERROR'
    assert window.reader_selector.currentData() == 1
    assert window.execution_title.text().endswith('B')


def test_old_profile_repeats_do_not_invent_intermediate_results(qtbot):
    model = HistoryExecutionModel()
    model.set_entry(RunEntry(id='old', timestamp=1, workspace='',
                             nodeids=('test_a', 'test_a'), test_statuses={'test_a': 'PASSED'}))
    assert model.rowCount() == 2
    assert model.data(model.index(0, 1)) == 'Unknown (older run)'


def test_large_history_tree_is_virtualized(qtbot):
    model = HistoryExecutionModel()
    results = tuple((f'test_a.py::test_case[{i}]', 'PASSED') for i in range(50000))
    model.set_entry(RunEntry(id='big', timestamp=1, workspace='', executions=results))
    assert len(model._by_nodeid) == 50000
    assert model.data(model.index_for_nodeid('50000').siblingAtColumn(1)) == 'PASSED'


def test_global_verdict_keeps_reader_attempts_and_unknowns(qtbot):
    from runner.domain.models import Status
    node = 'suite/test_a.py::test_one'
    model = HistoryExecutionModel()
    model.set_entries([
        RunEntry(id='r', timestamp=1, workspace='', reader='A',
                 executions=((node, 'FAILED'), (node, 'PASSED'))),
        RunEntry(id='r', timestamp=1, workspace='', reader='B', executions=((node, 'SKIPPED'),)),
    ])
    parent = model.index_for_nodeid('1')
    assert parent.data(NODEID_ROLE) == node
    assert parent.siblingAtColumn(1).data() == 'FAILED'
    reader = model.index(0, 0, parent)
    assert reader.data() == 'A'
    assert model.rowCount(reader) == 2
    assert model.index(1, 1, reader).data() == 'PASSED'
    assert model.reader_for_index(reader) == 0


def test_history_counter_filters_global_tests_and_reader_details(qtbot, tmp_path):
    from runner.domain.models import Status
    node, passed = 'test_a.py::test_one', 'test_a.py::test_two'
    history = History(tmp_path)
    for reader, verdict in [('A', 'PASSED'), ('B', 'SKIPPED')]:
        history.add(RunEntry(id='r', timestamp=1, workspace='', reader=reader,
                            counts={verdict: 1, 'ERROR': 0}, nodeids=(node,),
                            executions=((node, verdict),)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    assert window.skipped_value.text() == '1'
    assert '100% success' in window.success_value.text()
    root = window.execution_model.index_for_nodeid('1')
    window.execution_tree.setCurrentIndex(root)
    assert window.execution_detail._nodeid == node
    window.result_cards[Status.PASSED].click()
    assert window.execution_tree.isRowHidden(0, root.parent())
    window.result_cards[Status.SKIPPED].click()
    assert not window.execution_tree.isRowHidden(0, root.parent())
    window.reader_selector.setCurrentIndex(1)
    assert window.skipped_value.text() == '0'
    assert window.passed_value.text() == '1'
    assert window._result_filter is None


def test_global_tree_preserves_folders_classes_and_parameter_parents(qtbot):
    nodeids = ('suite/cards/test_auth.py::TestAuth::test_login[valid]',
               'suite/cards/test_auth.py::TestAuth::test_login[invalid]')
    model = HistoryExecutionModel()
    model.set_entries([RunEntry(id='r', timestamp=1, workspace='', reader='A',
                               executions=tuple(zip(nodeids, ('PASSED', 'FAILED'))))])
    parent = model.index(0, 0)
    for name in ('suite', 'cards', 'test_auth.py', 'TestAuth', 'test_login'):
        assert parent.data() == name
        assert parent.siblingAtColumn(1).data() == 'FAILED'
        parent = model.index(0, 0, parent)
    assert parent.data() == '[valid]'
    assert parent.siblingAtColumn(1).data() == 'PASSED'
    assert model.index(0, 0, parent).data() == 'A'
    assert model.index_for_nodeid('2').data() == '[invalid]'
