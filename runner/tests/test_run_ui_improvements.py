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
