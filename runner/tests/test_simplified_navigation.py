"""The main shell stays intentionally small while runner features remain wired."""

from PySide6.QtCore import QSettings
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from runner.domain import interpreter as interpreter_mod
from runner.domain.interpreter import InterpreterInfo
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow


def test_main_navigation_separates_python_and_yaml_configuration(qapp):
    QSettings(ORG, APP).clear()
    window = MainWindow()
    try:
        assert list(window.nav_buttons) == [
            "workspace", "yaml", "history", "python"]
        assert [button.text() for button in window.nav_buttons.values()] == [
            "Workspace", "Configuration YAML", "Historique",
            "Environnement Python"]
        assert window.page_theme_button.text() == ""
        assert window.page_theme_button.width() <= 32
        assert window.sidebar_toggle_button.width() <= 32
        assert window.pages.currentWidget() is window.workspace_page
        assert window.menuBar().isHidden()
    finally:
        window.close()


def test_sidebar_can_collapse_to_icons_and_expand_again(qapp):
    window = MainWindow()
    try:
        window._set_sidebar_collapsed(True, animate=False)
        assert window.navigation.width() == 56
        assert window.navigation.maximumWidth() == 56
        assert window.navigation_title.isHidden()
        assert not window.navigation_logo.isHidden()
        assert not window.navigation_logo.pixmap().isNull()
        assert all(button.text() == "" for button in window.nav_buttons.values())
        assert all(button.property("compact") for button in window.nav_buttons.values())
        assert all(button.toolTip() for button in window.nav_buttons.values())

        window._set_sidebar_collapsed(False, animate=False)
        assert window.navigation.width() == 220
        assert window.nav_buttons["workspace"].text() == "Workspace"
        assert not window.nav_buttons["workspace"].property("compact")
        assert not window.navigation_title.isHidden()
        assert window.navigation_logo.isHidden()
    finally:
        window.close()


def test_python_and_yaml_have_distinct_pages(qapp):
    window = MainWindow()
    try:
        window._show_page("python")
        assert window.pages.currentWidget() is window.python_page
        assert window.python_editor.isVisibleTo(window.python_page)
        assert not window.workspace_config_button.isVisibleTo(window.python_page)

        window._show_page("yaml")
        assert window.pages.currentWidget() is window.yaml_page
        assert window.yaml_empty.isVisibleTo(window.yaml_page)
        assert not window.interpreter_config_button.isVisibleTo(window.yaml_page)
    finally:
        window.close()


def test_yaml_editor_is_embedded_when_workspace_has_a_configuration(
        qapp, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("Reader: OMNIKEY\nLOG_PATH: logs\n", encoding="utf-8")
    window = MainWindow()
    try:
        window.workspace = Workspace.load(str(tmp_path))
        window._show_page("yaml")

        assert window.yaml_stack.currentWidget() is window.yaml_editor_host
        assert window.yaml_editor.parentWidget() is window.yaml_editor_host
        assert not window.yaml_editor.isWindow()
        assert window.yaml_editor.tabs.count() == 2
    finally:
        window.close()


def test_history_navigation_shows_the_dashboard_inside_the_main_window(qapp):
    window = MainWindow()
    try:
        window.open_history()

        assert window.pages.currentWidget() is window.history_page
        assert window.history_dashboard.parentWidget() is window.history_page
        assert window.history_dashboard.windowFlags() & Qt.WindowType_Mask == Qt.Widget
        assert not window.history_dashboard.isWindow()
    finally:
        window.close()


def test_an_unavailable_interpreter_is_reported_inline_on_workspace(
        qapp, tmp_path, monkeypatch):
    window = MainWindow()
    try:
        window.workspace = Workspace(str(tmp_path), "", {})
        window._interpreter_override = str(tmp_path / "missing-python.exe")
        missing = InterpreterInfo(
            path=window._interpreter_override, error="Interpreter not found")
        monkeypatch.setattr(interpreter_mod, "cached_probe", lambda path: missing)

        window._refresh_interpreter_alert()

        assert window.interpreter_alert.isVisibleTo(window.workspace_page)
        assert "indisponible" in window.interpreter_alert_label.text()
        visible_copy = " ".join(
            label.text() for label in window.workspace_page.findChildren(QLabel)
            if label is not window.interpreter_alert_label)
        assert window._effective_interpreter() not in visible_copy
    finally:
        window.close()
