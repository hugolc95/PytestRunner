"""Recherche dans les vrais documents Qt des logs et des lecteurs compares."""

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence

from runner.domain.models import Reader
from runner.ui.console_view import ConsoleView, MAX_LIGNES
from runner.ui.results_panel import ONGLET_LOGS, ResultsPanel


@pytest.fixture
def log(qtbot):
    widget = ConsoleView(show_lens=False)
    qtbot.addWidget(widget)
    widget.resize(650, 350)
    widget.show()
    return widget


def find(log, text):
    log.search.field.setText(text)
    log.search.refresh()


@pytest.mark.parametrize('prefix', [
    '2026-10-27 00:31:45,233 - ',
    '2026-10-27T00:31:45.233Z | ',
    '[2026-10-27 00:31:45.233] ',
    '00:31:45,233 - ',
])
def test_log_hides_timestamp_prefix_but_keeps_message_dates_and_original(log, prefix):
    message = 'INFO - Card expires at 2027-10-27 00:31:45,233'
    original = prefix + message
    log.set_text(original)
    assert log.view.toPlainText().rstrip('\n') == message
    assert log.text() == original
    log.copy_all()
    from PySide6.QtWidgets import QApplication
    assert QApplication.clipboard().text() == message
    log.restyle()
    assert log.view.toPlainText().rstrip('\n') == message


def test_live_coloured_log_preserves_lines_search_and_error_navigation(log):
    log.append('\x1b[31m2026-10-27 00:31:45,233 - ER')
    log.append('ROR - rejected\x1b[0m\n2026-10-27 00:31:45,234 - INFO - accepted\n')
    assert log.view.toPlainText() == 'ERROR - rejected\nINFO - accepted\n'
    find(log, 'accepted')
    assert log.view.textCursor().selectedText() == 'accepted'
    assert log.view.textCursor().blockNumber() == 1
    log.navigate_error(-1)
    assert log.view.textCursor().selectedText() == 'ERROR - rejected'
    log.set_text('2026-10-27 00:31:45 is the message, not a logging prefix')
    assert log.view.toPlainText().startswith('2026-10-27 00:31:45 is')


@pytest.mark.parametrize('show_lens', [False, True])
def test_ctrl_a_selects_active_log_or_output_instead_of_tests(qtbot, show_lens):
    widget = ConsoleView(show_lens=show_lens)
    qtbot.addWidget(widget)
    tree_calls = []
    action = QAction(widget)
    action.setShortcut(QKeySequence.SelectAll)
    action.triggered.connect(lambda: tree_calls.append(True))
    widget.addAction(action)
    original = '2026-10-27 00:31:45,233 - INFO - first\nsecond'
    widget.set_text(original)
    widget.show()
    widget.activateWindow()
    widget.view.setFocus()
    qtbot.keyClick(widget.view, Qt.Key_A, Qt.ControlModifier)
    assert widget.view.textCursor().selectedText().replace('\u2029', '\n') == widget.view.toPlainText()
    assert not tree_calls
    if show_lens:
        assert widget.view.toPlainText().startswith('2026-10-27')
    else:
        widget.search.field.setText('first')
        widget.search.field.setFocus()
        qtbot.keyClick(widget.search.field, Qt.Key_A, Qt.ControlModifier)
        assert widget.search.field.selectedText() == 'first'
        assert not tree_calls


def test_literal_case_insensitive_search_preserves_context_and_ansi(log):
    log.set_text("\x1b[31mERROR [9E EE]\x1b[0m\ncontext\ninfo [9e ee]\n")
    before = log.text()
    find(log, "[9e ee]")
    assert log.search.counter.text() == "1/2"
    assert log.view.textCursor().selectedText() == "[9E EE]"
    assert len(log.view.extraSelections()) == 2
    assert log.text() == before
    assert "context" in log.view.toPlainText()
    assert not log.following()


def test_navigation_wraps_and_handles_utf16_offsets(log):
    log.set_text("💳 café\nCAFÉ\nfin")
    find(log, "café")
    assert log.view.textCursor().selectedText() == "café"
    log.search.next.click()
    assert log.search.counter.text() == "2/2"
    assert log.view.textCursor().blockNumber() == 1
    log.search.next.click()
    assert log.search.counter.text() == "1/2"
    log.search.previous.click()
    assert log.search.counter.text() == "2/2"


def test_pending_query_enter_selects_first_then_shift_enter_wraps(log, qtbot):
    log.set_text("first target\nsecond target")
    log.search.field.setText("target")
    qtbot.keyClick(log.search.field, Qt.Key_Return)
    assert log.search.counter.text() == "1/2"
    qtbot.keyClick(log.search.field, Qt.Key_Return, Qt.ShiftModifier)
    assert log.search.counter.text() == "2/2"
    qtbot.keyClick(log.search.field, Qt.Key_Return)
    assert log.search.counter.text() == "1/2"


def test_find_shortcut_stays_in_log_instead_of_global_tree_action(log, qtbot):
    tree_calls = []
    action = QAction(log)
    action.setShortcut(QKeySequence.Find)
    action.triggered.connect(lambda: tree_calls.append(True))
    log.addAction(action)
    log.view.setFocus()
    qtbot.keyClick(log.view, Qt.Key_F, Qt.ControlModifier)
    assert log.search.field.hasFocus()
    assert not tree_calls
    find(log, "absent")
    qtbot.keyClick(log.search.field, Qt.Key_Escape)
    assert not log.search.field.text()
    assert log.view.hasFocus()


