import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QBoxLayout

from runner.domain import history
from runner.ui import tokens as t
from runner.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(history, "dossier", lambda: tmp_path)
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1440, 900)
    w.show()
    yield w
    w.close()
    settings.clear()
    t.set_theme("dark")


@pytest.mark.parametrize("name", ["settings", "console"])
def test_page_detaches_and_reattaches_same_content(window, name):
    window._show_page(name)
    page = getattr(window, name + "_page")
    content = page.content
    assert window.pages.currentWidget() is page
    page.toggle_detach()
    native = page.detached_window
    assert native.isWindow() and native.isVisible()
    assert native.centralWidget() is page.body
    assert window.pages.currentWidget() is window.workspace_page
    native.close()
    assert page.detached_window is native
    assert not native.isVisible()
    window._show_page(name)
    assert native.isVisible()
    assert window.pages.currentWidget() is window.workspace_page
    page.detach_button.click()
    assert page.detached_window is None
    assert page.content is content
    assert page.body.parentWidget() is page
    assert page.body.isVisible()


@pytest.mark.parametrize("name", ["settings", "console"])
def test_detached_page_restores_mode_and_geometry_after_restart(window, name, qtbot):
    page = getattr(window, name + "_page")
    window._show_page(name)
    page.toggle_detach()
    page.detached_window.resize(720, 570)
    size = page.detached_window.size()
    window.close()
    assert window.settings.value(page.settings_key + "/detached", type=bool)
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.show()
    try:
        restored = getattr(reopened, name + "_page")
        qtbot.waitUntil(lambda: restored.detached_window is not None)
        assert restored.detached_window.isVisible()
        assert restored.detached_window.size() == size
        restored.reattach()
        assert not reopened.settings.value(page.settings_key + "/detached", type=bool)
    finally:
        reopened.close()


def test_detach_returns_to_last_attached_page_and_skips_floating_pages(window):
    window._show_page("python")
    window._show_page("settings")
    window.settings_page.toggle_detach()
    assert window.pages.currentWidget() is window.python_page
    window._show_page("console")
    window.console_page.toggle_detach()
    assert window.pages.currentWidget() is window.python_page
    window.nav_buttons["settings"].click()
    assert window.pages.currentWidget() is window.python_page
    assert window.settings_page.detached_window.isVisible()
    assert window.nav_buttons["python"].isChecked()
    assert not window.nav_buttons["settings"].isChecked()


def test_console_filters_pause_and_preserves_detached_contents(window):
    controller = window.preferences
    controller.record("commands", "python -m pytest --collect-only")
    controller.record("errors", "ValueError: diagnostic fixture")
    console = controller.console
    console.refresh()
    console.search.setText("ValueError")
    assert "ValueError" in console.text.toPlainText()
    assert "--collect-only" not in console.text.toPlainText()
    console.set_paused(True)
    before = console.text.toPlainText()
    controller.record("errors", "ValueError: second event")
    console.refresh()
    assert console.text.toPlainText() == before
    window.console_page.toggle_detach()
    window.console_page.reattach()
    assert console.search.text() == "ValueError"
    assert console.paused
    console.set_paused(False)
    assert "second event" in console.text.toPlainText()


def test_apply_cancel_and_persistence(window):
    controller = window.preferences
    panel = controller.settings_panel
    panel.controls["atr_bottom"].setChecked(True)
    assert window.run_header.atr_presentation.parentWidget() is window.statusBar()
    panel.cancel()
    assert window.run_header.atr_presentation.parentWidget() is window.reader_controls
    panel.controls["tree_density"].setCurrentText("Comfortable")
    controller.save()
    saved = window.settings.value("preferences/personal")
    assert '"tree_density": "Comfortable"' in saved
    panel.controls["tree_density"].setCurrentText("Compact")
    panel.cancel()
    assert controller.values["tree_density"] == "Comfortable"


def test_actual_subprocess_command_is_recorded(window):
    import subprocess
    subprocess.run([sys.executable, "-c", "print('trace probe')"], capture_output=True, check=True)
    QApplication.processEvents()
    console = window.preferences.console
    console.refresh()
    assert "trace probe" in console.text.toPlainText()


