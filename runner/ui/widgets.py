"""Widgets reutilisables : etats vides, erreurs, pastilles, barre de recherche.

Aucun ne connait le domaine autrement que par des types de donnees : ils
recoivent du texte et des couleurs, ils n'appellent rien.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from runner.domain.models import Status
from runner.ui import icons
from runner.ui import theme
from runner.ui import tokens as t


class EmptyState(QWidget):
    """Ce qu'on montre quand il n'y a rien a montrer.

    Une zone vide laisse l'utilisateur deviner s'il a mal fait quelque chose ou
    si l'outil est casse. Un etat vide dit ce qu'il se passe ET propose la
    suite : c'est souvent le premier ecran qu'on voit en ouvrant l'outil.
    """

    action_clicked = pyqtSignal()

    def __init__(self, glyph: str, titre: str, detail: str,
                 action: str = "", raccourci: str = "", parent=None):
        super().__init__(parent)

        colonne = QVBoxLayout(self)
        colonne.setAlignment(Qt.AlignCenter)
        colonne.setSpacing(t.SPACE_3)
        colonne.setContentsMargins(t.SPACE_8, t.SPACE_8, t.SPACE_8, t.SPACE_8)

        self._glyph = glyph
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignCenter)
        colonne.addWidget(self._image)

        self.title_label = QLabel(titre)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setObjectName("Title")
        colonne.addWidget(self.title_label)

        self.detail_label = QLabel(detail)
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setMaximumWidth(360)
        self.detail_label.setObjectName("Muted")
        colonne.addWidget(self.detail_label, alignment=Qt.AlignCenter)

        if action:
            bouton = QPushButton(action)
            bouton.setObjectName("Primary")
            bouton.setCursor(Qt.PointingHandCursor)
            if raccourci:
                bouton.setToolTip(f"{action}  ({raccourci})")
            bouton.clicked.connect(self.action_clicked)
            colonne.addWidget(bouton, alignment=Qt.AlignCenter)

        self.restyle()

    def restyle(self) -> None:
        """Repeint le pictogramme : une image posee une fois ne suit pas la
        feuille de style, et gardait le gris du theme de depart -- bien visible
        au centre d'un panneau devenu blanc."""
        self._image.setPixmap(icons.icon(self._glyph, t.TEXT_FAINT).pixmap(40, 40))

    def update_text(self, titre: str, detail: str) -> None:
        self.title_label.setText(titre)
        self.detail_label.setText(detail)


class StatusPill(QWidget):
    """Compteur d'un statut : une pastille de couleur, un nombre, un libelle.

    Sans boite ni bordure. Quatre compteurs encadres se disputaient
    l'attention, dont trois affichant zero ; ici tout s'eteint a zero et seul
    ce qui a une valeur ressort.

    C'est aussi un filtre : cliquer ne montre plus que les tests de ce statut.
    Le compteur et le filtre sont le meme geste -- on lit « 44 failed », on
    veut voir lesquels, on clique dessus.
    """

    clicked = pyqtSignal(object)  # le Status de cette pastille

    def __init__(self, status: Status, parent=None):
        super().__init__(parent)
        self._status = status
        self._value = 0
        self._active = False

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(t.SPACE_2, 0, t.SPACE_2, 0)
        ligne.setSpacing(t.SPACE_1)

        self._dot = QLabel("●")
        self._text = QLabel()
        ligne.addWidget(self._dot)
        ligne.addWidget(self._text)

        self.setCursor(Qt.PointingHandCursor)
        self.set_value(0)

    @property
    def status(self) -> Status:
        return self._status

    def set_value(self, valeur: int) -> None:
        self._value = valeur
        self._repaint()

    def set_active(self, actif: bool) -> None:
        """Marque la pastille comme filtre en cours."""
        self._active = actif
        self._repaint()

    def restyle(self) -> None:
        """Rejoue les couleurs : elles dependent du statut, pas de la feuille."""
        self._repaint()

    def is_active(self) -> bool:
        return self._active

    def value(self) -> int:
        return self._value

    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._value:
            self.clicked.emit(self._status)
        super().mousePressEvent(event)

    def _repaint(self) -> None:
        allume = self._value > 0
        couleur = t.status_color(self._status)
        libelle = self._status.label.lower()

        self._dot.setStyleSheet(
            f"color: {couleur if allume else t.BORDER_STRONG};"
            f"font-size: 9px; background: transparent;")
        self._text.setText(f"{self._value} {libelle}")
        self._text.setStyleSheet(theme.counter_style(couleur, allume))

        # Le fond ne s'allume que sur le filtre actif : c'est le seul etat qui
        # doit se distinguer d'un simple compteur.
        self.setStyleSheet(
            f"background-color: {t.rgba(couleur, 0.16)};"
            f"border-radius: {t.RADIUS_SM}px;" if self._active
            else "background: transparent;")

        if not allume:
            self.setToolTip(f"No {libelle} test")
        elif self._active:
            self.setToolTip(f"Showing only {libelle} tests — click to show all")
        else:
            self.setToolTip(f"{self._value} {libelle} — click to show only these")


