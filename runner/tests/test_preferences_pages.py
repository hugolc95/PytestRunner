import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QBoxLayout

from runner.domain import history
from runner.ui import tokens as t
from runner.ui.main_window import APP, ORG, MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(history, "dossier", lambda: tmp_path)
    settings = QSettings(ORG, APP)
    settings.clear()
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
    assert page.placeholder.isVisible()
    native.close()
    assert page.detached_window is None
    assert page.content is content
    assert page.body.parentWidget() is page
    assert page.body.isVisible()


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
