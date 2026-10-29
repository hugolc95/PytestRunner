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


def test_profile_parameters_open_in_a_separate_dialog_after_runtime_install(qtbot, monkeypatch):
    from runner.domain.execution_profile import ExecutionProfile
    from runner.ui.main_window import MainWindow
    from runner.ui.widgets import ErrorDialog
    from runner.ui.profile_dialogs import StepParametersDialog
    from runner.ui import runtime_polish
    from PySide6.QtCore import QTimer
    monkeypatch.setattr(MainWindow, '_build_ui', MainWindow._build_ui)
    monkeypatch.setattr(ErrorDialog, 'show_error', ErrorDialog.__dict__['show_error'])
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    runtime_polish.install()
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1600, 1000)
    window.show()
    page = window.profiles_page
    profile = ExecutionProfile('Grouped profile', ['test_card.py::test_a', 'test_card.py::test_b'],
                               'config.yaml', 'timeout: 15\nprotocol: T0\n')
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    window._show_page('profiles')
    page._expand_groups()
    step = page._step_items()[0]
    page.sequence_list.setCurrentItem(step)
    checked = []
    def inspect_dialog():
        from PySide6.QtWidgets import QApplication
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, StepParametersDialog)
        mode, editor = dialog.controls[('timeout',)]
        checked.append(mode.isVisible() and editor.isVisible() and dialog.height() > 300)
        dialog.reject()
    QTimer.singleShot(0, inspect_dialog)
    page.parameters_button.click()
    assert checked == [True]
    assert step.childCount() == 0
    assert page._step_patches() == [{}, {}]
