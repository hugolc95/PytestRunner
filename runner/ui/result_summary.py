"""Cases de resultats dont la geometrie ne depend pas des compteurs."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QStyle, QStyleOptionButton

from runner.ui import icons, tokens as t
from runner.ui.widgets import StatusPill


class ResultCounter(StatusPill):
    """Conserve le bouton teinte d'origine dans une case de taille stable."""

    def sizeHint(self):
        return QSize(96, 36)

    def minimumSizeHint(self):
        return QSize(84, 36)

    def _repaint(self):
        color = t.status_color(self._status)
        lit = self._value > 0
        label = self._status.label.lower()
        self.setText(f"{self._value} {self._status.label}")
        self.setAccessibleName(f"{self._value} {label}")
        self.setIcon(icons.icon(icons.STATUS_GLYPHS_GROUP.get(self._status,
                              'mdi.circle-small'), color if lit else t.BORDER_STRONG))
        border = color if self._active else t.rgba(color, 0.32 if lit else 0.14)
        background = t.rgba(color, 0.22 if self._active else 0.10 if lit else 0.04)
        self.setStyleSheet(
            f"QPushButton {{ background: {background}; border: 1px solid {border}; "
            f"border-radius: {t.RADIUS_MD}px; padding: 0; }}"
            f"QPushButton:hover {{ background: {t.rgba(color, 0.16 if lit else 0.07)}; }}"
            f"QPushButton:pressed {{ background: {t.rgba(color, 0.18)}; }}")
        # Ni le nombre de chiffres ni le passage de zero a un verdict ne
        # doivent changer la taille demandee au layout.
        self.setMinimumWidth(84)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(f"Showing only {label} tests — click to show all" if self._active else
                        f"{self._value} {label} — click to show only these" if self._value else
                        f"No {label} test")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        option.icon = QIcon()
        self.style().drawControl(QStyle.CE_PushButton, option, painter, self)
        number_font, label_font, number, label, number_width, label_width = self._inline_text()
        content_width = 18 + 5 + number_width + 4 + label_width
        left = max(5, (self.width() - content_width) // 2)
        self.icon().paint(painter, QRect(left, (self.height() - 18) // 2, 18, 18))
        painter.setFont(number_font)
        painter.setPen(QColor(t.status_color(self._status) if self._value else t.TEXT_FAINT))
        painter.drawText(QRect(left + 23, 0, number_width + 1, self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, number)
        painter.setFont(label_font)
        painter.drawText(QRect(left + 27 + number_width, 0, label_width + 1, self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, label)

    def _inline_text(self):
        # On adapte seulement la typographie aux gros nombres : la grille
        # ne bouge pas et le nombre exact reste toujours dans l'infobulle.
        number_font = QFont(self.font())
        label_font = QFont(self.font())
        number_font.setWeight(QFont.Bold)
        label_font.setWeight(QFont.Normal)
        number = str(self._value)
        label = self._status.label
        for size in (12, 11, 10):
            number_font.setPixelSize(size)
            label_font.setPixelSize(size)
            number_width = QFontMetrics(number_font).horizontalAdvance(number)
            label_width = QFontMetrics(label_font).horizontalAdvance(label)
            if number_width + label_width + 27 <= self.width() - 10:
                break
        available = max(0, self.width() - 37 - number_width)
        label = QFontMetrics(label_font).elidedText(label, Qt.ElideRight, available)
        label_width = QFontMetrics(label_font).horizontalAdvance(label)
        return number_font, label_font, number, label, number_width, label_width


class RingProgressLabel(QLabel):
    """Le texte reste lisible au centre sans agrandir la case de l'anneau."""

    def sizeHint(self):
        return QSize(0, 0)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        done, separator, total = self.text().partition(' / ')
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        font.setPixelSize(18)
        while QFontMetrics(font).horizontalAdvance(done) > self.width() - 20 and font.pixelSize() > 10:
            font.setPixelSize(font.pixelSize() - 1)
        painter.setFont(font)
        painter.setPen(QColor(t.TEXT))
        painter.drawText(self.rect().adjusted(8, 0, -8, -12 if separator else 0), Qt.AlignCenter, done)
        if separator:
            font.setPixelSize(t.TEXT_XS)
            font.setWeight(QFont.Normal)
            painter.setFont(font)
            painter.setPen(QColor(t.TEXT_MUTED))
            painter.drawText(self.rect().adjusted(8, 29, -8, 0), Qt.AlignCenter, f'/ {total}')
