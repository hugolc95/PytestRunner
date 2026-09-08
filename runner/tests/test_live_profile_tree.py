from PySide6.QtCore import Qt
from runner.domain.execution_profile import ExecutionProfile, ExecutionOptions
from runner.domain.models import Reader, ReaderReport, RunRequest, Status
from runner.domain.tree import build_tree
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.main_window import MainWindow


NODE = 'suite/test_card.py::test_read'


def test_profile_status_filter_tracks_occurrences_readers_and_live_retries(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.model.set_tree(build_tree([NODE]))
    window._running_execution_profile = profile()
    window._on_run_started(RunRequest(workspace='', interpreter='python', nodeids=(NODE, NODE),
                                      readers=(Reader('A', 0), Reader('C', 2))))
    window._on_profile_execution(0, 0, 0, NODE, Status.PASSED)
    window._on_profile_execution(0, 0, 2, NODE, Status.ERROR)
    window._on_profile_execution(1, 0, 0, NODE, Status.FAILED)

    def hidden(key):
        index = window.profile_model.index_for_nodeid(key)
        return window.profile_tree.isRowHidden(index.row(), index.parent())

    window.filter_by_status(Status.FAILED)
    assert hidden('0:0') and not hidden('1:0')
    window._on_profile_execution(0, 1, 2, NODE, Status.RUNNING)
    assert hidden('0:1')
    window._on_profile_execution(0, 1, 2, NODE, Status.FAILED)
    assert not hidden('0:1')
    index = window.profile_model.index_for_nodeid('0:1').parent()
    while index.isValid():
        assert not window.profile_tree.isRowHidden(index.row(), index.parent())
        index = index.parent()
    window.filter_by_status(Status.ERROR)
    assert not hidden('0:0') and hidden('1:0') and hidden('0:1')
    window._set_profile_tree_visible(False)
    window.filter_by_status(Status.ERROR)  # Clear while in the other view.
    window._set_profile_tree_visible(True)
    assert not any(hidden(key) for key in ('0:0', '0:1', '1:0'))
    window.filter_by_status(Status.SKIPPED)
    assert all(hidden(key) for key in ('0:0', '0:1', '1:0'))
    window._on_profile_execution(1, 0, 2, NODE, Status.SKIPPED)
    assert not hidden('1:0')
    window._elapsed.stop()


def test_profile_notification_uses_same_counts_as_visible_results(qtbot, monkeypatch):
    from types import SimpleNamespace
    from collections import Counter
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: True)
    window = MainWindow()
    qtbot.addWidget(window)
    messages = []
    window._tray = SimpleNamespace(showMessage=lambda *args: messages.append(args))
    window.model.set_tree(build_tree([NODE]))
    window.model.apply_outcome(NODE, Status.PASSED, 0)
    window._profile_count_statuses = {}
    window._profile_verdict_counts = Counter({Status.PASSED: 8, Status.FAILED: 2,
                                              Status.SKIPPED: 3, Status.ERROR: 1})
    window._notifier_fin_de_run('All tests passed')
    assert messages[-1][0] == 'Profile run finished'
    assert messages[-1][1] == '8 passed · 2 failed · 3 skipped · 1 error'
    assert messages[-1][2] == QSystemTrayIcon.Critical
    window._profile_count_statuses = None
    window._notifier_fin_de_run('All tests passed')
    assert messages[-1][0] == 'All tests passed'
    assert messages[-1][1] == '1 passed · 0 failed · 0 skipped · 0 error'
    assert messages[-1][2] == QSystemTrayIcon.Information


