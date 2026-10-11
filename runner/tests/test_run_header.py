"""The experimental header must keep controls usable at smaller widths."""
import pytest
from PySide6.QtCore import Qt
from runner.domain.models import Status
from runner.ui.main_window import MainWindow


@pytest.mark.parametrize("width", [1100, 1600])
def test_header_reflows_without_overlapping_controls(qtbot, width, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "header.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(width, 900)
    window.show()
    window.reader_controls.show()
    from runner.domain.models import Reader
    window.readers_bar.set_readers([Reader(index=i, name=f"Reader {i}") for i in range(2)])
    window.run_header.update_environment()
    window.view_failures_button.show()
    window.view_differences_button.show()
    window.profile_chip_label.setText("Qualification")
    window.profile_chip.show()
    qtbot.wait(30)

    panels = [window.run_header.environment, window.run_header.execution, window.run_header.results]
    assert window.run_header.results.isVisible()
    assert window.compass_ring.isVisible()
    assert window.run_header.execution.isAncestorOf(window.reader_controls)
    assert window.run_header.execution.isAncestorOf(window.reader_selector)
    assert window.run_header.execution.isAncestorOf(window.readers_bar)
    execution = window.run_header.execution
    reader_position = window.reader_controls.mapTo(execution, window.reader_controls.rect().topLeft())
    assert reader_position.x() + window.reader_controls.width() == (
        execution.contentsRect().right() + 1 - execution.layout().contentsMargins().right()
    )
    selector_top = window.reader_selector.mapTo(execution, window.reader_selector.rect().topLeft()).y()
    atr_top = window.run_header.atr_presentation.mapTo(execution, window.run_header.atr_presentation.rect().topLeft()).y()
    readers_top = window.readers_bar.mapTo(execution, window.readers_bar.rect().topLeft()).y()
    assert selector_top < atr_top < readers_top
    assert window.run_button.mapTo(execution, window.run_button.rect().topLeft()).y() == selector_top
    selector_left = window.reader_selector.mapTo(execution, window.reader_selector.rect().topLeft()).x()
    assert window.run_header.atr_presentation.mapTo(execution, window.run_header.atr_presentation.rect().topLeft()).x() == selector_left
    assert window.readers_bar.mapTo(execution, window.readers_bar.rect().topLeft()).x() == selector_left
    assert window.run_button.mapTo(execution, window.run_button.rect().topRight()).x() < reader_position.x()
    assert abs(window.reader_selector.geometry().right() - window.reader_controls.contentsRect().right()) <= 1
    results = window.run_header.results
    ring_position = window.compass_ring.mapTo(results, window.compass_ring.rect().topLeft())
    margins = results.layout().contentsMargins()
    assert ring_position.y() == results.contentsRect().top() + margins.top()
    assert ring_position.x() + window.compass_ring.width() == (
        results.contentsRect().right() + 1 - margins.right()
    )
    for button in (window.view_failures_button, window.view_differences_button):
        assert button.mapTo(results, button.rect().topRight()).x() < ring_position.x()
    for i, panel in enumerate(panels):
        assert window.run_header.rect().contains(panel.geometry())
        for other in panels[i + 1:]:
            assert not panel.geometry().intersects(other.geometry())
    for control in (window.run_button, window.stop_button, window.rerun_button,
                    window.reader_controls, window.workspace_combo,
                    window.view_failures_button, window.view_differences_button,
                    window.readers_bar, *window.pills.values()):
        assert control.isVisible()
        assert control.parentWidget().rect().contains(control.geometry())

    # A status click must still reach the original filter implementation.
    window.pills[Status.FAILED].set_value(8)
    qtbot.mouseClick(window.pills[Status.FAILED], Qt.LeftButton)
    assert window._status_filter == Status.FAILED

    window._set_interpreter_alert("Interpreter unavailable")
    qtbot.wait(10)
    assert window.interpreter_alert.isVisible()
    assert window.interpreter_alert.geometry().top() >= window.run_header.geometry().bottom()
    window.close()


def test_execution_actions_stay_compact_without_readers(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "no-readers.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1920, 900)
    window.show()
    window.reader_controls.hide()
    window.readers_bar.hide()
    window.run_header.update_environment()
    qtbot.wait(30)
    execution = window.run_header.execution
    assert window.run_button.width() < 300
    assert window.stop_button.width() < 120
    assert window.run_button.width() < execution.width() / 2
    assert window.run_button.mapTo(execution, window.run_button.rect().topLeft()).x() == (
        execution.contentsRect().left() + execution.layout().contentsMargins().left()
    )
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
    qtbot.wait(10)
    visible = [toggle for toggle in bar._toggles if toggle.isVisible()]
    assert all(toggle.height() == 32 for toggle in visible)
    assert all(not first.geometry().intersects(second.geometry())
               for first, second in zip(visible, visible[1:]))
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
