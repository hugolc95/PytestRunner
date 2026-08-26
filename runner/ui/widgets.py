"""Widgets reutilisables : etats vides, erreurs, pastilles, barre de recherche.

Aucun ne connait le domaine autrement que par des types de donnees : ils
recoivent du texte et des couleurs, ils n'appellent rien.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHeaderView,
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


class ReaderHeaderView(QHeaderView):
    """En-tete d'arbre qui conserve la couleur propre a chaque lecteur.

    La feuille de style de Qt impose normalement une seule couleur a toutes les
    sections et masque donc le ``ForegroundRole`` fourni par le modele. Le
    texte est peint ici, tandis que le modele reste la source de la couleur.
    """

    def paintSection(self, painter, rect, logical_index) -> None:
        if not rect.isValid():
            return

        painter.save()
        painter.fillRect(rect, QColor(t.BG_APP))
        painter.setPen(QColor(t.BORDER))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        modele = self.model()
        texte = modele.headerData(logical_index, self.orientation(), Qt.DisplayRole)
        couleur = modele.headerData(
            logical_index, self.orientation(), Qt.ForegroundRole)
        if not isinstance(couleur, QColor) or not couleur.isValid():
            couleur = QColor(t.TEXT_MUTED)

        fonte = QFont(self.font())
        fonte.setPixelSize(t.TEXT_XS)
        fonte.setWeight(QFont.DemiBold)
        painter.setFont(fonte)
        painter.setPen(couleur)

        alignement = modele.headerData(
            logical_index, self.orientation(), Qt.TextAlignmentRole)
        if alignement is None:
            alignement = int(Qt.AlignLeft | Qt.AlignVCenter)
        else:
            alignement = int(alignement) | int(Qt.AlignVCenter)

        zone = rect.adjusted(t.SPACE_2, 0, -t.SPACE_2, 0)
        elide = QFontMetrics(fonte).elidedText(
            str(texte or ""), Qt.ElideRight, max(0, zone.width()))
        painter.drawText(zone, alignement, elide)
        painter.restore()

    def restyle(self) -> None:
        self.viewport().update()


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


SCOPE_TESTS = "tests"
SCOPE_FAILURES = "failures"


class SearchBar(QWidget):
    """Champ de recherche avec compteur et navigation entre correspondances.

    Une recherche, pas un filtre : masquer ce qui ne correspond pas fait perdre
    le contexte du test trouve (son fichier, sa classe, ses voisins).

    Deux portees : par NOM (les tests eux-memes) ou dans les TRACES d'echec du
    dernier run. Le meme champ, le meme compteur, la meme navigation -- seul
    ce qui est compare change, d'un cote a l'autre du selecteur.
    """

    query_changed = pyqtSignal(str)
    next_match = pyqtSignal()
    previous_match = pyqtSignal()
    scope_changed = pyqtSignal(str)  # SCOPE_TESTS ou SCOPE_FAILURES

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QButtonGroup, QLineEdit

        self._last_emitted = ""
        self._scope = SCOPE_TESTS
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(120)
        self._typing_timer.timeout.connect(self._emit_query)

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
        self.field.textChanged.connect(self._queue_query)
        self.field.returnPressed.connect(self._submit)

        self.counter = QLabel("")
        self.counter.setObjectName("Faint")
        self.counter.setMinimumWidth(52)
        self.counter.setAlignment(Qt.AlignCenter)

        self.prev_button = self._nav("mdi.chevron-up", "Previous match (Shift+Enter)",
                                     self.previous_match)
        self.next_button = self._nav("mdi.chevron-down", "Next match (Enter)",
                                     self.next_match)

        # Deux icones a bascule, PAS une rangee segmentee sous le champ : une
        # deuxieme rangee poussait tout le reste (l'arbre) vers le bas des
        # qu'on ouvrait la fenetre. Le fond allume dit lequel est actif,
        # comme le bouton de comparaison des consoles juste a cote ailleurs
        # dans l'appli -- pas besoin d'un libelle en toutes lettres.
        self._scope_group = QButtonGroup(self)
        self._scope_group.setExclusive(True)
        self.tests_button = self._nav("mdi.magnify", "Search by test name",
                                      lambda: self._set_scope(SCOPE_TESTS))
        self.tests_button.setCheckable(True)
        self.tests_button.setChecked(True)
        self.tests_button.setEnabled(True)

        self.failures_button = self._nav(
            "mdi.alert-circle-outline",
            "Search inside the failure output of the last run",
            lambda: self._set_scope(SCOPE_FAILURES))
        self.failures_button.setCheckable(True)
        self.failures_button.setEnabled(True)

        self._scope_group.addButton(self.tests_button)
        self._scope_group.addButton(self.failures_button)

        ligne.addWidget(self.field, 1)
        ligne.addWidget(self.counter)
        ligne.addWidget(self.prev_button)
        ligne.addWidget(self.next_button)
        ligne.addWidget(self.tests_button)
        ligne.addWidget(self.failures_button)

    @property
    def scope(self) -> str:
        return self._scope

    def _set_scope(self, scope: str) -> None:
        if scope == self._scope:
            return
        self._scope = scope
        self.field.setPlaceholderText(
            "Find a test…" if scope == SCOPE_TESTS
            else "Search in failure output…")
        # Une recherche par nom n'a aucun sens rejouee dans les traces, et
        # inversement : mieux vaut repartir d'un champ vide que d'un resultat
        # qui pretend repondre a la meme question.
        self.field.clear()
        self.scope_changed.emit(scope)

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
        self.tests_button.setIcon(icons.icon("mdi.magnify", t.TEXT_MUTED))
        self.failures_button.setIcon(icons.icon("mdi.alert-circle-outline", t.TEXT_MUTED))

    def _queue_query(self, texte: str) -> None:
        """Regroupe une rafale de frappes en une seule recherche.

        Une recherche change la selection de l'arbre et peut charger les logs
        du premier resultat. La rejouer apres chaque lettre rendait donc la
        saisie saccadee sur une grande suite. Une suppression reste immediate
        pour rendre tout de suite l'arbre a son etat normal.
        """
        if not texte.strip():
            self._typing_timer.stop()
            self.set_matches(0, 0)
            self._emit_query()
            return

        self.counter.setText("…")
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self._typing_timer.start()

    def _emit_query(self) -> None:
        texte = self.field.text()
        if texte == self._last_emitted:
            return
        self._last_emitted = texte
        self.query_changed.emit(texte)

    def _submit(self) -> None:
        # Entree ne doit jamais naviguer dans les resultats de la requete
        # precedente si le delai de frappe n'est pas encore ecoule. Dans ce
        # cas elle valide la recherche et reste sur le PREMIER resultat ; les
        # appuis suivants seulement passent au suivant.
        en_attente = (self._typing_timer.isActive()
                      or self.field.text() != self._last_emitted)
        self._typing_timer.stop()
        self._emit_query()
        if not en_attente:
            self.next_match.emit()

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


class ReaderToggle(QPushButton):
    """Un lecteur, dans sa couleur, qu'on inclut ou non dans le prochain run."""

    def __init__(self, reader, parent=None):
        super().__init__(reader.short_name, parent)
        self._index = reader.index
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(reader.name)
        self.toggled.connect(lambda _: self.restyle())
        self.restyle()

    def reader_index(self) -> int:
        return self._index

    def restyle(self) -> None:
        # Eteinte plutot qu'absente : un lecteur decoche garde sa place et sa
        # couleur en creux, donc on voit d'un coup d'oeil ce qu'on a exclu.
        self.setStyleSheet(theme.pill_style(t.reader_color(self._index),
                                            actif=self.isChecked()))