def test_profile_counters_count_occurrences_readers_and_retries(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.model.set_tree(build_tree([NODE]))
    window._running_execution_profile = profile()
    readers = (Reader('A', 0), Reader('C', 2))
    request = RunRequest(workspace='', interpreter='python', nodeids=(NODE, NODE), readers=readers)
    window._on_run_started(request)
    events = [(0, 0, Status.FAILED), (0, 2, Status.PASSED),
              (1, 0, Status.SKIPPED), (1, 2, Status.ERROR)]
    for position, reader, status in events:
        window._on_profile_execution(position, 0, reader, NODE, status)
    window._rafraichir_compteurs()
    assert window._completed_executions() == 4
    assert window.progress.maximum() == 4
    assert all(window.compass_ring._counts[status] == 1 for status in
               (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR))
    window._on_profile_execution(0, 1, 0, NODE, Status.RUNNING)
    window._on_profile_execution(0, 1, 0, NODE, Status.PASSED)
    window._on_profile_execution(0, 1, 0, NODE, Status.PASSED)
    window._on_progress(4, 4)  # Service progress excludes retries.
    window._rafraichir_compteurs()
    assert window._completed_executions() == 5
    assert window.progress.maximum() == 5
    assert window.compass_ring._counts[Status.PASSED] == 2
    window._set_profile_tree_visible(False)
    window._rafraichir_compteurs()
    assert window._completed_executions() == 5
    window._running_execution_profile = None
    window._show_failure_actions([])
    assert window._completed_executions() == 5
    window._on_run_started(request)
    assert window._completed_executions() == 0
    assert window.compass_ring._counts[Status.PASSED] == 0
    window._elapsed.stop()


def test_reader_columns_use_classic_icons_and_preserve_expansion(qtbot):
    from PySide6.QtWidgets import QTreeView
    from runner.ui.tree_model import TestTreeModel

    model = LiveProfileModel()
    readers = (Reader('A', 0), Reader('C', 2), Reader('D', 3))
    model.prepare(profile(), readers[:2])
    tree = QTreeView()
    qtbot.addWidget(tree)
    tree.setModel(model)
    tree.expandAll()
    root = model.index(0, 0)
    model.set_readers(readers)
    assert tree.isExpanded(root)
    assert model.columnCount() == 4
    classic = TestTreeModel()
    classic.set_tree(build_tree([NODE]))
    classic.set_readers(readers)
    for reader, status in zip(readers, (Status.PASSED, Status.ERROR, Status.SKIPPED)):
        model.apply_execution(0, 0, reader.index, NODE, status)
        classic.apply_outcome(NODE, status, reader.index)
    for column in range(1, 4):
        index = model.index_for_nodeid('0:0').siblingAtColumn(column)
        reference = classic.index_for_nodeid(NODE).siblingAtColumn(column)
        assert index.data() is None
        expected = classic._data_colonne_statut(reference.internalPointer(), readers[column - 1].index, Qt.DecorationRole)
        assert index.data(Qt.DecorationRole).cacheKey() == expected.cacheKey()
        assert model.index_for_nodeid('1:0').siblingAtColumn(column).data(Qt.DecorationRole) is None
    model.set_readers(readers[1:])
    assert model.columnCount() == 3
    assert tree.isExpanded(root)
    assert model.statuses_for_nodeid('0:0')[2] is Status.ERROR


def profile():
    return ExecutionProfile(name='Card validation', sequence=[NODE],
                            configuration_name='', configuration_text='',
                            execution=ExecutionOptions(repetitions=2))


def test_occurrences_and_retries_are_separate_with_sparse_readers(qtbot):
    model = LiveProfileModel()
    model.prepare(profile(), (Reader('A', 0), Reader('C', 2)))
    model.apply_execution(0, 0, 0, NODE, Status.FAILED)
    model.apply_execution(1, 0, 0, NODE, Status.RUNNING)
    model.apply_execution(1, 0, 0, NODE, Status.PASSED)
    model.apply_execution(1, 0, 2, NODE, Status.ERROR)
    model.apply_execution(0, 1, 0, NODE, Status.PASSED)
    assert model.statuses_for_nodeid('0:0')[0] is Status.FAILED
    assert model.statuses_for_nodeid('0:1')[0] is Status.PASSED
    assert model.statuses_for_nodeid('1:0')[0] is Status.PASSED
    status_index = model.index_for_nodeid('1:0').siblingAtColumn(2)
    assert model.data(status_index) is None
    assert not model.data(status_index, Qt.DecorationRole).isNull()
    assert model.statuses_for_nodeid('1:0')[2] is Status.ERROR
    assert model.status_for(model._roots[1], 0) is Status.PASSED
    assert len(model.locations) == 3


def test_stop_does_not_leave_a_running_execution(qtbot):
    model = LiveProfileModel()
    model.prepare(profile(), ())
    model.apply_execution(0, 0, 0, NODE, Status.RUNNING)
    model.finish()
    assert model.data(model.index_for_nodeid('0:0').siblingAtColumn(1), Qt.ToolTipRole) == 'Interrupted'
    assert model.data(model.index_for_nodeid('1:0').siblingAtColumn(1), Qt.ToolTipRole) == 'Not run'
    assert model.data(model.index_for_nodeid('1:0').siblingAtColumn(1)) is None


def test_switch_keeps_classic_selection_and_execution_details(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.model.set_tree(build_tree([NODE]))
    window.tree.expandAll()
    expanded = window._expanded_tree_paths()
    window._running_execution_profile = profile()
    reader = Reader('A', 0)
    window._on_run_started(RunRequest(workspace='', interpreter='python', nodeids=(NODE, NODE), readers=(reader,)))
    assert window.left_stack.currentWidget() is window.profile_tree
    window._on_profile_execution(0, 0, 0, NODE, Status.FAILED)
    window._on_profile_execution(1, 0, 0, NODE, Status.PASSED)
    window._on_profile_batch_report(0, 1, 0, ReaderReport(reader=reader, output='first attempt failed\n'))
    window._on_profile_batch_report(1, 1, 0, ReaderReport(reader=reader, output='second attempt passed\n'))
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid('1:0'))
    window._refresh_profile_selection()
    assert window.profile_results._statuses[0] is Status.PASSED
    assert 'second attempt' in window.profile_results.output.views[0].text()
    window._set_profile_tree_visible(False)
    assert window.left_stack.currentWidget() is window.tree
    assert window.model.checked_nodeids() == [NODE]
    assert window._expanded_tree_paths() == expanded
    window._set_profile_tree_visible(True)
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid('0:0'))
    assert window.profile_results._statuses[0] is Status.FAILED
    assert 'first attempt' in window.profile_results.output.views[0].text()
    assert 'second attempt' not in window.profile_results.output.views[0].text()
    window._elapsed.stop()
    window._profile_selection_timer.stop()


