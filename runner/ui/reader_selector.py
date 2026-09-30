"""Compact primary-reader editor using the workspace's test interpreter."""
import json

from PySide6.QtCore import QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QComboBox, QLineEdit, QStyle

from runner.domain import reader_discovery
from runner.domain.card_presence import CardPresence
from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t


class ReaderSelector(QComboBox):
    committed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setAccessibleName("Primary reader")
        self.setMinimumWidth(200)
        self.setMaximumWidth(440)
        self.setMinimumContentsLength(38)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.lineEdit().setPlaceholderText("Select or enter a reader…")
        self.activated.connect(lambda *_: self._commit())
        self.lineEdit().editingFinished.connect(self._commit)
        self._context = None
        self._value = ""
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._timed_out)
        self._expired = False

    def set_context(self, workspace, interpreter, value, known=()):
        context = (workspace, interpreter, value, tuple(known))
        if context == self._context:
            return
        self.stop_discovery()
        self._context = context
        self._value = value
        self.setCurrentText(value)
        self._set_names(known)
        if workspace and interpreter:
            QTimer.singleShot(0, self.discover)

    def _set_names(self, names):
        current = self.currentText() if self.hasFocus() or self.lineEdit().hasFocus() else self._value
        self.blockSignals(True)
        self.clear()
        self.addItems(list(dict.fromkeys([current, self._value, *names])))
        self.setCurrentText(current)
        self.blockSignals(False)

    def _commit(self):
        value = self.currentText().strip()
        if self.isEnabled() and value != self._value:
            self.committed.emit(value)

    def showPopup(self):
        # Long device names can use more space in the open list than in the header.
        width = max((self.fontMetrics().horizontalAdvance(self.itemText(i))
                     for i in range(self.count())), default=0) + 48
        self.view().setMinimumWidth(min(max(self.width(), width),
                                       self.screen().availableGeometry().width()))
        super().showPopup()

    def discover(self):
        if not self._context or self._process.state() != QProcess.NotRunning:
            return
        workspace, interpreter, *_ = self._context
        if not workspace or not interpreter:
            return
        env = QProcessEnvironment()
        for key, value in reader_discovery.discovery_environment().items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(workspace)
        self._expired = False
        self.setToolTip("Looking for HubReader devices… Manual entry remains available.")
        self._process.start(interpreter, ["-u", "-c", reader_discovery.PROBE])
        self._timeout.start(10000)

    def _finished(self, code, *_):
        self._timeout.stop()
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        errors = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        if self._expired:
            return
        try:
            line = next(line for line in output.splitlines() if line.startswith("HUBREADERS_JSON:"))
            names = json.loads(line.split(":", 1)[1])
            if code or not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise ValueError()
        except (StopIteration, ValueError):
            message = errors.strip().splitlines()[-1] if errors.strip() else "No valid response from HubReader."
            self.setToolTip(message + " Manual entry remains available.")
            return
        names = tuple(dict.fromkeys(name.strip() for name in names if name.strip()))
        self._set_names(names)
        self.setToolTip(f"{len(names)} available HubReader devices. Select or enter the primary reader.")

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self.setToolTip("Could not start the test Python interpreter. Manual entry remains available.")

    def _timed_out(self):
        self._expired = True
        self._process.kill()
        self.setToolTip("HubReader discovery timed out. Manual entry remains available.")

    def stop_discovery(self):
        self._timeout.stop()
        self._expired = True
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)


