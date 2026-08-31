"""Reglages communs aux tests de l'interface PySide6.

La migration garde temporairement quelques imports historiques PyQt5 dans les
modules UI. Le bootstrap les redirige vers PySide6 avant la collection des
tests, ce qui permet de tester le runtime Qt6 sans installer PyQt5.
"""

from __future__ import annotations

import pytest

from qt_compat import install_pyqt5_compat

# Doit arriver avant l'import des modules runner.ui par les fichiers de test.
install_pyqt5_compat()


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
