"""Selectable trace text with local source links and no automatic URL launch."""
from dataclasses import replace
from html import escape
import re

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QTextBrowser

from runner.domain.trace_locations import TraceLocation, references
from runner.ui import tokens as t


def linked_line(text: str, workspace: str = "") -> str:
    parts, start = [], 0
    for begin, end, location in references(text, workspace):
        parts.append(escape(text[start:begin]))
        parts.append(f'<a href="{escape(location.href(), quote=True)}" '
                     f'style="color:{t.ACCENT};text-decoration:underline;">{escape(text[begin:end])}</a>')
        start = end
    parts.append(escape(text[start:]))
    return "".join(parts)


class TraceBrowser(QTextBrowser):
    source_requested = Signal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.default_workspace = ""
        self.require_context = False
        self._activation_modifiers = Qt.NoModifier
        self._workspace_hint = ""
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._activate)
        self.highlighted.connect(self._tooltip)

    def _activate(self, url):
        location = TraceLocation.from_href(url.toString(QUrl.FullyEncoded))
        if location is not None:
            self.source_requested.emit(location, bool(self._activation_modifiers & Qt.ControlModifier))

    def mouseReleaseEvent(self, event):
        # Le modificateur du clic est fiable meme si un ancien Ctrl de Qt
        # reste dans son etat global (tests synthetiques, changement de focus).
        self._activation_modifiers = event.modifiers()
        try:
            super().mouseReleaseEvent(event)
        finally:
            self._activation_modifiers = Qt.NoModifier

    def keyPressEvent(self, event):
        self._activation_modifiers = event.modifiers()
        try:
            super().keyPressEvent(event)
        finally:
            self._activation_modifiers = Qt.NoModifier

    def _tooltip(self, url):
        location = TraceLocation.from_href(url.toString(QUrl.FullyEncoded))
        self.setToolTip(f"Open {location.path}:{location.line}\nCtrl+click: external editor" if location else "")

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        location = TraceLocation.from_href(self.anchorAt(event.pos()))
        if location:
            menu.addSeparator()
            menu.addAction("Open source", lambda: self.source_requested.emit(location, False))
            menu.addAction("Open in external editor", lambda: self.source_requested.emit(location, True))
            menu.addAction("Copy file:line", lambda: QApplication.clipboard().setText(
                f"{location.path}:{location.line}:{location.column}"))
            menu.addAction("Locate file…", lambda: self.locate_file(location))
        menu.exec(event.globalPos())

    def locate_file(self, location):
        path, _ = QFileDialog.getOpenFileName(self, "Locate the source file",
                                             location.workspace or self.default_workspace, "All files (*)")
        if path:
            self.source_requested.emit(replace(location, path=path, context_required=False), False)

    def setPlainText(self, text):
        # Qt's cursor insertion keeps the console's incremental rendering and
        # clipboard text intact. Only file/line spans receive anchor formats.
        super().setPlainText("")
        self._workspace_hint = self.default_workspace
        self.insert_trace_text(QTextCursor(self.document()), text)

    def insert_trace_text(self, cursor, text):
        base = QTextCharFormat()
        for index, line in enumerate(text.split("\n")):
            if index:
                cursor.insertText("\n", base)
            if self.require_context and re.match(r"^\d\d:\d\d:\d\d\s+\[|^\[", line):
                self._workspace_hint = ""
            match = re.search(r"(?:^|\]\s+)Workspace: (.+)$", line)
            if match:
                self._workspace_hint = match[1]
            begin = 0
            for start, end, location in references(line, self._workspace_hint, self.require_context):
                cursor.insertText(line[begin:start], base)
                link = QTextCharFormat()
                link.setAnchor(True)
                link.setAnchorHref(location.href())
                link.setFontUnderline(True)
                link.setForeground(QColor(t.ACCENT))
                cursor.insertText(line[start:end], link)
                begin = end
            cursor.insertText(line[begin:], base)

    def restyle(self):
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    format = QTextCharFormat()
                    format.setForeground(QColor(t.ACCENT))
                    cursor.mergeCharFormat(format)
                iterator += 1
            block = block.next()
