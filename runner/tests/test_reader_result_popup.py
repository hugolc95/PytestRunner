"""Le verdict ne doit jamais devenir une fenetre flottante transitoire."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QLabel

from runner.domain.models import Status


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _TopLevelLabelSpy(QObject):
    def __init__(self):
        super().__init__()
        self.shown = []

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Show
                and isinstance(obj, QLabel) and obj.isWindow()):
            self.shown.append(obj)
        return False


def test_an_executed_status_never_flashes_as_a_top_level_window(qapp):
    """Regression du rectangle de 14 px vu a chaque clic apres un run."""
    from runner.ui.widgets import ReaderResult

    spy = _TopLevelLabelSpy()
    result = None
    qapp.installEventFilter(spy)
    try:
        result = ReaderResult("", 0, Status.PASSED)
        assert spy.shown == []
    finally:
        qapp.removeEventFilter(spy)
        if result is not None:
            result.deleteLater()
        qapp.processEvents()
