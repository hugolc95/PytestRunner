"""Panneau de droite : la fiche d'un test, la sortie brute, les logs.

L'ordre des onglets est un choix, pas un hasard. Mesure faite sur un run reel
de 160 tests dont 44 en echec, la console produit 292 lignes :

    160  verdicts       -> deja dans l'arbre, une colonne par lecteur
      9  bannieres      -> jamais lues
      2  vides
    121  traces d'echec <- la SEULE chose qu'on ne trouve nulle part ailleurs

Le seul apport propre de la console represente 41 % de ses lignes, et c'est
justement ce qu'elle rend le plus difficile a trouver : il faut passer neuf
lignes avant la premiere trace, puis chercher la bonne parmi quarante-quatre.

D'ou la disposition : `Detail` d'abord, qui repond a la question posee (ce test
la, pourquoi), et la console juste derriere, entiere et copiable, pour tout ce
que la fiche ne peut pas deviner.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain import failures as failures_mod
from runner.domain import logs
from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.source import path_of as source_path
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.console_view import ConsoleView
from runner.ui.detail_panel import DetailPanel
from runner.ui.source_panel import SourcePanel

ONGLET_DETAIL = 0
ONGLET_SOURCE = 1
ONGLET_OUTPUT = 2
ONGLET_LOGS = 3


class ReaderViews(QWidget):
    """Une console par lecteur : une seule visible, ou toutes.

    Sert deux fois -- la sortie pytest et les logs -- avec un sens de
    comparaison different. Les sorties defilent, on les empile pour garder la
    largeur ; les logs se comparent ligne a ligne, on les met cote a cote.
    """

    reader_selected = pyqtSignal(int)

    def __init__(self, orientation=Qt.Vertical, sync_scroll: bool = False,
                 show_lens: bool = True, parent=None):
        super().__init__(parent)
        self._sync = sync_scroll
        self._show_lens = show_lens
        self._defile = False
        self._readers: tuple[Reader, ...] = ()

        self.views: list[ConsoleView] = []
        self.headers: list[QLabel] = []

        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)

        self.compare = QPushButton()
        self.compare.setObjectName("IconSm")
        self.compare.setIcon(icons.icon("mdi.view-split-vertical", t.TEXT_MUTED))
        self.compare.setCheckable(True)
        self.compare.setToolTip("Compare every reader  (Ctrl+Shift+D)")
        self.compare.setVisible(False)
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

    def _add_view(self) -> ConsoleView:
        vue = ConsoleView(show_lens=self._show_lens)

        entete = QLabel()
        entete.setVisible(False)
        entete.setObjectName("Faint")

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
            self.views[index].append(texte)

    def set_text(self, index: int, texte: str, entete: str = "",
                 chemin: str = "") -> None:
        if 0 <= index < len(self.views):
            self.views[index].set_text(texte)
            self.headers[index].setText(entete)
            # Le chemin en infobulle plutot qu'en clair : deux logs se
            # ressemblent beaucoup et savoir DUQUEL on parle est la premiere
            # chose qu'on verifie, mais l'afficher en entier mangerait la
            # largeur de la console.
            self.headers[index].setToolTip(chemin)

    def clear(self) -> None:
        for vue in self.views:
            vue.clear()
        for entete in self.headers:
            entete.clear()


class ResultsPanel(QWidget):
    """Fiche du test, sortie brute et logs, derriere un etat vide au demarrage."""

    reader_selected = pyqtSignal(int)
    test_chosen = pyqtSignal(str)   # relaye la fiche de groupe vers l'arbre

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_root: Path | None = None
        self._readers: tuple[Reader, ...] = ()
        self._sorties: dict[int, str] = {}
        self._index_echecs: dict[int, dict] = {}
        self._nodeid = ""
        self._statuses: dict[int, Status] = {}

        self.detail = DetailPanel()
        self.detail.open_output.connect(self.show_output)
        self.detail.test_chosen.connect(self.test_chosen)

        self.source = SourcePanel()

        self.output = ReaderViews(Qt.Vertical)
        self.logs = ReaderViews(Qt.Horizontal, sync_scroll=True, show_lens=False)

        # Les trois panneaux suivent le meme lecteur : lire le log de l'un en
        # regardant la sortie de l'autre n'a pas de sens.
        self.output.reader_selected.connect(self._on_reader, Qt.UniqueConnection)
        self.logs.reader_selected.connect(self._on_reader, Qt.UniqueConnection)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.detail,
                         icons.icon("mdi.text-box-search-outline", t.TEXT_MUTED),
                         "Detail")
        self.tabs.addTab(self.source,
                         icons.icon("mdi.file-code-outline", t.TEXT_MUTED),
                         "Source")
        self.tabs.addTab(self.output, icons.icon("mdi.console", t.TEXT_MUTED),
                         "Output")
        self.tabs.addTab(self.logs,
                         icons.icon("mdi.file-document-outline", t.TEXT_MUTED),
                         "Logs")
        self.tabs.setTabToolTip(ONGLET_DETAIL,
                                "What happened to the selected test  (Ctrl+1)")
        self.tabs.setTabToolTip(ONGLET_SOURCE,
                                "The file of the selected test, editable  (Ctrl+2)")
        self.tabs.setTabToolTip(ONGLET_OUTPUT, "Everything pytest wrote  (Ctrl+3)")
        self.tabs.setTabToolTip(ONGLET_LOGS,
                                "The .log files of the selected test  (Ctrl+4)")

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self.tabs)

    # ------------------------------------------------------------- navigation

    def restyle(self) -> None:
        """Fait redescendre le changement de theme dans tout le panneau."""
        for vues in (self.output, self.logs):
            for vue in vues.views:
                vue.restyle()
        self.source.restyle()
        for position, glyphe in (
                (ONGLET_DETAIL, "mdi.text-box-search-outline"),
                (ONGLET_SOURCE, "mdi.file-code-outline"),
                (ONGLET_OUTPUT, "mdi.console"),
                (ONGLET_LOGS, "mdi.file-document-outline")):
            self.tabs.setTabIcon(position, icons.icon(glyphe, t.TEXT_MUTED))

    def show_tab(self, position: int) -> None:
        self.tabs.setCurrentIndex(position)

    def show_output(self) -> None:
        self.show_tab(ONGLET_OUTPUT)

    def _on_reader(self, index: int) -> None:
        self.output.select_silently(index)
        self.logs.select_silently(index)
        self.reader_selected.emit(index)

    # ------------------------------------------------------------------- run

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        """Nouvelle collecte : les lecteurs changent, la selection ne vaut plus."""
        self._readers = tuple(readers)
        self._nodeid = ""
        self._statuses = {}
        self._sorties.clear()
        self._index_echecs.clear()
        self.detail.clear()
        self.source.save()
        self.source.clear()
        self.output.set_readers(readers)
        self.logs.set_readers(readers)

    def begin_run(self) -> None:
        """Vide les vues sans changer d'onglet.

        Basculer d'office sur la console au lancement volait l'ecran a
        l'utilisateur : l'avancement se lit dans l'arbre et dans la barre
        d'etat, la console n'a pas a s'imposer.
        """
        self.output.clear()
        self.logs.clear()
        self._sorties.clear()
        self._index_echecs.clear()
        self._refresh_detail()

    def set_report(self, rapport: ReaderReport) -> None:
        """Range la sortie complete d'un lecteur qui vient de finir.

        Les traces d'echec ne sont extraites qu'a la demande : sur un run de
        plusieurs milliers de lignes, les decouper a chaque fin de lecteur
        couterait pour rien si personne ne clique.
        """
        index = rapport.reader.index
        self._sorties[index] = rapport.output
        self._index_echecs.pop(index, None)
        self._refresh_detail()

    def append_output(self, index: int, texte: str) -> None:
        self.output.append(index, texte)

    # ---------------------------------------------------------------- detail

    def show_test(self, nodeid: str, statuses: dict[int, Status],
                  workspace: str = "") -> None:
        """Selectionne un test : sa fiche, sa source, et ses logs."""
        self._nodeid = nodeid
        self._statuses = dict(statuses)
        self._refresh_detail()
        self.source.show_file(source_path(workspace, nodeid), nodeid)
        self.show_logs_for(nodeid, self._readers)

    def show_group(self, path: str, name: str, readers, counts: dict,
                   failures: list, source: Path | None = None,
                   jump_nodeid: str = "") -> None:
        """Selectionne un regroupement : son bilan, et sa source s'il en a une.

        Un module a un fichier, un dossier n'en a pas. Laisser celui du test
        precedent quand il n'y en a pas ferait croire qu'il parle de ce qu'on
        vient de cliquer ; le refuser a un module priverait du geste le plus
        courant, cliquer un `.py` pour le lire.

        Les logs, eux, restent vides : ils sont ecrits PAR TEST, et il n'y en
        a aucun qui reponde pour un lot entier.
        """
        self._nodeid = ""
        self._statuses = {}
        self.detail.show_group(path, name, tuple(readers), counts, failures)
        self.source.show_file(source, jump_nodeid)
        self.logs.clear()

    def update_statuses(self, nodeid: str, statuses: dict[int, Status]) -> None:
        """Rafraichit la fiche si elle porte sur ce test, sans toucher aux logs.

        Appele a chaque resultat pendant un run : relire les .log a ce
        rythme-la balayerait le disque des centaines de fois.
        """
        if nodeid and nodeid == self._nodeid:
            self._statuses = dict(statuses)
            self._refresh_detail()

    def _refresh_detail(self) -> None:
        if not self._nodeid:
            self.detail.clear()
            return
        cibles = self._readers or (Reader("", 0),)
        echecs = {
            lecteur.index: failures_mod.failure_for(
                self._echecs_de(lecteur.index), self._nodeid)
            for lecteur in cibles
        }
        self.detail.show_test(self._nodeid, self._readers, self._statuses, echecs)

    def _echecs_de(self, reader_index: int) -> dict:
        index = self._index_echecs.get(reader_index)
        if index is None:
            index = failures_mod.index_failures(self._sorties.get(reader_index, ""))
            self._index_echecs[reader_index] = index
        return index

    # ------------------------------------------------------------------ logs

    def set_log_root(self, racine: Path | None) -> None:
        self._log_root = racine

    def show_logs_for(self, nodeid: str, readers: tuple[Reader, ...]) -> None:
        """Charge le .log de ce test, un par lecteur."""
        if not nodeid or self._log_root is None:
            return

        cibles = readers or (Reader("", 0),)
        for lecteur in cibles:
            chemin = logs.find_test_log(self._log_root, nodeid, lecteur.name)
            if chemin is None:
                self.logs.set_text(lecteur.index,
                                   self._rien_trouve(lecteur),
                                   lecteur.name or "")
                continue
            try:
                contenu = chemin.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                contenu = f"Could not read {chemin}:\n{exc}"
            # Le chemin en tete : deux logs se ressemblent beaucoup, et savoir
            # DUQUEL on parle est la premiere chose qu'on veut verifier.
            self.logs.set_text(lecteur.index, contenu,
                               lecteur.name or chemin.name, str(chemin))

    def _rien_trouve(self, lecteur: Reader) -> str:
        """Dire ou l'on a cherche, et pas seulement qu'on n'a rien trouve.

        « No log found » tout seul se lit comme une panne de l'outil. La liste
        des dossiers examines montre au contraire tout de suite si le dossier
        est vide, si le run n'a rien ecrit, ou si le reglage du chemin des logs
        ne pointe pas la ou l'on croyait.
        """
        ou = logs.places_searched(self._log_root)
        lignes = ["No log found for this test"
                  + (f" on {lecteur.name}." if lecteur.name else ".")]

        if not ou:
            lignes += ["", f"The log folder does not exist yet:",
                       f"    {self._log_root}", "",
                       "It is created by the workspace conftest on the first "
                       "run. Check the log path setting if the run did write "
                       "somewhere else."]
        else:
            lignes += ["", "Looked in, most recent first:"]
            lignes += [f"    {chemin}" for chemin in ou]
        return "\n".join(lignes)