class ReaderBar(QWidget):
    """Les lecteurs du workspace, et lesquels le prochain run va parcourir.

    Un seul lecteur ne se choisit pas : la barre reste alors cachee. Avec
    plusieurs, tout tester est le cas courant -- tout est coche au depart, et
    on decoche pour restreindre.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggles: list[ReaderToggle] = []

        self._ligne = QHBoxLayout(self)
        self._ligne.setContentsMargins(0, 0, 0, 0)
        self._ligne.setSpacing(t.SPACE_2)

        self._label = QLabel("Run on")
        self._label.setObjectName("Faint")
        self._ligne.addWidget(self._label)

        self._mode = QLabel("")
        self._mode.setObjectName("Faint")

        self._ligne.addStretch(1)
        self._ligne.addWidget(self._mode)
        self.setVisible(False)

    def set_readers(self, readers, sequential: bool = False) -> None:
        for bouton in self._toggles:
            self._ligne.removeWidget(bouton)
            bouton.deleteLater()
        self._toggles.clear()

        for position, lecteur in enumerate(readers):
            bouton = ReaderToggle(lecteur)
            bouton.toggled.connect(self.changed)
            # Apres le libelle, avant l'espace elastique.
            self._ligne.insertWidget(1 + position, bouton)
            self._toggles.append(bouton)

        # Le mode vient du workspace et ne se change pas d'ici : c'est une
        # contrainte du materiel ou du code de test, pas une preference. Il est
        # affiche parce qu'il explique la duree du run.
        self._mode.setText("one reader at a time" if sequential else "")
        self._mode.setVisible(sequential)
        self.setVisible(len(readers) > 1)

    def selected_indexes(self) -> tuple[int, ...]:
        return tuple(b.reader_index() for b in self._toggles if b.isChecked())

    def select_names(self, readers, names) -> None:
        """Coche exactement les lecteurs nommes par un run historique."""
        retenus = {str(name) for name in names}
        by_index = {reader.index: reader.name for reader in readers}
        for bouton in self._toggles:
            bouton.setChecked(by_index.get(bouton.reader_index()) in retenus)

    # Pas de `restyle()` ici : le balayage de la fenetre atteint les boutons
    # directement, ils portent le leur. En ajouter un a ce niveau ne ferait que
    # les repeindre deux fois.


class StatusRibbon(QWidget):
    """Repartition des statuts d'un lot de tests, en une barre.

    Douze nombres alignes demandent d'etre lus et compares ; une barre se voit.
    C'est la seule chose qu'on veut savoir en cliquant un dossier : est-ce que
    c'est majoritairement vert, et combien de rouge.

    Les segments gardent l'ordre des statuts, toujours le meme : le rouge est
    au meme endroit d'une barre a l'autre, donc deux lecteurs se comparent d'un
    coup d'oeil sans lire les nombres.
    """

    ORDRE = (Status.PASSED, Status.FAILED, Status.ERROR, Status.SKIPPED,
             Status.RUNNING, Status.PENDING)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict = {}
        self.setFixedHeight(t.SPACE_2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_counts(self, counts: dict) -> None:
        self._counts = {s: n for s, n in counts.items() if n > 0}
        self.setToolTip(" · ".join(
            f"{self._counts[s]} {s.name.lower()}"
            for s in self.ORDRE if s in self._counts))
        self.update()

    def restyle(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        from PyQt5.QtGui import QColor, QPainter

        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.Antialiasing)
        largeur, hauteur = self.width(), self.height()
        rayon = hauteur / 2

        # Le fond porte la barre quand rien n'a encore tourne : sans lui, un
        # lot entierement en attente ne dessinerait rien du tout et se lirait
        # comme un widget casse.
        peintre.setPen(Qt.NoPen)
        peintre.setBrush(QColor(t.BG_RAISED))
        peintre.drawRoundedRect(0, 0, largeur, hauteur, rayon, rayon)

        total = sum(self._counts.values())
        if not total:
            return

        # Les arrondis des extremites sont obtenus en dessinant dans la forme
        # du fond : chaque segment reste rectangulaire, seul l'ensemble est
        # arrondi. Arrondir chaque segment creerait des encoches entre eux.
        from PyQt5.QtGui import QPainterPath

        forme = QPainterPath()
        forme.addRoundedRect(0, 0, largeur, hauteur, rayon, rayon)
        peintre.setClipPath(forme)

        depart = 0.0
        for statut in self.ORDRE:
            nombre = self._counts.get(statut, 0)
            if not nombre:
                continue
            part = largeur * nombre / total
            peintre.setBrush(QColor(t.status_color(statut)))
            # Un demi-pixel de recouvrement : sans lui, l'arrondi des bornes
            # laisse une raie du fond entre deux segments voisins.
            peintre.drawRect(int(depart), 0, int(part + 1), hauteur)
            depart += part


def separator() -> QFrame:
    """Trait de 1 px entre deux zones."""
    trait = QFrame()
    trait.setObjectName("Separator")
    trait.setFrameShape(QFrame.HLine)
    trait.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return trait


class StressBanner(QWidget):
    """Pastille compacte, dans l'espace vide a droite de la barre Run, pendant
    et apres "Run until it fails" / "Run N times".

    Une teinte par etat (bleu en cours, rouge sur un echec, neutre une fois
    fini) : c'est ce qu'on regarde du coin de l'oeil en continuant a
    travailler ailleurs. Le texte reste court expres -- le detail complet
    (quel test, quel mode) est dans l'infobulle, pas dans la pastille.

    Un `QWidget` nu n'applique PAS `background-color` depuis sa feuille de
    style sur tous les styles Qt (silencieusement ignore sous le style natif
    Windows, alors que ca passait par chance ailleurs) : `WA_StyledBackground`
    est ce qui le force a se peindre depuis le CSS plutot que depuis son
    style natif.
    """

    stop_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(t.CONTROL_SM)

        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(t.SPACE_3, 0, t.SPACE_1, 0)
        ligne.setSpacing(t.SPACE_1)

        self._icone = QLabel()
        self._icone.setStyleSheet("background: transparent;")
        self._texte = QLabel()
        self._texte.setStyleSheet(
            f"background: transparent; font-size: {t.TEXT_XS}px; font-weight: 600;")

        self.stop_button = QPushButton()
        self.stop_button.setObjectName("IconSm")
        self.stop_button.setIcon(icons.icon("mdi.stop"))
        self.stop_button.setToolTip("Stop this series")
        self.stop_button.clicked.connect(self.stop_clicked)

        self.dismiss_button = QPushButton()
        self.dismiss_button.setObjectName("IconSm")
        self.dismiss_button.setIcon(icons.icon("mdi.close"))
        self.dismiss_button.setToolTip("Dismiss")
        self.dismiss_button.clicked.connect(self._fermer)
        self.dismiss_button.setVisible(False)

        ligne.addWidget(self._icone)
        ligne.addWidget(self._texte)
        ligne.addWidget(self.stop_button)
        ligne.addWidget(self.dismiss_button)

    def _fermer(self) -> None:
        self.setVisible(False)
        self.dismissed.emit()

    def _peindre(self, glyphe: str, couleur: str, fond: str) -> None:
        self._icone.setPixmap(icons.icon(glyphe, couleur).pixmap(14, 14))
        if fond:
            self.setStyleSheet(
                f"background-color: {fond}; border-radius: {t.RADIUS_PILL}px;")
        else:
            self.setStyleSheet(
                f"background-color: {t.BG_RAISED}; border: 1px solid "
                f"{t.BORDER_STRONG}; border-radius: {t.RADIUS_PILL}px;")

    def _afficher(self, texte: str, detail: str) -> None:
        self._texte.setText(texte)
        self.setToolTip(detail or texte)
        self.setVisible(True)

    def show_running(self, texte: str, detail: str = "") -> None:
        self._afficher(texte, detail)
        self._peindre("mdi.repeat", t.status_color(Status.RUNNING),
                      t.rgba(t.status_color(Status.RUNNING), 0.16))
        self.stop_button.setVisible(True)
        self.dismiss_button.setVisible(False)

    def show_failed(self, texte: str, detail: str = "") -> None:
        self._afficher(texte, detail)
        self._peindre("mdi.alert", t.status_color(Status.FAILED),
                      t.rgba(t.status_color(Status.FAILED), 0.16))
        self.stop_button.setVisible(False)
        self.dismiss_button.setVisible(True)

    def show_done(self, texte: str, detail: str = "") -> None:
        self._afficher(texte, detail)
        self._peindre("mdi.check-circle-outline", t.TEXT_MUTED, "")
        self.stop_button.setVisible(False)
        self.dismiss_button.setVisible(True)
