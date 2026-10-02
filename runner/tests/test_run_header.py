"""The experimental header must keep controls usable at smaller widths."""
import pytest
from PySide6.QtCore import Qt
from runner.domain.models import Status
from runner.ui.main_window import MainWindow


@pytest.mark.parametrize("width", [1100, 1600])
def test_header_reflows_without_overlapping_controls(qtbot, width):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(width, 900)
    window.show()
    window.reader_controls.show()
    window.view_failures_button.show()
    window.profile_chip_label.setText("Qualification")
    window.profile_chip.show()
    qtbot.wait(30)

    panels = [window.run_header.environment, window.run_header.execution,
              window.run_header.results]
    for i, panel in enumerate(panels):
        assert window.run_header.rect().contains(panel.geometry())
        for other in panels[i + 1:]:
            assert not panel.geometry().intersects(other.geometry())
    for control in (window.run_button, window.stop_button, window.rerun_button,
                    window.reader_controls, window.workspace_combo,
                    window.view_failures_button, *window.pills.values()):
        assert control.isVisible()
        assert control.parentWidget().rect().contains(control.geometry())

    # A status click must still reach the original filter implementation.
    window.pills[Status.FAILED].set_value(8)
    with qtbot.waitSignal(window.pills[Status.FAILED].filter_clicked) as signal:
        qtbot.mouseClick(window.pills[Status.FAILED], Qt.LeftButton)
    assert signal.args == [Status.FAILED]

    window._set_interpreter_alert("Interpreter unavailable")
    qtbot.wait(10)
    assert window.interpreter_alert.isVisible()
    assert window.interpreter_alert.geometry().top() >= window.run_header.geometry().bottom()
    window.close()


def test_integrated_readers_overflow_keeps_selection_and_reload(qtbot):
    from runner.domain.models import Reader
    from runner.ui.widgets import ReaderBar
    bar = ReaderBar()
    qtbot.addWidget(bar)
    bar.set_integrated()
    readers = [Reader(index=i, name=f"Reader{i + 1}") for i in range(8)]
    bar.set_readers(readers, sequential=True)
    bar.show()
    assert sum(not toggle.isHidden() for toggle in bar._toggles) == 3
    assert len(bar._overflow_menu.actions()) == 5
    with qtbot.waitSignal(bar.changed):
        bar._overflow_menu.actions()[0].setChecked(False)
    assert bar.selected_indexes() == (0, 1, 2, 4, 5, 6, 7)
    bar.select_names(readers, ["Reader8"])
    assert bar.selected_indexes() == (7,)
    assert [action.isChecked() for action in bar._overflow_menu.actions()] == [False] * 4 + [True]
    bar.setEnabled(False)
    assert not bar._more.isEnabled()
    bar.setEnabled(True)
    bar.set_readers(readers[:2])
    assert bar._more.isHidden()
    assert not bar._overflow_menu.actions()
    assert bar.selected_indexes() == (0, 1)


def test_atr_stays_inline_and_copies_full_value_at_any_width(qtbot):
    from PySide6.QtWidgets import QApplication
    from runner.domain.reader_discovery import ATR_OK
    from runner.ui.reader_selector import ReaderAtrField
    from runner.ui.run_header import ResponsiveAtr
    field = ReaderAtrField()
    widget = ResponsiveAtr(field)
    qtbot.addWidget(widget)
    atr = "3B 8F 80 01 80 4F 0C A0 00 00 03 06 03 00 01 00 00 00 00 6A"
    field._show(ATR_OK, atr, atr)
    widget.resize(130, 34)
    widget.show()
    qtbot.wait(20)
    assert widget.stack.currentIndex() == 0
    assert field.isVisible()
    assert not widget.button.isVisible()
    assert field.font().pixelSize() <= 10
    field.selectAll()
    field.copy()
    assert QApplication.clipboard().text() == atr
    widget.resize(900, 34)
    qtbot.wait(20)
    assert widget.stack.currentIndex() == 0
    assert field.text() == atr
    assert field.font().pixelSize() == 10
