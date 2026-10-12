from PySide6.QtCore import Qt
from runner.domain.history import History, RunEntry
from runner.ui.history_dashboard import group_entries, HistoryWindow
from runner.ui.comparison_page import ComparisonPage, NODE, GROUP_NODES, GROUP_PATH


NODEID = 'suite/test_auth.py::TestAuth::test_login'


def test_compact_matrix_selection_and_trace_leave_top_tree_unchanged(qtbot, tmp_path):
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QHeaderView
    from runner.domain.failures import Failure
    history = populate(tmp_path)
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page._failures[('r1', 'Reader A')] = {NODEID: Failure(
        NODEID, body='unique trace\nE AssertionError: bad <value>')}
    parent = find_test(page).parent()
    page.resize(1450, 1000)
    page.show()
    page.tree.setCurrentIndex(parent)
    assert page.detail_stack.currentWidget() is page.group_matrix
    assert 'bad <value>' in page.group_preview.toPlainText()
    page.group_preview.anchorClicked.emit(QUrl('trace:1:0'))
    assert 'unique trace' in page.group_preview.toPlainText()
    assert page.tree.currentIndex() == parent
    assert page.differences.isChecked()
    page.group_preview.anchorClicked.emit(QUrl('trace:1:0'))
    assert 'unique trace' not in page.group_preview.toPlainText()
    for column in range(page.group_table.columnCount()):
        assert page.group_table.horizontalHeader().sectionResizeMode(column) == QHeaderView.Interactive
        assert '\n' not in page.group_table.horizontalHeaderItem(column).text()
    assert 'passed' in page.group_table.horizontalHeaderItem(1).toolTip()
    assert not page.group_table.grab().isNull()  # Exercise real badge painting.


def test_parent_recap_counts_all_tests_and_opens_hidden_failure(qtbot, tmp_path):
    from PySide6.QtCore import QUrl
    from runner.domain.failures import Failure
    stable = 'suite/test_auth.py::TestAuth::test_stable'
    error = 'suite/test_auth.py::TestAuth::test_setup'
    outside = 'other/test_other.py::test_other'
    history = History(tmp_path)
    for run, status in [('old', 'PASSED'), ('new', 'FAILED')]:
        history.add(RunEntry(id=run, timestamp=1 if run == 'old' else 2,
                            workspace='/tests', reader='A', executions=(
                                (NODEID, status), (NODEID, status),
                                (stable, 'PASSED'), (error, 'ERROR'), (outside, 'FAILED'))))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page._failures[('new', 'A')] = {NODEID: Failure(NODEID, body='E AssertionError: bad <value>')}
    page._failures[('old', 'A')] = {}
    parent = find_test(page).parent()
    page.tree.setCurrentIndex(parent)
    text = page.group_scope.text() + page.group_preview.toPlainText()
    assert '3 tests · 2 runs' in text
    assert '1 test with differences' in text
    assert page.group_table.item(0, 2).text() == 'FAILED'
    assert page.group_table.item(1, 1).text() == 'ERROR'
    assert 'bad <value>' in text
    assert 'test_other' not in text
    assert set(parent.data(GROUP_NODES)) == {NODEID, stable, error}
    assert page._group_links == [NODEID, error]
    path = tuple(parent.data(GROUP_PATH))
    page.detail.anchorClicked.emit(QUrl('group-test:1'))
    assert not page.differences.isChecked()  # The unchanged error was hidden.
    assert page.tree.currentIndex().data(NODE) == error
    assert page._test == error
    assert 'Back to group' in page.detail.toPlainText()
    page.detail.anchorClicked.emit(QUrl('group-back:'))
    assert tuple(page.tree.currentIndex().data(GROUP_PATH)) == path
    assert '3 tests · 2 runs' in page.group_scope.text()
    page.reference.setCurrentIndex(1)
    assert tuple(page.tree.currentIndex().data(GROUP_PATH)) == path
    assert 'Reference' in page.group_table.horizontalHeaderItem(2).text()


def test_parent_recap_distinguishes_missing_unknown_and_reader_scope(qtbot, tmp_path):
    history = History(tmp_path)
    sibling = 'suite/test_auth.py::TestAuth::test_other'
    for run, values in [('old', ((NODEID, ''), (sibling, 'SKIPPED'))),
                        ('new', ((sibling, 'SKIPPED'),))]:
        history.add(RunEntry(id=run, timestamp=1 if run == 'old' else 2,
                            workspace='/tests', reader='A', executions=values))
        history.add(RunEntry(id=run, timestamp=1 if run == 'old' else 2,
                            workspace='/tests', reader='B', executions=((NODEID, 'ERROR'),)))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page.tree.setCurrentIndex(find_test(page).parent())
    page.reader.setCurrentIndex(page.reader.findData('A'))
    text = page.group_scope.text() + ' '.join(
        page.group_table.horizontalHeaderItem(i).text() for i in range(page.group_table.columnCount()))
    assert '2 tests · 2 runs' in text
    assert page.group_table.item(0, 1).text() == 'Unknown'
    assert page.group_table.item(0, 2).text() == 'Not run'
    assert 'skipped' in page.group_table.horizontalHeaderItem(1).toolTip()
    assert 'ERROR' not in text
    assert '1 test with differences' in text


