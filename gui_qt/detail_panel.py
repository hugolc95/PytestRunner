"""Panneau de droite : Console, Source et Log.

Cliquer sur un test dans l'arbre affiche son code source et son fichier de log
sans quitter l'application. La console reste l'onglet par defaut et conserve
exactement son comportement : `panel.console` est le QTextEdit historique.

Le log est retrouve par le meme chemin que le mode "Ouvrir le log" : le conftest
du workspace ecrit un fichier par test dans le dossier indique par la cle
`log_directory` de son config.yml, et un manifeste fait le lien nodeid -> fichier.
"""

from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QLabel, QPlainTextEdit, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from gui_qt.config.config_loader import find_test_log, resolve_log_root
from gui_qt.styles import styles
from gui_qt.styles.styles import console_style

CONSOLE_TAB = 0
SOURCE_TAB = 1
LOG_TAB = 2

# Taille au-dela de laquelle on n'affiche que le debut du fichier : ouvrir un log
# de plusieurs dizaines de Mo figerait l'interface.
MAX_DISPLAY_BYTES = 2_000_000


def function_name_from_nodeid(nodeid: str) -> str | None:
    """Nom de la fonction de test, sans la classe ni le parametre.

    'a/test_x.py::TestC::test_f[cas]' -> 'test_f'
    """
    if "::" not in nodeid:
        return None
    last = nodeid.split("::")[-1]
    return last.split("[", 1)[0].strip() or None


def read_text_file(path: Path) -> tuple[str, str | None]:
    """Contenu du fichier et message d'avertissement eventuel.

    Les logs de test peuvent contenir des octets non decodables (traces APDU
    brutes) : on remplace plutot que d'echouer.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "", f"Lecture impossible : {exc}"

    warning = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > MAX_DISPLAY_BYTES:
                content = f.read(MAX_DISPLAY_BYTES)
                warning = (
                    f"Fichier tronque a {MAX_DISPLAY_BYTES // 1_000_000} Mo "
                    f"(taille reelle : {size / 1_000_000:.1f} Mo)."
                )
            else:
                content = f.read()
    except OSError as exc:
        return "", f"Lecture impossible : {exc}"

    return content, warning


class DetailPanel(QWidget):
    """Onglets Console / Source / Log affiches a droite de l'arbre."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.workspace: str | None = None
        self._current_source: Path | None = None

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(12000)

        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.source_header = QLabel("Cliquez un test dans l'arbre pour voir son code source.")
        self.log_header = QLabel("Cliquez un test dans l'arbre pour voir son log.")
        for header in (self.source_header, self.log_header):
            header.setWordWrap(True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.console, "Console")
        self.tabs.addTab(self._wrap(self.source_header, self.source_view), "Source")
        self.tabs.addTab(self._wrap(self.log_header, self.log_view), "Log")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        self.restyle()

    @staticmethod
    def _wrap(header: QLabel, view: QPlainTextEdit) -> QWidget:
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(6, 6, 6, 6)
        box.setSpacing(4)
        box.addWidget(header)
        box.addWidget(view)
        return container

    def restyle(self):
        self.console.setStyleSheet(console_style())
        self.source_view.setStyleSheet(console_style())
        self.log_view.setStyleSheet(console_style())
        self.source_header.setStyleSheet(styles.muted_label())
        self.log_header.setStyleSheet(styles.muted_label())

    def set_workspace(self, workspace: str | None):
        self.workspace = workspace

    def clear_details(self):
        self.source_view.clear()
        self.log_view.clear()
        self.source_header.setText("Cliquez un test dans l'arbre pour voir son code source.")
        self.log_header.setText("Cliquez un test dans l'arbre pour voir son log.")

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def show_for(self, target: str | None, nodeid: str | None):
        """Charge la source et le log correspondant a l'element clique.

        `target` porte le chemin (fichier, classe ou fonction), `nodeid` n'existe
        que pour les feuilles executables.
        """
        self._load_source(target, nodeid)
        self._load_log(nodeid)

    def _load_source(self, target: str | None, nodeid: str | None):
        if not self.workspace or not target:
            self.source_header.setText("Aucun workspace charge.")
            self.source_view.clear()
            return

        relative = target.split("::", 1)[0]
        if not relative.endswith(".py"):
            self.source_header.setText(
                f"{relative} est un dossier : choisissez un fichier ou un test."
            )
            self.source_view.clear()
            return

        path = Path(self.workspace) / relative
        if not path.is_file():
            self.source_header.setText(f"Fichier source introuvable : {path}")
            self.source_view.clear()
            return

        content, warning = read_text_file(path)
        self.source_view.setPlainText(content)
        self._current_source = path

        header = str(path)
        if warning:
            header += f"    ({warning})"
        self.source_header.setText(header)

        function = function_name_from_nodeid(nodeid or target or "")
        if function:
            self._scroll_to_function(content, function)

    def _scroll_to_function(self, content: str, function: str):
        """Place le curseur sur la definition du test, pour ne pas atterrir en
        haut d'un fichier de plusieurs milliers de lignes."""
        # Espaces horizontaux uniquement : \s engloberait les sauts de ligne, et
        # le motif commencerait alors a matcher sur les lignes vides qui
        # precedent la definition, placant le curseur trop haut.
        pattern = re.compile(
            rf"^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(function)}[ \t]*\(",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if not match:
            return

        line = content.count("\n", 0, match.start())
        cursor = self.source_view.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, line)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        self.source_view.setTextCursor(cursor)
        self.source_view.centerCursor()

    def _load_log(self, nodeid: str | None):
        if not self.workspace:
            self.log_header.setText("Aucun workspace charge.")
            self.log_view.clear()
            return

        if not nodeid:
            self.log_header.setText(
                "Selectionnez un test precis (une feuille de l'arbre) pour voir son log."
            )
            self.log_view.clear()
            return

        path = find_test_log(self.workspace, nodeid)
        if path is None:
            log_root = resolve_log_root(self.workspace)
            self.log_header.setText(
                f"Aucun log pour ce test.\n"
                f"Les logs sont lus dans : {log_root}\n"
                "Lancez le test, ou ajustez la cle log_directory du config.yml du workspace."
            )
            self.log_view.clear()
            return

        content, warning = read_text_file(Path(path))
        self.log_view.setPlainText(content)
        header = str(path)
        if warning:
            header += f"    ({warning})"
        self.log_header.setText(header)
        self.log_view.moveCursor(QTextCursor.End)

    # ------------------------------------------------------------------
    # Confort
    # ------------------------------------------------------------------

    def show_console(self):
        self.tabs.setCurrentIndex(CONSOLE_TAB)

    def show_source(self):
        self.tabs.setCurrentIndex(SOURCE_TAB)

    def show_log(self):
        self.tabs.setCurrentIndex(LOG_TAB)
