from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeView

from runner.ui.runtime_polish import _polish_item_view


def test_item_view_keeps_normal_background_repainting(qapp):
    tree = QTreeView()
    tree.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    _polish_item_view(tree)

    assert not tree.viewport().testAttribute(
        Qt.WidgetAttribute.WA_OpaquePaintEvent)


def test_long_test_id_does_not_force_splitter_width(qtbot, monkeypatch):
    from runner.ui.main_window import MainWindow
    from runner.ui import runtime_polish
    # Restore the runtime wrappers after this test.
    from runner.ui.widgets import ErrorDialog
    monkeypatch.setattr(MainWindow, '_build_ui', MainWindow._build_ui)
    monkeypatch.setattr(ErrorDialog, 'show_error', ErrorDialog.__dict__['show_error'])
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    runtime_polish.install()
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 850)
    window.show()
    qtbot.wait(20)
    assert window.split.opaqueResize()
    before = window.minimumSizeHint().width()
    window.results.detail.nodeid_label.setText('test_suite.py::test_case[' + 'x' * 1000 + ']')
    window.results.detail.path_label.setText('nested/' * 100)
    window.results.source.path_label.setText('nested/' * 100)
    qtbot.wait(20)
    assert window.minimumSizeHint().width() <= before + 10
    window.split.setSizes([300, 700])
    qtbot.wait(20)
    first = window.split.sizes()[0]
    window.split.setSizes([500, 500])
    qtbot.wait(20)
    assert window.split.sizes()[0] > first + 50
