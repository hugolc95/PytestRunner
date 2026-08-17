"""Filtre par markers : un bouton, et un panneau qui ne s'ouvre qu'a la demande.

La premiere version posait les markers en puces, sur une rangee permanente
au-dessus de l'arbre. Mesure faite sur une suite de 120 tests et 30 markers --
un ordre de grandeur banal pour une suite de cartes -- cette rangee reclamait
2892 px de large. Qt ne l'elargit pas : il comprime. Les puces devenaient des
moignons d'un caractere, la largeur minimale du panneau gauche suivait, et le
reste de la fenetre se retrouvait ecrase.

Un filtre est une intention passagere, pas un affichage permanent. Il ne doit
donc rien couter en place fixe : un bouton dans la barre d'outils qui existe
deja, et un panneau qui s'ouvre par-dessus. Ce qui reste visible en
permanence, c'est le RESULTAT -- combien de tests sont retenus, et par quelle
expression -- la ou le compte de selection vit deja.

Le champ d'expression reste la SEULE verite ; les cases du panneau ne sont
qu'une facon de l'ecrire sans clavier.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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

HAUTEUR_LISTE = 260
LARGEUR_PANNEAU = 320
HAUTEUR_LIGNE = 26


class MarkerFilter(QPushButton):
    """Bouton d'ouverture du panneau, qui porte l'etat du filtre.

    C'est lui l'objet public : la fenetre ne connait que `set_markers()`,
    `matcher()`, `expression()` et le signal `filter_changed`.
    """

    filter_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Markers", parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(styles.TOOLBAR_HEIGHT)

        self.popup = MarkerPopup(self)
        self.popup.changed.connect(self._on_changed)

        self.clicked.connect(self.toggle_popup)
        self.apply_theme()
        self.setVisible(False)

    # ------------------------------------------------------------- apparence

    def apply_theme(self):
        """Reapplique les styles : v1 bascule entre theme clair et sombre."""
        # marker_chip et non filter_chip : « Failed only » vire au rouge parce
        # qu'il montre des echecs. Un filtre de selection n'alerte pas, il
        # prend l'accent de l'application.
        self.setStyleSheet(styles.marker_chip())
        self.popup.apply_theme()

    # ------------------------------------------------------------ chargement

    def set_markers(self, markers):
        """Charge les markers de la suite. Sans aucun, le bouton disparait."""
        self.popup.set_markers(markers)
        self.setVisible(bool(markers))
        self._refresh()

    def clear(self):
        self.popup.clear()
        self._refresh()

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

    # ------------------------------------------------------------- ouverture

    def toggle_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            self.popup.open_under(self)
        self._refresh()

    def _on_changed(self):
        self._refresh()
        self.filter_changed.emit()

    def _refresh(self):
        """Le bouton dit s'il filtre. Un filtre pose derriere un panneau ferme
        serait invisible : on chercherait pourquoi l'arbre est a moitie
        decoche."""
        actif = bool(self.expression())
        noms = self.active_names()

        self.setText(f"Markers · {len(noms)}" if noms
                     else "Markers · ƒ" if actif else "Markers")
        if not actif:
            self.setToolTip("Filter the selection by pytest marker (Ctrl+M)")
        elif noms:
            self.setToolTip("Filtering on " + ", ".join(noms))
        else:
            self.setToolTip(f"Filtering on '{self.expression()}'")

        self.setChecked(actif)


class MarkerPopup(QFrame):
    """Panneau flottant : chercher un marker, le cocher, ou tout ecrire.

    Une liste qui defile plutot qu'une rangee qui s'etale : trente markers y
    tiennent aussi bien que trois, et deux cents aussi.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("MarkerPopup")
        self.setFixedWidth(LARGEUR_PANNEAU)

        self._markers = ()
        self._rows = {}
        self._boxes = {}
        self._silence = False

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(10, 10, 10, 10)
        colonne.setSpacing(8)

        # Chercher un marker parmi trente : sans ce champ, il faut parcourir la
        # liste a l'oeil.
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a marker...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(styles.TOOLBAR_HEIGHT)
        self.search.textChanged.connect(self._apply_search)
        colonne.addWidget(self.search)

        self.liste = QWidget()
        self._liste_layout = QVBoxLayout(self.liste)
        self._liste_layout.setContentsMargins(0, 0, 0, 0)
        self._liste_layout.setSpacing(0)
        self._liste_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.liste)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        colonne.addWidget(self.scroll)

        self.empty = QLabel("No marker matches.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setVisible(False)
        colonne.addWidget(self.empty)

        self.trait = QFrame()
        self.trait.setFrameShape(QFrame.HLine)
        self.trait.setFixedHeight(1)
        colonne.addWidget(self.trait)

        self.field = QLineEdit()
        self.field.setPlaceholderText("smoke and not slow")
        self.field.setClearButtonEnabled(True)
        self.field.setFixedHeight(styles.TOOLBAR_HEIGHT)
        self.field.textChanged.connect(self._on_text)
        colonne.addWidget(self.field)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        colonne.addWidget(self.message)

        pied = QHBoxLayout()
        pied.setContentsMargins(0, 0, 0, 0)
        pied.setSpacing(8)

        self.count = QLabel("")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(styles.TOOLBAR_HEIGHT)
        self.clear_button.clicked.connect(self._on_clear)

        pied.addWidget(self.count, 1)
        pied.addWidget(self.clear_button)
        colonne.addLayout(pied)

        self.apply_theme()

    # ------------------------------------------------------------- apparence

    def apply_theme(self):
        p = styles.palette()
        # Le contour est pose sur le cadre SEUL : sans `#MarkerPopup`, chaque
        # etiquette et chaque case du panneau heritait de la bordure et les
        # comptes apparaissaient dans de petites boites.
        self.setStyleSheet(
            f"QFrame#MarkerPopup {{ background-color: {p['surface']};"
            f" border: 1px solid {p['border']}; border-radius: 6px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
            f"QCheckBox {{ border: none; background: transparent;"
            f" color: {p['text']}; }}")
        self.search.setStyleSheet(styles.line_edit())
        self.field.setStyleSheet(styles.line_edit())
        self.clear_button.setStyleSheet(styles.toolbar_button())
        self.count.setStyleSheet(styles.muted_label())
        self.empty.setStyleSheet(styles.muted_label())
        self.trait.setStyleSheet(f"background-color: {p['border']}; border: none;")
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget "
                                  "{ background: transparent; border: none; }")
        self._refresh()

    # ------------------------------------------------------------ chargement

    def set_markers(self, markers):
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
        self.apply_theme()

    def _ajuster_hauteur(self):
        """Coupe la liste sur une ligne entiere, jamais au milieu de l'une.

        Hauteur FIXE et non plafonnee : la disposition du panneau reprend
        quelques pixels a une hauteur seulement maximale, et la derniere ligne
        se retrouve coupee en deux malgre le calcul juste.
        """
        if not self._rows:
            self.scroll.setFixedHeight(0)
            return
        visibles = max(1, min(len(self._rows), HAUTEUR_LISTE // HAUTEUR_LIGNE))
        self.scroll.setFixedHeight(HAUTEUR_LIGNE * visibles)

    def _make_row(self, marker) -> QWidget:
        ligne = QWidget()
        ligne.setFixedHeight(HAUTEUR_LIGNE)
        disposition = QHBoxLayout(ligne)
        disposition.setContentsMargins(4, 0, 4, 0)
        disposition.setSpacing(8)

        case = QCheckBox(marker.name)
        case.setCursor(Qt.PointingHandCursor)
        case.toggled.connect(self._on_box)

        compte = QLabel(str(marker.count))
        compte.setStyleSheet(styles.muted_label())
        compte.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        disposition.addWidget(case, 1)
        disposition.addWidget(compte)

        if marker.description:
            ligne.setToolTip(marker.description)

        self._boxes[marker.name] = case
        self._rows[marker.name] = ligne
        return ligne

    def clear(self):
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
        return tuple(n for n, c in self._boxes.items() if c.isChecked())

    # ------------------------------------------------------------- ouverture

    def open_under(self, ancre):
        """Ouvre le panneau sous le bouton, sans deborder de l'ecran."""
        self.adjustSize()
        coin = ancre.mapToGlobal(ancre.rect().bottomLeft())
        x, y = coin.x(), coin.y() + 4

        ecran = QApplication.desktop().availableGeometry(ancre)
        x = max(ecran.left(), min(x, ecran.right() - self.width()))
        if y + self.height() > ecran.bottom():
            y = ancre.mapToGlobal(ancre.rect().topLeft()).y() - self.height()

        self.move(x, y)
        self.show()
        self.search.setFocus()

    def keyPressEvent(self, event):
        # Echap ferme sans annuler : le filtre pose reste pose.
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- reactions

    def _apply_search(self, texte):
        requete = str(texte).strip().lower()
        visibles = 0
        for nom, ligne in self._rows.items():
            garde = requete in nom.lower()
            ligne.setVisible(garde)
            visibles += garde
        self.empty.setVisible(bool(self._rows) and not visibles)

    def _on_box(self):
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

    def _on_text(self, _texte):
        if self._silence:
            return
        self._sync_boxes()
        self._refresh()
        self.changed.emit()

    def _on_clear(self):
        self.clear()
        self.changed.emit()

    def _sync_boxes(self):
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

    def _refresh(self):
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

        inconnus = unknown_names(texte, self._boxes)
        # Pas une erreur : pytest accepte un marker inconnu, il ne selectionne
        # simplement rien. Le dire evite de chercher pourquoi c'est vide.
        self._dire("unknown: " + ", ".join(sorted(inconnus)) if inconnus else "",
                   False)

        retenus = sum(1 for m in self._markers if predicat(frozenset({m.name})))
        self.count.setText(f"{retenus} of {len(self._markers)} markers match")

    def _dire(self, texte, erreur):
        self.message.setText(texte)
        self.message.setVisible(bool(texte))
        self.message.setStyleSheet(
            styles.error_label() if erreur else styles.muted_label())
        self.field.setStyleSheet(styles.line_edit(invalid=erreur))
