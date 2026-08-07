"""Zone de code en lecture seule avec numeros de ligne.

Utilisee pour l'onglet Source. Les numeros aident a se reperer dans un fichier
de test long et a faire le lien avec les numeros cites par les traces pytest.
"""

from __future__ import annotations

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QTextFormat
from PyQt5.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from gui_qt.styles import styles


class _LineNumberArea(QWidget):
    """Gouttiere : sa largeur est imposee par l'editeur, qui la dessine."""

    def __init__(self, editor: "CodeView"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeView(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        self._line_numbers = _LineNumberArea(self)

        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self._update_width()

    # ------------------------------------------------------------------ gouttiere

    def line_number_area_width(self) -> int:
        chiffres = max(1, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * chiffres

    def _update_width(self, _=0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_area(self, rect: QRect, dy: int):
        if dy:
            self._line_numbers.scroll(0, dy)
        else:
            self._line_numbers.update(0, rect.y(), self._line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        zone = self.contentsRect()
        self._line_numbers.setGeometry(
            QRect(zone.left(), zone.top(), self.line_number_area_width(), zone.height())
        )

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_numbers)
        palette = styles.palette()
        painter.fillRect(event.rect(), QColor(palette["gutter_bg"]))
        painter.setPen(QColor(palette["gutter_text"]))

        bloc = self.firstVisibleBlock()
        numero = bloc.blockNumber()
        haut = round(self.blockBoundingGeometry(bloc).translated(self.contentOffset()).top())
        bas = haut + round(self.blockBoundingRect(bloc).height())

        # Le numero de la ligne courante est mis en avant : c'est le repere le
        # plus net, la teinte de fond restant volontairement discrete pour ne
        # pas gener la lecture du code.
        ligne_courante = self.textCursor().blockNumber()
        normal = QColor(palette["gutter_text"])
        accent = QColor(palette["gutter_current"])
        gras = painter.font()

        while bloc.isValid() and haut <= event.rect().bottom():
            if bloc.isVisible() and bas >= event.rect().top():
                courante = numero == ligne_courante
                painter.setPen(accent if courante else normal)
                gras.setBold(courante)
                painter.setFont(gras)
                painter.drawText(
                    0, haut, self._line_numbers.width() - 6,
                    self.fontMetrics().height(), Qt.AlignRight, str(numero + 1),
                )
            bloc = bloc.next()
            haut = bas
            bas = haut + round(self.blockBoundingRect(bloc).height())
            numero += 1

    # ------------------------------------------------------------ ligne courante

    def highlight_current_line(self):
        """Souligne la ligne du curseur, qui est aussi celle ou l'on a saute
        pour montrer la definition du test."""
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(styles.palette()["current_line"]))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
        self._line_numbers.update()

    def restyle(self):
        self._update_width()
        self.highlight_current_line()
        self._line_numbers.update()
