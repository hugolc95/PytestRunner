"""Onglet Source : le fichier du test selectionne, modifiable sur place.

Corriger un test demandait de quitter l'outil, retrouver le fichier, l'ouvrir
ailleurs, revenir, relancer. Le fichier est deja identifie par le nodeid : le
montrer, et le laisser modifier, evite cet aller-retour.

L'edition n'est pas active par defaut. On ecrit dans les vrais fichiers de
test de quelqu'un : la bascule est explicite, et ce qui n'est pas surement
reecrivable (fichier tronque, encodage non UTF-8) reste en lecture seule.

Une fois l'edition active, l'enregistrement est automatique -- apres une
courte pause dans la frappe, en changeant de test, et a la fermeture. Un
Ctrl+S oublie avant un run ferait relancer l'ancienne version du test et
chercher pourquoi la correction n'a rien change.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain.source import SourceFile, function_line, read_source, write_source
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.code_editor import CodeEditor
from runner.ui.widgets import EmptyState

# Assez court pour qu'un run lance juste apres parte du bon fichier, assez long
# pour ne pas ecrire a chaque touche.
AUTOSAVE_MS = 700


class SourcePanel(QWidget):
    """Fichier source du test selectionne, en lecture puis en edition."""

    saved = Signal(str)  # chemin ecrit

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file = SourceFile()
        self._dirty = False
        self._loading = False

        self.empty = EmptyState(
            "mdi.file-code-outline",
            "No source to show",
            "Click a test in the tree to read its file here — and to fix it "
            "without leaving the runner.",
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self._build_content())

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self.stack)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AUTOSAVE_MS)
        self._timer.timeout.connect(self.save)

    # ------------------------------------------------------------- structure

    def _build_content(self) -> QWidget:
        contenu = QWidget()
        colonne = QVBoxLayout(contenu)
        colonne.setContentsMargins(0, t.SPACE_2, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(t.SPACE_2)

        self.path_label = QLabel()
        self.path_label.setObjectName("Faint")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.status_label = QLabel()
        self.status_label.setObjectName("Faint")

        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("Ghost")
        self.edit_button.setCheckable(True)
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setIcon(icons.icon("mdi.pencil-outline", t.TEXT_MUTED))
        self.edit_button.toggled.connect(self.set_editable)

        barre.addWidget(self.path_label, 1)
        barre.addWidget(self.status_label)
        barre.addWidget(self.edit_button)
        colonne.addLayout(barre)

        self.editor = CodeEditor()
        self.editor.textChanged.connect(self._on_edited)
        colonne.addWidget(self.editor, 1)
        return contenu

    # ------------------------------------------------------------ chargement

    def show_file(self, chemin: Path | None, nodeid: str = "") -> None:
        """Charge un fichier et saute a la definition du test.

        Change de fichier en enregistrant d'abord : une frappe en attente ne
        doit jamais disparaitre parce qu'on a clique ailleurs.
        """
        self.save()

        if chemin is None:
            self.clear()
            return

        fichier = read_source(chemin)
        if not fichier.loaded:
            self.empty.update_text("Could not open this file", fichier.warning)
            self.stack.setCurrentWidget(self.empty)
            self._file = SourceFile()
            return

        self._file = fichier
        self._dirty = False
        self.stack.setCurrentWidget(self.stack.widget(1))

        self._loading = True
        try:
            self.editor.setPlainText(fichier.text)
        finally:
            self._loading = False

        self.path_label.setText(str(chemin))
        self.path_label.setToolTip(str(chemin))

        # L'edition ne survit pas au changement de fichier : reactiver
        # explicitement rappelle qu'on ecrit dans un vrai fichier de test.
        self.edit_button.blockSignals(True)
        self.edit_button.setChecked(False)
        self.edit_button.blockSignals(False)
        self.editor.setReadOnly(True)
        self._refresh_button()

        self.editor.goto_line(function_line(fichier.text, nodeid))

    def clear(self) -> None:
        self._file = SourceFile()
        self._dirty = False
        self.empty.update_text(
            "No source to show",
            "Click a test in the tree to read its file here — and to fix it "
            "without leaving the runner.")
        self.stack.setCurrentWidget(self.empty)

    def path(self) -> Path | None:
        return self._file.path

    # --------------------------------------------------------------- edition

    def set_editable(self, modifiable: bool) -> None:
        """Bascule entre lecture seule et edition. Sortir enregistre."""
        if modifiable and not self._file.editable:
            self.edit_button.blockSignals(True)
            self.edit_button.setChecked(False)
            self.edit_button.blockSignals(False)
            return

        self.editor.setReadOnly(not modifiable)
        if modifiable:
            self.editor.setFocus()
            self._say("Editing — saved automatically")
        else:
            self.save()
        self._refresh_button()

    def _on_edited(self) -> None:
        if self._loading or self.editor.isReadOnly():
            return
        self._dirty = True
        self._say("Modified…")
        self._timer.start()

    def save(self) -> bool:
        """Ecrit ce qui est en attente. Vrai si le fichier sur disque est a jour.

        Appele avant chaque run : c'est ce qui garantit que pytest relit bien
        ce qui est affiche, et pas la version d'avant la correction.
        """
        self._timer.stop()
        if not self._dirty or self._file.path is None:
            return True

        erreur = write_source(self._file.path, self.editor.toPlainText(),
                              self._file.newline)
        if erreur:
            self._say(erreur, erreur=True)
            return False

        self._dirty = False
        self._say("Saved")
        self.saved.emit(str(self._file.path))
        return True

    @property
    def dirty(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------- affichage

    def restyle(self) -> None:
        """Rejoue ce qui porte une couleur calculee, puis l'editeur."""
        self.edit_button.setIcon(icons.icon("mdi.pencil-outline", t.TEXT_MUTED))
        self.editor.restyle()
        self._refresh_button()

    def _refresh_button(self) -> None:
        modifiable = self._file.editable
        self.edit_button.setEnabled(modifiable)

        if not modifiable:
            # Le dire, et dire pourquoi : un bouton grise sans explication se
            # lit comme une panne.
            self._say(self._file.warning or "Read-only")
            self.edit_button.setToolTip(
                self._file.warning or "This file cannot be edited here.")
        elif self.edit_button.isChecked():
            self.edit_button.setToolTip("Stop editing and save")
        else:
            self.edit_button.setToolTip("Edit this file — changes are saved for you")
            if not self._dirty:
                self._say("Read-only")

    def _say(self, texte: str, erreur: bool = False) -> None:
        from runner.domain.models import Status

        self.status_label.setText(texte)
        self.status_label.setStyleSheet(
            f"color: {t.status_color(Status.FAILED)}; font-size: {t.TEXT_XS}px;"
            "background: transparent;" if erreur else theme.faint())
