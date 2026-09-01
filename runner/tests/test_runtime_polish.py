from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeView

from runner.ui.runtime_polish import _polish_item_view


def test_item_view_keeps_normal_background_repainting(qapp):
    tree = QTreeView()
    tree.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    _polish_item_view(tree)

    assert not tree.viewport().testAttribute(
        Qt.WidgetAttribute.WA_OpaquePaintEvent)
