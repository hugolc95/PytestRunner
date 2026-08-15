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

        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        image.setPixmap(icons.icon(glyph, t.TEXT_FAINT).pixmap(40, 40))
        colonne.addWidget(image)

        self.title_label = QLabel(titre)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.TEXT_LG}px; font-weight: 600;"
            "background: transparent;")
        colonne.addWidget(self.title_label)

        self.detail_label = QLabel(detail)
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setMaximumWidth(360)
        self.detail_label.setStyleSheet(theme.muted())
        colonne.addWidget(self.detail_label, alignment=Qt.AlignCenter)

        if action:
            bouton = QPushButton(action)
            bouton.setObjectName("Primary")
            bouton.setCursor(Qt.PointingHandCursor)
            if raccourci:
                bouton.setToolTip(f"{action}  ({raccourci})")
            bouton.clicked.connect(self.action_clicked)
            colonne.addWidget(bouton, alignment=Qt.AlignCenter)

    def update_text(self, titre: str, detail: str) -> None:
        self.title_label.setText(titre)
        self.detail_label.setText(detail)


class StatusPill(QWidget):
    """Compteur d'un statut : une pastille de couleur, un nombre, un libelle.

    Sans boite ni bordure. Quatre compteurs encadres se disputaient
    l'attention, dont trois affichant zero ; ici tout s'eteint a zero et seul
    ce qui a une valeur ressort.
    """

    def __init__(self, status: Status, parent=None):
        super().__init__(parent)
        self._status = status
        self._value = 0

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(t.SPACE_2, 0, t.SPACE_2, 0)
        ligne.setSpacing(t.SPACE_1)

        self._dot = QLabel("●")
        self._text = QLabel()
        ligne.addWidget(self._dot)
        ligne.addWidget(self._text)

        self.set_value(0)

    @property
    def status(self) -> Status:
        return self._status

    def set_value(self, valeur: int) -> None:
        self._value = valeur
        actif = valeur > 0
        couleur = t.status_color(self._status)

        self._dot.setStyleSheet(
            f"color: {couleur if actif else t.BORDER_STRONG};"
            f"font-size: 9px; background: transparent;")
        self._text.setText(f"{valeur} {self._status.label.lower()}")
        self._text.setStyleSheet(theme.counter_style(couleur, actif))
        self.setToolTip(f"{valeur} {self._status.label.lower()}")

    def value(self) -> int:
        return self._value


class ReaderBadge(QLabel):
    """Nom d'un lecteur, dans sa couleur, pour relier colonne / onglet / log."""

    def __init__(self, nom: str, index: int, parent=None):
        super().__init__(nom, parent)
        self.setStyleSheet(theme.pill_style(t.reader_color(index)))


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
        self.field.addAction(icons.icon("mdi.magnify", t.TEXT_FAINT),
                             QLineEdit.LeadingPosition)
        self.field.textChanged.connect(self.query_changed)
        self.field.returnPressed.connect(self.next_match)

        self.counter = QLabel("")
        self.counter.setStyleSheet(theme.faint())
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
