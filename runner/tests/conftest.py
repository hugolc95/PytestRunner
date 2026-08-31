"""Reglages communs aux tests de l'interface PySide6."""

from __future__ import annotations

import pytest


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