class RemainingPill(QWidget):
    """Ce qu'il reste a passer. Gris : ce n'est pas un verdict, c'est un reste.

    Un compteur qui descend dit mieux « ca avance » qu'une barre de
    progression seule, et il repond a la question qu'on se pose vraiment
    devant une suite longue : combien de temps encore.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(t.SPACE_2, 0, t.SPACE_2, 0)
        ligne.setSpacing(t.SPACE_1)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {t.BORDER_STRONG}; font-size: 9px; background: transparent;")
        self._text = QLabel()
        ligne.addWidget(self._dot)
        ligne.addWidget(self._text)

        self.set_value(0)
        self.setVisible(False)

    def set_value(self, valeur: int) -> None:
        self._value = max(0, valeur)
        self._text.setText(f"{self._value} left")
        self._text.setStyleSheet(theme.counter_style(t.TEXT_MUTED, self._value > 0))
        self.setToolTip(f"{self._value} tests still to run")

    def value(self) -> int:
        return self._value

    def restyle(self) -> None:
        self.set_value(self._value)


class ReaderBadge(QLabel):
    """Nom d'un lecteur, dans sa couleur, pour relier colonne / onglet / log."""

    def __init__(self, nom: str, index: int, parent=None):
        super().__init__(nom, parent)
        self._index = index
        self.restyle()

    def restyle(self) -> None:
        self.setStyleSheet(theme.pill_style(t.reader_color(self._index)))


class ReaderResult(QWidget):
    """Verdict d'un test sur un lecteur : le lecteur, puis son statut.

    Reunis dans une seule etiquette pour qu'on lise « ce lecteur, ce
    resultat » et non deux informations a rapprocher soi-meme.
    """

    def __init__(self, nom: str, index: int, status: Status, parent=None):
        super().__init__(parent)

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)

        if nom:
            ligne.addWidget(ReaderBadge(nom, index))

        # Pas de `restyle()` ici : le panneau de detail rebatit ces etiquettes
        # a chaque affichage, y compris quand il rejoue le theme. Les couleurs
        # lues maintenant sont donc toujours celles de la palette courante.
        couleur = t.status_color(status)
        actif = status is not Status.PENDING

        icone = QLabel()
        icone.setPixmap(icons.status_icon(status).pixmap(14, 14))
        icone.setStyleSheet("background: transparent;")
        icone.setVisible(actif)

        texte = QLabel(status.label if actif else "NOT RUN")
        texte.setStyleSheet(
            f"color: {couleur if actif else t.TEXT_FAINT};"
            f"font-size: {t.TEXT_XS}px; font-weight: 700;"
            "background: transparent;")

        ligne.addWidget(icone)
        ligne.addWidget(texte)


