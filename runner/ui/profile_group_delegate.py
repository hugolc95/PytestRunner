"""Descriptions colorees sans widgets par ligne, selection et statuts conserves."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFontMetrics, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from runner.ui.widgets import DivergenceDelegate
from runner.ui import tokens as t
from runner.ui import icons
from runner.ui.tree_model import NODEID_ROLE

GROUP_ROLE = Qt.UserRole + 26
EXCEPTION_ROLE = Qt.UserRole + 27
TRANSFER_ROLE = Qt.UserRole + 28


class ProfileGroupDelegate(DivergenceDelegate):
    @staticmethod
    def _group(index):
        if index.column() == 0 and not index.data(NODEID_ROLE):
            return index.data(GROUP_ROLE)
        return None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if self._group(index):
            # Le style Qt doit peindre le fond, l'icone et le focus seulement.
            # Vider le texte AVANT son paint evite deux rendus superposes.
            option.text = ''

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        group = self._group(index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        height = QFontMetrics(opt.font).height()
        size.setHeight(max(size.height(), height * 2 + 10 if group and group.get('description') else 30))
        return size

    def paint(self, painter, option, index):
        transfer = index.data(TRANSFER_ROLE) if index.column() == 0 else None
        content = QStyleOptionViewItem(option)
        if transfer:
            content.rect.adjust(0, 0, -23, 0)
        self._paint_content(painter, content, index)
        if transfer:
            color = QColor(t.ACCENT if transfer == 'copied' else '#55b86f')
            painter.save()
            pen = QPen(color, 1)
            pen.setStyle(Qt.DashLine if transfer == 'copied' else Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(1, 2, -2, -3), 3, 3)
            glyph = 'mdi.content-copy' if transfer == 'copied' else 'mdi.check'
            rect = QRect(option.rect.right() - 20, option.rect.center().y() - 8, 16, 16)
            icons.icon(glyph, color.name()).paint(painter, rect)
            painter.restore()

    def _paint_content(self, painter, option, index):
        group = self._group(index)
        if not group:
            if index.column() != 0 or not index.data(EXCEPTION_ROLE):
                return super().paint(painter, option, index)
            compact = QStyleOptionViewItem(option)
            compact.rect.adjust(0, 0, -22, 0)
            super().paint(painter, compact, index)
            self._exception_icon(painter, option)
            return
        painter.save()
        super().paint(painter, option, index)
        painter.restore()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        painter.save()
        painter.setClipRect(option.rect)
        painter.fillRect(option.rect.left(), option.rect.top() + 3, 3,
                         max(0, option.rect.height() - 6), QColor(group['color']))
        painter.setFont(opt.font)
        fm = painter.fontMetrics()
        selected = bool(opt.state & QStyle.State_Selected)
        painter.setPen(opt.palette.highlightedText().color() if selected else QColor(t.TEXT))
        left = option.rect.left() + max(16, opt.decorationSize.width()) + 8
        width = max(0, option.rect.right() - left - (26 if index.data(EXCEPTION_ROLE) else 4))
        title = str(index.data(Qt.DisplayRole) or '').split('\n', 1)[0]
        desc = group.get('description', '')
        if desc:
            top = QRect(left, option.rect.top() + 4, width, fm.height())
            painter.drawText(top, Qt.AlignVCenter | Qt.TextSingleLine, fm.elidedText(title, Qt.ElideRight, width))
            top.translate(0, fm.height() + 2)
            painter.setPen(QColor(group['color']))
            painter.drawText(top, Qt.AlignVCenter | Qt.TextSingleLine, fm.elidedText(desc, Qt.ElideRight, width))
        else:
            rect = QRect(left, option.rect.top(), width, option.rect.height())
            painter.drawText(rect, Qt.AlignVCenter | Qt.TextSingleLine, fm.elidedText(title, Qt.ElideRight, width))
        painter.restore()
        if index.data(EXCEPTION_ROLE):
            self._exception_icon(painter, option)

    @staticmethod
    def _exception_icon(painter, option):
        rect = QRect(option.rect.right() - 20, option.rect.center().y() - 8, 16, 16)
        icons.icon('mdi.alert-outline', '#d89a17').paint(painter, rect)
