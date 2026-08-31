"""Widgets reutilisables : etats vides, erreurs, pastilles, barre de recherche.

Aucun ne connait le domaine autrement que par des types de donnees : ils
recoivent du texte et des couleurs, ils n'appellent rien.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
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

    action_clicked = Signal()

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


class StatusPill(QPushButton):
    """Compteur d'un statut : icone + nombre, pose en legende a cote de
    l'anneau (`CompassRing`) -- un vrai QPushButton, comme Run/Stop/les
    lecteurs, pas un QWidget nu recompose a la main.

    Un QWidget nu ignore silencieusement `background-color`/`border` poses
    par une feuille de style sous le style natif Windows tant que
    `WA_StyledBackground` n'est pas force -- le bug deja vu une fois ce
    sprint sur le bandeau de stress-test, puis a nouveau sur la premiere
    version de ce badge. Un QPushButton, lui, peint son fond depuis sa
    feuille de style nativement : c'est le meme mecanisme que les boutons
    Run/Stop/Ghost et les lecteurs (`ReaderToggle`) juste a cote.

    A zero, la legende s'eteint (icone et texte en gris) : seul ce qui a une
    valeur ressort. Un rectangle discretement teinte marque le filtre actif --
    pas un aplat pilule complet, cette legende reste un texte compact, pas un
    badge autonome.

    C'est aussi un filtre : cliquer ne montre plus que les tests de ce statut.
    Le compteur et le filtre sont le meme geste -- on lit « 44 failed », on
    veut voir lesquels, on clique dessus.
    """

    filter_clicked = Signal(object)  # le Status de cette pastille

    def __init__(self, status: Status, parent=None):
        super().__init__(parent)
        self._status = status
        self._value = 0
        self._active = False

        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._sur_clic)
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

    def _sur_clic(self) -> None:
        if self._value:
            self.filter_clicked.emit(self._status)

    def _repaint(self) -> None:
        allume = self._value > 0
        couleur = t.status_color(self._status)
        libelle = self._status.label.lower()

        # La variante EVIDEE (contour + marque, sans aplat) partout : pleine,
        # la marque est une decoupe transparente dans le glyphe -- posee sur
        # un fond deja teinte, elle laissait ce fond transparaitre au milieu
        # de l'icone au lieu d'un trait net.
        glyphe = icons.STATUS_GLYPHS_GROUP.get(self._status, "mdi.circle-small")
        self.setIcon(icons.icon(glyphe, couleur if allume else t.BORDER_STRONG))
        self.setIconSize(QSize(20, 20))
        self.setText(f"{self._value}\n{self._status.label}")

        couleur_texte = couleur if allume else t.TEXT_FAINT
        fond = t.rgba(couleur, 0.22 if self._active else 0.10 if allume else 0.04)
        fond_survol = t.rgba(couleur, 0.16 if allume else 0.07)
        bordure = couleur if self._active else t.rgba(couleur, 0.32 if allume else 0.14)
        poids = "700" if self._active else "600" if allume else "400"

        base = (
            f"color: {couleur_texte}; border: 1px solid {bordure}; "
            f"border-radius: {t.RADIUS_MD}px; padding: {t.SPACE_1}px {t.SPACE_2}px;"
            f"font-size: {t.TEXT_SM + 2}px; font-weight: {poids};")
        # Le survol/l'appui doivent etre ecrits ICI : sans eux, le style natif
        # de Windows dessine SON propre relief au survol -- un rectangle
        # sombre par-dessus notre fond clair, illisible en theme clair.
        self.setStyleSheet(
            f"QPushButton {{ background-color: {fond}; {base} }}"
            f"QPushButton:hover {{ background-color: {fond_survol}; {base} }}"
            f"QPushButton:pressed {{ background-color: {fond_survol}; {base} }}")
        # Apres la feuille locale : le QSS global des QPushButton ne doit pas
        # ramener ces compteurs a la hauteur compacte des boutons ordinaires.
        self.setMinimumSize(72, 48)

        if not allume:
            self.setToolTip(f"No {libelle} test")
        elif self._active:
            self.setToolTip(f"Showing only {libelle} tests — click to show all")
        else:
            self.setToolTip(f"{self._value} {libelle} — click to show only these")


class CompassRing(QWidget):
    """Anneau proportionnel passed/failed/skipped/error : la largeur de
    chaque arc dit la part de ce statut dans le run, le taux de reussite
    global tient dans une seule bulle-info.

    Purement visuel -- l'interaction (filtrer, voir le detail par statut)
    reste sur les `StatusPill` en legende juste a cote, qui l'avaient deja
    et restent testes pour ca. Dupliquer le clic sur l'anneau (par angle)
    ajouterait une seconde facon de faire la meme chose sans rien montrer de
    plus.
    """

    ORDER = (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR)

    def __init__(self, parent=None, diameter: int = 45, thickness: int = 8):
        super().__init__(parent)
        self._diameter = diameter
        self._thickness = thickness
        self._counts = {statut: 0 for statut in self.ORDER}
        self.setFixedSize(diameter, diameter)
        self.restyle()

    def set_counts(self, counts) -> None:
        self._counts = {statut: counts.get(statut, 0) for statut in self.ORDER}
        total = sum(self._counts.values())
        passed = self._counts[Status.PASSED]
        taux = round(100 * passed / total) if total else 0
        self.setToolTip(
            f"{taux}% pass — " +
            "  ".join(f"{self._counts[s]} {s.label.lower()}" for s in self.ORDER))
        self.update()

    def restyle(self) -> None:
        """Rejoue le dessin : les couleurs par statut dependent du theme."""
        self.update()

    def paintEvent(self, event) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.Antialiasing)
        marge = self._thickness / 2
        zone = QRectF(marge, marge,
                      self._diameter - self._thickness, self._diameter - self._thickness)

        trait = QPen()
        trait.setWidth(self._thickness)
        trait.setCapStyle(Qt.FlatCap)

        total = sum(self._counts.values())
        if not total:
            trait.setColor(QColor(t.BORDER))
            peintre.setPen(trait)
            peintre.drawArc(zone, 0, 360 * 16)
            peintre.end()
            return

        # Depart a midi, sens horaire -- comme une jauge de chargement.
        depart = 90 * 16
        for statut in self.ORDER:
            valeur = self._counts[statut]
            if not valeur:
                continue
            portee = round(360 * 16 * valeur / total)
            trait.setColor(QColor(t.status_color(statut)))
            peintre.setPen(trait)
            peintre.drawArc(zone, depart, -portee)
            depart -= portee
        peintre.end()


class LiveDot(QWidget):
    """Point qui respire, a cote du texte de statut, tant qu'un run -- normal
    ou stress-test -- tourne EN CE MOMENT.

    Le texte seul ("Running…") se lit tout aussi bien immobile ; le pouls est
    ce qui attire l'oeil du coin en travaillant ailleurs dans la fenetre.
    Cache et arrete au repos : une animation qui tourne pour rien coute un
    signal Qt a chaque frame, sans rien a montrer.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(9, 9)
        self._couleur = t.ACCENT

        self._effet = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effet)

        self._anim = QPropertyAnimation(self._effet, b"opacity", self)
        self._anim.setDuration(1400)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setKeyValueAt(0.0, 1.0)
        self._anim.setKeyValueAt(0.5, 0.25)
        self._anim.setKeyValueAt(1.0, 1.0)
        self._anim.setLoopCount(-1)

        self.setVisible(False)

    def set_color(self, couleur: str) -> None:
        self._couleur = couleur
        self.update()

    def start(self) -> None:
        self.setVisible(True)
        self._anim.start()

    def stop(self) -> None:
        self._anim.stop()
        self._effet.setOpacity(1.0)
        self.setVisible(False)

    def paintEvent(self, event) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.Antialiasing)
        peintre.setPen(Qt.NoPen)
        peintre.setBrush(QColor(self._couleur))
        peintre.drawEllipse(self.rect())


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
        actif = status is not Status.PENDING

        icone = QLabel()
        icone.setPixmap(icons.status_icon(status).pixmap(14, 14))
        icone.setVisible(actif)

        # Nom d'objet + regle globale (voir QLabel#ReaderVerdict_* dans
        # theme.py), PAS `setStyleSheet()` sur ce label : assez imbrique dans
        # la mise en page (cette rangee, dans une carte, dans un panneau,
        # dans une fenetre), poser une feuille ici -- meme une seule regle de
        # couleur -- faisait dessiner a Qt un contour fantome autour de la
        # rangee entiere.
        texte = QLabel(status.label if actif else "NOT RUN")
        texte.setObjectName(f"ReaderVerdict_{status.value}")

        ligne.addWidget(icone)
        ligne.addWidget(texte)


