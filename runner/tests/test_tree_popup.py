"""Le tree principal ne doit jamais ouvrir de mini-fenetre au survol."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("event_type", [
    QEvent.Type.ToolTip,
    QEvent.Type.WhatsThis,
])
def test_tree_consumes_popup_events(qapp, event_type):
    from runner.ui.main_window import ResultsTreeView

    tree = ResultsTreeView()
    event = QEvent(event_type)

    try:
        assert tree.viewportEvent(event) is True
        assert event.isAccepted()
    finally:
        tree.deleteLater()
        qapp.processEvents()