def test_exception_hook_restored_on_shutdown(window):
    controller = window.preferences
    previous = controller.previous_excepthook
    assert sys.excepthook is controller.exception_handler
    controller.shutdown()
    assert sys.excepthook is previous


def test_sidebar_settings_stay_at_bottom_and_utilities_fit_when_collapsed(window):
    layout = window.navigation.layout()
    settings_index = layout.indexOf(window.nav_buttons["settings"])
    assert layout.itemAt(settings_index - 1).spacerItem() is not None
    utilities = window.navigation_utilities
    assert utilities.indexOf(window.page_theme_button) < utilities.indexOf(window.sidebar_toggle_button)
    assert utilities.direction() == QBoxLayout.LeftToRight
    assert window.nav_buttons["settings"].y() > window.nav_buttons["console"].y() + 150
    window._set_sidebar_collapsed(True)
    QApplication.processEvents()
    assert utilities.direction() == QBoxLayout.TopToBottom
    for button in (window.page_theme_button, window.sidebar_toggle_button):
        assert button.geometry().right() < window.navigation.width()


def test_theme_shortcut_preserves_text_size_and_synchronizes_settings(window):
    panel = window.preferences.settings_panel
    panel.controls["font_size"].setValue(16)
    window.settings_page.toggle_detach()
    window.apply_theme("light")
    assert panel.controls["theme"].currentData() == "light"
    assert "font-size: 16px" in window.styleSheet()
    assert window.settings_page.detached_window.styleSheet() == window.styleSheet()
    panel.controls["theme"].setCurrentIndex(panel.controls["theme"].findData("dark"))
    panel.cancel()
    assert t.current_theme() == "light"


def test_console_limit_applies_immediately_and_errors_keep_real_tracebacks(window):
    controller = window.preferences
    for i in range(300):
        controller.record("output", f"trace {i}")
    controller.values["limit"] = 250
    controller.apply()
    assert len(controller.console.events) == 250
    previous = controller.previous_excepthook
    controller.previous_excepthook = lambda *_: None
    try:
        raise ValueError("actual exception probe")
    except ValueError:
        controller.exception_handler(*sys.exc_info())
    finally:
        controller.previous_excepthook = previous
    controller.console.refresh()
    assert "Traceback (most recent call last)" in controller.console.text.toPlainText()
    assert "ValueError: actual exception probe" in controller.console.text.toPlainText()


def test_unrelated_preferences_do_not_restyle_the_interface(window, monkeypatch):
    controller = window.preferences
    calls = []
    monkeypatch.setattr(window, "setStyleSheet", lambda *_: calls.append("window"))
    monkeypatch.setattr(window.tree, "setStyleSheet", lambda *_: calls.append("tree"))
    controller.settings_panel.update_value("timestamps", False)
    controller.settings_panel.update_value("notify_end", False)
    assert calls == []


def test_theme_preview_gives_feedback_and_cancel_stops_pending_change(window, qtbot):
    panel = window.preferences.settings_panel
    original = t.current_theme()
    target = "light" if original == "dark" else "dark"
    panel.controls["theme"].setCurrentIndex(panel.controls["theme"].findData(target))
    assert "Updating" in panel.notice.text()
    panel.cancel()
    qtbot.wait(100)
    assert t.current_theme() == original
    panel.controls["theme"].setCurrentIndex(panel.controls["theme"].findData(target))
    qtbot.waitUntil(lambda: t.current_theme() == target)


def test_theme_applies_global_stylesheet_once(window, monkeypatch):
    calls = []
    original = window.setStyleSheet
    def track(stylesheet):
        calls.append(stylesheet)
        original(stylesheet)
    monkeypatch.setattr(window, "setStyleSheet", track)
    window.apply_theme("light" if t.is_dark() else "dark")
    assert len(calls) == 1


