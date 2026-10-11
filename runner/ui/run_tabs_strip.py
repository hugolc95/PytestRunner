"""Compact run cards whose execution state stays visible on inactive tabs."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QTabBar

from runner.ui import tokens as t


class RunTabClose(QAbstractButton):
    """Quiet close affordance drawn with the current application palette."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Close run")
        self.setAccessibleName("Close run")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t.BG_SURFACE))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)
        painter.setPen(QPen(QColor(t.TEXT if self.underMouse() or self.hasFocus()
                                  else t.TEXT_MUTED), 1.4))
        painter.drawLine(8, 8, 14, 14)
        painter.drawLine(8, 14, 14, 8)


class RunTabBar(QTabBar):
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        return QSize(min(225, max(160, size.width())), 42)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index in range(self.count()):
            data = self.tabData(index) or {}
            rect = self.tabRect(index).adjusted(3, 3, -3, -3)
            if not rect.intersects(event.rect()):
                continue
            selected = index == self.currentIndex()
            colour = data.get("colour", t.TEXT_MUTED)
            painter.setPen(QPen(QColor(colour if selected else t.BORDER), 1))
            painter.setBrush(QColor(t.blend(colour, t.BG_SURFACE, .18 if selected else .07)))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(colour))
            path = QPainterPath()
            path.addRoundedRect(rect, 6, 6)
            painter.save()
            painter.setClipPath(path)
            painter.drawRect(QRect(rect.left(), rect.top(), 3, rect.height()))
            painter.restore()
            icon_rect = QRect(rect.left() + 10, rect.top() + 3, 14, 14)
            self.tabIcon(index).paint(painter, icon_rect)
            width = max(0, rect.width() - 60)
            font = self.font()
            font.setBold(selected)
            painter.setFont(font)
            painter.setPen(QColor(t.TEXT))
            name = painter.fontMetrics().elidedText(data.get("name", self.tabText(index)), Qt.ElideRight, width)
            painter.drawText(QRect(rect.left() + 30, rect.top() + 1, width, 17), Qt.AlignVCenter, name)
            font.setBold(False)
            font.setPointSize(max(8, font.pointSize() - 1))
            painter.setFont(font)
            painter.setPen(QColor(colour))
            detail = painter.fontMetrics().elidedText(data.get("detail", "Draft"), Qt.ElideRight, width + 23)
            painter.drawText(QRect(rect.left() + 10, rect.top() + 18, width + 20, 15), Qt.AlignVCenter, detail)
