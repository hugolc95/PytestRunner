"""Recherche locale dans un log, sans filtrer ni modifier son contenu."""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QWidget,
)

from runner.ui import icons
from runner.ui import tokens as t


class LogSearchBar(QWidget):
    highlights_changed = Signal()
    navigated = Signal()

    # Navigation and counting cover the entire displayed document. Limit the
    # painted overlays so a search for a common character stays responsive.
    MAX_HIGHLIGHTS = 2000

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self._matches: list[tuple[int, int]] = []
        self._index = -1
        self._active = QTextCursor(editor.document())
        self._revision = -1
        self._query_changed = False
        self._status = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.refresh)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Find in log…")
        self.field.setAccessibleName("Find in log")
        self.field.setClearButtonEnabled(True)
        self.field.setMinimumWidth(60)
        self.field.setToolTip(
            "Find literal text in the displayed log, ignoring case. "
            "Ctrl+F · Enter / Shift+Enter · F3 / Shift+F3 · Esc to clear")
        self._magnify = self.field.addAction(
            icons.icon("mdi.magnify", t.TEXT_FAINT), QLineEdit.LeadingPosition)
        self.counter = QLabel("")
        self.counter.setObjectName("Faint")
        self.counter.setMinimumWidth(44)
        self.counter.setMaximumWidth(80)
        self.counter.setAlignment(Qt.AlignCenter)
        self.previous = self._button("mdi.chevron-up", "Previous match (Shift+Enter / Shift+F3)", -1)
        self.next = self._button("mdi.chevron-down", "Next match (Enter / F3)", 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_1)
        layout.addWidget(self.field, 1)
        layout.addWidget(self.counter)
        layout.addWidget(self.previous)
        layout.addWidget(self.next)
        self.field.textChanged.connect(self._queue_query)
        editor.document().contentsChanged.connect(self._queue_document)
        for widget in (editor, self.field):
            widget.installEventFilter(self)

    def _button(self, glyph, tooltip, direction):
        button = QPushButton()
        button.setObjectName("IconSm")
        button.setIcon(icons.icon(glyph, t.TEXT_MUTED))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setEnabled(False)
        button.clicked.connect(lambda: self.navigate(direction))
        return button

    def focus_search(self):
        self.field.setFocus()
        self.field.selectAll()

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.ShortcutOverride, QEvent.KeyPress):
            return super().eventFilter(watched, event)
        find = event.matches(QKeySequence.Find)
        step = event.key() == Qt.Key_F3
        enter = watched is self.field and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        escape = event.key() == Qt.Key_Escape and (bool(self.field.text()) or watched is self.field)
        if not (find or step or enter or escape):
            return super().eventFilter(watched, event)
        # Claim Ctrl+F before the window-wide tree search action sees it.
        event.accept()
        if event.type() == QEvent.KeyPress:
            if find:
                self.focus_search()
            elif escape:
                self.field.clear()
                self.editor.setFocus()
            else:
                self.navigate(-1 if event.modifiers() & Qt.ShiftModifier else 1)
        return True

    def _queue_query(self):
        self._query_changed = True
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        if not self.field.text():
            self.refresh()
        else:
            self.counter.setText("…")
            self._timer.start()

    def _queue_document(self):
        if self.field.text() and not self._timer.isActive():
            self._timer.start()

    def refresh(self):
        """Reindex after typing or a document replacement/append."""
        self._timer.stop()
        reveal = self._query_changed
        self._query_changed = False
        position = self._active.selectionStart() if self._index >= 0 and not reveal else 0
        query = self.field.text()
        if not query and reveal and self.editor.textCursor() == self._active:
            cursor = self.editor.textCursor()
            cursor.clearSelection()
            self.editor.setTextCursor(cursor)
        self._matches = []
        if query:
            cursor = QTextCursor(self.editor.document())
            while True:
                cursor = self.editor.document().find(query, cursor)
                if cursor.isNull():
                    break
                self._matches.append((cursor.selectionStart(), cursor.selectionEnd()))
        self._index = (next((i for i, match in enumerate(self._matches)
                             if match[0] >= position), 0)
                       if self._matches else -1)
        self._revision = self.editor.document().revision()
        self._update()
        if reveal and self._matches:
            self._reveal()

    def navigate(self, direction):
        new_query = self._query_changed
        if self._timer.isActive():
            self.refresh()
        if not self._matches:
            return
        if not new_query or direction < 0:
            self._index = (self._index + direction) % len(self._matches)
        self._update()
        self._reveal()

    def _reveal(self):
        self.editor.setTextCursor(self._active)
        self.editor.centerCursor()
        self.navigated.emit()

    def _update(self):
        total = len(self._matches)
        if self._index >= 0:
            self._active = self._cursor(self._matches[self._index])
        self._update_counter()
        self.previous.setEnabled(total > 1)
        self.next.setEnabled(total > 1)
        self.highlights_changed.emit()

    def set_status(self, text):
        self._status = text
        self._update_counter()

    def _update_counter(self):
        if self.field.text():
            total = len(self._matches)
            self.counter.setText(f"{self._index + 1}/{total}")
            self.counter.setToolTip(
                f"{total} matches in the displayed log" if total else "No matches in the displayed log")
        else:
            self.counter.setText(self.counter.fontMetrics().elidedText(
                self._status, Qt.ElideRight, self.counter.maximumWidth()))
            self.counter.setToolTip(self._status)

    def selections(self):
        selections = []
        if self._revision != self.editor.document().revision():
            return selections
        # Paint a bounded neighbourhood around the active result, including it
        # even when it is beyond the first MAX_HIGHLIGHTS matches.
        start = max(0, self._index - self.MAX_HIGHLIGHTS // 2)
        end = min(len(self._matches), start + self.MAX_HIGHLIGHTS)
        for index in range(start, end):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = self._cursor(self._matches[index])
            current = index == self._index
            colour = QColor(t.ACCENT)
            colour.setAlpha(210 if current else 65)
            selection.format.setBackground(colour)
            if current:
                selection.format.setForeground(QColor(t.ON_ACCENT))
            selections.append(selection)
        return selections

    def _cursor(self, match):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(match[0])
        cursor.setPosition(match[1], QTextCursor.KeepAnchor)
        return cursor

    def restyle(self):
        self._magnify.setIcon(icons.icon("mdi.magnify", t.TEXT_FAINT))
        self.previous.setIcon(icons.icon("mdi.chevron-up", t.TEXT_MUTED))
        self.next.setIcon(icons.icon("mdi.chevron-down", t.TEXT_MUTED))
        self.highlights_changed.emit()
