from PySide6.QtCore import Qt

from runner.domain.history import History, RunEntry
from runner.ui.history_dashboard import HistoryWindow
from runner.ui.history_execution_tree import HistoryExecutionModel
from runner.ui.tree_model import NODEID_ROLE


def test_history_parent_header_reserves_space_for_issues(qtbot, tmp_path):
    from PySide6.QtCore import QPoint
    from runner.ui.widgets import StatusRibbon

    history = History(tmp_path)
    for reader in ('Reader A', 'Reader B'):
        history.add(RunEntry(id='r', timestamp=1, workspace='', reader=reader,
                            executions=(('suite/test_a.py::test_one', 'FAILED'),)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    window.resize(1400, 950)
    window.show()
    window.execution_tree.setCurrentIndex(window.execution_model.index(0, 0))
    detail = window.execution_detail
    qtbot.waitUntil(lambda: detail.failures.isVisible())
    assert detail.group_path.isHidden()
    assert detail.failures_title.isHidden()
    assert not detail.ribbons_host.findChildren(StatusRibbon)
    assert detail.group_name.mapTo(detail, QPoint()).y() == detail.group_total.mapTo(detail, QPoint()).y()
    assert detail.failures.mapTo(detail, QPoint()).y() - detail.group_name.mapTo(detail, QPoint()).y() < 135
    assert detail.failures.count() == 1


def test_group_heading_uses_tab_row_and_returns_when_space_is_limited(qtbot, tmp_path):
    history = History(tmp_path)
    history.add(RunEntry(id='r', timestamp=1, workspace='', reader='A',
                        executions=(('suite/test_a.py::test_one', 'FAILED'),)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    window.resize(1800, 950)
    window.show()
    root = window.execution_model.index(0, 0)
    window.execution_tree.setCurrentIndex(root)
    qtbot.waitUntil(lambda: window.group_corner.isVisible())
    assert window.group_corner_name.text() == 'suite'
    assert '1 test' in window.group_corner_total.text()
    assert window.execution_detail.group_heading.isHidden()
    window.tabs.setCurrentIndex(1)
    assert window.group_corner.isHidden()
    window.tabs.setCurrentIndex(0)
    assert window.group_corner.isVisible()
    window.tabs.setFixedWidth(750)
    qtbot.waitUntil(lambda: window.group_corner.isHidden())
    assert not window.execution_detail.group_heading.isHidden()


def test_parent_summary_counts_tests_once_and_keeps_reader_unknowns(qtbot):
    from runner.domain.models import Status
    model = HistoryExecutionModel()
    good, bad, error = ('suite/security/test_auth.py::TestAuth::test_login[valid]',
                        'suite/security/test_auth.py::TestAuth::test_login[invalid]',
                        'suite/test_api.py::test_setup')
    entries = [RunEntry(id='r', timestamp=1, workspace='', reader='A',
                        executions=((good, 'PASSED'), (bad, 'FAILED'), (bad, 'PASSED'), (error, 'ERROR'))),
               RunEntry(id='r', timestamp=1, workspace='', reader='B',
                        executions=((good, 'PASSED'), (bad, 'PASSED')))]
    model.set_entries(entries)
    counts, failures, total, verdicts = model.group_results(model.index(0, 0))
    assert total == 3
    assert verdicts == {Status.PASSED: 1, Status.FAILED: 1, Status.ERROR: 1}
    assert counts[0] == {Status.PASSED: 1, Status.FAILED: 1, Status.ERROR: 1}
    assert counts[1] == {Status.PASSED: 2, Status.PENDING: 1}
    assert failures == [(bad, 0), (error, 0)]
    model.set_entry(entries[0])
    counts, failures, total, verdicts = model.group_results(model.index(0, 0), 0)
    assert total == 3
    assert sum(counts[0].values()) == 4
    assert failures == [(bad, 0), (error, 0)]


def test_history_parent_recap_navigates_directly_to_error_and_back(qtbot, tmp_path):
    nodeid = 'suite/security/test_auth.py::TestAuth::test_login[invalid]'
    output = tmp_path / 'output.txt'
    output.write_text('================ FAILURES ================\n'
                      '________ TestAuth.test_login[invalid] ________\n'
                      'E AssertionError: invalid PIN\n', encoding='utf-8')
    history = History(tmp_path)
    history.add(RunEntry(id='r', timestamp=1, workspace='', reader='A',
                         executions=((nodeid, 'FAILED'),), output_file=str(output)))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    model = window.execution_model
    root = model.index(0, 0)
    window.execution_tree.setCurrentIndex(root)
    detail = window.execution_detail
    assert detail.group_name.text() == 'suite'
    assert '1 test' in detail.group_total.text()
    assert '1 failed' in detail.group_summary.text()
    assert 'invalid PIN' in detail.failures.item(0).text()
    window.execution_tree.collapseAll()
    detail._sur_echec(detail.failures.item(0))
    assert detail._nodeid == nodeid
    assert window.execution_tree.currentIndex().data(NODEID_ROLE) == nodeid
    assert window.execution_tree.isExpanded(root)
    window._back_to_history_group()
    assert window.execution_tree.currentIndex() == root
    assert detail.group_name.text() == 'suite'
    window.reader_selector.setCurrentIndex(1)
    assert window._history_parent_index is None
    window._back_to_history_group()  # A reset model must never reuse an old index.


def test_expand_errors_keeps_successful_branches_closed(qtbot, tmp_path):
    history = History(tmp_path)
    history.add(RunEntry(id='r', timestamp=1, workspace='', reader='A', executions=(
        ('suite/security/test_ok.py::test_ok', 'PASSED'),
        ('suite/api/test_error.py::TestApi::test_error', 'ERROR'))))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    window._expand_history_failures()
    model = window.execution_model
    root = model.index(0, 0)
    assert window.execution_tree.isExpanded(root)
    good_branch = model.index(0, 0, root)
    bad_branch = model.index(1, 0, root)
    assert not window.execution_tree.isExpanded(good_branch)
    assert window.execution_tree.isExpanded(bad_branch)
    assert not window.execution_tree.isExpanded(model.index_for_nodeid('2'))


def test_every_parent_level_in_history_has_a_scoped_recap(qtbot, tmp_path):
    history = History(tmp_path)
    history.add(RunEntry(id='r', timestamp=1, workspace='', reader='A', executions=(
        ('suite/cards/test_auth.py::TestAuth::test_login[valid]', 'PASSED'),
        ('suite/cards/test_auth.py::TestAuth::test_login[invalid]', 'FAILED'))))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    index = window.execution_model.index(0, 0)
    for name in ('suite', 'cards', 'test_auth.py', 'TestAuth', 'test_login'):
        window.execution_tree.setCurrentIndex(index)
        assert window.execution_detail.group_name.text() == name
        assert '2 tests' in window.execution_detail.group_total.text()
        assert '1 passed' in window.execution_detail.group_summary.text()
        assert '1 failed' in window.execution_detail.group_summary.text()
        assert window.execution_detail.failures.count() == 1
        index = window.execution_model.index(0, 0, index)


def test_parent_unknown_results_are_not_reported_as_passed(qtbot):
    from runner.domain.models import Status
    model = HistoryExecutionModel()
    model.set_entry(RunEntry(id='old', timestamp=1, workspace='',
                             nodeids=('suite/test_a.py::test_unknown',)))
    counts, failures, total, verdicts = model.group_results(model.index(0, 0), 0)
    assert counts == {0: {Status.PENDING: 1}}
    assert verdicts == {Status.PENDING: 1}
    assert total == 1 and not failures


def test_history_issues_have_explicit_verdicts_and_filters_without_saved_traces(qtbot, tmp_path):
    from runner.domain.models import Status
    from runner.ui.group_issue_delegate import ISSUE_ROLE
    history = History(tmp_path)
    history.add(RunEntry(id='r', timestamp=1, workspace='', reader='A', executions=(
        ('suite/test_a.py::test_failed', 'FAILED'),
        ('suite/test_a.py::test_error', 'ERROR'),
        ('suite/test_a.py::test_passed', 'PASSED'))))
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    root = window.execution_model.index(0, 0)
    window.execution_tree.setCurrentIndex(root)
    panel = window.execution_detail
    assert panel.issue_filters.tabText(1) == 'Failed (1)'
    assert panel.issue_filters.tabText(2) == 'Errors (1)'
    assert panel.failures.item(0).data(ISSUE_ROLE)[0] is Status.FAILED
    assert panel.failures.item(1).data(ISSUE_ROLE)[0] is Status.ERROR
    panel.issue_filters.setCurrentIndex(2)
    assert panel.failures.item(0).isHidden()
    assert not panel.failures.item(1).isHidden()
    panel.issue_filters.setCurrentIndex(1)
    assert not panel.failures.item(0).isHidden()
    assert panel.failures.item(1).isHidden()
    for button in (window.history_expand_failures, window.history_expand_all, window.history_collapse_all):
        assert button.text() == '' and not button.icon().isNull()
        assert button.accessibleName()
    window.history_expand_all.click()
    assert window.execution_tree.isExpanded(root)
    window.history_collapse_all.click()
    assert not window.execution_tree.isExpanded(root)
    assert window.execution_tree.currentIndex() == root
    window.resize(1280, 900)
    window.show()
    qtbot.waitExposed(window)
    assert not panel.failures.grab().isNull()  # Exercise the delegate's painting.


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
