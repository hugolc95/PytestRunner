"""Descriptions colorees sans widgets par ligne, selection et statuts conserves."""
import re
from PySide6.QtCore import Qt, QRect, QEvent
from PySide6.QtGui import QColor, QFontMetrics, QFontInfo, QPen, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem, QToolTip

from runner.ui.widgets import DivergenceDelegate
from runner.ui import tokens as t
from runner.ui import icons
from runner.ui.tree_model import NODEID_ROLE
from runner.ui.profile_yaml_tooltip import profile_yaml_tooltip

GROUP_ROLE = Qt.UserRole + 26
EXCEPTION_ROLE = Qt.UserRole + 27
TRANSFER_ROLE = Qt.UserRole + 28
YAML_ROLE = Qt.UserRole + 29
GROUP_COLOR_ROLE = Qt.UserRole + 30
CONFIG_ISSUES_ROLE = Qt.UserRole + 31


class ProfileGroupDelegate(DivergenceDelegate):
    def helpEvent(self, event, view, option, index):
        if event.type() != QEvent.ToolTip or not index.isValid() or index.column() != 0:
            return super().helpEvent(event, view, option, index)
        annotation = index.data(YAML_ROLE) or {}
        problems = index.data(CONFIG_ISSUES_ROLE) or []
        if not annotation.get('state') and not problems:
            return super().helpEvent(event, view, option, index)
        nodeid = index.data(NODEID_ROLE)
        metadata = self._group(index) or {}
        title = metadata.get('name') or (str(nodeid).split('::')[-1] if nodeid else self._plain_title(str(index.data() or '')))
        groups = []
        parent = index if metadata else index.parent()
        while parent.isValid():
            group = self._group(parent)
            if group:
                groups.append(group['name'])
            parent = parent.parent()
        disabled = getattr(index.model(), 'disabled_data', None)
        extra = disabled(nodeid, Qt.ToolTipRole) if callable(disabled) and nodeid else ''
        rich = profile_yaml_tooltip(title, annotation, membership=' / '.join(reversed(groups)),
                                    description=metadata.get('description', ''), problems=problems,
                                    read_only=bool(view.property('profileYamlReadOnly')), extra=extra or '',
                                    font_scale=QFontInfo(view.font()).pixelSize() / t.TEXT_MD)
        QToolTip.showText(event.globalPos(), rich, view.viewport(), view.visualRect(index))
        return True

    @staticmethod
    def _group(index):
        if index.column() == 0 and not index.data(NODEID_ROLE):
            return index.data(GROUP_ROLE)
        return None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # La pastille porte l'information sans repeter un suffixe dans le nom.
        if index.data(YAML_ROLE):
            option.text = self._plain_title(option.text)
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
        painter.save()
        painter.setClipRect(option.rect, Qt.IntersectClip)
        try:
            self._paint_row(painter, option, index)
        finally:
            painter.restore()

    def _paint_row(self, painter, option, index):
        transfer = index.data(TRANSFER_ROLE) if index.column() == 0 else None
        content = QStyleOptionViewItem(option)
        if transfer:
            content.rect.adjust(0, 0, -23, 0)
        annotation = index.data(YAML_ROLE) if index.column() == 0 else None
        warning_rect = None
        if index.column() == 0 and index.data(CONFIG_ISSUES_ROLE):
            warning_rect = QRect(content.rect.right() - 20, content.rect.center().y() - 8, 16, 16)
            content.rect.adjust(0, 0, -24, 0)
        self._paint_content(painter, content, index)
        if annotation and annotation.get('state') == 'custom':
            self._custom_dot(painter, content, index)
        if warning_rect:
            icons.icon('mdi.alert-outline', '#d89a17').paint(painter, warning_rect)
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
            return super().paint(painter, option, index)
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
        width = max(0, option.rect.right() - left - 4)
        title = str(index.data(Qt.DisplayRole) or '').split('\n', 1)[0]
        if index.data(YAML_ROLE):
            title = self._plain_title(title)
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

    @staticmethod
    def _plain_title(text):
        text = text.replace(' · Custom YAML', '').replace(' · YAML exception', '')
        return re.sub(r' · \d+ exceptions?\b', '', text)

    def _custom_dot(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = option.widget.style() if option.widget else QApplication.style()
        decoration = style.subElementRect(QStyle.SE_ItemViewItemDecoration, opt, option.widget)
        rect = (QRect(decoration.right() - 5, decoration.top() - 1, 7, 7) if decoration.isValid()
                else QRect(option.rect.left() + 2, option.rect.center().y() - 3, 7, 7))
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(t.BG_SURFACE), 1.5))
        painter.setBrush(QColor('#e8b355' if t.is_dark() else '#875500'))
        painter.drawEllipse(rect)
        painter.restore()
