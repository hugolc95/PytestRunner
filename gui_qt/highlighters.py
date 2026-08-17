"""Coloration syntaxique du code Python, de la sortie pytest et des logs.

Volontairement fondee sur des expressions regulieres appliquees a l'affichage,
et non sur les couleurs ANSI de pytest (--color=yes) : ces codes
d'echappement se retrouveraient dans la sortie brute, celle qui sert a
l'historique, a l'extraction des traces d'echec et a la detection des statuts.
Colorer a l'affichage laisse le texte intact.

Les couleurs viennent de la palette active, donc suivent le theme. Apres un
changement de theme, appeler refresh() sur chaque coloriseur.
"""

from __future__ import annotations

import re

from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from gui_qt.styles import styles

# Au-dela, la ligne n'est pas coloree : le cout d'analyse serait paye sur le
# thread de l'interface sans benefice visible.
MAX_HIGHLIGHT_LENGTH = 2000


def _format(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class _ThemedHighlighter(QSyntaxHighlighter):
    """Base commune : reconstruit ses formats quand le theme change."""

    def __init__(self, document):
        super().__init__(document)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self.refresh()

    def build_rules(self) -> list[tuple]:
        """Regles (motif, format) ou (motif, format, groupe_de_capture)."""
        raise NotImplementedError

    def refresh(self):
        # Une regle peut viser un groupe de capture plutot que le motif entier :
        # "def (\w+)" doit colorer le nom de la fonction sans recouvrir le
        # mot-cle, deja colore par une regle precedente.
        self.rules = []
        for regle in self.build_rules():
            motif, fmt = regle[0], regle[1]
            groupe = regle[2] if len(regle) > 2 else 0
            self.rules.append((QRegularExpression(motif), fmt, groupe))
        self.rehighlight()

    def highlightBlock(self, text: str):
        # Une ligne demesuree (vidage hexadecimal, trace brute) couterait cher a
        # analyser pour un gain visuel nul, et ce cout serait paye sur le thread
        # de l'interface pendant le run.
        if len(text) > MAX_HIGHLIGHT_LENGTH:
            return

        for expression, fmt, groupe in self.rules:
            it = expression.globalMatch(text)
            while it.hasNext():
                match = it.next()
                debut = match.capturedStart(groupe)
                if debut >= 0:
                    self.setFormat(debut, match.capturedLength(groupe), fmt)


PYTHON_KEYWORDS = (
    "False None True and as assert async await break class continue def del elif "
    "else except finally for from global if import in is lambda nonlocal not or "
    "pass raise return try while with yield"
).split()

PYTHON_BUILTINS = (
    "abs all any bool bytes callable dict dir enumerate filter float format "
    "frozenset getattr hasattr hash int isinstance issubclass len list map max min "
    "next object open print range repr reversed round set setattr sorted str sum "
    "super tuple type zip"
).split()


class PythonHighlighter(_ThemedHighlighter):
    """Coloration Python : mots-cles, chaines, commentaires, decorateurs..."""

    def build_rules(self):
        mot_cle = _format(styles.syntax_color("keyword"), bold=True)
        builtin = _format(styles.syntax_color("builtin"))
        chaine = _format(styles.syntax_color("string"))
        commentaire = _format(styles.syntax_color("comment"), italic=True)
        nombre = _format(styles.syntax_color("number"))
        decorateur = _format(styles.syntax_color("decorator"))
        fonction = _format(styles.syntax_color("function"))
        classe = _format(styles.syntax_color("classname"), bold=True)
        soi = _format(styles.syntax_color("self"), italic=True)

        regles = [
            (r"\b(?:" + "|".join(PYTHON_KEYWORDS) + r")\b", mot_cle),
            (r"\b(?:" + "|".join(PYTHON_BUILTINS) + r")\b(?=\s*\()", builtin),
            (r"\b(?:self|cls)\b", soi),
            (r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b", nombre),
            (r"^\s*@[\w.]+", decorateur),
            (r"\bdef\s+(\w+)", fonction, 1),
            (r"\bclass\s+(\w+)", classe, 1),
            # Les chaines viennent apres pour recouvrir ce qu'elles contiennent.
            (r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'", chaine),
            (r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"', chaine),
            # Le commentaire est pose en dernier : il l'emporte sur le reste de
            # la ligne, sauf s'il est lui-meme dans une chaine (cas rare, assume).
            (r"#[^\n]*", commentaire),
        ]
        return regles

    def highlightBlock(self, text: str):
        super().highlightBlock(text)
        self._highlight_triple_quoted(text)

    def _highlight_triple_quoted(self, text: str):
        """Chaines sur plusieurs lignes : necessitent un etat entre les blocs.

        Etat 1 = a l'interieur d'un bloc ''' ou \"\"\".
        """
        docstring = _format(styles.syntax_color("docstring"))
        delimiteur = re.compile(r"'''|\"\"\"")

        depart = 0
        if self.previousBlockState() != 1:
            premier = delimiteur.search(text)
            if not premier:
                return
            # Un delimiteur ouvrant ET fermant sur la meme ligne ne change rien.
            fermeture = delimiteur.search(text, premier.end())
            if fermeture:
                self.setFormat(premier.start(), fermeture.end() - premier.start(), docstring)
                return
            self.setFormat(premier.start(), len(text) - premier.start(), docstring)
            self.setCurrentBlockState(1)
            return

        fermeture = delimiteur.search(text, depart)
        if fermeture:
            self.setFormat(0, fermeture.end(), docstring)
        else:
            self.setFormat(0, len(text), docstring)
            self.setCurrentBlockState(1)


class PytestOutputHighlighter(_ThemedHighlighter):
    """Coloration de la sortie pytest : statuts, separateurs, nodeids, traces."""

    def build_rules(self):
        return [
            (r"\bPASSED\b", _format(styles.output_color("passed"), bold=True)),
            (r"\b(?:FAILED|XPASS)\b", _format(styles.output_color("failed"), bold=True)),
            (r"\b(?:SKIPPED|XFAIL)\b", _format(styles.output_color("skipped"), bold=True)),
            (r"\bERRORS?\b", _format(styles.output_color("error"), bold=True)),
            (r"^[=_\-]{5,}.*$", _format(styles.output_color("separator"))),
            (r"\S+\.py(?:::\S+)?", _format(styles.output_color("nodeid"))),
            (r"\[\s*\d+%\]", _format(styles.output_color("percent"))),
            # Lignes d'assertion des traces pytest : "E   assert 1 == 2".
            (r"^E\s+.*$", _format(styles.output_color("traceback"))),
            (r"^\s*\d+ (?:passed|failed|error|skipped).*$",
             _format(styles.output_color("separator"), bold=True)),
        ]


class LogHighlighter(_ThemedHighlighter):
    """Coloration des fichiers de log : horodatage et niveaux."""

    def build_rules(self):
        return [
            (r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?",
             _format(styles.output_color("timestamp"))),
            (r"\b(?:DEBUG|TRACE)\b", _format(styles.output_color("separator"))),
            (r"\bINFO\b", _format(styles.output_color("info"), bold=True)),
            (r"\b(?:WARNING|WARN)\b", _format(styles.output_color("warning"), bold=True)),
            (r"\b(?:ERROR|CRITICAL|FATAL)\b", _format(styles.output_color("failed"), bold=True)),
            # Trames APDU : des octets hexadecimaux en majuscules.
            (r"\b[0-9A-F]{8,}\b", _format(styles.output_color("nodeid"))),
        ]
