"""The experimental header must keep controls usable at smaller widths."""
import pytest
from PySide6.QtCore import Qt
from runner.domain.models import Status
from runner.ui.main_window import MainWindow


@pytest.mark.parametrize("width", [960, 1100, 1280, 1600])
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
    diagram = window.run_header.result_diagram
    assert diagram.rect().contains(window.compass_ring.geometry())
    assert window.compass_pct.geometry() == window.compass_ring.geometry()
    assert window.view_failures_button.text() == 'View failures'
    assert window.view_differences_button.text() == 'View differences'
    assert results.minimumSizeHint().height() <= 148
    assert not window.view_failures_button.geometry().intersects(window.view_differences_button.geometry())
    for action in (window.view_failures_button, window.view_differences_button):
        assert action.width() >= action.fontMetrics().horizontalAdvance(action.text()) + 6
    positions = [pill.mapTo(results, pill.rect().topLeft()).y() for pill in window.pills.values()]
    assert len(set(positions)) == 2
    for pill in window.pills.values():
        position = pill.mapTo(results, pill.rect().bottomRight())
        assert results.rect().contains(position)
    for button in (window.view_failures_button, window.view_differences_button):
        assert button.mapTo(results, button.rect().bottomLeft()).y() < window.pills[Status.PASSED].y()
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


def test_half_screen_keeps_navigation_preference_and_all_result_tabs(qtbot):
    from runner.ui.main_window import K_SIDEBAR_COLLAPSED
    window = MainWindow()
    qtbot.addWidget(window)
    window.settings.setValue(K_SIDEBAR_COLLAPSED, False)
    window.resize(960, 900)
    window.show()
    qtbot.waitUntil(lambda: window.navigation.width() == 56)
    assert window.width() == 960
    assert not window.settings.value(K_SIDEBAR_COLLAPSED, type=bool)
    bar = window.results.tabs.tabBar()
    for index in range(4):
        assert bar.rect().contains(bar.tabRect(index))
        window.results.show_tab(index)
        assert window.results.tabs.currentIndex() == index
    window.resize(1600, 900)
    qtbot.waitUntil(lambda: window.navigation.width() == 220)
    window._set_sidebar_collapsed(True)
    window.resize(960, 900)
    window.resize(1600, 900)
    assert window.navigation.width() == 56


def test_profile_options_remain_reachable_on_a_short_window(qtbot):
    from PySide6.QtWidgets import QScrollArea
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(960, 600)
    window.show()
    window._show_page('profiles')
    options = window.profiles_page.save_logs
    scroll = options.parentWidget()
    while scroll is not None and not isinstance(scroll, QScrollArea):
        scroll = scroll.parentWidget()
    assert scroll is not None
    scroll.ensureWidgetVisible(options)
    qtbot.waitUntil(lambda: scroll.viewport().rect().contains(
        options.mapTo(scroll.viewport(), options.rect().center())))