def test_f3_works_from_log_content_and_no_results_disable_navigation(log, qtbot):
    log.set_text("target\ntarget")
    find(log, "target")
    qtbot.keyClick(log.view, Qt.Key_F3)
    assert log.search.counter.text() == "2/2"
    qtbot.keyClick(log.view, Qt.Key_F3, Qt.ShiftModifier)
    assert log.search.counter.text() == "1/2"
    find(log, "missing")
    assert log.search.counter.text() == "0/0"
    assert not log.search.next.isEnabled()
    assert not log.search.previous.isEnabled()
    assert not log.view.extraSelections()
    qtbot.keyClick(log.view, Qt.Key_F3)
    assert log.search.counter.text() == "0/0"


def test_search_updates_after_append_replacement_and_clear(log, qtbot):
    log.set_text("target\n")
    find(log, "target")
    log.append("another target\n")
    qtbot.waitUntil(lambda: log.search.counter.text() == "1/2")
    assert not log.following()
    log.search.navigate(1)
    log.set_text("new target\n")
    qtbot.waitUntil(lambda: log.search.counter.text() == "1/1")
    assert log.search.field.text() == "target"
    log.clear()
    assert log.search.counter.text() == "0/0"
    assert not log.view.extraSelections()
    assert log.following()


def test_comparison_and_search_highlights_survive_each_other(log):
    log.set_text("INFO - ok\nERRO - target\ncontext")
    log.highlight_lines((1,), (1,))
    find(log, "target")
    selections = log.view.extraSelections()
    assert len(selections) == 2
    assert selections[0].cursor.blockNumber() == 1
    log.search.field.clear()
    assert len(log.view.extraSelections()) == 1
    assert not log.view.textCursor().hasSelection()
    find(log, "target")
    log.highlight_lines()
    assert len(log.view.extraSelections()) == 1
    log.restyle()
    log.search.refresh()
    assert log.search.counter.text() == "1/1"
    assert len(log.view.extraSelections()) == 1


def test_search_keeps_viewport_when_live_text_is_appended(log, qtbot):
    log.set_text("target\n" + "context\n" * 500)
    find(log, "target")
    scroll = log.view.verticalScrollBar().value()
    log.append("target at the end\n")
    qtbot.waitUntil(lambda: log.search.counter.text() == "1/2")
    assert log.view.verticalScrollBar().value() == scroll
    assert not log.following()


def test_continuous_output_does_not_postpone_search_refresh_forever(log, qtbot):
    log.set_text("target\n")
    find(log, "target")
    stream = QTimer(log)
    stream.setInterval(5)
    stream.timeout.connect(lambda: log.append("target\n"))
    stream.start()
    try:
        qtbot.waitUntil(lambda: log.search.counter.text() != "1/1", timeout=2000)
        assert stream.isActive()
        assert len(log.search._matches) > 1
    finally:
        stream.stop()


def test_replacing_a_long_log_discards_old_search_overlays_before_reindex(log, qtbot):
    log.set_text("context\n" * 100 + "target\n")
    find(log, "target")
    log.set_text("short\n")
    # Comparison can repaint immediately, before the deferred search update.
    log.highlight_lines((0,))
    assert len(log.view.extraSelections()) == 1
    assert log.view.extraSelections()[0].cursor.blockNumber() == 0
    qtbot.waitUntil(lambda: log.search.counter.text() == "0/0")


def test_only_displayed_lines_are_searched_and_painted_overlays_are_bounded(log):
    log.set_text("discarded\n" + "match match\n" * (MAX_LIGNES * 2))
    find(log, "discarded")
    assert log.search.counter.text() == "0/0"
    find(log, "match")
    count = len(log.search._matches)
    assert count > log.search.MAX_HIGHLIGHTS
    assert len(log.view.extraSelections()) <= log.search.MAX_HIGHLIGHTS
    log.search.navigate(-1)
    assert log.search.counter.text() == f"{count}/{count}"
    assert log.view.textCursor().selectedText() == "match"
    assert len(log.view.extraSelections()) <= log.search.MAX_HIGHLIGHTS


def test_each_reader_has_its_own_search_and_output_is_unchanged(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_readers((Reader("Blue Reader", 0), Reader("Green Reader", 1)))
    panel.show_tab(ONGLET_LOGS)
    panel.logs.set_text(0, "alpha\nbeta alpha")
    panel.logs.set_text(1, "beta\nalpha beta")
    find(panel.logs.views[0], "alpha")
    find(panel.logs.views[1], "beta")
    panel.logs.compare.setChecked(True)
    for console in panel.logs.views:
        assert console.search.counter.text() == "1/2"
        assert console.view.extraSelections()
    panel.logs.compare.setChecked(False)
    panel.logs.tabs.setCurrentIndex(1)
    assert panel.logs.views[1].search.field.text() == "beta"
    assert panel.logs.views[0].search.field.text() == "alpha"
    assert panel.output.views[0].search is None
