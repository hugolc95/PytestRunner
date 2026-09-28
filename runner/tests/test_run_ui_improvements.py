from types import SimpleNamespace

from PySide6.QtGui import QTextCursor

from runner.ui.console_view import ConsoleView
from runner.ui.main_window import MainWindow
from runner.services.run_service import RunService


def test_single_log_severity_and_error_navigation(qtbot):
    widget = ConsoleView(show_lens=False)
    qtbot.addWidget(widget)
    widget.set_text('INFO - ERROR mentioned, not an error\n'
                    '2026-09-07 10:00:00 - ERROR - failed\n'
                    'WARNING - caution\nDEBUG - details\nERRO - second failure\n')
    widget.log_highlighter.rehighlight()
    document = widget.view.document()
    assert not document.firstBlock().layout().formats()
    for number in range(1, 5):
        assert document.findBlockByNumber(number).layout().formats()
    widget.view.setTextCursor(QTextCursor(document.firstBlock()))
    widget.next_error.click()
    assert widget.view.textCursor().blockNumber() == 1
    widget.next_error.click()
    assert widget.view.textCursor().blockNumber() == 4
    widget.next_error.click()
    assert widget.view.textCursor().blockNumber() == 1
    widget.previous_error.click()
    assert widget.view.textCursor().blockNumber() == 4


def test_profile_detail_distinguishes_repetition_and_retry(qtbot):
    service = RunService()
    service._current_batch = ['a', 'b']
    service._profile_expanded_length = 6
    service._profile_queue = ['a', 'b', 'a', 'b']
    service._profile_sequence_length = 2
    service._profile_repetitions = 3
    service._profile_attempt = 1
    service._profile_reruns = 2
    details = []
    service.profile_detail.connect(lambda reader, text: details.append(text))
    service._emit_profile_detail(0, 'b')
    assert details == ['Repetition 2/3 · Step 2/2 · Retry 1/2 · b']


def test_recollect_preserves_expansion(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    collection = SimpleNamespace(
        nodeids=['folder/test_a.py::test_one', 'folder/test_b.py::test_two'],
        markers={}, marker_list=lambda: [])
    window._on_collected(collection)
    window.tree.collapseAll()
    first = window.tree.model().index(0, 0)
    window.tree.setExpanded(first, True)
    expanded = window._expanded_tree_paths()
    window._on_collected(collection)
    assert window._expanded_tree_paths() == expanded
    window.tree.collapseAll()
    window._on_collected(collection)
    assert window._expanded_tree_paths() == set()


def test_profile_progress_lives_in_status_bar_without_wrapping(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window._show_profile_detail(-1, 'Repetition 1/3 · Step 1/2 · Preparing: test_a')
    window._show_profile_detail(0, 'Repetition 1/3 · Step 1/2 · test_a')
    window._show_profile_detail(1, 'Repetition 1/3 · Step 2/2 · Retry 1/2 · test_b')
    label = window.profile_progress_label
    assert window.statusBar().isAncestorOf(label)
    assert not label.wordWrap()
    assert '\n' not in label.text()
    assert 'Retry 1/2' in label.text()
    assert 'test_a' in label.toolTip() and 'test_b' in label.toolTip()
    window._show_failure_actions([])
    assert label.isHidden()


def test_recollect_keeps_checks_current_result_and_open_tab(qtbot, monkeypatch):
    from runner.domain.models import Status
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    a, b, c = ('folder/test_a.py::test_one', 'folder/test_b.py::test_two',
               'folder/test_c.py::test_new')
    def collect(ids):
        window._on_collected(SimpleNamespace(nodeids=ids, markers={}, marker_list=lambda: []))
    collect([a, b])
    window.model.set_checked_nodeids([b])
    window.model.apply_outcome(b, Status.SKIPPED, 0)
    window.tree.setCurrentIndex(window.model.index_for_nodeid(b))
    window.results.tabs.setCurrentIndex(2)
    before = window.results.detail.body.toPlainText()
    collect([a, b, c])
    assert window.model.checked_nodeids() == [b]
    assert window.tree.currentIndex() == window.model.index_for_nodeid(b)
    assert window.model.statuses_for_nodeid(b)[0] is Status.SKIPPED
    assert window.results.detail.body.toPlainText() == before
    assert window.results.tabs.currentIndex() == 2
    collect([a, c])
    assert not window.tree.currentIndex().isValid()
    assert window.model.checked_nodeids() == []
    assert window.results._nodeid == ''


def test_recollect_keeps_profile_view_open(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    collection = SimpleNamespace(nodeids=['test_a.py::test_one'], markers={}, marker_list=lambda: [])
    window._on_collected(collection)
    window._set_profile_tree_visible(True)
    window._on_collected(collection)
    assert window.profile_tree_button.isChecked()
    assert window.left_stack.currentWidget() is window.profile_tree
    assert window.results_stack.currentWidget() is window.profile_result_page


def test_recollect_keeps_scroll_and_group_but_new_workspace_resets(qtbot, monkeypatch, tmp_path):
    from runner.domain.workspace import Workspace
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    collection = SimpleNamespace(
        nodeids=[f'folder/test_a.py::test_{i:03}' for i in range(100)],
        markers={}, marker_list=lambda: [])
    window._on_collected(collection)
    window.show()
    window.tree.expandAll()
    group = window.model.index(0, 0)
    window.tree.setCurrentIndex(group)
    window.tree.doItemsLayout()
    window.tree.verticalScrollBar().setValue(30)
    scroll = window.tree.verticalScrollBar().value()
    assert scroll > 0
    window.model.set_all_checked(False)
    group_name = group.data()
    window._on_collected(collection)
    assert window.tree.verticalScrollBar().value() == scroll
    assert window.tree.currentIndex().data() == group_name
    assert window.model.checked_nodeids() == []
    other = tmp_path / 'other'
    other.mkdir()
    window.workspace = Workspace.load(str(other))
    window._on_collected(collection)
    assert len(window.model.checked_nodeids()) == 100
    assert not window.tree.currentIndex().isValid()
