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
    assert window._execution_reader_buttons.checkedId() == 0
    index = window.execution_model.index_for_nodeid('1').siblingAtColumn(1)
    assert window.execution_model.data(index) == 'PASSED'
    window._execution_reader_buttons.button(1).click()
    index = window.execution_model.index_for_nodeid('1').siblingAtColumn(1)
    assert window.execution_model.data(index) == 'ERROR'
    assert window._execution_reader_buttons.checkedId() == 1
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
