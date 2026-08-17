"""Les runs passes : les relire, les exporter, les comparer.

Un verdict seul ne dit pas grand-chose. Ce qu'on veut savoir devant un rouge,
c'est s'il est nouveau ; devant un vert, s'il tient. Cette fenetre repond aux
deux : la comparaison de deux runs montre ce qui s'est mis a echouer et ce qui
est repare, et la liste des tests instables montre ceux dont le verdict ne
veut rien dire.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from runner.domain import report
from runner.domain.history import History, compare
from runner.domain.models import Status
from runner.ui import tokens as t
from runner.ui.console_view import ConsoleView
from runner.ui.widgets import EmptyState, ErrorDialog

COLONNES = ("When", "Reader", "Passed", "Failed", "Skipped", "Error",
            "Duration", "Workspace")


def _quand(horodatage: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(horodatage))


class HistoryWindow(QDialog):
    """La liste des runs enregistres, et ce qu'on peut en faire."""

    def __init__(self, historique: History, parent=None):
        super().__init__(parent)
        self.history = historique
        self._entries: list = []

        self.setWindowTitle("Run history")
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint)
        self.setSizeGripEnabled(True)
        self.resize(1020, 620)

        self.table = QTableWidget(0, len(COLONNES))
        self.table.setHorizontalHeaderLabels(COLONNES)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Deux lignes selectionnables : c'est ce que demande la comparaison,
        # et c'est le seul geste de cette fenetre qui en attend plusieurs.
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLONNES) - 1, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.itemDoubleClicked.connect(lambda _: self.view_output())

        self.empty = EmptyState(
            "mdi.history",
            "No run recorded yet",
            "Every run you launch is kept here with its output, so you can "
            "compare it with the next one.")

        self.status = QLabel("")
        self.status.setObjectName("Muted")

        self.view_button = self._bouton("View output", self.view_output)
        self.html_button = self._bouton("Export HTML…", self.export_html)
        self.junit_button = self._bouton("Export JUnit XML…", self.export_junit)
        self.compare_button = self._bouton("Compare 2 runs", self.compare_runs)
        self.flaky_button = self._bouton("Unstable tests…", self.show_flaky)
        self.clear_button = self._bouton("Clear history", self.clear_history)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        actions.addWidget(self.status, 1)
        for bouton in (self.view_button, self.html_button, self.junit_button,
                       self.compare_button, self.flaky_button,
                       self.clear_button):
            actions.addWidget(bouton)

        fermer = QPushButton("Close")
        fermer.setObjectName("Ghost")
        fermer.clicked.connect(self.accept)
        actions.addWidget(fermer)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(self.table, 1)
        colonne.addWidget(self.empty, 1)
        colonne.addLayout(actions)

        self.refresh()

    def _bouton(self, texte: str, action) -> QPushButton:
        bouton = QPushButton(texte)
        bouton.setObjectName("Ghost")
        bouton.clicked.connect(action)
        return bouton

    # ------------------------------------------------------------- affichage

    def refresh(self) -> None:
        self._entries = self.history.entries()
        self.table.setRowCount(len(self._entries))

        for ligne, entree in enumerate(self._entries):
            valeurs = (
                _quand(entree.timestamp),
                entree.reader or "—",
                str(entree.count(Status.PASSED)),
                str(entree.count(Status.FAILED)),
                str(entree.count(Status.SKIPPED)),
                str(entree.count(Status.ERROR)),
                f"{entree.duration:.1f}s",
                entree.workspace,
            )
            for colonne, valeur in enumerate(valeurs):
                item = QTableWidgetItem(valeur)
                if colonne in (2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(ligne, colonne, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLONNES) - 1, QHeaderView.Stretch)

        vide = not self._entries
        self.table.setVisible(not vide)
        self.empty.setVisible(vide)
        self._update_actions()

    def _selection(self) -> list:
        lignes = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._entries[i] for i in lignes if 0 <= i < len(self._entries)]

    def _update_actions(self) -> None:
        choisis = self._selection()
        un_seul = len(choisis) == 1
        self.view_button.setEnabled(un_seul)
        self.html_button.setEnabled(un_seul)
        # L'export XML n'a de sens que si pytest en a ecrit un pour ce run.
        self.junit_button.setEnabled(un_seul and bool(choisis[0].junit_path))
        self.compare_button.setEnabled(len(choisis) == 2)
        self.flaky_button.setEnabled(bool(self._entries))
        self.clear_button.setEnabled(bool(self._entries))

    def _dire(self, message: str, alerte: bool = False) -> None:
        self.status.setText(message)
        couleur = t.status_color(Status.FAILED) if alerte else t.TEXT_MUTED
        self.status.setStyleSheet(
            f"color: {couleur}; font-size: {t.TEXT_SM}px; background: transparent;")

    # ---------------------------------------------------------------- actions

    def view_output(self) -> None:
        choisis = self._selection()
        if len(choisis) != 1:
            return
        entree = choisis[0]

        boite = QDialog(self)
        boite.setWindowTitle(f"Output — {entree.label}")
        boite.resize(940, 640)

        vue = ConsoleView()
        texte = entree.output()
        vue.set_text(texte or "This run kept no output.")

        fermer = QPushButton("Close")
        fermer.setObjectName("Ghost")
        fermer.clicked.connect(boite.accept)

        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(fermer)

        colonne = QVBoxLayout(boite)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        colonne.addWidget(vue, 1)
        colonne.addLayout(bas)
        boite.exec_()

    def export_html(self) -> None:
        choisis = self._selection()
        if len(choisis) != 1:
            return
        entree = choisis[0]

        propose = f"report_{entree.id}.html"
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Save the report", propose, "HTML (*.html)")
        if not chemin:
            return

        ok, message = report.write_html(entree, Path(chemin), entree.output())
        if ok:
            self._dire(f"Report written to {chemin}")
        else:
            self._dire(f"Could not write the report: {message}", alerte=True)

    def export_junit(self) -> None:
        choisis = self._selection()
        if len(choisis) != 1:
            return
        entree = choisis[0]

        propose = f"junit_{entree.id}.xml"
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Save the JUnit report", propose, "XML (*.xml)")
        if not chemin:
            return

        ok, message = report.write_junit(entree, Path(chemin))
        if ok:
            self._dire(f"JUnit XML written to {chemin}")
        else:
            self._dire(message, alerte=True)

    def compare_runs(self) -> None:
        choisis = self._selection()
        if len(choisis) != 2:
            return
        ComparisonDialog(compare(*choisis), self).exec_()

    def show_flaky(self) -> None:
        FlakyDialog(self.history.flaky(), self).exec_()

    def clear_history(self) -> None:
        from PyQt5.QtWidgets import QMessageBox

        # Effacer supprime aussi les sorties conservees : c'est irreversible,
        # et cela ne doit pas tenir a un clic mal place.
        reponse = QMessageBox.question(
            self, "Clear the history",
            f"Delete all {len(self._entries)} recorded runs, with their saved "
            "output? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return

        self.history.clear()
        self.refresh()
        self._dire("History cleared.")


class ComparisonDialog(QDialog):
    """Ce qui a change entre deux runs."""

    def __init__(self, comparaison, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparing two runs")
        self.resize(760, 600)

        entete = QLabel(
            f"<b>Reference</b>  {_quand(comparaison.older.timestamp)}"
            f"  <span style='color:{t.TEXT_MUTED}'>({comparaison.older.summary})"
            f"</span><br>"
            f"<b>Compared to</b>  {_quand(comparaison.newer.timestamp)}"
            f"  <span style='color:{t.TEXT_MUTED}'>({comparaison.newer.summary})"
            f"</span>")
        entete.setTextFormat(Qt.RichText)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(entete)

        if comparaison.unchanged:
            # Le dire franchement : une fenetre avec deux listes vides laisse
            # croire que la comparaison n'a pas tourne.
            rien = QLabel("Nothing changed between these two runs.")
            rien.setObjectName("Muted")
            colonne.addWidget(rien)

        sections = (
            ("New failures", comparaison.newly_failed, Status.FAILED,
             "No test started failing."),
            ("Fixed", comparaison.newly_fixed, Status.PASSED,
             "No test was fixed."),
            ("Still failing", comparaison.still_failing, Status.SKIPPED,
             "Nothing was already failing."),
        )
        for titre, nodeids, statut, vide in sections:
            # La place va aux sections qui ont quelque chose a montrer. A part
            # egale, une section vide poussait sa phrase a cent pixels de son
            # titre et la liste voisine se retrouvait a l'etroit.
            colonne.addWidget(self._section(titre, nodeids, statut, vide),
                              1 if nodeids else 0)
        if not any(n for _, n, _, _ in sections):
            colonne.addStretch(1)

        fermer = QPushButton("Close")
        fermer.setObjectName("Ghost")
        fermer.clicked.connect(self.accept)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(fermer)
        colonne.addLayout(bas)

    def _section(self, titre: str, nodeids, statut: Status, vide: str) -> QWidget:
        boite = QWidget()
        interieur = QVBoxLayout(boite)
        interieur.setContentsMargins(0, 0, 0, 0)
        interieur.setSpacing(t.SPACE_1)

        etiquette = QLabel(f"{titre} ({len(nodeids)})")
        etiquette.setStyleSheet(
            f"color: {t.status_color(statut)}; font-weight: 600;"
            f"font-size: {t.TEXT_MD}px; background: transparent;")
        interieur.addWidget(etiquette)

        if not nodeids:
            rien = QLabel(vide)
            rien.setObjectName("Faint")
            interieur.addWidget(rien)
            return boite

        table = QTableWidget(len(nodeids), 1)
        table.setHorizontalHeaderLabels(["Test"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for ligne, nodeid in enumerate(nodeids):
            table.setItem(ligne, 0, QTableWidgetItem(nodeid))
        interieur.addWidget(table)
        return boite


class FlakyDialog(QDialog):
    """Les tests dont le verdict ne tient pas d'un run a l'autre."""

    def __init__(self, instables, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unstable tests")
        self.resize(820, 560)

        explication = QLabel(
            "Tests that both passed and failed across the recorded runs. A "
            "test that always fails is not here — it is broken, which is a "
            "different conversation.")
        explication.setObjectName("Muted")
        explication.setWordWrap(True)

        table = QTableWidget(len(instables), 5)
        table.setHorizontalHeaderLabels(
            ["Test", "Reader", "Runs", "Failed", "Failure rate"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for ligne, essai in enumerate(instables):
            # Le lecteur est une colonne a lui : l'instabilite se mesure sur
            # un lecteur donne, et savoir lequel est la moitie de l'enquete.
            cellules = (essai.nodeid, essai.reader or "—", str(essai.seen),
                        str(essai.failed), f"{100 * essai.ratio:.0f} %")
            for colonne, valeur in enumerate(cellules):
                item = QTableWidgetItem(valeur)
                if colonne:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(ligne, colonne, item)

        fermer = QPushButton("Close")
        fermer.setObjectName("Ghost")
        fermer.clicked.connect(self.accept)
        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(fermer)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_3)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(explication)

        if not instables:
            rien = QLabel("No unstable test in the recorded runs.")
            rien.setObjectName("Faint")
            colonne.addWidget(rien)
        colonne.addWidget(table, 1)
        colonne.addLayout(bas)