def test_parameter_parent_recap_is_scoped_to_its_cases(qtbot, tmp_path):
    history = History(tmp_path)
    nodes = [NODEID + '[valid]', NODEID + '[invalid]',
             'suite/test_auth.py::TestAuth::test_other']
    for run in range(2):
        history.add(RunEntry(id=str(run), timestamp=run+1, workspace='/tests', reader='A',
                            executions=tuple((node, 'PASSED' if run == 0 else 'FAILED') for node in nodes)))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    parent = page._find_index(NODE, nodes[0]).parent()
    page.tree.setCurrentIndex(parent)
    assert set(parent.data(GROUP_NODES)) == set(nodes[:2])
    text = page.group_scope.text() + ' '.join(page.group_table.item(i, 0).text()
                                           for i in range(page.group_table.rowCount()))
    assert '2 tests · 2 runs' in text
    assert 'test_other' not in text
    assert 'test_login[valid]' in text and 'test_login[invalid]' in text


def test_identical_results_show_explicit_message_and_can_be_revealed(qtbot, tmp_path):
    history = History(tmp_path)
    for i in range(2):
        history.add(RunEntry(id=str(i), timestamp=i+1, workspace='/tests',
                             reader='A', executions=((NODEID, 'FAILED'),)))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    assert page.results_stack.currentWidget() is page.empty_results
    assert page.empty_title.text() == 'No result differences'
    assert '1 compared tests' in page.empty_message.text()
    page.show_all_results.click()
    assert not page.differences.isChecked()
    assert page.results_stack.currentWidget() is not page.empty_results
    assert find_test(page) is not None
    page.differences.setChecked(True)
    page.reader.setCurrentIndex(page.reader.findData('A'))
    assert page.empty_scope.text().startswith('A ·')
    page.set_groups([])
    assert page.results_stack.currentWidget() is not page.empty_results


def test_unknown_results_do_not_claim_runs_are_identical(qtbot, tmp_path):
    history = History(tmp_path)
    for i in range(2):
        history.add(RunEntry(id=str(i), timestamp=i+1, workspace='/tests',
                             executions=((NODEID, ''),)))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    assert page.empty_title.text() == 'No differences in available results'
    assert 'cannot be confirmed' in page.empty_message.text()


def populate(path):
    history = History(path)
    for i, status in enumerate(('PASSED', 'FAILED', 'SKIPPED')):
        history.add(RunEntry(id=f'r{i}', timestamp=i + 1, workspace='/tests', reader='Reader A',
                             nodeids=(NODEID,), executions=((NODEID, status),),
                             replay_profile={'configuration_text': f'timeout: {i + 1}\n',
                                             'execution': {'repetitions': 1}, 'reports': {}}))
    return history


def find_test(page):
    def walk(parent):
        for row in range(page.model.rowCount(parent)):
            index = page.model.index(row, 0, parent)
            if index.data(NODE) == NODEID:
                return index
            found = walk(index)
            if found is not None:
                return found
    from PySide6.QtCore import QModelIndex
    return walk(QModelIndex())


def test_three_run_matrix_and_configuration(qtbot, tmp_path):
    history = populate(tmp_path)
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    assert page.model.columnCount() == 4
    index = find_test(page)
    assert [index.siblingAtColumn(i).data() for i in (1, 2, 3)] == ['PASSED', 'FAILED', 'SKIPPED']
    page.tree.setCurrentIndex(index)
    assert 'Reader A' in page.detail.toPlainText()
    assert page.config_model.item(0).text() == 'YAML.timeout'
    assert [page.config_model.item(0, i).text() for i in (1, 2, 3)] == ['1', '2', '3']
    page.reference.setCurrentIndex(2)
    page.refresh()
    assert page.reference.currentData() == 'r2'
    assert len(page.groups) == 3


def test_reader_changes_and_repetitions_are_not_hidden(qtbot, tmp_path):
    history = History(tmp_path)
    for run, readers in [('a', [('A', 'PASSED'), ('B', 'FAILED')]),
                         ('b', [('A', 'FAILED'), ('B', 'PASSED')])]:
        for reader, status in readers:
            history.add(RunEntry(id=run, timestamp=1, workspace='/tests', reader=reader,
                                 nodeids=(NODEID,), executions=((NODEID, status),)))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    assert find_test(page) is not None  # Equal global status, different readers.
    page.reader.setCurrentIndex(page.reader.findData('A'))
    assert page.reader.currentData() == 'A'
    assert find_test(page) is not None


