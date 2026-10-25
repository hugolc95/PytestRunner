"""Garde les colonnes de resultat visibles quand l'arbre retrecit."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer


class NameColumnFitter(QObject):
    """La colonne des noms cede la place, jamais les colonnes Status / Duration.

    Sa largeur reste celle que l'utilisateur a choisie (ou restauree) tant
    qu'elle tient. Quand le panneau devient trop etroit, elle se reduit juste
    assez pour que les colonnes de droite restent a l'ecran ; elle retrouve sa
    largeur choisie des que la place revient. Avant, ces colonnes partaient
    hors champ derriere une barre de defilement horizontale.
    """

    MINIMUM = 100

    def __init__(self, tree, parent=None):
        super().__init__(parent or tree)
        self._tree = tree
        self._preferred = tree.columnWidth(0)
        self._fitting = False
        header = tree.header()
        header.sectionResized.connect(self._on_section_resized)
        tree.viewport().installEventFilter(self)
        # Apres un changement de lecteurs, la largeur des colonnes de droite
        # change sans que le panneau bouge.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.fit)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            # Jamais pendant le redimensionnement lui-meme : la vue peut etre
            # en train de remettre son modele a zero (expandAll, set_tree).
            self._timer.start()
        return False

    def _on_section_resized(self, index: int, _old: int, new: int) -> None:
        if self._fitting:
            return
        if index == 0:
            self._preferred = new
        else:
            self._timer.start()

    def fit(self) -> None:
        header = self._tree.header()
        others = sum(header.sectionSize(i) for i in range(1, header.count())
                     if not header.isSectionHidden(i))
        available = self._tree.viewport().width() - others
        width = max(self.MINIMUM, min(self._preferred, available))
        if width == header.sectionSize(0):
            return
        self._fitting = True
        try:
            header.resizeSection(0, width)
        finally:
            self._fitting = False