def test_bottom_atr_keeps_status_bar_height_and_ui_font(window, qtbot):
    from runner.domain.reader_discovery import ATR_OK
    window.reader_atr._show(ATR_OK, "3B8F8001804F0CA000000306030001000000006A", "")
    QApplication.processEvents()
    height = window.statusBar().height()
    window.preferences.settings_panel.controls["atr_bottom"].setChecked(True)
    QApplication.processEvents()
    assert window.statusBar().height() == height
    assert window.reader_atr.font().family() == window.status_label.font().family()
    assert window.reader_atr.text().endswith("006A")
    window.preferences.settings_panel.cancel()
    assert not window.reader_atr.bottom_bar


def test_bottom_atr_refresh_is_compact_adjacent_and_keeps_its_action(window, monkeypatch):
    from PySide6.QtCore import QSize
    atr = window.run_header.atr_presentation
    refreshed = []
    monkeypatch.setattr(window.reader_atr, "refresh", lambda: refreshed.append(True))
    window.preferences.settings_panel.controls["atr_bottom"].setChecked(True)
    QApplication.processEvents()
    assert atr.refresh_button.size() == QSize(20, 20)
    assert atr.refresh_button.iconSize() == QSize(14, 14)
    assert atr.layout().indexOf(atr.refresh_button) == 0
    assert atr.stack.x() - atr.refresh_button.geometry().right() <= 8
    atr.refresh_button.click()
    assert refreshed == [True]
    window.preferences.settings_panel.cancel()
    QApplication.processEvents()
    assert atr.refresh_button.size() == QSize(t.CONTROL_SM, t.CONTROL_SM)
    assert atr.layout().indexOf(atr.refresh_button) == 1


def test_status_metadata_stays_at_right_when_atr_moves_and_window_resizes(window):
    from runner.ui.main_ux import _add_status_metadata
    _add_status_metadata(window)
    metadata = window._version_copyright_label
    for width in (1440, 1000):
        window.resize(width, 900)
        for bottom in (True, False, True):
            window.preferences.settings_panel.controls["atr_bottom"].setChecked(bottom)
            QApplication.processEvents()
            status = window.statusBar()
            right = metadata.mapTo(status, metadata.rect().topRight()).x()
            assert 0 <= status.width() - right <= 30
            if bottom:
                atr = window.run_header.atr_presentation
                assert atr.mapTo(status, atr.rect().topRight()).x() < metadata.mapTo(status, metadata.rect().topLeft()).x()


def test_hidden_console_defers_rendering_and_appends_without_document_reset(window):
    from PySide6.QtGui import QTextCursor
    console = window.preferences.console
    console.clear()
    window.preferences.record("output", "first\nsecond")
    console._flush()
    assert console.text.toPlainText() == ""
    window._show_page("console")
    assert "first\nsecond" in console.text.toPlainText()
    cursor = console.text.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.KeepAnchor)
    console.text.setTextCursor(cursor)
    selected = cursor.selectedText()
    window.preferences.record("output", "third")
    console.refresh()
    assert console.text.textCursor().selectedText() == selected
    assert "third" in console.text.toPlainText()


def test_console_rollover_preserves_multiline_events(window):
    console = window.preferences.console
    console.clear()
    window.preferences.values["limit"] = 3
    for message in ("one\ncontinuation", "two", "three"):
        console.append("output", message)
    console.refresh()
    console.append("output", "four\nlast")
    console.refresh()
    assert "continuation" not in console.text.toPlainText()
    assert "two" in console.text.toPlainText()
    assert console.text.toPlainText().endswith("four\nlast")


def test_theme_change_detaches_previous_source_highlighter(window):
    editor = window.results.source.editor
    previous = editor.highlighter
    window.apply_theme("light" if t.is_dark() else "dark")
    assert previous.document() is None
    assert editor.highlighter.document() is editor.document()


def test_sidebar_theme_request_completes_with_feedback(window, qtbot):
    target = "light" if t.is_dark() else "dark"
    window.request_theme(target)
    assert not window.page_theme_button.isEnabled()
    assert "Updating" in window.page_theme_button.toolTip()
    qtbot.waitUntil(lambda: window.page_theme_button.isEnabled())
    assert t.current_theme() == target
