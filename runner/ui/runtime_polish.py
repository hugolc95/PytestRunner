"""Runtime polish for the PySide6 interface.

The runner already keeps collection and execution outside the GUI thread. This
module focuses on the remaining interaction details that are easy to feel on a
large workspace: modal error windows, expensive live repaints while resizing,
and tree painting work that Qt can avoid when every test row has the same
height.
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

    Errors used to be displayed with ``QDialog.exec()``. Besides interrupting
    keyboard/mouse flow, native Windows dialogs can briefly flash as a second
    top-level window while Qt applies its stylesheet. Keeping the same
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

        self.close_button = QPushButton()
        self.close_button.setObjectName("IconSm")
        self.close_button.setToolTip("Dismiss")
        self.close_button.clicked.connect(self.hide_notice)
        row.addWidget(self.close_button, 0, Qt.AlignTop)
        root.addLayout(row)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMinimumHeight(120)
        self.detail_view.setMaximumHeight(220)
        self.detail_view.setVisible(False)
        root.addWidget(self.detail_view)

        self._clipboard_text = ""
        self.restyle()

    def restyle(self) -> None:
        """Follow the current light/dark theme without recreating the widget."""
        colour = t.status_color(Status.FAILED)
        self.setStyleSheet(
            f"QFrame#InlineNotice {{"
            f"background-color: {t.rgba(colour, 0.09)};"
            f"border: 1px solid {t.rgba(colour, 0.55)};"
            f"border-radius: {t.RADIUS_MD}px;"
            f"}}"
            f"QLabel#InlineNoticeTitle {{"
            f"background: transparent; color: {colour}; font-weight: 700;"
            f"}}"
            f"QLabel#InlineNoticeMessage {{"
            f"background: transparent; color: {t.TEXT};"
            f"}}")
        self.close_button.setIcon(icons.icon("mdi.close", t.TEXT_MUTED))
        if self.isVisible():
            self.icon_label.setPixmap(
                icons.icon("mdi.alert-circle-outline", colour).pixmap(20, 20))

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


def _polish_item_view(view: QAbstractItemView) -> None:
    """Keep scrolling smooth without bypassing Qt's background repaint.

    ``WA_OpaquePaintEvent`` leaves stylesheet-backed viewports partially
    unpainted with Qt 6.8 on Windows. The untouched regions then show up as
    black rectangles and stale column separators after resize/scroll.
    """
    view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    view.setAutoScrollMargin(24)
    viewport = view.viewport()
    if viewport is not None:
        viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)


def install() -> None:
    """Install lightweight rendering and non-modal feedback refinements."""
    from runner.ui.main_window import MainWindow
    from runner.ui.widgets import ErrorDialog

    original_build_ui = MainWindow._build_ui

    def build_ui_polished(self) -> None:
        original_build_ui(self)

        # Move only the splitter outline while dragging. The expensive tree and
        # output panels repaint once when the handle is released.
        if hasattr(self, "split"):
            self.split.setOpaqueResize(False)
            self.split.setHandleWidth(max(5, t.SPACE_1 + 2))

        # Reduce geometry work and make scrolling feel continuous on large
        # parameterized suites.
        for view in self.findChildren(QAbstractItemView):
            _polish_item_view(view)
        for tree in self.findChildren(QTreeView):
            tree.setUniformRowHeights(True)
            tree.setAnimated(False)

        # Hidden notices consume no space. They appear below the workspace bar
        # and never become a second top-level Windows window.
        notice = InlineNotice(self.workspace_page)
        self._inline_notice = notice
        layout = self.workspace_page.layout()
        layout.insertWidget(1, notice)

    MainWindow._build_ui = build_ui_polished

    original_show_error = ErrorDialog.show_error.__func__

    def show_error_inline(cls, parent, title: str, message: str, detail: str = "") -> None:
        window = _find_main_window(parent)
        notice = getattr(window, "_inline_notice", None) if window is not None else None
        if notice is not None:
            notice.show_error(title, message, detail)
            # If an error originates from History/Configuration, show it in the
            # main workspace instead of opening a floating dialog.
            if hasattr(window, "_show_page"):
                window._show_page("workspace")
            return
        original_show_error(cls, parent, title, message, detail)

    ErrorDialog.show_error = classmethod(show_error_inline)
