"""Le compare des logs ignore le bruit et montre les ecarts de comportement."""

from PySide6.QtCore import Qt

from runner.domain.log_compare import compare_logs, is_error_line, normalize_line
from runner.domain.models import Reader
from runner.ui.results_panel import ReaderViews


def test_timestamps_durations_and_reader_names_are_not_differences():
    left = """2026-08-18 14:02:10.123 INFO - Cosmo11Secured Reader
INFO - Duration : 2.53 ms
INFO - Expected Status : 9EEE
"""
    right = """2026-08-18 14:09:44.981 INFO - Cosmo11SecuredCVertif Reader
INFO - Duration : 0.26 ms
INFO - Expected Status : 9EEE
"""

    result = compare_logs(
        (left, right),
        ("Cosmo11Secured Reader", "Cosmo11SecuredCVertif Reader"),
    )

    assert not result.any


def test_an_inserted_logger_error_is_the_difference_that_stands_out():
    left = """INFO - APDU Status : 9E EE
INFO - Expected Status : 9EEE
INFO - ## Step 2.7 : Garbage Collector deleteInstance()
"""
    right = """INFO - APDU Status : 6F EE
INFO - Expected Status : 9EEE
ERRO - Wrong Status Word, received: 6FEE ; authorized : {'9EEE'}
INFO - Start of Teardown
"""

    result = compare_logs((left, right))

    assert 2 in result.changed[1]
    assert 1 not in result.changed[0]
    assert 1 not in result.changed[1]
    assert result.errors[1] == frozenset({2})
    assert is_error_line(right.splitlines()[2])


def test_apdu_values_are_never_normalized_away():
    assert normalize_line("INFO - APDU Status : 9E EE") != normalize_line(
        "INFO - APDU Status : 6F EE")


def test_difference_navigation_only_appears_while_comparing(qapp):
    views = ReaderViews(Qt.Horizontal, highlight_differences=True)
    views.set_readers((Reader("Blue Reader", 0), Reader("Green Reader", 1)))
    views.set_text(0, "same\nleft A\nsame 2\nleft B\nsame 3")
    views.set_text(1, "same\nright A\nsame 2\nright B\nsame 3")

    assert views.difference_navigation.isHidden()

    views.compare.setChecked(True)

    assert not views.difference_navigation.isHidden()
    assert views.difference_counter.text() == "1 / 2"
    assert views.views[0].view.textCursor().blockNumber() == 1

    views.next_difference.click()
    assert views.difference_counter.text() == "2 / 2"
    assert views.views[0].view.textCursor().blockNumber() == 3

    # La navigation boucle : apres le dernier ecart, on revient au premier.
    views.next_difference.click()
    assert views.difference_counter.text() == "1 / 2"

    views.compare.setChecked(False)
    assert views.difference_navigation.isHidden()


def test_comparison_opens_on_the_difference_containing_an_error(qapp):
    views = ReaderViews(Qt.Horizontal, highlight_differences=True)
    views.set_readers((Reader("Blue Reader", 0), Reader("Green Reader", 1)))
    views.set_text(0, "same\nleft A\nsame 2\nINFO - accepted\nsame 3")
    views.set_text(1, "same\nright A\nsame 2\nERRO - rejected\nsame 3")

    views.compare.setChecked(True)

    assert views.difference_counter.text() == "2 / 2"
    assert views.views[1].view.textCursor().blockNumber() == 3


def test_comparison_keeps_the_tree_width_and_offers_local_horizontal_scrolling(qtbot):
    from runner.ui.main_window import MainWindow
    from runner.ui.results_panel import ONGLET_LOGS
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(960, 900)
    window.results.set_readers(tuple(Reader(f'Reader {i}', i) for i in range(3)))
    window.results.show_tab(ONGLET_LOGS)
    window.show()
    window.split.setSizes([450, 450])
    qtbot.waitUntil(lambda: window.results.logs.width() > 300)
    previous = window.split.sizes()[0]
    views = window.results.logs
    views.compare.setChecked(True)
    qtbot.waitUntil(lambda: views.split.orientation() == Qt.Vertical)
    assert window.split.sizes()[0] >= previous - 4
    assert 'Comparing 3 readers' == views.compare.text()
    views.set_compare_layout(Qt.Horizontal)
    qtbot.waitUntil(lambda: views._comparison_scroll.horizontalScrollBar().maximum() > 0)
    assert window.split.sizes()[0] >= previous - 4
    views.compare.setChecked(False)
    qtbot.waitUntil(lambda: views._comparison_scroll.horizontalScrollBar().maximum() == 0)
    assert not views.tabs.isHidden()


def test_wrapping_applies_to_all_readers_and_newly_added_columns(qtbot):
    from PySide6.QtWidgets import QPlainTextEdit
    views = ReaderViews(Qt.Horizontal, show_lens=False, highlight_differences=True)
    qtbot.addWidget(views)
    views.set_readers((Reader('A', 0), Reader('B', 1)))
    views.views[1].wrap_button.setChecked(True)
    assert views.wrap_all.isChecked()
    assert all(v.view.lineWrapMode() == QPlainTextEdit.WidgetWidth for v in views.views)
    views.set_readers((Reader('A', 0), Reader('B', 1), Reader('C', 2)))
    assert views.views[2].wrap_button.isChecked()
    views.wrap_all.setChecked(False)
    assert all(v.view.lineWrapMode() == QPlainTextEdit.NoWrap for v in views.views)


def test_comparison_state_remains_explicit_when_contents_change(qtbot):
    views = ReaderViews(Qt.Horizontal, show_lens=False, highlight_differences=True)
    qtbot.addWidget(views)
    views.set_readers((Reader('A', 0), Reader('B', 1)))
    views.compare.setChecked(True)
    views.set_text(0, 'INFO - first test')
    views.set_text(1, 'ERROR - first test')
    views.clear()
    views.set_text(0, 'INFO - second test')
    views.set_text(1, 'INFO - second test')
    assert views.compare.isChecked() and views.compare.text() == 'Comparing 2 readers'
    assert not views.layout_button.isHidden()