class RecentRunsSparkline(QWidget):
    """Mini-tendance d'un test sur ses derniers runs : un trait par tentative,
    du plus ancien (a gauche) au plus recent (a droite).

    Juste assez pour repondre a une question sans ouvrir History : ce test
    est-il fiable, ou instable depuis peu ? Pas de chiffres, pas d'axes -- une
    barre verte ou rouge suffit a cette echelle.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._runs: tuple[bool, ...] = ()

        self._ligne = QHBoxLayout(self)
        self._ligne.setContentsMargins(0, 0, 0, 0)
        self._ligne.setSpacing(2)
        self.setFixedHeight(14)

    def set_runs(self, runs: list[bool]) -> None:
        self._runs = tuple(runs)
        self._repeindre()

    def _repeindre(self) -> None:
        while self._ligne.count():
            element = self._ligne.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._runs:
            self.setToolTip("No recorded history for this test yet.")
            return

        for ok in self._runs:
            barre = QFrame()
            barre.setFixedWidth(4)
            couleur = t.status_color(Status.PASSED if ok else Status.FAILED)
            barre.setStyleSheet(
                f"background-color: {couleur}; border-radius: 1px;")
            self._ligne.addWidget(barre)

        echecs = sum(1 for ok in self._runs if not ok)
        if echecs:
            self.setToolTip(
                f"Failed {echecs} of the last {len(self._runs)} runs.")
        else:
            self.setToolTip(f"Passed every one of the last {len(self._runs)} runs.")


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

    query_changed = Signal(str)
    next_match = Signal()
    previous_match = Signal()
    scope_changed = Signal(str)  # SCOPE_TESTS ou SCOPE_FAILURES

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QLineEdit

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
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(texte)

    @classmethod
    def show_error(cls, parent, titre: str, message: str, detail: str = "") -> None:
        cls(titre, message, detail, parent).exec()


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

    changed = Signal()

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
        from PySide6.QtGui import QColor, QPainter

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
        from PySide6.QtGui import QPainterPath

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
