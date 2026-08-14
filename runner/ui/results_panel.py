"""Panneau de droite : sortie pytest et logs, une vue par lecteur."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain.models import Reader
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.widgets import EmptyState


class ReaderViews(QWidget):
    """Une zone de texte par lecteur : une seule visible, ou toutes.

    Sert deux fois -- la sortie pytest et les logs -- avec un sens de
    comparaison different. Les sorties defilent, on les empile pour garder la
    largeur ; les logs se comparent ligne a ligne, on les met cote a cote.
    """

    reader_selected = pyqtSignal(int)

    def __init__(self, orientation=Qt.Vertical, sync_scroll: bool = False, parent=None):
        super().__init__(parent)
        self._sync = sync_scroll
        self._defile = False
        self._readers: tuple[Reader, ...] = ()

        self.views: list[QPlainTextEdit] = []
        self.headers: list[QLabel] = []

        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)

        self.compare = QPushButton()
        self.compare.setObjectName("Quiet")
        self.compare.setIcon(icons.icon("mdi.view-split-vertical", t.TEXT_MUTED))
        self.compare.setCheckable(True)
        self.compare.setToolTip("Compare every reader  (Ctrl+D)")
        self.compare.setVisible(False)
        self.compare.setFixedWidth(t.CONTROL_MD)
        self.compare.toggled.connect(lambda _: self._apply_layout())

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(t.SPACE_1)
        barre.addWidget(self.tabs, 1)
        barre.addWidget(self.compare)

        self.split = QSplitter(orientation)
        self.split.setChildrenCollapsible(False)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addLayout(barre)
        colonne.addWidget(self.split, 1)

        self._add_view()

    # ------------------------------------------------------------- structure

    def _add_view(self) -> QPlainTextEdit:
        vue = QPlainTextEdit()
        vue.setReadOnly(True)
        vue.setLineWrapMode(QPlainTextEdit.NoWrap)
        vue.document().setMaximumBlockCount(20000)

        entete = QLabel()
        entete.setVisible(False)
        entete.setStyleSheet(theme.faint())

        boite = QWidget()
        col = QVBoxLayout(boite)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_1)
        col.addWidget(entete)
        col.addWidget(vue, 1)

        self.views.append(vue)
        self.headers.append(entete)
        self.split.addWidget(boite)

        if self._sync:
            for sens in ("verticalScrollBar", "horizontalScrollBar"):
                getattr(vue, sens)().valueChanged.connect(
                    lambda valeur, s=sens, v=vue: self._propager(s, v, valeur))
        return vue

    def _propager(self, sens: str, source, valeur: int) -> None:
        """Fait suivre les autres vues : cote a cote, chacune ne montre qu'une
        fraction de la largeur, et sans cela comparer deux valeurs demanderait
        de faire defiler chaque colonne separement."""
        if self._defile:
            return
        self._defile = True
        try:
            for vue in self.views:
                if vue is not source:
                    barre = getattr(vue, sens)()
                    if barre.value() != valeur:
                        barre.setValue(valeur)
        finally:
            self._defile = False

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        self._readers = tuple(readers)
        multi = len(self._readers) > 1

        while len(self.views) < max(1, len(self._readers)):
            self._add_view()

        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for lecteur in (self._readers if multi else ()):
            position = self.tabs.addTab(lecteur.short_name)
            self.tabs.setTabToolTip(position, lecteur.name)
            from PyQt5.QtGui import QColor

            self.tabs.setTabTextColor(position, QColor(t.reader_color(lecteur.index)))
        self.tabs.blockSignals(False)

        self.tabs.setVisible(multi)
        self.compare.setVisible(multi)
        self._apply_layout()

    def _apply_layout(self) -> None:
        nombre = max(1, len(self._readers))
        comparer = self.compare.isChecked()
        courant = max(0, self.tabs.currentIndex())

        for position, vue in enumerate(self.views):
            boite = vue.parentWidget()
            visible = position < nombre and (comparer or nombre == 1 or position == courant)
            boite.setVisible(visible)
            self.headers[position].setVisible(visible and comparer and nombre > 1)

    def _on_tab(self, index: int) -> None:
        self._apply_layout()
        self.reader_selected.emit(index)

    def select_silently(self, index: int) -> None:
        """Change d'onglet sans reemettre : evite que deux panneaux qui se
        suivent ne se renvoient leur choix indefiniment."""
        if 0 <= index < self.tabs.count() and index != self.tabs.currentIndex():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
            self._apply_layout()

    def toggle_compare(self) -> None:
        if self.compare.isVisible():
            self.compare.setChecked(not self.compare.isChecked())

    # ---------------------------------------------------------------- contenu

    def append(self, index: int, texte: str) -> None:
        if 0 <= index < len(self.views):
            vue = self.views[index]
            vue.moveCursor(QTextCursor.End)
            vue.insertPlainText(texte)
            vue.moveCursor(QTextCursor.End)

    def set_text(self, index: int, texte: str, entete: str = "") -> None:
        if 0 <= index < len(self.views):
            self.views[index].setPlainText(texte)
            self.headers[index].setText(entete)

    def clear(self) -> None:
        for vue in self.views:
            vue.clear()
        for entete in self.headers:
            entete.clear()


class ResultsPanel(QWidget):
    """Sortie pytest et logs, avec un etat vide tant que rien n'a tourne."""

    reader_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_root: Path | None = None

        self.output = ReaderViews(Qt.Vertical)
        self.logs = ReaderViews(Qt.Horizontal, sync_scroll=True)

        # Les deux panneaux suivent le meme lecteur : lire le log de l'un en
        # regardant la sortie de l'autre n'a pas de sens.
        self.output.reader_selected.connect(self._on_reader, Qt.UniqueConnection)
        self.logs.reader_selected.connect(self._on_reader, Qt.UniqueConnection)

        self.empty = EmptyState(
            "mdi.console-line",
            "No run yet",
            "Select the tests you want on the left, then start a run. "
            "The output of every reader shows up here.",
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self.output, icons.icon("mdi.console", t.TEXT_MUTED), "Output")
        self.tabs.addTab(self.logs, icons.icon("mdi.file-document-outline", t.TEXT_MUTED), "Logs")

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.tabs)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self.stack)

    def _on_reader(self, index: int) -> None:
        self.output.select_silently(index)
        self.logs.select_silently(index)
        self.reader_selected.emit(index)

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        self.output.set_readers(readers)
        self.logs.set_readers(readers)

    def begin_run(self) -> None:
        self.output.clear()
        self.logs.clear()
        self.stack.setCurrentWidget(self.tabs)
        self.tabs.setCurrentWidget(self.output)

    def set_log_root(self, racine: Path | None) -> None:
        self._log_root = racine

    def show_logs_for(self, nodeid: str, readers: tuple[Reader, ...]) -> None:
        """Charge le .log de ce test, un par lecteur.

        Le conftest du workspace range ses logs par lecteur : le nom du lecteur
        est un DOSSIER du chemin. Comparer par composant et non par sous-chaine
        evite qu'un lecteur nomme `Reader` ne recupere le log de
        `Cosmo11Secured Reader`.
        """
        if not nodeid or self._log_root is None:
            return

        cibles = readers or (Reader("", 0),)
        for lecteur in cibles:
            chemin = _trouver_log(self._log_root, nodeid, lecteur.name)
            if chemin is None:
                self.logs.set_text(
                    lecteur.index,
                    f"No log found for this test"
                    + (f" on {lecteur.name}." if lecteur.name else "."),
                    lecteur.name or "",
                )
                continue
            try:
                contenu = chemin.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                contenu = f"Could not read {chemin}: {exc}"
            self.logs.set_text(lecteur.index, contenu,
                               lecteur.name or chemin.name)


def _cle(valeur: str) -> str:
    return "".join(c for c in str(valeur).lower() if c.isalnum())


def _trouver_log(racine: Path, nodeid: str, reader: str) -> Path | None:
    """Fichier .log de ce test pour ce lecteur, le plus recent d'abord."""
    if not racine.is_dir():
        return None

    fonction = nodeid.split("::")[-1]
    attendu = _cle(fonction)
    cle_lecteur = _cle(reader)

    meilleur: tuple[float, Path] | None = None
    examines = 0
    for fichier in racine.rglob("*.log"):
        examines += 1
        if examines > 4000:  # un historique de plusieurs mois ne doit pas figer l'UI
            break
        if cle_lecteur and not any(_cle(p) == cle_lecteur for p in fichier.parts):
            continue
        if attendu and attendu not in _cle(fichier.stem):
            continue
        try:
            date = fichier.stat().st_mtime
        except OSError:
            continue
        if meilleur is None or date > meilleur[0]:
            meilleur = (date, fichier)

    return meilleur[1] if meilleur else None