def _window_with_readers(qtbot, monkeypatch, tmp_path, size):
    from PySide6.QtCore import QSettings
    from runner.domain.models import Reader
    settings = QSettings(str(tmp_path / "header.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(*size)
    window.show()
    window.reader_controls.show()
    window.readers_bar.set_readers([Reader(index=i, name=f"Reader {i}") for i in range(3)])
    window.run_header.update_environment()
    window.view_failures_button.show()
    qtbot.waitExposed(window)
    qtbot.waitUntil(lambda: not window.run_header._whole_timer.isActive())
    return window


def test_stacked_header_is_never_squeezed_below_its_controls(qtbot, monkeypatch, tmp_path):
    """A 800 x 560, les cartes empilees etaient ecrasees : le bouton Run n'etait
    plus qu'une barre verte sans texte et Collect chevauchait le chemin. La
    fenetre garde maintenant la hauteur que l'en-tete exige."""
    window = _window_with_readers(qtbot, monkeypatch, tmp_path, (800, 560))
    header = window.run_header
    qtbot.waitUntil(lambda: header._compact == "stacked")
    qtbot.waitUntil(lambda: header.height() >= header.minimumSizeHint().height())
    for panel in (header.environment, header.execution, header.results):
        assert panel.height() >= panel.minimumSizeHint().height()
    assert window.run_button.height() >= window.run_button.minimumSizeHint().height()
    assert window.minimumHeight() > 560

    # Sur toute la largeur, le chemin et ses actions partagent une ligne.
    combo_top = window.workspace_combo.mapTo(header, window.workspace_combo.rect().topLeft()).y()
    browse_top = window.browse_button.mapTo(header, window.browse_button.rect().topLeft()).y()
    assert abs(combo_top - browse_top) <= window.workspace_combo.height()
    heading = header.result_heading
    assert heading.width() >= heading.fontMetrics().horizontalAdvance("RESULTS")


def test_window_gets_its_minimum_back_once_the_header_fits(qtbot, monkeypatch, tmp_path):
    window = _window_with_readers(qtbot, monkeypatch, tmp_path, (800, 560))
    qtbot.waitUntil(lambda: window.minimumHeight() > 560)
    window.resize(1100, window.height())
    qtbot.waitUntil(lambda: window.run_header._compact != "stacked")
    qtbot.waitUntil(lambda: window.minimumHeight() == 560)


def test_readers_arriving_after_collection_do_not_squeeze_the_header(qtbot, monkeypatch, tmp_path):
    """Les lecteurs n'arrivent qu'apres la collecte : la carte Execution grandit
    sans que l'en-tete change de taille. C'est le parcours reel de
    l'application, que la verification au redimensionnement ne voyait pas."""
    from PySide6.QtCore import QSettings
    from runner.domain.models import Reader
    settings = QSettings(str(tmp_path / "header.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(800, 560)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(100)
    header = window.run_header

    window.reader_controls.show()
    window.readers_bar.set_readers([Reader(index=i, name=f"Reader {i}") for i in range(3)])
    window.run_header.update_environment()

    qtbot.waitUntil(lambda: header.height() >= header.minimumSizeHint().height())
    assert header.execution.height() >= header.execution.minimumSizeHint().height()


@pytest.mark.parametrize("width", [1920, 1600, 1280, 930, 800])
def test_all_five_counters_stay_visible_and_readable(qtbot, monkeypatch, tmp_path, width):
    """La grille reste identique meme avec plusieurs millions de tests."""
    window = _window_with_readers(qtbot, monkeypatch, tmp_path, (width, 900))
    pills = list(window.pills.values())
    assert len(pills) == 5
    qtbot.waitUntil(lambda: all(pill.isVisible() for pill in pills))
    tops = {pill.mapTo(window, pill.rect().topLeft()).y() for pill in pills}
    assert len(tops) == 2
    assert pills[0].y() == pills[1].y()
    assert pills[2].y() == pills[3].y() == pills[4].y()
    assert pills[0].y() < pills[2].y()
    assert max(pill.width() for pill in pills) - min(pill.width() for pill in pills) <= 1
    assert len({pill.height() for pill in pills}) == 1
    assert window.run_header.result_diagram.geometry().bottom() < pills[4].y()
    for pill in pills:
        assert "\n" not in pill.text()
    results = window.run_header.results
    for pill in pills:
        assert results.rect().contains(pill.mapTo(results, pill.rect().bottomRight()))
    cells = [*pills, window.run_header.result_diagram]
    before = [cell.geometry() for cell in cells]
    window.view_differences_button.show()
    qtbot.wait(20)
    assert [cell.geometry() for cell in cells] == before
    for value in (1, 999, 12000, 1000000, 9999999, 0):
        for pill in pills:
            pill.set_value(value)
        window.compass_pct.setText(f'{value} / 12000')
        qtbot.wait(20)
        assert [cell.geometry() for cell in cells] == before
        for pill in pills:
            number_font, label_font, number, label, number_width, label_width = pill._inline_text()
            assert number == str(value)
            assert label == pill.status.label
            assert number_font.bold() and not label_font.bold()
            assert number_width + label_width + 27 <= pill.width() - 10
        for index, cell in enumerate(cells):
            assert all(not cell.geometry().intersects(other.geometry())
                       for other in cells[index + 1:])
