"""Compact primary-reader editor using the workspace's test interpreter."""
import json

from PySide6.QtCore import QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QComboBox, QLineEdit, QStyle

from runner.domain import reader_discovery
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

    Suivi par PROBE_MONITOR, un processus unique qui tourne dans
    l'interpreteur des tests -- PyHubReader n'est utilisable que la, et
    l'interface ne l'attend jamais. Il demande `IsCardPresent()` toutes les
    `INTERVALLE_S` secondes et ne lit l'ATR qu'a l'arrivee d'une carte ; un
    retrait s'affiche sans rien lire. Le bouton de la fin du champ relance la
    surveillance, donc une lecture. Aucun appel au lecteur pendant un run : le
    processus est arrete, puis relance a la fin.
    """

    NO_CARD = "No card in reader"
    INTERVALLE_S = 2.0
    DEMARRAGE_MS = 10000
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
        self._context = None
        self._busy = False
        # Relance en attente de la fin d'un processus qu'on vient de tuer :
        # None, ou le `quiet` de la relance.
        self._pending = None
        self._buffer = b""
        self._got_event = False
        self._expired = True
        self.state = ""
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_events)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._error)
        self._startup = QTimer(self)
        self._startup.setSingleShot(True)
        self._startup.timeout.connect(self._timed_out)

    def restyle(self):
        # Appele par le balayage de `MainWindow._restyle()` a chaque bascule.
        self._refresh_action.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def release(self):
        self._pending = None
        self.stop()

    def set_context(self, workspace, interpreter, reader, busy=False):
        context = (workspace, interpreter, (reader or "").strip())
        was_busy, self._busy = self._busy, busy
        if busy:
            self._pending = None
            self.stop()
            return
        if context != self._context:
            self._context = context
            self.refresh()
        elif was_busy:
            # Meme lecteur qu'avant le run : son ATR reste affiche jusqu'au
            # nouveau resultat, sans passer par "Reading card...". La carte a
            # pu changer pendant le run : la surveillance repart d'une lecture.
            self.refresh(quiet=True)

    def refresh(self, quiet=False):
        """(Re)lance la surveillance ; sa premiere mesure lit la carte."""
        if not self._context or self._busy:
            return
        workspace, interpreter, reader = self._context
        if not reader:
            self.stop()
            self._show("", "", "No reader selected.")
            return
        if not workspace or not interpreter:
            return
        if not quiet or not self.state:
            self._show("reading", "Reading card…", f"Reading the card in {reader}…")
        self.stop()
        if self._process.state() != QProcess.NotRunning:
            # Tue, mais pas encore tout a fait termine : on relance des qu'il
            # l'est (`_finished`).
            self._pending = quiet
            return
        self._start()

    def _start(self):
        workspace, interpreter, reader = self._context
        env = QProcessEnvironment()
        for key, value in reader_discovery.discovery_environment().items():
            env.insert(key, value)
        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(workspace)
        self._expired = False
        self._buffer = b""
        self._got_event = False
        self._process.start(interpreter, ["-u", "-c", reader_discovery.PROBE_MONITOR,
                                          reader, str(self.INTERVALLE_S)])
        self._startup.start(self.DEMARRAGE_MS)

    def stop(self):
        # Tue net, sans l'attendre : attendre figerait l'interface au moment
        # precis ou un run demarre. Sa sortie tardive est ignoree (`_expired`).
        self._startup.stop()
        self._expired = True
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def _read_events(self):
        data = bytes(self._process.readAllStandardOutput())
        if self._expired:
            return
        self._buffer += data
        *lignes, self._buffer = self._buffer.split(b"\n")
        for ligne in lignes:
            self._apply_line(ligne)

    def _apply_line(self, ligne: bytes):
        event = reader_discovery.parse_atr_line(ligne.decode("utf-8", "replace").strip())
        if event is None:
            return
        state, atr, detail, note = event
        self._got_event = True
        self._startup.stop()
        reader = self._context[2] if self._context else ""
        if state == reader_discovery.ATR_OK:
            text, tooltip = atr, f"ATR of the card in {reader}:\n{atr}"
        elif state == reader_discovery.ATR_NO_CARD:
            text, tooltip = self.NO_CARD, detail or "No card could be read in this reader."
        else:
            text, tooltip = "ATR unavailable", detail
        self._show(state, text, f"{tooltip}\n\n{note}" if note else tooltip)

    def _finished(self, *_):
        self._startup.stop()
        reste = bytes(self._process.readAllStandardOutput())
        errors = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        if not self._expired:
            # Arret de lui-meme : PyHubReader indisponible, IsCardPresent en
            # echec, ou plantage. Pas de relance automatique -- le bouton reste.
            for ligne in (self._buffer + reste).split(b"\n"):
                self._apply_line(ligne)
            self._buffer = b""
            self._expired = True
            if not self._got_event:
                detail = (errors.strip().splitlines()[-1] if errors.strip()
                          else "No valid response from HubReader.")
                self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable", detail)
        pending, self._pending = self._pending, None
        if pending is not None and not self._busy:
            QTimer.singleShot(0, lambda: self.refresh(quiet=pending))

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._startup.stop()
            self._expired = True
            self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable",
                       "Could not start the test Python interpreter.")

    def _timed_out(self):
        self.stop()
        self._show(reader_discovery.ATR_UNAVAILABLE, "ATR unavailable",
                   "Reading the ATR timed out.")

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
        bouton = (self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize) + 8
                  if self._refresh_action.isVisible() else 0)
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
        taille = getattr(self, "maximum_text_size", t.TEXT_SM)
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
