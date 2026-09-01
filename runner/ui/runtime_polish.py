"""Runtime polish for the PySide6 interface.

The runner already keeps collection and execution outside the GUI thread.  This
module focuses on the remaining interaction details that are easy to feel on a
large workspace: modal error windows, expensive live repaints while resizing,
and tree painting work that Qt can avoid when every test row has the same
height.

Installed as a small compatibility layer before ``MainWindow`` is created so
none of the domain/execution code needs to know about visual behaviour.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t


class InlineNotice(QFrame):
    """Non-modal message hosted inside the main window.

    Errors used to be displayed with ``QDialog.exec()``.  Besides interrupting
    keyboard/mouse flow, native Windows dialogs can briefly flash as a second
    top-level window while Qt applies its stylesheet.  Keeping the exact same
    information inline removes that distraction and never blocks the event
    loop.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InlineNotice")
        self.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_2, t.SPACE_2)
        root.setSpacing(t.SPACE_2)

        row = QHBoxLayout()
        row.setSpacing(t.SPACE_2)

        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(24)
        row.addWidget(self.icon_label, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("InlineNoticeTitle")
        self.message_label = QLabel()
        self.message_label.setObjectName("InlineNoticeMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.message_label)
        row.addLayout(text_box, 1)

        self.details_button = QPushButton("Details")
        self.details_button.setObjectName("Ghost")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        row.addWidget(self.details_button, 0, Qt.AlignTop)

        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("Ghost")
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button, 0, Qt.AlignTop)

        close = QPushButton()
        close.setObjectName("IconSm")
        close.setIcon(icons.icon("mdi.close", t.TEXT_MUTED))
        close.setToolTip("Dismiss")
        close.clicked.connect(self.hide_notice)
        row.addWidget(close, 0, Qt.AlignTop)
        root.addLayout(row)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMinimumHeight(120)
        self.detail_view.setMaximumHeight(220)
        self.detail_view.setVisible(False)
        root.addWidget(self.detail_view)

        self._clipboard_text = ""

    def show_error(self, title: str, message: str, detail: str = "") -> None:
        colour = t.status_color(Status.FAILED)
        self.icon_label.setPixmap(
            icons.icon("mdi.alert-circle-outline", colour).pixmap(20, 20))
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.detail_view.setPlainText(detail)
        self._clipboard_text = detail or message

        has_details = bool(detail and detail.strip() != message.strip())
        self.details_button.setVisible(has_details)
        self.copy_button.setVisible(bool(self._clipboard_text))
        self.details_button.setChecked(False)
        self.detail_view.setVisible(False)
        self.setVisible(True)
        self.raise_()

    def hide_notice(self) -> None:
        self.details_button.setChecked(False)
        self.setVisible(False)

    def _toggle_details(self, visible: bool) -> None:
        self.detail_view.setVisible(visible)
        self.details_button.setText("Hide details" if visible else "Details")

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._clipboard_text)


def _find_main_window(parent=None):
    widget = parent if isinstance(parent, QWidget) else QApplication.activeWindow()
    if widget is None:
        return None
    window = widget.window()
    return window if window is not None else widget


def install() -> None:
    """Install lightweight rendering and non-modal feedback refinements."""
    from runner.ui.main_window import MainWindow
    from runner.ui.widgets import ErrorDialog

    original_build_ui = MainWindow._build_ui

    def build_ui_polished(self) -> None:
        original_build_ui(self)

        # Resizing should move the splitter outline first and repaint the two
        # heavy panels only when the user releases the handle.  This is much
        # smoother on workspaces with thousands of visible rows/live output.
        if hasattr(self, "split"):
            self.split.setOpaqueResize(False)
            self.split.setHandleWidth(max(5, t.SPACE_1 + 2))

        # Qt can skip a large amount of per-row geometry calculation when test
        # rows all use the same height.  Per-pixel scrolling also removes the
        # small jump visible with long parameter names.
        for view in self.findChildren(QAbstractItemView):
            view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            view.setAutoScrollMargin(24)
            viewport = view.viewport()
            if viewport is not None:
                viewport.setAttribute(Qt.WA_OpaquePaintEvent, True)
        for tree in self.findChildren(QTreeView):
            tree.setUniformRowHeights(True)
            tree.setAnimated(False)

        # Insert the notice just below the workspace command bar.  It consumes
        # no space while hidden and therefore does not change the normal UI.
        notice = InlineNotice(self.workspace_page)
        self._inline_notice = notice
        layout = self.workspace_page.layout()
        # command bar is index 0; the existing interpreter alert remains below
        # the generic notice if both ever need to be shown.
        layout.insertWidget(1, notice)

    MainWindow._build_ui = build_ui_polished

    original_show_error = ErrorDialog.show_error.__func__

    def show_error_inline(cls, parent, title: str, message: str, detail: str = "") -> None:
        window = _find_main_window(parent)
        notice = getattr(window, "_inline_notice", None) if window is not None else None
        if notice is not None:
            notice.show_error(title, message, detail)
            # An error raised from History/Configuration must still be visible:
            # bring the user back to Workspace where the notice lives, but do
            # not create another top-level window.
            if hasattr(window, "_show_page"):
                window._show_page("workspace")
            return
        original_show_error(cls, parent, title, message, detail)

    ErrorDialog.show_error = classmethod(show_error_inline)
