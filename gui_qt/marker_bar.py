"""Selection par markers : des puces, et un champ pour les cas tordus.

Le champ est la SEULE verite. Les puces ne sont qu'une facon de l'ecrire sans
clavier : cliquer `smoke` puis `perso` y inscrit `smoke or perso`, et taper
`smoke and not slow` a la main eteint les puces, qui ne savent representer
qu'une union. Deux etats concurrents -- des puces d'un cote, une expression de
l'autre -- auraient oblige a inventer une regle de priorite, et cette regle
aurait ete fausse une fois sur deux.

La barre ne selectionne rien elle-meme : elle dit ce qu'elle veut, la fenetre
coche l'arbre. C'est l'arbre qui reste le contrat de ce qui va tourner.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.markers import (
    ExpressionError,
    compile_expression,
    names_of_union,
    union_expression,
    unknown_names,
)
from gui_qt.styles import styles


class MarkerBar(QWidget):
    """Puces de markers et expression pytest, au-dessus de l'arbre."""

    # Emis quand la selection demandee change. La fenetre lit `matcher()`.
    filter_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._markers = ()
        self._chips = {}
        self._silence = False

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(4)

        rangee = QHBoxLayout()
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(6)

        self._legende = QLabel("Markers")
        rangee.addWidget(self._legende)

        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        rangee.addLayout(self._chip_row)
        rangee.addStretch()
        colonne.addLayout(rangee)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Marker expression - smoke and not slow")
        self.field.setClearButtonEnabled(True)
        self.field.setFixedHeight(styles.TOOLBAR_HEIGHT)
        self.field.textChanged.connect(self._on_text)
        colonne.addWidget(self.field)

        # Sous le champ, sur toute la largeur : a cote, le message se ferait
        # tronquer et volerait au passage la moitie de la place du champ.
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        colonne.addWidget(self.message)

        self.apply_theme()
        self.setVisible(False)

    # ------------------------------------------------------------- apparence

    def apply_theme(self) -> None:
        """Reapplique les styles : v1 bascule entre theme clair et sombre."""
        self._legende.setStyleSheet(styles.muted_label())
        self.field.setStyleSheet(styles.line_edit())
        for puce in self._chips.values():
            puce.setStyleSheet(styles.marker_chip())
        self._update_message()

    # ------------------------------------------------------------ chargement

    def set_markers(self, markers) -> None:
        """Reconstruit les puces. Sans marker, la barre disparait entierement.

        Beaucoup de suites n'en utilisent aucun : leur laisser une rangee vide
        au-dessus de l'arbre serait de la place prise pour rien.
        """
        self._markers = tuple(markers)
        self.clear()

        while self._chip_row.count():
            element = self._chip_row.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._chips = {}

        for marker in self._markers:
            puce = QPushButton(f"{marker.name}  {marker.count}")
            puce.setCheckable(True)
            puce.setCursor(Qt.PointingHandCursor)
            puce.setToolTip(marker.tooltip)
            puce.setFixedHeight(styles.TOOLBAR_HEIGHT)
            puce.setStyleSheet(styles.marker_chip())
            puce.clicked.connect(self._on_chip)
            self._chip_row.addWidget(puce)
            self._chips[marker.name] = puce

        self.setVisible(bool(self._markers))

    def clear(self) -> None:
        self._silence = True
        try:
            self.field.clear()
            for puce in self._chips.values():
                puce.setChecked(False)
        finally:
            self._silence = False
        self._update_message()

    # --------------------------------------------------------------- lecture

    def expression(self) -> str:
        return self.field.text().strip()

    def matcher(self):
        """Predicat de selection, ou None si le champ est vide ou invalide.

        None veut dire « la barre ne demande rien » : la fenetre laisse alors
        la selection de l'arbre telle quelle plutot que de tout decocher.
        """
        texte = self.expression()
        if not texte:
            return None
        try:
            return compile_expression(texte)
        except ExpressionError:
            return None

    def is_valid(self) -> bool:
        return not self.expression() or self.matcher() is not None

    # ------------------------------------------------------------- reactions

    def _on_chip(self) -> None:
        """Reecrit l'expression a partir des puces allumees."""
        actifs = [m.name for m in self._markers if self._chips[m.name].isChecked()]
        self._silence = True
        try:
            self.field.setText(union_expression(actifs))
        finally:
            self._silence = False
        self._update_message()
        self.filter_changed.emit()

    def _on_text(self, _texte: str) -> None:
        if self._silence:
            return
        self._sync_chips()
        self._update_message()
        self.filter_changed.emit()

    def _sync_chips(self) -> None:
        """Rallume les puces quand le champ dit exactement ce qu'elles disent."""
        texte = self.expression()
        noms = set(names_of_union(texte) or ()) if texte else set()
        for nom, puce in self._chips.items():
            puce.blockSignals(True)
            puce.setChecked(nom in noms)
            puce.blockSignals(False)

    def _update_message(self) -> None:
        texte = self.expression()
        if not texte:
            self._dire("", False)
            return

        try:
            compile_expression(texte)
        except ExpressionError as exc:
            self._dire(str(exc), True)
            return

        inconnus = unknown_names(texte, self._chips)
        # Pas une erreur : pytest accepte un marker inconnu, il ne selectionne
        # simplement rien. Le dire evite de chercher pourquoi c'est vide.
        self._dire("unknown: " + ", ".join(sorted(inconnus)) if inconnus else "",
                   False)

    def _dire(self, texte: str, erreur: bool) -> None:
        self.message.setText(texte)
        self.message.setVisible(bool(texte))
        self.message.setStyleSheet(
            styles.error_label() if erreur else styles.muted_label())
        self.field.setStyleSheet(
            styles.line_edit(invalid=erreur))
