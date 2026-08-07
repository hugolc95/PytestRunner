# gui_qt/status_icons.py
#
# Rendu partage des statuts de test (couleur + icone), utilise par les arbres
# du mode Workspace (test_tree_view.py) et du mode Campaign (campaign_window.py).

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter

from gui_qt.styles import styles

STATUS_PRIORITY = {
    "ERROR": 4,
    "FAILED": 3,
    "SKIPPED": 2,
    "PASSED": 1,
}


class _ThemedStatusColors:
    """Couleurs de statut suivant le theme actif.

    Reste indexable comme l'ancien dictionnaire (STATUS_COLORS[status]) pour ne
    rien casser chez les appelants, mais relit la palette a chaque acces : un
    vert fonce lisible sur fond blanc devient illisible sur fond sombre.
    """

    def __getitem__(self, status: str) -> QColor:
        return QColor(styles.status_color(status))

    def get(self, status: str, default=None):
        if status in STATUS_PRIORITY:
            return QColor(styles.status_color(status))
        return default

    def __contains__(self, status: str) -> bool:
        return status in STATUS_PRIORITY


STATUS_COLORS = _ThemedStatusColors()

# Un symbole par statut en plus de la couleur : la couleur seule n'est pas
# lisible pour un utilisateur daltonien.
STATUS_ICON_CHARS = {
    "PASSED": "✓",
    "FAILED": "✗",
    "SKIPPED": "▸",
    "ERROR": "!",
}

_status_icon_cache: dict[str, QIcon] = {}


def forget_status_icons() -> None:
    """Vide le cache d'icones : a appeler apres un changement de theme, sinon
    les icones gardent les couleurs de l'ancienne palette."""
    _status_icon_cache.clear()


def status_icon(status: str) -> QIcon:
    if status in _status_icon_cache:
        return _status_icon_cache[status]

    color = QColor(styles.status_color(status))
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
