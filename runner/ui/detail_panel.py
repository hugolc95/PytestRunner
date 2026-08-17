"""Fiche d'un test : son verdict sur chaque lecteur, et pourquoi il a echoue.

C'est la reponse a la question qu'on se pose vraiment devant un run rouge :
« celui-la, qu'est-ce qui s'est passe ? ». La console contient la reponse,
mais melangee a des centaines de lignes de verdicts que l'arbre affiche deja,
et sans lien visible avec le test qu'on vient de cliquer.

Ici le lien est explicite : un test selectionne, une trace par lecteur qui a
echoue, et rien d'autre.
"""

from __future__ import annotations

from html import escape

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner.domain.ansi import strip_ansi
from runner.domain.failures import Failure, classify_line
from runner.domain.models import Reader, Status
from runner.ui import theme
from runner.ui import tokens as t
from runner.ui.widgets import EmptyState, ReaderResult

# Nature de ligne -> teinte. La table vit ici et pas dans le domaine : c'est
# une decision de theme, elle change avec la palette, pas avec pytest.
_TEINTES = {
    "exception": t.status_color(Status.FAILED),
    "code": t.TEXT,
    "frame": t.ACCENT,
    "section": t.TEXT_FAINT,
    "text": t.TEXT_MUTED,
}


