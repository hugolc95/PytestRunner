"""Filtre par markers : un bouton, et un panneau qui ne s'ouvre qu'a la demande.

La premiere version posait les markers en puces, sur une rangee permanente
au-dessus de l'arbre. Mesure faite sur une suite de 120 tests et 30 markers --
un ordre de grandeur banal pour une suite de cartes -- cette rangee reclamait
2892 px de large. Qt ne l'elargit pas : il comprime. Les puces devenaient des
moignons d'un caractere (`d`, `al`, `l3`), la largeur minimale du panneau
gauche suivait, et le panneau de droite se retrouvait ecrase.

Un filtre est une intention passagere, pas un affichage permanent. Il ne doit
donc rien couter en place fixe : un bouton dans la rangee d'outils qui existe
deja, et un panneau qui s'ouvre par-dessus. Ce qui reste visible en
permanence, c'est le RESULTAT -- combien de tests sont retenus, et par quelle
expression -- la ou le compte de selection vit deja.

Le champ d'expression reste la SEULE verite ; les cases du panneau ne sont
qu'une facon de l'ecrire sans clavier. Deux etats concurrents auraient oblige
a inventer une regle de priorite, fausse une fois sur deux.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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

# Au-dela, la liste defile. Assez pour voir une dizaine de markers d'un coup
# sans que le panneau ne couvre tout l'arbre.
HAUTEUR_LISTE = 260
LARGEUR_PANNEAU = 320


class MarkerFilter(QPushButton):
    """Bouton d'ouverture du panneau, qui porte l'etat du filtre.

    C'est lui l'objet public : la fenetre ne connait que `set_markers()`,
    `matcher()`, `expression()` et le signal `filter_changed`. La forme du
    panneau peut changer sans que rien d'autre ne bouge.
    """

    filter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Sans libelle, carre comme ses voisins de la rangee : « Markers »
        # ecrit en toutes lettres affamait le champ de recherche, reduit a
        # « Find a... ». Ce que fait le filtre se lit dans son infobulle, dans
        # le menu Select, et surtout dans l'etiquette du pied de panneau.
        self.setObjectName("Icon")
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(icons.icon("mdi.tag-multiple-outline", t.TEXT_MUTED))

        self.popup = MarkerPopup(self)
        self.popup.changed.connect(self._on_changed)

        self.clicked.connect(self.toggle_popup)
        self._refresh_label()
        self.setVisible(False)

    # ------------------------------------------------------------ chargement

    def set_markers(self, markers) -> None:
        """Charge les markers de la suite. Sans aucun, le bouton disparait."""
        self.popup.set_markers(markers)
        self.setVisible(bool(markers))
        self._refresh_label()

    def clear(self) -> None:
        self.popup.clear()
        self._refresh_label()

    # --------------------------------------------------------------- lecture

    def expression(self) -> str:
        return self.popup.expression()

    def matcher(self):
        """Predicat de selection, ou None si vide ou invalide.

        None veut dire « le filtre ne demande rien » : la fenetre laisse alors
        la selection de l'arbre telle quelle plutot que de tout decocher.
        """
        return self.popup.matcher()

    def is_valid(self) -> bool:
        return self.popup.is_valid()

    def active_names(self) -> tuple:
        return self.popup.active_names()

    # ------------------------------------------------------------ ouverture

    def restyle(self) -> None:
        """Rejoue l'icone et le panneau avec la palette courante."""
        self._refresh_label()
        self.popup.restyle()

    def toggle_popup(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
            return
        self.popup.open_under(self)

    def _on_changed(self) -> None:
        self._refresh_label()
        self.filter_changed.emit()

    def _refresh_label(self) -> None:
        """Le bouton dit s'il filtre, et sur combien de markers.

        Un filtre actif derriere un panneau ferme serait invisible : on
        chercherait pourquoi la moitie de l'arbre est decochee.
        """
        noms = self.active_names()
        actif = bool(self.expression())

        if not actif:
            self.setToolTip("Filter the selection by marker  (Ctrl+M)")
        elif noms:
            self.setToolTip("Filtering on " + ", ".join(noms) + "  (Ctrl+M)")
        else:
            self.setToolTip(f"Filtering on “{self.expression()}”  (Ctrl+M)")

        self.setIcon(icons.icon(
            "mdi.tag-multiple" if actif else "mdi.tag-multiple-outline",
            t.ACCENT if actif else t.TEXT_MUTED))
        self.setProperty("active", actif)
        self.style().unpolish(self)
        self.style().polish(self)


class MarkerPopup(QFrame):
    """Panneau flottant : chercher un marker, le cocher, ou tout ecrire.

    Une liste qui defile plutot qu'une rangee qui s'etale : trente markers y
    tiennent aussi bien que trois, et deux cents aussi.
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popup")
        self.setFixedWidth(LARGEUR_PANNEAU)

        self._markers: tuple = ()
        self._rows: dict = {}
        self._boxes: dict = {}
        self._silence = False

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        colonne.setSpacing(t.SPACE_2)

        # Chercher un marker parmi trente : sans ce champ, il faut parcourir la
        # liste a l'oeil.
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a marker…")
        self.search.setClearButtonEnabled(True)
        # Gardee sous la main : au changement de theme on lui repeint son
        # icone, sinon `addAction` en empile une deuxieme a chaque bascule.
        self._magnify = self.search.addAction(
            icons.icon("mdi.magnify", t.TEXT_FAINT), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._on_search)
        colonne.addWidget(self.search)

        self.liste = QWidget()
        self._liste_layout = QVBoxLayout(self.liste)
        self._liste_layout.setContentsMargins(0, 0, 0, 0)
        self._liste_layout.setSpacing(0)
        self._liste_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("Plain")
        self.scroll.setWidget(self.liste)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMaximumHeight(HAUTEUR_LISTE)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        colonne.addWidget(self.scroll)

        self.empty = QLabel("No marker matches.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(theme.faint())
        self.empty.setVisible(False)
        colonne.addWidget(self.empty)

        trait = QFrame()
        trait.setObjectName("Separator")
        trait.setFrameShape(QFrame.HLine)
        trait.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        colonne.addWidget(trait)

        self.field = QLineEdit()
        self.field.setPlaceholderText("smoke and not slow")
        self.field.setClearButtonEnabled(True)
        self.field.textChanged.connect(self._on_text)
        colonne.addWidget(self.field)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        colonne.addWidget(self.message)

        pied = QHBoxLayout()
        pied.setContentsMargins(0, 0, 0, 0)
        pied.setSpacing(t.SPACE_2)

        self.count = QLabel("")
        self.count.setStyleSheet(theme.faint())

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self._on_clear)

        pied.addWidget(self.count, 1)
        pied.addWidget(self.clear_button)
        colonne.addLayout(pied)

    # ------------------------------------------------------------ chargement

    def set_markers(self, markers) -> None:
        self._markers = tuple(markers)
        self.clear()

        while self._liste_layout.count():
            element = self._liste_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}
        self._boxes = {}

        for marker in self._markers:
            self._liste_layout.addWidget(self._make_row(marker))
        self._liste_layout.addStretch(1)

        self.search.clear()
        self._apply_search("")
        self._ajuster_hauteur()

    def _ajuster_hauteur(self) -> None:
        """Coupe la liste sur une ligne entiere, jamais au milieu de l'une."""
        if not self._rows:
            self.scroll.setFixedHeight(0)
            return
        visibles = max(1, min(len(self._rows), HAUTEUR_LISTE // t.CONTROL_SM))
        # Hauteur FIXE et non maximale : la disposition du panneau reprenait
        # une douzaine de pixels a une hauteur seulement plafonnee, et la
        # derniere ligne se retrouvait coupee en deux malgre le calcul juste.
        self.scroll.setFixedHeight(t.CONTROL_SM * visibles)

    def _make_row(self, marker: Marker) -> QWidget:
        ligne = QWidget()
        ligne.setObjectName("MarkerRow")
        # Hauteur imposee : c'est elle qui permet d'arreter la liste sur une
        # ligne entiere. Mesuree apres coup, elle depend du style et le calcul
        # tombait a cote d'un ou deux pixels -- soit une derniere ligne coupee.
        ligne.setFixedHeight(t.CONTROL_SM)
        disposition = QHBoxLayout(ligne)
        disposition.setContentsMargins(t.SPACE_1, t.SPACE_1, t.SPACE_1, t.SPACE_1)
        disposition.setSpacing(t.SPACE_2)

        case = QCheckBox(marker.name)
        case.setCursor(Qt.PointingHandCursor)
        case.toggled.connect(self._on_box)

        compte = QLabel(str(marker.count))
        compte.setStyleSheet(theme.faint())
        compte.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        disposition.addWidget(case, 1)
        disposition.addWidget(compte)

        if marker.description:
            ligne.setToolTip(marker.description)

        self._boxes[marker.name] = case
        self._rows[marker.name] = ligne
        return ligne

    def clear(self) -> None:
        self._silence = True
        try:
            self.field.clear()
            for case in self._boxes.values():
                case.setChecked(False)
        finally:
            self._silence = False
        self._refresh()

    # --------------------------------------------------------------- lecture

    def expression(self) -> str:
        return self.field.text().strip()

    def matcher(self):
        texte = self.expression()
        if not texte:
            return None
        try:
            return compile_expression(texte)
        except ExpressionError:
            return None

    def is_valid(self) -> bool:
        return not self.expression() or self.matcher() is not None

    def active_names(self) -> tuple:
        """Markers coches, si l'expression n'est qu'une union. Sinon rien."""
        return tuple(n for n, c in self._boxes.items() if c.isChecked())

    # ------------------------------------------------------------ ouverture

    def restyle(self) -> None:
        self._magnify.setIcon(icons.icon("mdi.magnify", t.TEXT_FAINT))
        self._refresh()

    def open_under(self, ancre: QWidget) -> None:
        """Ouvre le panneau sous le bouton, sans deborder de l'ecran."""
        self.adjustSize()
        coin = ancre.mapToGlobal(ancre.rect().bottomLeft())
        x, y = coin.x(), coin.y() + t.SPACE_1

        # `QApplication.desktop()` a disparu avec Qt6 : sous PySide6, l'ecran
        # se lit sur le widget lui-meme. La levee d'exception qui en
        # resultait etait avalee en silence par Qt au milieu du slot
        # connecte au clic -- le bouton semblait ne rien faire du tout.
        ecran = ancre.screen().availableGeometry()
        x = max(ecran.left(), min(x, ecran.right() - self.width()))
        if y + self.height() > ecran.bottom():
            y = ancre.mapToGlobal(ancre.rect().topLeft()).y() - self.height()

        self.move(x, y)
        self.show()
        self.search.setFocus()

    def keyPressEvent(self, event) -> None:
        # Echap ferme sans annuler : le filtre pose reste pose.
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- reactions

    def _on_search(self, texte: str) -> None:
        self._apply_search(texte)

    def _apply_search(self, texte: str) -> None:
        requete = texte.strip().lower()
        visibles = 0
        for nom, ligne in self._rows.items():
            garde = requete in nom.lower()
            ligne.setVisible(garde)
            visibles += garde
        self.empty.setVisible(bool(self._rows) and not visibles)

    def _on_box(self) -> None:
        """Reecrit l'expression a partir des cases cochees."""
        if self._silence:
            return
        actifs = [m.name for m in self._markers if self._boxes[m.name].isChecked()]
        self._silence = True
        try:
            self.field.setText(union_expression(actifs))
        finally:
            self._silence = False
        self._refresh()
        self.changed.emit()

    def _on_text(self, _texte: str) -> None:
        if self._silence:
            return
        self._sync_boxes()
        self._refresh()
        self.changed.emit()

    def _on_clear(self) -> None:
        self.clear()
        self.changed.emit()

    def _sync_boxes(self) -> None:
        """Recoche les cases quand le champ dit exactement ce qu'elles disent."""
        texte = self.expression()
        noms = set(names_of_union(texte) or ()) if texte else set()
        self._silence = True
        try:
            for nom, case in self._boxes.items():
                case.setChecked(nom in noms)
        finally:
            self._silence = False

    # ------------------------------------------------------------- affichage

    def _refresh(self) -> None:
        texte = self.expression()
        self.clear_button.setEnabled(bool(texte))

        if not texte:
            self._dire("", False)
            self.count.setText(f"{len(self._markers)} markers")
            return

        try:
            predicat = compile_expression(texte)
        except ExpressionError as exc:
            self._dire(str(exc), True)
            self.count.setText("")
            return

        connus = set(self._boxes)
        inconnus = _noms_de(texte) - connus
        # Pas une erreur : pytest accepte un marker inconnu, il ne selectionne
        # simplement rien. Le dire evite de chercher pourquoi c'est vide.
        self._dire("unknown: " + ", ".join(sorted(inconnus)) if inconnus else "",
                   False)

        retenus = sum(1 for m in self._markers if predicat(frozenset({m.name})))
        self.count.setText(f"{retenus} of {len(self._markers)} markers match")

    def _dire(self, texte: str, erreur: bool) -> None:
        self.message.setText(texte)
        self.message.setVisible(bool(texte))
        self.message.setStyleSheet(
            f"color: {t.status_color(Status.FAILED)}; font-size: {t.TEXT_XS}px;"
            "background: transparent;" if erreur else theme.faint())
        self.field.setProperty("invalid", erreur)
        self.field.style().unpolish(self.field)
        self.field.style().polish(self.field)


def _noms_de(texte: str) -> set:
    import ast

    try:
        arbre = ast.parse((texte or "").strip(), mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)}