class SearchBar(QWidget):
    """Champ de recherche avec compteur et navigation entre correspondances.

    Une recherche, pas un filtre : masquer ce qui ne correspond pas fait perdre
    le contexte du test trouve (son fichier, sa classe, ses voisins).
    """

    query_changed = pyqtSignal(str)
    next_match = pyqtSignal()
    previous_match = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QLineEdit

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_1)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Find a test…")
        self.field.setClearButtonEnabled(True)
        # La loupe est gardee sous la main : au changement de theme il faut lui
        # repeindre son icone, et non en ajouter une deuxieme a cote.
        self._magnify = self.field.addAction(
            icons.icon("mdi.magnify", t.TEXT_FAINT), QLineEdit.LeadingPosition)
        self.field.textChanged.connect(self.query_changed)
        self.field.returnPressed.connect(self.next_match)

        self.counter = QLabel("")
        self.counter.setObjectName("Faint")
        self.counter.setMinimumWidth(52)
        self.counter.setAlignment(Qt.AlignCenter)

        self.prev_button = self._nav("mdi.chevron-up", "Previous match (Shift+Enter)",
                                     self.previous_match)
        self.next_button = self._nav("mdi.chevron-down", "Next match (Enter)",
                                     self.next_match)

        ligne.addWidget(self.field, 1)
        ligne.addWidget(self.counter)
        ligne.addWidget(self.prev_button)
        ligne.addWidget(self.next_button)

    def _nav(self, glyph: str, infobulle: str, signal) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("Icon")
        bouton.setIcon(icons.icon(glyph, t.TEXT_MUTED))
        bouton.setToolTip(infobulle)
        bouton.setEnabled(False)
        bouton.clicked.connect(signal)
        return bouton

    def restyle(self) -> None:
        self._magnify.setIcon(icons.icon("mdi.magnify", t.TEXT_FAINT))
        self.prev_button.setIcon(icons.icon("mdi.chevron-up", t.TEXT_MUTED))
        self.next_button.setIcon(icons.icon("mdi.chevron-down", t.TEXT_MUTED))

    def set_matches(self, position: int, total: int) -> None:
        """Met a jour le compteur. `position` est en base 1, 0 si aucun."""
        if not self.field.text().strip():
            self.counter.setText("")
        elif total:
            self.counter.setText(f"{position}/{total}")
        else:
            self.counter.setText("none")

        self.prev_button.setEnabled(total > 1)
        self.next_button.setEnabled(total > 1)

    def text(self) -> str:
        return self.field.text()


class ErrorDialog(QDialog):
    """Erreur lisible : une phrase, et le detail seulement si on le demande.

    Une stacktrace jetee dans une QMessageBox est illisible et deborde de
    l'ecran. Le message court dit ce qui s'est passe ; le detail reste
    disponible pour qui doit le coller dans un ticket.
    """

    def __init__(self, titre: str, message: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setMinimumWidth(460)

        colonne = QVBoxLayout(self)
        colonne.setSpacing(t.SPACE_3)
        colonne.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_4)

        entete = QHBoxLayout()
        entete.setSpacing(t.SPACE_3)

        image = QLabel()
        image.setPixmap(icons.icon("mdi.alert-circle",
                                   t.status_color(Status.FAILED)).pixmap(24, 24))
        image.setAlignment(Qt.AlignTop)
        entete.addWidget(image)

        texte = QLabel(message)
        texte.setWordWrap(True)
        texte.setTextInteractionFlags(Qt.TextSelectableByMouse)
        texte.setStyleSheet(f"color: {t.TEXT}; background: transparent;")
        entete.addWidget(texte, 1)
        colonne.addLayout(entete)

        self.detail_view: QPlainTextEdit | None = None
        if detail and detail.strip() != message.strip():
            self.toggle = QPushButton("Show details")
            self.toggle.setObjectName("Quiet")
            self.toggle.setCheckable(True)
            self.toggle.setCursor(Qt.PointingHandCursor)
            self.toggle.toggled.connect(self._on_toggled)
            colonne.addWidget(self.toggle, alignment=Qt.AlignLeft)

            self.detail_view = QPlainTextEdit(detail)
            self.detail_view.setReadOnly(True)
            self.detail_view.setVisible(False)
            self.detail_view.setMinimumHeight(180)
            colonne.addWidget(self.detail_view)

        boutons = QHBoxLayout()
        boutons.addStretch(1)

        if detail:
            copier = QPushButton("Copy")
            copier.setObjectName("Ghost")
            copier.setToolTip("Copy the full details to the clipboard")
            copier.clicked.connect(lambda: self._copier(detail or message))
            boutons.addWidget(copier)

        fermer = QPushButton("Close")
        fermer.setObjectName("Primary")
        fermer.setDefault(True)
        fermer.clicked.connect(self.accept)
        boutons.addWidget(fermer)
        colonne.addLayout(boutons)

    def _on_toggled(self, ouvert: bool) -> None:
        if self.detail_view is not None:
            self.detail_view.setVisible(ouvert)
        self.toggle.setText("Hide details" if ouvert else "Show details")
        self.adjustSize()

    @staticmethod
    def _copier(texte: str) -> None:
        from PyQt5.QtWidgets import QApplication

        QApplication.clipboard().setText(texte)

    @classmethod
    def show_error(cls, parent, titre: str, message: str, detail: str = "") -> None:
        cls(titre, message, detail, parent).exec_()


def separator() -> QFrame:
    """Trait de 1 px entre deux zones."""
    trait = QFrame()
    trait.setObjectName("Separator")
    trait.setFrameShape(QFrame.HLine)
    trait.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return trait
