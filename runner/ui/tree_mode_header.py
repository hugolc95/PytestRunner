"""Controls hosted inside the first tree header section, not a new toolbar."""

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtWidgets import QWidget, QComboBox
from runner.ui import tokens as t


class ProfilePicker(QComboBox):
    opening = Signal()

    def showPopup(self):
        self.opening.emit()
        super().showPopup()


class TreeModeHeader(QWidget):
    def __init__(self):
        super().__init__()
        self._header = None
        self.setObjectName('TreeModeHeader')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.restyle()

    def restyle(self):
        self.setStyleSheet(f'QWidget#TreeModeHeader {{background:{t.BG_SURFACE};}}')

    def attach(self, header):
        if self._header is not header:
            if self._header is not None:
                self._header.viewport().removeEventFilter(self)
                self._header.sectionResized.disconnect(self._place)
                self._header.geometriesChanged.disconnect(self._place)
            self._header = header
            self.setParent(header.viewport())
            header.setMinimumHeight(40)
            header.viewport().installEventFilter(self)
            header.sectionResized.connect(self._place)
            header.geometriesChanged.connect(self._place)
        self._place()

    def _place(self, *_):
        if self._header is not None:
            self.setGeometry(self._header.sectionViewportPosition(0), 0,
                             self._header.sectionSize(0), self._header.viewport().height())

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self._place()
        return False
