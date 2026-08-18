"""Tests for the icon shared by the two application entry points."""

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QDialog

from app_icon import APP_ICON_RELATIVE_PATH, install_application_icon, resource_path


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_source_icon_exists() -> None:
    assert resource_path(APP_ICON_RELATIVE_PATH).is_file()


def test_resource_path_uses_pyinstaller_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_path(APP_ICON_RELATIVE_PATH) == tmp_path / APP_ICON_RELATIVE_PATH


def test_icon_is_inherited_by_application_windows() -> None:
    app = _application()

    icon = install_application_icon(app)
    dialog = QDialog()

    assert not icon.isNull()
    assert not app.windowIcon().isNull()
    assert dialog.windowIcon().cacheKey() == app.windowIcon().cacheKey()
