"""Selection par markers : des puces, et un champ pour les cas tordus.

Le champ est la SEULE verite. Les puces ne sont qu'une facon de l'ecrire sans
clavier : cliquer `smoke` puis `perso` y inscrit `smoke or perso`, et taper
`smoke and not slow` a la main rallume ce que les puces savent representer.
Deux etats concurrents -- des puces d'un cote, une expression de l'autre --
auraient oblige a inventer une regle de priorite, et cette regle aurait ete
fausse une fois sur deux.

La barre ne selectionne rien elle-meme : elle dit ce qu'elle veut, la fenetre
coche l'arbre. C'est l'arbre qui reste le contrat de ce qui va tourner.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from runner.domain.markers import (
    ExpressionError,
    Marker,
    compile_expression,
    names_of_union,
    union_expression,
)
from runner.domain.models import Status
from runner.ui import icons, theme
from runner.ui import tokens as t


class MarkerBar(QWidget):
    """Puces de markers et expression pytest, au-dessus de l'arbre."""

    # Emis quand la selection demandee change. La fenetre lit `matcher()`.
    filter_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._markers: tuple[Marker, ...] = ()
        self._chips: dict[str, QPushButton] = {}
        self._silence = False

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)

        self._chip_row = QWidget()
        self._chip_layout = QHBoxLayout(self._chip_row)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(t.SPACE_1)
        colonne.addWidget(self._chip_row)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Marker expression — smoke and not slow")
        self.field.setClearButtonEnabled(True)
        self.field.addAction(icons.icon("mdi.tag-multiple-outline", t.TEXT_FAINT),
                             QLineEdit.LeadingPosition)
        self.field.textChanged.connect(self._on_text)
        colonne.addWidget(self.field)

        # Sous le champ, sur toute la largeur : a cote, le message se faisait
        # tronquer au tiers et volait au passage la moitie du champ.
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(theme.faint())
        self.message.setVisible(False)
        colonne.addWidget(self.message)

        self.setVisible(False)

    # ------------------------------------------------------------- chargement

    def set_markers(self, markers: list[Marker]) -> None:
        """Reconstruit les puces. Sans marker, la barre disparait entierement.

        Beaucoup de suites n'en utilisent aucun : leur laisser une rangee vide
        au-dessus de l'arbre serait de la place prise pour rien.
        """
        self._markers = tuple(markers)
        self.clear()

        while self._chip_layout.count():
            element = self._chip_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._chips = {}

        for marker in self._markers:
            puce = QPushButton(f"{marker.name}  {marker.count}")
            puce.setObjectName("Chip")
            puce.setCheckable(True)
            puce.setCursor(Qt.PointingHandCursor)
            puce.setToolTip(marker.tooltip)
            puce.clicked.connect(self._on_chip)
            self._chip_layout.addWidget(puce)
            self._chips[marker.name] = puce

        self._chip_layout.addStretch(1)
        self._chip_row.setVisible(bool(self._markers))
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

    # ---------------------------------------------------------------- lecture

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

    # -------------------------------------------------------------- reactions

    def _on_chip(self) -> None:
        """Reecrit l'expression a partir des puces allumees."""
        actifs = [m.name for m in self._markers
                  if self._chips[m.name].isChecked()]
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
            self.message.setText("")
            self.message.setStyleSheet(theme.faint())
            self.field.setProperty("invalid", False)
            self._show_message()
            return

        try:
            compile_expression(texte)
        except ExpressionError as exc:
            self.message.setText(str(exc))
            self.message.setStyleSheet(
                f"color: {t.status_color(Status.FAILED)}; font-size: {t.TEXT_XS}px;"
                "background: transparent;")
            self.field.setProperty("invalid", True)
        else:
            inconnus = self._unknown_names(texte)
            if inconnus:
                # Pas une erreur : pytest accepte un marker inconnu, il ne
                # selectionne simplement rien. Le dire evite de chercher
                # pourquoi la selection est vide.
                self.message.setText("unknown: " + ", ".join(sorted(inconnus)))
            else:
                self.message.setText("")
            self.message.setStyleSheet(theme.faint())
            self.field.setProperty("invalid", False)
        self._show_message()

    def _unknown_names(self, texte: str) -> set[str]:
        import ast

        connus = {m.name for m in self._markers}
        try:
            arbre = ast.parse(texte, mode="eval")
        except SyntaxError:
            return set()
        return {n.id for n in ast.walk(arbre)
                if isinstance(n, ast.Name) and n.id not in connus}

    def _show_message(self) -> None:
        """Affiche la ligne de message seulement quand elle dit quelque chose.

        Qt ne relit pas le QSS quand une propriete change : il faut le dire.
        """
        self.message.setVisible(bool(self.message.text()))
        self.field.style().unpolish(self.field)
        self.field.style().polish(self.field)
