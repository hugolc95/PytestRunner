"""Reglages communs aux tests de l'interface PySide6."""

from __future__ import annotations

import pytest


@pytest.fixture
def isolated_run_state(tmp_path, monkeypatch):
    """Keep profile integration tests away from real sessions and run copies."""
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr("runner.domain.history.dossier", lambda: tmp_path / "history")


@pytest.fixture(autouse=True)
def sans_widget_orphelin():
    """Detruit les widgets sans parent qu'un test laisse derriere lui."""
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    avant = set(application.topLevelWidgets()) if application is not None else set()

    yield

    application = QApplication.instance()
    if application is None:
        return

    for widget in application.topLevelWidgets():
        if widget in avant:
            continue
        widget.close()
        widget.deleteLater()

    application.processEvents()
