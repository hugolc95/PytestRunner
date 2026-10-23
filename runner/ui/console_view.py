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

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMenu,
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


LOG_LEVEL = re.compile(r"(?:^|\s[-|:]\s|\[|\blogger\.)\s*(ERROR|ERRO|CRITICAL|WARNING|WARN|DEBUG|INFO)\b", re.I)


class LogLevelHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        match = LOG_LEVEL.search(text)
        if not match:
            return
        level = match.group(1).upper()
        if level == "INFO":
            return
        color = (t.status_color(Status.FAILED) if level in ("ERROR", "ERRO", "CRITICAL")
                 else t.status_color(Status.SKIPPED) if level in ("WARN", "WARNING")
                 else t.ACCENT)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        self.setFormat(0, len(text), fmt)


class ConsoleView(QWidget):
    """Zone de texte teintee ANSI, avec lentilles et suivi de fin.

    Le tampon (`self._lines`) est la verite ; la zone de texte n'en est qu'un
    rendu. Changer de lentille redessine, ne detruit rien.
    """

    def __init__(self, show_lens: bool = True, parent=None):
        super().__init__(parent)
        self._lines: list[str] = []
        self._visibles = 0          # lignes retenues par la lentille courante
        self._tronque_source = 0    # lignes coupees par `set_text()`, avant la lentille
        self._reste = ""            # ligne en cours, pas encore terminee
        self._lens = Lens.ALL
        # Le filtre suit le flux au fur et a mesure : il doit savoir dans
        # quelle section pytest se trouve pour decider d'une ligne.
        self._filtre = LensFilter(Lens.ALL)
        self._follow = True
        self._defile_seul = False   # garde : distinguer nos scrolls des siens
        self._formats: dict[ansi.Style, QTextCharFormat] = {}
        self._line_selections = []
        self.search = None
        self._secondary_tools = []
        self.more_tools = None

        self.view = QPlainTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setUndoRedoEnabled(False)
        self.view.document().setMaximumBlockCount(MAX_LIGNES)
        self.view.verticalScrollBar().valueChanged.connect(self._on_scroll)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        if not show_lens:
            from runner.ui.log_search import LogSearchBar
            self.search = LogSearchBar(self.view, self)
            self.search.highlights_changed.connect(self._update_highlights)
            self.search.navigated.connect(lambda: self.set_follow(False))
            self.previous_error = self._error_button("mdi.arrow-up", "Previous error in this log", -1)
            self.next_error = self._error_button("mdi.arrow-down", "Next error in this log", 1)
        self._toolbar = self._build_toolbar(show_lens)
        colonne.addWidget(self._toolbar)
        colonne.addWidget(self.view, 1)
        self.log_highlighter = LogLevelHighlighter(self.view.document()) if not show_lens else None
        self._update_counter()

    # ------------------------------------------------------------- structure

    def _build_toolbar(self, show_lens: bool) -> QWidget:
        barre = QWidget(self)
        ligne = QHBoxLayout(barre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_1)

        # Segmente : trois vues d'une meme chose, dont une seule a la fois.
        # Trois boutons separes auraient laisse croire a trois actions ; colles
        # et sans espace entre eux, ils se lisent comme un seul selecteur.
        # Visibility is set before the toolbar layout adopts this widget.
        # Keep it parented so it cannot flash as a native top-level window.
        self.lens_bar = QWidget(self)
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
        if show_lens:
            ligne.addWidget(self.lens_bar)

        self.counter = QLabel("", self)
        self.counter.setObjectName("Faint")

        if self.search is not None:
            ligne.addWidget(self.search, 1)
            ligne.addWidget(self.previous_error)
            ligne.addWidget(self.next_error)
            # The search counter also carries the line/error status when idle.
            self.counter.hide()
        else:
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
        self._tools = ligne
        if self.search is not None:
            self._secondary_tools = [self.wrap_button, self.follow_button, self.copy_button]
            self.more_tools = QPushButton()
            self.more_tools.setObjectName("IconSm")
            self.more_tools.setIcon(icons.icon("mdi.dots-horizontal", t.TEXT_MUTED))
            self.more_tools.setToolTip("More log actions")
            self.more_tools.setAccessibleName("More log actions")
            self.more_tools.clicked.connect(self._show_log_tools)
            ligne.addWidget(self.more_tools)
        return barre

    def _error_button(self, glyph, tooltip, direction):
        button = QPushButton()
        button.setObjectName("IconSm")
        button.setIcon(icons.icon(glyph, t.status_color(Status.FAILED)))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(lambda: self.navigate_error(direction))
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adapt_log_tools()

    def _adapt_log_tools(self):
        if self.more_tools is None:
            return
        compact = self.width() < 560
        for button in self._secondary_tools:
            button.setVisible(not compact)
        self.more_tools.setVisible(compact)

    def _show_log_tools(self):
        menu = QMenu(self)
        for button in self._secondary_tools:
            action = menu.addAction(button.icon(), button.toolTip())
            action.setEnabled(button.isEnabled())
            action.setCheckable(button.isCheckable())
            action.setChecked(button.isChecked())
            action.triggered.connect(button.click)
        menu.exec(self.more_tools.mapToGlobal(self.more_tools.rect().bottomLeft()))
        menu.deleteLater()

    def add_tool(self, bouton: QPushButton) -> None:
        """Ajoute un bouton au bout de la barre d'outils de CETTE console.

        Ce que la console sait faire est ici ; ce qu'on peut faire du contenu
        d'une console precise appartient a sa propre barre. Un appelant qui
        gere plusieurs consoles cote a cote peut ainsi donner a chacune son
        bouton, au lieu d'un seul bouton partage dont on devrait deviner sur
        laquelle il porte.
        """
        if self.more_tools is None:
            self._tools.addWidget(bouton)
        else:
            self._secondary_tools.append(bouton)
            self._tools.insertWidget(self._tools.indexOf(self.more_tools), bouton)
            self._adapt_log_tools()

    def navigate_error(self, direction: int) -> None:
        document = self.view.document()
        errors = []
        block = document.firstBlock()
        while block.isValid():
            match = LOG_LEVEL.search(block.text())
            if match and match.group(1).upper() in ("ERROR", "ERRO", "CRITICAL"):
                errors.append(block.blockNumber())
            block = block.next()
        if not errors:
            self._set_counter_text("No errors in displayed log")
            return
        current = self.view.textCursor().blockNumber()
        target = (next((n for n in errors if n > current), errors[0]) if direction > 0
                  else next((n for n in reversed(errors) if n < current), errors[-1]))
        self.follow_button.setChecked(False)
        cursor = QTextCursor(document.findBlockByNumber(target))
        cursor.select(QTextCursor.LineUnderCursor)
        self.view.setTextCursor(cursor)
        self.view.centerCursor()
        self._set_counter_text(f"Error {errors.index(target) + 1} / {len(errors)}")

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
        if self.log_highlighter is not None:
            self.log_highlighter.rehighlight()
        if self.search is not None:
            self.search.restyle()
            self.previous_error.setIcon(icons.icon("mdi.arrow-up", t.status_color(Status.FAILED)))
            self.next_error.setIcon(icons.icon("mdi.arrow-down", t.status_color(Status.FAILED)))
            self.more_tools.setIcon(icons.icon("mdi.dots-horizontal", t.TEXT_MUTED))
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
        """Remplace tout le flux d'un coup.

        Contrairement a `append()`, tout arrive ici en une seule fois -- un run
        historique charge depuis le disque peut compter plusieurs centaines de
        milliers de lignes. `setMaximumBlockCount()` sur la zone de texte ne
        protege que le flux qui arrive petit a petit : il faudrait quand meme
        d'abord INSERER chaque ligne avant que Qt n'en rejette les plus
        anciennes, et c'est cette insertion, ligne par ligne, qui gele
        l'interface. Le tampon est donc rogne AVANT le rendu, comme `append()`
        le fait deja au fil de l'eau -- le fichier complet reste ouvrable via
        "Open log", seul l'affichage se limite.
        """
        self._reste = ""
        lignes = (texte or "").replace("\r\n", "\n").replace("\r", "").split("\n")
        if lignes and lignes[-1] == "":
            lignes.pop()
        self._tronque_source = max(0, len(lignes) - MAX_LIGNES) if len(lignes) > MARGE_LIGNES else 0
        if self._tronque_source:
            del lignes[:len(lignes) - MAX_LIGNES]
        self._lines = lignes
        self._repaint()

    def clear(self) -> None:
        self._lines = []
        self._visibles = 0
        self._tronque_source = 0
        self._reste = ""
        self._filtre.reset()
        self._line_selections = []
        self.view.clear()
        if self.search is not None:
            self.search.refresh()
        self._update_highlights()
        self.set_follow(True)
        self._update_counter()

    def text(self) -> str:
        """Le flux complet, lentille ou pas, debarrasse de ses codes ANSI."""
        from runner.domain.diagnostics import PREFIX
        return ansi.strip_ansi("\n".join(line for line in self._lines
                              if not ansi.strip_ansi(line).strip().startswith(PREFIX)))

    def copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication

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
        self._line_selections = selections
        self._update_highlights()

    def _update_highlights(self) -> None:
        selections = list(self._line_selections)
        if self.search is not None:
            selections.extend(self.search.selections())
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
            self._set_counter_text("")
        elif self._tronque_source:
            # Le fichier source depassait largement ce qu'on garde affiche :
            # le dire evite de croire, a tort, qu'un run enorme n'a produit
            # que ces quelques milliers de lignes.
            self._set_counter_text(
                f"last {visibles} of {total + self._tronque_source} lines "
                "— open the log file for the rest")
        elif caches:
            # Dire combien de lignes sont masquees : sans ce chiffre, une
            # lentille active ressemble a une console qui a perdu sa sortie.
            self._set_counter_text(f"{visibles} of {total} lines")
        else:
            self._set_counter_text(f"{total} lines")

    def _set_counter_text(self, text):
        self.counter.setText(text)
        if self.search is not None:
            self.search.set_status(text)
            self.previous_error.setToolTip(f"Previous error in this log\n{text}".rstrip())
            self.next_error.setToolTip(f"Next error in this log\n{text}".rstrip())

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