class DetailPanel(QWidget):
    """Ce qu'on sait d'un test, pour tous ses lecteurs a la fois."""

    open_output = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodeid = ""
        self._texte_brut = ""

        self.empty = EmptyState(
            "mdi.cursor-default-click-outline",
            "No test selected",
            "Click a test in the tree to see its verdict on every reader — "
            "and the traceback when it fails.",
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self._build_content())

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self.stack)

    # ------------------------------------------------------------- structure

    def _build_content(self) -> QWidget:
        contenu = QWidget()
        colonne = QVBoxLayout(contenu)
        # Un peu d'air sous les onglets : colle a la barre, le chemin se lisait
        # comme un quatrieme onglet.
        colonne.setContentsMargins(0, t.SPACE_2, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        # Le chemin au-dessus, en petit : il situe, il ne se lit pas. Le nom du
        # test en dessous, en grand : c'est lui qu'on cherchait.
        self.path_label = QLabel()
        self.path_label.setStyleSheet(theme.faint())
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.name_label.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.TEXT_LG}px; font-weight: 600;"
            "background: transparent;")

        colonne.addWidget(self.path_label)
        colonne.addWidget(self.name_label)

        self.results_row = QWidget()
        self._results_layout = QHBoxLayout(self.results_row)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(t.SPACE_4)
        colonne.addWidget(self.results_row)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setLineWrapMode(QTextEdit.NoWrap)
        colonne.addWidget(self.body, 1)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        actions.addStretch(1)

        self.copy_button = QPushButton("Copy traceback")
        self.copy_button.setObjectName("Ghost")
        self.copy_button.clicked.connect(self._copier)

        self.output_button = QPushButton("Open the raw output")
        self.output_button.setObjectName("Ghost")
        self.output_button.clicked.connect(self.open_output)

        actions.addWidget(self.copy_button)
        actions.addWidget(self.output_button)
        colonne.addLayout(actions)
        return contenu

    # ---------------------------------------------------------------- contenu

    def clear(self) -> None:
        self._nodeid = ""
        self._texte_brut = ""
        self.stack.setCurrentWidget(self.empty)

    def nodeid(self) -> str:
        return self._nodeid

    def show_test(self, nodeid: str, readers: tuple[Reader, ...],
                  statuses: dict[int, Status],
                  failures: dict[int, Failure | None]) -> None:
        """Affiche un test. `statuses` et `failures` sont indexes par lecteur."""
        if not nodeid:
            self.clear()
            return

        self._nodeid = nodeid
        self.stack.setCurrentWidget(self.stack.widget(1))

        chemin, _, reste = nodeid.partition("::")
        self.path_label.setText(chemin)
        self.name_label.setText(reste.replace("::", " › ") or chemin)

        self._remplir_resultats(readers, statuses)
        self._remplir_corps(readers, statuses, failures)

    def _remplir_resultats(self, readers, statuses: dict[int, Status]) -> None:
        while self._results_layout.count():
            element = self._results_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()

        cibles = readers or (Reader("", 0),)
        for lecteur in cibles:
            statut = statuses.get(lecteur.index, Status.PENDING)
            self._results_layout.addWidget(
                ReaderResult(lecteur.short_name, lecteur.index, statut))
        self._results_layout.addStretch(1)

    def _remplir_corps(self, readers, statuses: dict[int, Status],
                       failures: dict[int, Failure | None]) -> None:
        cibles = readers or (Reader("", 0),)
        blocs: list[str] = []
        brut: list[str] = []

        for lecteur in cibles:
            statut = statuses.get(lecteur.index, Status.PENDING)
            if not statut.is_bad:
                continue
            echec = failures.get(lecteur.index)
            blocs.append(self._html_bloc(lecteur, statut, echec))
            entete = f"--- {lecteur.name or 'run'} ---" if len(cibles) > 1 else ""
            brut.append("\n".join(x for x in (entete, echec.body if echec else "") if x))

        if not blocs:
            blocs.append(self._html_sans_echec(cibles, statuses))

        self.body.setHtml(
            f'<body style="background:transparent;">{"".join(blocs)}</body>')
        self._texte_brut = "\n\n".join(x for x in brut if x.strip())
        self.copy_button.setEnabled(bool(self._texte_brut))

    # ------------------------------------------------------------------- html

    def _html_bloc(self, lecteur: Reader, statut: Status,
                   echec: Failure | None) -> str:
        couleur = t.reader_color(lecteur.index)
        titre = ""
        if lecteur.name:
            titre = (
                f'<p style="margin:0 0 2px 0; color:{couleur};'
                f' font-size:{t.TEXT_XS}px; font-weight:700;">'
                f"{escape(lecteur.short_name.upper())}</p>")

        if echec is None:
            # Un run annule, ou un echec que pytest a resume sans trace : le
            # dire vaut mieux qu'un cadre vide qu'on prend pour un bug.
            return titre + self._html_note(
                f"{statut.label} — pytest printed no traceback for this test. "
                "The raw output may say more.")

        avertissement = ""
        if echec.ambiguous:
            avertissement = self._html_note(
                "Another test has the same name in this run; pytest does not "
                "print the file in its traceback headers, so this one may "
                "belong to the other.")

        resume = (
            f'<p style="margin:0 0 {t.SPACE_2}px 0;'
            f' color:{t.status_color(statut)}; font-size:{t.TEXT_MD}px;'
            f' font-weight:600;">{escape(echec.headline)}</p>')

        return titre + resume + avertissement + self._html_trace(echec.body)

    def _html_trace(self, corps: str) -> str:
        lignes = []
        for ligne in corps.splitlines():
            nature = classify_line(ligne)
            teinte = _TEINTES.get(nature, t.TEXT_MUTED)
            gras = "font-weight:600;" if nature == "exception" else ""
            nue = escape(strip_ansi(ligne)) or "&nbsp;"
            lignes.append(f'<span style="color:{teinte};{gras}">{nue}</span>')

        return (
            f'<pre style="font-family:{t.FONT_MONO}; font-size:{t.TEXT_SM}px;'
            f' margin:0 0 {t.SPACE_4}px 0;">' + "<br/>".join(lignes) + "</pre>")

    def _html_note(self, texte: str) -> str:
        return (f'<p style="margin:0 0 {t.SPACE_3}px 0; color:{t.TEXT_MUTED};'
                f' font-size:{t.TEXT_SM}px;">{escape(texte)}</p>')

    def _html_sans_echec(self, cibles, statuses: dict[int, Status]) -> str:
        vus = [statuses.get(l.index, Status.PENDING) for l in cibles]
        if all(s is Status.PENDING for s in vus):
            return self._html_note("This test has not run yet.")
        if all(s is Status.SKIPPED for s in vus):
            return self._html_note("Skipped everywhere in the last run.")

        pluriel = "every reader" if len(cibles) > 1 else "the last run"
        return (f'<p style="margin:0; color:{t.status_color(Status.PASSED)};'
                f' font-size:{t.TEXT_MD}px; font-weight:600;">'
                f"Passed on {pluriel}. Nothing to explain.</p>")

    def _copier(self) -> None:
        from PyQt5.QtWidgets import QApplication

        if self._texte_brut:
            QApplication.clipboard().setText(self._texte_brut)
