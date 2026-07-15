# gui_qt/status_icons.py
#
# Rendu partage des statuts de test (couleur + icone), utilise par les arbres
# du mode Workspace (test_tree_view.py) et du mode Campaign (campaign_window.py).

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter

STATUS_PRIORITY = {
    "ERROR": 4,
    "FAILED": 3,
    "SKIPPED": 2,
    "PASSED": 1,
}

STATUS_COLORS = {
    "PASSED": QColor("#2e7d32"),
    "FAILED": QColor("#c62828"),
    "SKIPPED": QColor("#ef6c00"),
    "ERROR": QColor("#6a1b9a"),
}

# Un symbole par statut en plus de la couleur : la couleur seule n'est pas
# lisible pour un utilisateur daltonien.
STATUS_ICON_CHARS = {
    "PASSED": "✓",
    "FAILED": "✗",
    "SKIPPED": "▸",
    "ERROR": "!",
}

_status_icon_cache: dict[str, QIcon] = {}


def status_icon(status: str) -> QIcon:
    if status in _status_icon_cache:
        return _status_icon_cache[status]

    color = STATUS_COLORS.get(status, QColor("#616161"))
    char = STATUS_ICON_CHARS.get(status, "?")

    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(color)
    font = painter.font()
    font.setBold(True)
    font.setPointSize(9)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, char)
    painter.end()

    icon = QIcon(pixmap)
    _status_icon_cache[status] = icon
    return icon
