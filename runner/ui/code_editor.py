"""Editeur de code : numeros de ligne, ligne courante, coloration Python.

Un fichier de test se lit avec ses numeros de ligne : ce sont eux que citent
les traces pytest (`test_apdu.py:42`), et c'est par eux qu'on fait le lien
entre un echec et l'endroit ou le corriger.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from runner.ui import tokens as t

PYTHON_KEYWORDS = (
    "and as assert async await break class continue def del elif else except "
    "finally for from global if import in is lambda nonlocal not or pass raise "
    "return try while with yield True False None match case"
).split()

PYTHON_BUILTINS = (
    "abs all any bool bytes callable chr dict dir enumerate eval filter float "
    "format frozenset getattr hasattr hash hex id input int isinstance issubclass "
    "iter len list map max min next object open print range repr reversed round "
    "set setattr sorted str sum super tuple type zip"
).split()

_TRIPLE = re.compile(r"'''|\"\"\"")


def _format(couleur: str, gras: bool = False, italique: bool = False) -> QTextCharFormat:
    mise_en_forme = QTextCharFormat()
    mise_en_forme.setForeground(QColor(couleur))
    if gras:
        mise_en_forme.setFontWeight(QFont.Bold)
    if italique:
        mise_en_forme.setFontItalic(True)
    return mise_en_forme


class PythonHighlighter(QSyntaxHighlighter):
    """Coloration Python : mots-cles, chaines, commentaires, decorateurs."""

    def __init__(self, document):
        super().__init__(document)
        chaine = _format(t.syntax_color("string"))

        # L'ordre compte : chaque regle repeint par-dessus les precedentes. Les
        # chaines passent apres les mots-cles pour recouvrir ce qu'elles
        # contiennent, et le commentaire en dernier pour l'emporter sur sa ligne.
        self._regles = [
            (re.compile(r"\b(?:" + "|".join(PYTHON_KEYWORDS) + r")\b"),
             _format(t.syntax_color("keyword"), gras=True), 0),
            (re.compile(r"\b(?:" + "|".join(PYTHON_BUILTINS) + r")\b(?=\s*\()"),
             _format(t.syntax_color("builtin")), 0),
            (re.compile(r"\b(?:self|cls)\b"),
             _format(t.syntax_color("self"), italique=True), 0),
            (re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"),
             _format(t.syntax_color("number")), 0),
            (re.compile(r"^\s*@[\w.]+"), _format(t.syntax_color("decorator")), 0),
            (re.compile(r"\bdef\s+(\w+)"), _format(t.syntax_color("function")), 1),
            (re.compile(r"\bclass\s+(\w+)"),
             _format(t.syntax_color("classname"), gras=True), 1),
            (re.compile(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'"), chaine, 0),
            (re.compile(r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"'), chaine, 0),
            (re.compile(r"#[^\n]*"), _format(t.syntax_color("comment"), italique=True), 0),
        ]
        self._docstring = _format(t.syntax_color("docstring"))

    def highlightBlock(self, texte: str) -> None:
        for motif, mise_en_forme, groupe in self._regles:
            for trouve in motif.finditer(texte):
                debut, fin = trouve.span(groupe)
                self.setFormat(debut, fin - debut, mise_en_forme)
        self._triple_quotes(texte)

    def _triple_quotes(self, texte: str) -> None:
        """Chaines sur plusieurs lignes : demandent un etat entre les blocs.

        Etat 1 = on est a l'interieur d'un bloc `'''` ou `\"\"\"`.
        """
        if self.previousBlockState() != 1:
            premier = _TRIPLE.search(texte)
            if premier is None:
                return
            # Ouvrant ET fermant sur la meme ligne : rien ne deborde.
            fermeture = _TRIPLE.search(texte, premier.end())
            if fermeture is not None:
                self.setFormat(premier.start(), fermeture.end() - premier.start(),
                               self._docstring)
                return
            self.setFormat(premier.start(), len(texte) - premier.start(),
                           self._docstring)
            self.setCurrentBlockState(1)
            return

        fermeture = _TRIPLE.search(texte)
        if fermeture is not None:
            self.setFormat(0, fermeture.end(), self._docstring)
        else:
            self.setFormat(0, len(texte), self._docstring)
            self.setCurrentBlockState(1)


class _Gutter(QWidget):
    """Gouttiere : sa largeur est imposee par l'editeur, qui la dessine."""

    def __init__(self, editeur: "CodeEditor"):
        super().__init__(editeur)
        self.editeur = editeur

    def sizeHint(self) -> QSize:
        return QSize(self.editeur.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self.editeur.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    """Zone de code, en lecture seule ou non selon ce que l'appelant decide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        self._gutter = _Gutter(self)
        self.highlighter = PythonHighlighter(self.document())

        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self._update_width()
        self.highlight_current_line()

    # ------------------------------------------------------------- gouttiere

    def gutter_width(self) -> int:
        chiffres = max(2, len(str(max(1, self.blockCount()))))
        return t.SPACE_3 + self.fontMetrics().horizontalAdvance("9") * chiffres

    def _update_width(self, _=0) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        zone = self.contentsRect()
        self._gutter.setGeometry(
            QRect(zone.left(), zone.top(), self.gutter_width(), zone.height()))

    def paint_gutter(self, event) -> None:
        peintre = QPainter(self._gutter)
        peintre.fillRect(event.rect(), QColor(t.GUTTER_BG))

        bloc = self.firstVisibleBlock()
        numero = bloc.blockNumber()
        haut = round(self.blockBoundingGeometry(bloc)
                     .translated(self.contentOffset()).top())
        bas = haut + round(self.blockBoundingRect(bloc).height())

        # Le numero de la ligne courante ressort : c'est le repere le plus net,
        # la teinte de fond restant volontairement discrete pour ne pas gener
        # la lecture du code.
        ligne_courante = self.textCursor().blockNumber()
        normal, accent = QColor(t.GUTTER_TEXT), QColor(t.GUTTER_CURRENT)
        police = peintre.font()

        while bloc.isValid() and haut <= event.rect().bottom():
            if bloc.isVisible() and bas >= event.rect().top():
                courante = numero == ligne_courante
                peintre.setPen(accent if courante else normal)
                police.setBold(courante)
                peintre.setFont(police)
                peintre.drawText(0, haut, self._gutter.width() - t.SPACE_2,
                                 self.fontMetrics().height(),
                                 Qt.AlignRight, str(numero + 1))
            bloc = bloc.next()
            haut = bas
            bas = haut + round(self.blockBoundingRect(bloc).height())
            numero += 1

    # --------------------------------------------------------- ligne courante

    def highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(t.CURRENT_LINE))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
        self._gutter.update()

    def restyle(self) -> None:
        """Reconstruit la coloration avec la palette courante.

        Les formats du surligneur sont batis une fois a la construction : ils
        gardent sinon les couleurs du theme de depart, sur un fond qui, lui,
        a change.
        """
        self.highlighter = PythonHighlighter(self.document())
        self.highlight_current_line()
        self._update_width()
        self.viewport().update()

    def goto_line(self, ligne: int) -> None:
        """Place le curseur sur cette ligne (base 0) et la centre.

        Le curseur est pose sans rien selectionner : une selection poserait son
        fond par-dessus le texte. La surbrillance de la ligne courante suffit.
        """
        if ligne < 0:
            return
        from PySide6.QtGui import QTextCursor

        curseur = self.textCursor()
        curseur.movePosition(QTextCursor.Start)
        curseur.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, ligne)
        self.setTextCursor(curseur)
        self.centerCursor()
