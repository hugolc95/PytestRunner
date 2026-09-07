"""Compact, single-line profile status for the bottom status bar."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy


class ProfileProgressLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Muted")
        self.setTextFormat(Qt.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        text = self.fontMetrics().elidedText(
            self.text(), Qt.ElideRight, self.contentsRect().width())
        painter.drawText(self.contentsRect(), Qt.AlignLeft | Qt.AlignVCenter, text)