class ReaderAtrField(QLineEdit):
    """ATR de la carte presente dans le lecteur principal, sous son selecteur.

    Lu par PROBE_ATR dans l'interpreteur des tests, comme la liste des
    lecteurs : jamais dans le processus de l'interface, qui n'a pas forcement
    la meme architecture que les DLL du lecteur -- et qui ne l'attend donc
    jamais non plus.

    Relu seulement quand l'etat de la carte change : toutes les
    `INTERVALLE_MS`, on demande a Windows (`CardPresence`, PC/SC) si une carte
    est la, sans ouvrir le lecteur ni toucher a la carte, et l'ATR n'est relu
    que si elle est arrivee, partie ou a ete changee. Le bouton de la fin du
    champ relit a la demande. Jamais de lecture pendant un run, ni pour un
    champ qu'on ne voit pas.
    """

    NO_CARD = "No card in reader"
    INTERVALLE_MS = 1000
    # Pastille d'etat devant le texte : verte avec une carte, rouge sans.
    # `PADDING` reprend le retrait du texte de la liste au-dessus (feuille de
    # style), pour que pastille et nom du lecteur partent du meme bord.
    PADDING = t.SPACE_2 + 1
    PASTILLE = 6
    ECART = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReaderAtr")
        self.setReadOnly(True)
        self.setAccessibleName("Card ATR")
        self.setPlaceholderText("ATR")
        self.setTextMargins(self.PASTILLE + self.ECART, 0, 0, 0)
        self._refresh_action = self.addAction(
            icons.icon("mdi.refresh", t.TEXT_MUTED), QLineEdit.TrailingPosition)
        self._refresh_action.setToolTip("Read the card again")
        self._refresh_action.triggered.connect(lambda: self.refresh())
        # Remplacable dans les tests ; rend None quand on ne peut pas savoir.
        self._presence = CardPresence()
        self.presence = self._presence.check
        self._signature = None
        self._context = None
        self._busy = False
        self._stale = False
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._timed_out)
        self._expired = False
        self.state = ""
        self._ticker = QTimer(self)
        self._ticker.setInterval(self.INTERVALLE_MS)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start()

    def restyle(self):
        # Appele par le balayage de `MainWindow._restyle()` a chaque bascule.
        self._refresh_action.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def release(self):
        self.stop()
        self._presence.close()

    def _check_presence(self):
        try:
            return self.presence(self._context[2]) if self._context else None
        except Exception:
            return None

    def set_context(self, workspace, interpreter, reader, busy=False):
        context = (workspace, interpreter, (reader or "").strip())
        was_busy, self._busy = self._busy, busy
        if busy:
            self.stop()
            self._stale = True
            return
        if context != self._context:
            # Une lecture encore en vol concerne l'ancien lecteur : son
            # resultat ne doit pas s'afficher pour le nouveau.
            self.stop()
            self._context = context
            self._signature = self._check_presence()
            self.refresh()
        elif was_busy or self._stale:
            # Meme lecteur qu'avant le run : son ATR reste affiche jusqu'au
            # nouveau resultat, sans passer par "Reading card...".
            self._signature = self._check_presence()
            self.refresh(quiet=True)

    def _tick(self):
        """Surveille la presence de la carte ; ne relit l'ATR que si elle a
        change. Jamais pendant un run, jamais pour un champ qu'on ne voit pas."""
        if self._busy or not self._context or not self._context[2]:
            return
        if not self.isVisible() or self.window().isMinimized():
            return
        signature = self._check_presence()
        if signature is None or signature == self._signature:
            return
        self._signature = signature
        # PyHubReader absent : relire ne donnerait rien de plus. Le bouton,
        # un changement de lecteur ou la fin d'un run retentent quand meme.
        if self.state == reader_discovery.ATR_UNAVAILABLE:
            return
        self.refresh(quiet=True)

    def refresh(self, quiet=False):
        self._stale = False
        if not self._context or self._busy:
            return
        workspace, interpreter, reader = self._context
        if not reader:
            self._show("", "", "No reader selected.")
            return
        if not workspace or not interpreter:
            return
        # Une relecture automatique garde ce qui est affiche jusqu'au nouveau
        # resultat : "Reading card..." toutes les 3 secondes, ce serait un
        # clignotement, pas une information.
        if not quiet or not self.state:
            self._show("reading", "Reading card…", f"Reading the card in {reader}…")
        if self._process.state() != QProcess.NotRunning:
            # Une lecture tuee n'est pas encore tout a fait terminee : on
            # relance des qu'elle l'est (`_finished`).
            self._stale = True
            return
        env = QProcessEnvironment()
        for key, value in reader_discovery.discovery_environment().items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(workspace)
        self._expired = False
        self._process.start(interpreter, ["-u", "-c", reader_discovery.PROBE_ATR, reader])
        self._timeout.start(10000)

    def stop(self):
        # Tuee net, sans l'attendre : attendre figerait l'interface au moment
        # precis ou un run demarre. Son resultat tardif est ignore (`_expired`).
        self._timeout.stop()
        self._expired = True
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def _finished(self, *_):
        self._timeout.stop()
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        errors = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        if self._expired:
            if self._stale and not self._busy:
                QTimer.singleShot(0, self.refresh)
            return
        state, atr, detail = reader_discovery.parse_atr_output(output, errors)
        if self._stale and not self._busy:
            # L'etat de la carte a encore change pendant cette lecture.
            QTimer.singleShot(0, lambda: self.refresh(quiet=True))
        if state == reader_discovery.ATR_OK:
            self._show(state, atr, f"ATR of the card in {self._context[2]}:\n{atr}")
        elif state == reader_discovery.ATR_NO_CARD:
            self._show(state, self.NO_CARD, detail or "No card could be read in this reader.")
        else:
            self._show(state, "ATR unavailable", detail)

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable",
                       "Could not start the test Python interpreter.")

    def _timed_out(self):
        self._expired = True
        self._process.kill()
        self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable", "Reading the ATR timed out.")

    def _show(self, state, text, tooltip):
        # La relecture automatique rend le plus souvent la meme chose : ne rien
        # repeindre dans ce cas.
        if (state, text, tooltip) == (self.state, self.text(), self.toolTip()):
            return
        self.state = state
        self.setText(text)
        self.setCursorPosition(0)
        self.setToolTip(tooltip)
        # L'etat pilote la couleur depuis la feuille de style : elle suit ainsi
        # la bascule de theme sans rien repeindre a la main.
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        # Un ATR se lit en entier ou pas du tout. Le champ demande d'abord la
        # place de l'ATR, jusqu'a la largeur maximale du selecteur ; quand il ne
        # l'obtient pas (ATR tres long, fenetre etroite), le texte retrecit.
        # Largeur souhaitee, pas imposee : une largeur minimale ferait deborder
        # toute la barre sur une fenetre etroite.
        self.updateGeometry()
        self._fit()

    def sizeHint(self):
        base = super().sizeHint()
        if self.state != reader_discovery.ATR_OK:
            return base
        voulu = self._text_width(t.TEXT_SM) + self._margin()
        return QSize(max(base.width(), min(voulu, self.LARGEUR_MAX)), base.height())

    LARGEUR_MAX = 440
    TAILLE_MIN = 8

    def _margin(self):
        bouton = self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize) + 8
        return self.PADDING + self.PASTILLE + self.ECART + bouton + 12

    def dot_color(self):
        """Couleur de la pastille, ou None s'il n'y en a pas (lecture en cours,
        PyHubReader indisponible). Lue a chaque dessin : elle suit le theme."""
        if self.state == reader_discovery.ATR_OK:
            return QColor(t.status_color(Status.PASSED))
        if self.state == reader_discovery.ATR_NO_CARD:
            couleur = QColor(t.status_color(Status.FAILED))
            couleur.setAlphaF(0.85)
            return couleur
        return None

    def paintEvent(self, event):
        super().paintEvent(event)
        couleur = self.dot_color()
        if couleur is None:
            return
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.Antialiasing)
        peintre.setPen(Qt.NoPen)
        peintre.setBrush(couleur)
        haut = (self.height() - self.PASTILLE) / 2
        peintre.drawEllipse(QRectF(self.PADDING, haut, self.PASTILLE, self.PASTILLE))
        peintre.end()

    def _text_width(self, taille):
        police = QFont(self.font())
        police.setPixelSize(taille)
        return QFontMetrics(police).horizontalAdvance(self.text())

    def _fit(self):
        taille = t.TEXT_SM
        if self.state == reader_discovery.ATR_OK:
            place = self.width() - self._margin()
            while taille > self.TAILLE_MIN and self._text_width(taille) > place:
                taille -= 1
        # Une feuille propre au widget passe devant celle de la fenetre, qui
        # fixe sinon la taille pour tout le monde ; elle ne porte que ca.
        feuille = "" if taille == t.TEXT_SM else f"font-size: {taille}px;"
        if feuille != self.styleSheet():
            self.setStyleSheet(feuille)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()
