"""Compact run cards whose execution state stays visible on inactive tabs."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QTabBar

from runner.ui import tokens as t


class RunTabBar(QTabBar):
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        return QSize(min(270, max(190, size.width())), 58)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index in range(self.count()):
            data = self.tabData(index) or {}
            rect = self.tabRect(index).adjusted(3, 4, -3, -4)
            if not rect.intersects(event.rect()):
                continue
            selected = index == self.currentIndex()
            colour = data.get("colour", t.TEXT_MUTED)
            painter.setPen(QPen(QColor(colour if selected else t.BORDER), 1))
            painter.setBrush(QColor(t.blend(colour, t.BG_SURFACE, .18 if selected else .07)))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(colour))
            painter.drawRoundedRect(QRect(rect.left() + 1, rect.top() + 7, 3, rect.height() - 14), 1, 1)
            icon_rect = QRect(rect.left() + 12, rect.top() + 7, 16, 16)
            self.tabIcon(index).paint(painter, icon_rect)
            width = max(0, rect.width() - 65)
            font = self.font()
            font.setBold(selected)
            painter.setFont(font)
            painter.setPen(QColor(t.TEXT))
            name = painter.fontMetrics().elidedText(data.get("name", self.tabText(index)), Qt.ElideRight, width)
            painter.drawText(QRect(rect.left() + 35, rect.top() + 4, width, 22), Qt.AlignVCenter, name)
            font.setBold(False)
            font.setPointSize(max(8, font.pointSize() - 1))
            painter.setFont(font)
            painter.setPen(QColor(colour))
            detail = painter.fontMetrics().elidedText(data.get("detail", "Draft"), Qt.ElideRight, width + 23)
            painter.drawText(QRect(rect.left() + 12, rect.top() + 27, width + 23, 18), Qt.AlignVCenter, detail)