def test_missing_is_distinct_from_unknown_and_skip(qtbot, tmp_path):
    history = History(tmp_path)
    for i, results in enumerate([((NODEID, 'SKIPPED'),), (), ((NODEID, ''),)]):
        history.add(RunEntry(id=str(i), timestamp=i + 1, workspace='/tests', reader='A', executions=results))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    index = find_test(page)
    assert [index.siblingAtColumn(i).data() for i in (1, 2, 3)] == ['SKIPPED', 'Not run', 'Unknown']


def test_history_shortcut_accepts_three_runs(qtbot, tmp_path):
    history = populate(tmp_path)
    window = HistoryWindow(history)
    qtbot.addWidget(window)
    captured = []
    window.compare_requested.connect(captured.append)
    window._enter_compare_mode()
    for row in range(window.run_list.count()):
        item = window.run_list.item(row)
        if item.data(Qt.UserRole) is not None:
            item.setSelected(True)
    assert window.compare_button.isEnabled()
    window._compare_clicked()
    assert len(captured[0]) == 3


def test_navigation_preserves_comparison(qtbot, tmp_path, monkeypatch):
    from runner.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    history = populate(tmp_path)
    window.comparison_page.history = history
    window._open_comparison(group_entries(history.entries()))
    assert window.pages.currentWidget() is window.comparison_page
    window.comparison_page.reference.setCurrentIndex(1)
    window._show_page('workspace')
    window._show_page('comparison')
    assert len(window.comparison_page.groups) == 3
    assert window.comparison_page.reference.currentIndex() == 1


def test_export_reloads_records_and_ignores_difference_filter(qtbot, tmp_path, monkeypatch):
    from zipfile import ZipFile
    from xml.etree import ElementTree as ET
    from runner.ui import comparison_page
    history = populate(tmp_path / 'history')
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page._records = [{}, {}, {}]  # A stale UI cache must not create an empty file.
    destination = tmp_path / 'report.xlsx'
    monkeypatch.setattr(comparison_page.QFileDialog, 'getSaveFileName',
                        lambda *args: (str(destination), ''))
    monkeypatch.setattr(comparison_page.QMessageBox, 'exec', lambda *args: None)
    page.export_excel()
    with ZipFile(destination) as book:
        root = ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    cells = {cell.attrib['r']: ''.join(cell.itertext()) for cell in root.findall('.//s:c', ns)}
    assert cells['A11'] == NODEID
    assert [cells[f'{col}11'] for col in 'CEG'] == ['PASSED', 'FAILED', 'SKIPPED']


def test_legacy_status_map_without_nodeids_is_compared(qtbot, tmp_path):
    history = History(tmp_path)
    for i, status in enumerate(('PASSED', 'FAILED')):
        history.add(RunEntry(id=str(i), timestamp=i+1, workspace='/tests',
                             test_statuses={NODEID: status}))
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    index = find_test(page)
    assert index is not None
    assert [index.siblingAtColumn(i).data() for i in (1, 2)] == ['PASSED', 'FAILED']


def test_detail_changes_follow_reference_and_reader(qtbot, tmp_path):
    history = populate(tmp_path)
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page.tree.setCurrentIndex(find_test(page))
    text = page.detail.toPlainText()
    assert text.count('Changed') == 2
    assert 'Reference' in text and '→' in text
    page.reference.setCurrentIndex(1)
    assert 'FAILED' in page.detail.toPlainText()
    assert page.detail.toPlainText().count('Changed') == 2


def test_detail_trace_toggle_preserves_skip_reason(qtbot, tmp_path):
    from PySide6.QtCore import QUrl
    from runner.domain.failures import Failure
    history = populate(tmp_path)
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(group_entries(history.entries()))
    page._failures[('r1', 'Reader A')] = {NODEID: Failure(NODEID, body='unique trace\nE AssertionError: bad <value>')}
    page._failures[('r2', 'Reader A')] = {NODEID: Failure(NODEID, kind='skip', body='Condition <demo>')}
    page.tree.setCurrentIndex(find_test(page))
    assert 'Condition <demo>' in page.detail.toPlainText()
    assert 'bad <value>' in page.detail.toPlainText()
    assert 'unique trace' not in page.detail.toPlainText()
    page.detail.anchorClicked.emit(QUrl('trace:1:0'))
    assert 'unique trace' in page.detail.toPlainText()
    page.detail.anchorClicked.emit(QUrl('trace:1:0'))
    assert 'unique trace' not in page.detail.toPlainText()
