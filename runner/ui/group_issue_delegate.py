"""Readable history issues without creating a widget for each list row."""
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from runner.ui import tokens as t

ISSUE_ROLE = Qt.UserRole + 1


class GroupIssueDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        if index.data(ISSUE_ROLE):
            return QSize(240, max(92, option.fontMetrics.height() * 3 + 34))
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        issue = index.data(ISSUE_ROLE)
        if not issue:
            return super().paint(painter, option, index)
        status, name, readers, message = issue
        color = t.status_color(status)
        rect = option.rect.adjusted(0, 3, -1, -3)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.ACCENT_SOFT if selected else t.BG_RAISED))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRect(rect.left() + 10, rect.top() + 13, 3, rect.height() - 26), 1, 1)
        font = QFont(t.FONT_UI)
        font.setPixelSize(max(t.TEXT_SM, option.font.pixelSize()))
        painter.setFont(font)
        fm = painter.fontMetrics()
        badge_width = max(58, fm.horizontalAdvance(status.label) + 16)
        badge = QRect(rect.left() + 23, rect.top() + 10, badge_width, fm.height() + 6)
        painter.setBrush(QColor(t.blend(color, t.BG_RAISED, 0.15)))
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor(color))
        painter.drawText(badge, Qt.AlignCenter, status.label)
        title = QRect(badge.right() + 10, badge.top(), max(0, rect.right() - badge.right() - 22), badge.height())
        painter.setPen(QColor(t.TEXT))
        painter.drawText(title, Qt.AlignVCenter, fm.elidedText(name, Qt.ElideRight, title.width()))
        line_height = fm.height() + 5
        line = QRect(badge.left(), badge.bottom() + 6, max(0, rect.width() - 36), line_height)
        painter.setPen(QColor(t.TEXT_MUTED))
        painter.drawText(line, Qt.AlignVCenter, fm.elidedText(readers, Qt.ElideRight, line.width()))
        line.translate(0, line_height)
        painter.setPen(QColor(t.TEXT))
        painter.drawText(line, Qt.AlignVCenter, fm.elidedText(message, Qt.ElideRight, line.width()))
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QColor(t.ACCENT))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        painter.restore()
