"""Console de sortie : un tampon complet, plusieurs facons de le regarder.

Une console brute est un mur. Sur un run reel de 160 tests, 160 des 292 lignes
sont des verdicts que l'arbre montre deja, 9 sont des bannieres, et il faut en
traverser une dizaine avant d'atteindre la premiere trace utile. Rien n'est
faux la-dedans : c'est juste range dans l'ordre ou pytest ecrit, pas dans
l'ordre ou on lit.

Ce widget ne jette rien. Il garde le flux entier -- copiable, exportable -- et
ajoute trois choses qui manquaient : la couleur (les sequences ANSI d'un
conftest s'affichaient en toutes lettres), une lentille pour ne garder que ce
qu'on cherche, et un suivi automatique qui se coupe des qu'on remonte lire.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QTextFormat
from PyQt5.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner.domain import ansi, console
from runner.domain.console import Lens, LensFilter
from runner.domain.models import Status
from runner.ui import icons, theme
from runner.ui import tokens as t

# Au-dela, la zone de texte devient lente a defiler. Un run de plusieurs
# milliers de tests depasse largement ce seuil ; c'est la fin qui interesse.
MAX_LIGNES = 20000

# On laisse le tampon depasser un peu avant de le rogner, puis on rogne d'un
# coup : c'est ce qui evite un recomptage a chaque ligne une fois plein.
MARGE_LIGNES = MAX_LIGNES + MAX_LIGNES // 4

_PLACEHOLDERS = {
    Lens.ALL: "Nothing has been written here yet.",
    Lens.PROBLEMS: "No failure in this output.",
    Lens.OUTLINE: "Nothing to outline yet.",
}


class ConsoleView(QWidget):
    """Zone de texte teintee ANSI, avec lentilles et suivi de fin.

    Le tampon (`self._lines`) est la verite ; la zone de texte n'en est qu'un
    rendu. Changer de lentille redessine, ne detruit rien.
    """

    def __init__(self, show_lens: bool = True, parent=None):
        super().__init__(parent)
        self._lines: list[str] = []
        self._visibles = 0          # lignes retenues par la lentille courante
        self._reste = ""            # ligne en cours, pas encore terminee
        self._lens = Lens.ALL
        # Le filtre suit le flux au fur et a mesure : il doit savoir dans
        # quelle section pytest se trouve pour decider d'une ligne.
        self._filtre = LensFilter(Lens.ALL)
        self._follow = True
        self._defile_seul = False   # garde : distinguer nos scrolls des siens
        self._formats: dict[ansi.Style, QTextCharFormat] = {}

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setUndoRedoEnabled(False)
        self.view.document().setMaximumBlockCount(MAX_LIGNES)
        self.view.verticalScrollBar().valueChanged.connect(self._on_scroll)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addWidget(self._build_toolbar(show_lens))
        colonne.addWidget(self.view, 1)

        self._update_counter()

    # ------------------------------------------------------------- structure

    def _build_toolbar(self, show_lens: bool) -> QWidget:
        barre = QWidget()
        ligne = QHBoxLayout(barre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_1)

        # Segmente : trois vues d'une meme chose, dont une seule a la fois.
        # Trois boutons separes auraient laisse croire a trois actions ; colles
        # et sans espace entre eux, ils se lisent comme un seul selecteur.
        self.lens_bar = QWidget()
        rangee = QHBoxLayout(self.lens_bar)
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(0)

        self.lens_group = QButtonGroup(self)
        self.lens_group.setExclusive(True)
        self.lens_buttons: dict[Lens, QPushButton] = {}

        lentilles = (
            (Lens.ALL, "first", "Everything pytest wrote"),
            (Lens.PROBLEMS, "middle", "Only what explains a failure"),
            (Lens.OUTLINE, "last", "Only the shape of the run"),
        )
        for lentille, place, infobulle in lentilles:
            bouton = QPushButton(lentille.label)
            bouton.setObjectName("Segment")
            bouton.setProperty("segment", place)
            bouton.setCheckable(True)
            bouton.setChecked(lentille is Lens.ALL)
            bouton.setCursor(Qt.PointingHandCursor)
            bouton.setToolTip(infobulle)
            bouton.clicked.connect(lambda _, choix=lentille: self.set_lens(choix))
            self.lens_group.addButton(bouton)
            self.lens_buttons[lentille] = bouton
            rangee.addWidget(bouton)

        self.lens_bar.setVisible(show_lens)
        ligne.addWidget(self.lens_bar)

        self.counter = QLabel("")
        self.counter.setObjectName("Faint")

        ligne.addSpacing(t.SPACE_2)
        ligne.addWidget(self.counter)
        ligne.addStretch(1)

        self.wrap_button = self._icon_toggle(
            "mdi.wrap", "Wrap long lines", self._on_wrap)
        self.follow_button = self._icon_toggle(
            "mdi.arrow-down-circle-outline", "Follow the output",
            self._on_follow_toggled, coche=True)
        self.copy_button = QPushButton()
        self.copy_button.setObjectName("IconSm")
        self.copy_button.setIcon(icons.icon("mdi.content-copy", t.TEXT_MUTED))
        self.copy_button.setToolTip("Copy the whole output")
        self.copy_button.clicked.connect(self.copy_all)

        ligne.addWidget(self.wrap_button)
        ligne.addWidget(self.follow_button)
        ligne.addWidget(self.copy_button)
        return barre

    def _icon_toggle(self, glyph: str, infobulle: str, slot,
                     coche: bool = False) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("IconSm")
        bouton.setIcon(icons.icon(glyph, t.TEXT_MUTED))
        bouton.setCheckable(True)
        bouton.setChecked(coche)
        bouton.setToolTip(infobulle)
        bouton.toggled.connect(slot)
        return bouton

    def restyle(self) -> None:
        """Rejoue le rendu avec la palette courante.

        Les formats ANSI sont mis en cache par style : ils portent des couleurs
        resolues au moment ou ils ont ete crees, et survivraient donc a une
        bascule de theme en gardant l'ancienne teinte.
        """
        self._formats.clear()
        self.copy_button.setIcon(icons.icon("mdi.content-copy", t.TEXT_MUTED))
        self.wrap_button.setIcon(icons.icon("mdi.wrap", t.TEXT_MUTED))
        self.follow_button.setIcon(
            icons.icon("mdi.arrow-down-circle-outline", t.TEXT_MUTED))
        self._repaint()

    # ---------------------------------------------------------------- contenu

    def append(self, texte: str) -> None:
        """Ajoute du texte au flux. Les lignes incompletes sont mises de cote.

        pytest ecrit ligne par ligne, mais rien ne le garantit : colorer un
        fragment sans attendre sa fin donnerait un rendu qui saute.
        """
        if not texte:
            return
        self._reste += texte.replace("\r\n", "\n").replace("\r", "")
        if "\n" not in self._reste:
            return

        morceaux = self._reste.split("\n")
        self._reste = morceaux.pop()

        curseur = QTextCursor(self.view.document())
        curseur.movePosition(QTextCursor.End)
        curseur.beginEditBlock()
        try:
            for ligne in morceaux:
                self._lines.append(ligne)
                if self._filtre.keep(ligne):
                    self._visibles += 1
                    self._ecrire(curseur, ligne)
        finally:
            curseur.endEditBlock()

        if len(self._lines) > MARGE_LIGNES:
            # Par blocs, pas ligne a ligne : rogner d'une ligne a chaque ligne
            # ajoutee forcerait un recomptage complet a chaque fois.
            del self._lines[:len(self._lines) - MAX_LIGNES]
            self._visibles = len(console.apply_lens(self._lines, self._lens))

        self._update_counter()
        self._scroll_si_suivi()

    def set_text(self, texte: str) -> None:
        """Remplace tout le flux d'un coup."""
        self._reste = ""
        self._lines = (texte or "").replace("\r\n", "\n").replace("\r", "").split("\n")
        if self._lines and self._lines[-1] == "":
            self._lines.pop()
        self._repaint()

    def clear(self) -> None:
        self._lines = []
        self._visibles = 0
        self._reste = ""
        self._filtre.reset()
        self.view.clear()
        self.set_follow(True)
        self._update_counter()

    def text(self) -> str:
        """Le flux complet, lentille ou pas, debarrasse de ses codes ANSI."""
        return ansi.strip_ansi("\n".join(self._lines))

    def copy_all(self) -> None:
        from PyQt5.QtWidgets import QApplication

        QApplication.clipboard().setText(self.text())

    def highlight_lines(self, lines=(), error_lines=()) -> None:
        """Surligne des lignes completes, plus fortement pour les erreurs."""
        errors = set(error_lines)
        selections = []
        for number in sorted(set(lines)):
            block = self.view.document().findBlockByNumber(number)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            colour = QColor(t.STATUS_COLORS[
                Status.FAILED if number in errors else Status.SKIPPED])
            colour.setAlpha(64 if number in errors else 38)
            selection.format.setBackground(colour)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            if number in errors:
                selection.format.setFontWeight(75)
                selection.format.setForeground(
                    QColor(t.STATUS_COLORS[Status.FAILED]))
            selections.append(selection)
        self.view.setExtraSelections(selections)

    def reveal_line(self, number: int) -> None:
        """Place une ligne au centre sans modifier le contenu de la console."""
        block = self.view.document().findBlockByNumber(number)
        if not block.isValid():
            return
        self.view.setTextCursor(QTextCursor(block))
        self.view.centerCursor()

    # --------------------------------------------------------------- lentille

    def set_lens(self, lens: Lens) -> None:
        if lens is self._lens:
            return
        self._lens = lens
        self._filtre = LensFilter(lens)
        bouton = self.lens_buttons.get(lens)
        if bouton is not None and not bouton.isChecked():
            bouton.setChecked(True)
        self._repaint()

    def lens(self) -> Lens:
        return self._lens

    def _repaint(self) -> None:
        """Redessine la zone de texte a partir du tampon."""
        self._filtre.reset()
        self._visibles = 0
        self.view.setUpdatesEnabled(False)
        try:
            self.view.clear()
            curseur = QTextCursor(self.view.document())
            curseur.beginEditBlock()
            try:
                for ligne in self._lines:
                    if self._filtre.keep(ligne):
                        self._visibles += 1
                        self._ecrire(curseur, ligne)
            finally:
                curseur.endEditBlock()
        finally:
            self.view.setUpdatesEnabled(True)

        self._update_counter()
        self._scroll_si_suivi()

    def _update_counter(self) -> None:
        total = len(self._lines)
        visibles = total if self._lens is Lens.ALL else self._visibles
        caches = total - visibles

        self.view.setPlaceholderText(
            _PLACEHOLDERS[self._lens] if total else _PLACEHOLDERS[Lens.ALL])

        if not total:
            self.counter.setText("")
        elif caches:
            # Dire combien de lignes sont masquees : sans ce chiffre, une
            # lentille active ressemble a une console qui a perdu sa sortie.
            self.counter.setText(f"{visibles} of {total} lines")
        else:
            self.counter.setText(f"{total} lines")

    # ----------------------------------------------------------------- rendu

    def _format(self, style: ansi.Style) -> QTextCharFormat:
        cache = self._formats.get(style)
        if cache is not None:
            return cache

        format_ = QTextCharFormat()
        couleur = t.ansi_color(style.couleur, style.vive)
        if couleur:
            format_.setForeground(QColor(couleur))
        if style.gras:
            format_.setFontWeight(75)
        if style.italique:
            format_.setFontItalic(True)
        if style.souligne:
            format_.setFontUnderline(True)

        self._formats[style] = format_
        return format_

    def _ecrire(self, curseur: QTextCursor, ligne: str) -> None:
        if not ansi.contient_ansi(ligne):
            curseur.insertText(ligne + "\n")
            return
        for contenu, style in ansi.parse_ansi(ligne):
            if style.neutre:
                curseur.insertText(contenu)
            else:
                curseur.insertText(contenu, self._format(style))
        curseur.insertText("\n", QTextCharFormat())

    # ------------------------------------------------------------- defilement

    def set_follow(self, suivre: bool) -> None:
        if self.follow_button.isChecked() != suivre:
            self.follow_button.setChecked(suivre)  # declenche _on_follow_toggled
            return
        self._follow = suivre
        if suivre:
            self._scroll_fin()

    def following(self) -> bool:
        return self._follow

    def _on_follow_toggled(self, suivre: bool) -> None:
        self._follow = suivre
        self.follow_button.setToolTip(
            "Following the output — click to stay put"
            if suivre else "Jump to the end and follow again")
        if suivre:
            self._scroll_fin()

    def _on_scroll(self, valeur: int) -> None:
        """Coupe le suivi des que l'utilisateur remonte.

        Une console qui saute a la fin pendant qu'on lit une trace est
        inutilisable. Remonter suffit a la figer ; le bouton reste la pour
        redescendre.
        """
        if self._defile_seul:
            return
        barre = self.view.verticalScrollBar()
        en_bas = valeur >= barre.maximum() - 2
        if self._follow != en_bas:
            self.follow_button.setChecked(en_bas)

    def _scroll_si_suivi(self) -> None:
        if self._follow:
            self._scroll_fin()

    def _scroll_fin(self) -> None:
        self._defile_seul = True
        try:
            barre = self.view.verticalScrollBar()
            barre.setValue(barre.maximum())
        finally:
            self._defile_seul = False

    def _on_wrap(self, enroule: bool) -> None:
        self.view.setLineWrapMode(
            QPlainTextEdit.WidgetWidth if enroule else QPlainTextEdit.NoWrap)

    # ---------------------------------- delegation, pour la synchronisation

    def verticalScrollBar(self):
        return self.view.verticalScrollBar()

    def horizontalScrollBar(self):
        return self.view.horizontalScrollBar()