def test_live_console_does_not_follow_another_repetition(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window._running_execution_profile = profile()
    window._on_run_started(RunRequest(workspace='', interpreter='python', nodeids=(NODE, NODE), readers=()))
    window._on_profile_output(0, 1, 0, 0, 'first batch\n')
    window._flush_profile_console()
    assert 'first batch' in window.profile_results.output.views[0].text()
    window._on_profile_output(1, 1, 0, 0, 'second batch\n')
    window._flush_profile_console()
    assert 'second batch' not in window.profile_results.output.views[0].text()
    window.profile_tree.setCurrentIndex(window.profile_model.index_for_nodeid('1:0'))
    assert 'second batch' in window.profile_results.output.views[0].text()
    assert 'first batch' not in window.profile_results.output.views[0].text()
    window._elapsed.stop()
    window._profile_selection_timer.stop()
    window._profile_console_timer.stop()


def test_large_profile_model_keeps_constant_depth_updates(qtbot):
    model = LiveProfileModel()
    large = ExecutionProfile(name='Large', configuration_name='', configuration_text='', sequence=[f'test_a.py::test_case[{i}]' for i in range(50000)])
    model.prepare(large, ())
    for position, nodeid in enumerate(large.sequence):
        model.apply_execution(position, 0, 0, nodeid, Status.RUNNING)
        model.apply_execution(position, 0, 0, nodeid, Status.PASSED)
    assert model.status_for(model._roots[0], 0) is Status.PASSED
