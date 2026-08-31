"""The main shell stays intentionally small while runner features remain wired."""

from PySide6.QtCore import QSettings
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from runner.domain import interpreter as interpreter_mod
from runner.domain.interpreter import InterpreterInfo
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow


def test_main_navigation_contains_only_the_three_primary_destinations(qapp):
    QSettings(ORG, APP).clear()
    window = MainWindow()
    try:
        assert list(window.nav_buttons) == [
            "workspace", "history", "configuration"]
        assert [button.text() for button in window.nav_buttons.values()] == [
            "Workspace", "Historique", "Configuration"]
        assert window.pages.currentWidget() is window.workspace_page
        assert window.menuBar().isHidden()
    finally:
        window.close()


def test_configuration_is_a_real_page_with_both_interpreter_and_workspace(qapp):
    window = MainWindow()
    try:
        window._show_page("configuration")
        assert window.pages.currentWidget() is window.configuration_page
        assert window.interpreter_config_button.isVisibleTo(window.configuration_page)
        assert "environnement Python" in window.interpreter_config_button.text()
        assert "fichiers YAML" in window.workspace_config_button.text()
        headings = {label.text() for label in window.configuration_page.findChildren(QLabel)}
        assert "Environnement Python" in headings
        assert "Configuration des tests YAML" in headings
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
