"""Fenetre principale : assemblage des zones, aucun travail metier ici.

Chaque slot se contente de traduire un geste en appel de service ou en mise a
jour de modele. Rien de bloquant : la collecte et les runs vivent dans des
QThread, la fenetre ne fait qu'ecouter leurs signaux.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QModelIndex, QSettings, Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from runner.domain.models import Reader, RunRequest, Status
from runner.domain.tree import build_tree, collapse_single_class
from runner.domain.workspace import Workspace
from runner.services.run_service import CollectWorker, RunService
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.results_panel import ResultsPanel
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import EmptyState, ErrorDialog, SearchBar, StatusPill

ORG, APP = "PytestRunner", "Runner"

# Cles QSettings. Regroupees ici : une cle ecrite a la main quelque part finit
# par diverger de celle qu'on relit.
K_GEOMETRY = "window/geometry"
K_STATE = "window/state"
K_SPLIT_MAIN = "window/split_main"
K_RECENT = "workspace/recent"
K_LAST = "workspace/last"
K_TREE_COLS = "tree/columns"


class MainWindow(QMainWindow):
    """Fenetre unique de l'application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Runner")
        self.setMinimumSize(1100, 640)

        self.settings = QSettings(ORG, APP)
        self.workspace: Workspace | None = None
        self.service = RunService(self)
        self._collector: CollectWorker | None = None
        self._matches: list[str] = []
        self._match_index = -1
        self._elapsed = QTimer(self)
        self._elapsed.setInterval(1000)
        self._elapsed.timeout.connect(self._tick)
        self._seconds = 0

        self.model = TestTreeModel(self)
        self.model.selection_changed.connect(self._on_selection_changed)

        self._build_ui()
        self._build_menus()
        self._connect_service()
        self._restore()
        self._update_actions()

    # =====================================================================
    # Construction
    # =====================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        colonne = QVBoxLayout(central)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_2)
        colonne.setSpacing(t.SPACE_3)

        colonne.addWidget(self._build_command_bar())

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self._build_left())
        self.split.addWidget(self._build_right())
        # 45/55 : a 40/60 les noms de tests parametres etaient tronques alors
        # que la sortie avait de la place a revendre.
        self.split.setStretchFactor(0, 45)
        self.split.setStretchFactor(1, 55)
        colonne.addWidget(self.split, 1)

        self.setCentralWidget(central)
        self._build_status_bar()

    def _build_command_bar(self) -> QWidget:
        barre = QWidget()
        ligne = QHBoxLayout(barre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)

        self.workspace_combo = QComboBox()
        self.workspace_combo.setEditable(True)
        self.workspace_combo.setInsertPolicy(QComboBox.NoInsert)
        self.workspace_combo.lineEdit().setPlaceholderText("Path to a folder of tests…")
        # Un chemin n'a pas besoin de mille pixels : au-dela, le champ ecrase
        # les actions qui comptent et la barre perd son equilibre.
        self.workspace_combo.setMaximumWidth(560)
        self.workspace_combo.setMinimumWidth(260)
        self.workspace_combo.lineEdit().returnPressed.connect(self.load_workspace)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.setObjectName("Ghost")
        self.browse_button.setIcon(icons.icon("mdi.folder-open-outline", t.TEXT_MUTED))
        self.browse_button.clicked.connect(self.browse_workspace)

        self.load_button = QPushButton("Load")
        self.load_button.setToolTip("Collect the tests of this workspace  (Ctrl+O)")
        self.load_button.clicked.connect(self.load_workspace)

        self.run_button = QPushButton("Run tests")
        self.run_button.setObjectName("Primary")
        self.run_button.setIcon(icons.icon("mdi.play", "#06101f"))
        self.run_button.setToolTip("Run the selected tests  (F5)")
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.clicked.connect(self.run_selected)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setIcon(icons.icon("mdi.stop", t.TEXT_MUTED))
        self.stop_button.setToolTip("Stop the current run  (Esc)")
        self.stop_button.clicked.connect(self.stop_run)

        ligne.addWidget(self.workspace_combo)
        ligne.addWidget(self.browse_button)
        ligne.addWidget(self.load_button)
        ligne.addStretch(1)
        ligne.addWidget(self.stop_button)
        ligne.addWidget(self.run_button)
        return barre

    def _build_left(self) -> QWidget:
        panneau = QWidget()
        colonne = QVBoxLayout(panneau)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        outils = QHBoxLayout()
        outils.setSpacing(t.SPACE_2)

        self.search = SearchBar()
        self.search.query_changed.connect(self._on_search)
        self.search.next_match.connect(lambda: self._goto_match(1))
        self.search.previous_match.connect(lambda: self._goto_match(-1))

        self.select_all_button = self._quiet("mdi.checkbox-multiple-marked-outline",
                                             "Select all  (Ctrl+A)",
                                             lambda: self.model.set_all_checked(True))
        self.select_none_button = self._quiet("mdi.checkbox-multiple-blank-outline",
                                              "Clear selection  (Ctrl+Shift+A)",
                                              lambda: self.model.set_all_checked(False))
        self.expand_button = self._quiet("mdi.unfold-more-horizontal", "Expand all",
                                         lambda: self.tree.expandAll())
        self.collapse_button = self._quiet("mdi.unfold-less-horizontal", "Collapse all",
                                           lambda: self.tree.collapseAll())

        outils.addWidget(self.search, 1)
        # Groupes par intention : cocher d'un cote, deplier de l'autre. Quatre
        # icones alignees a intervalle egal ne disaient pas lesquelles vont
        # ensemble.
        outils.addSpacing(t.SPACE_2)
        outils.addWidget(self.select_all_button)
        outils.addWidget(self.select_none_button)
        outils.addSpacing(t.SPACE_3)
        outils.addWidget(self.expand_button)
        outils.addWidget(self.collapse_button)

        # Chercher et cocher n'ont aucun sens tant qu'aucun test n'est charge :
        # des controles actifs sur du vide laissent croire a une panne.
        self.tree_toolbar = QWidget()
        self.tree_toolbar.setLayout(outils)
        self.tree_toolbar.setVisible(False)
        colonne.addWidget(self.tree_toolbar)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setUniformRowHeights(True)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setHeaderHidden(False)
        self.tree.clicked.connect(self._on_tree_clicked)

        entete = self.tree.header()
        entete.setStretchLastSection(False)
        entete.setSectionResizeMode(0, QHeaderView.Stretch)

        self.tree_empty = EmptyState(
            "mdi.folder-search-outline",
            "No workspace loaded",
            "Choose the folder that holds your tests. Everything pytest can "
            "collect there shows up as a tree.",
            action="Browse for a folder…",
            raccourci="Ctrl+O",
        )
        self.tree_empty.action_clicked.connect(self.browse_workspace)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self.tree_empty)
        self.left_stack.addWidget(self.tree)
        colonne.addWidget(self.left_stack, 1)

        self.selection_label = QLabel("")
        self.selection_label.setStyleSheet(theme.faint())
        colonne.addWidget(self.selection_label)
        return panneau

    def _quiet(self, glyph: str, infobulle: str, slot) -> QPushButton:
        bouton = QPushButton()
        bouton.setObjectName("Icon")
        bouton.setIcon(icons.icon(glyph, t.TEXT_MUTED))
        bouton.setToolTip(infobulle)
        bouton.clicked.connect(slot)
        return bouton

    def _build_right(self) -> QWidget:
        self.results = ResultsPanel()
        self.results.reader_selected.connect(self._on_reader_selected)
        return self.results

    def _build_status_bar(self) -> None:
        """L'avancement vit en bas, pas en haut.

        Un bandeau de compteurs en haut occupe de la hauteur en permanence pour
        une information qui n'existe que pendant et apres un run. La barre
        d'etat est faite pour ca, et c'est la que l'oeil la cherche.
        """
        barre = self.statusBar()

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(theme.muted())

        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet(theme.faint())

        self.pills = {
            statut: StatusPill(statut)
            for statut in (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR)
        }

        barre.addWidget(self.status_label)
        barre.addWidget(self.progress)
        barre.addWidget(self.elapsed_label)
        barre.addPermanentWidget(QLabel(""))
        for pastille in self.pills.values():
            barre.addPermanentWidget(pastille)

    def _build_menus(self) -> None:
        """Menus et raccourcis. Chaque action frequente en a un, visible ici."""
        fichier = self.menuBar().addMenu("&File")
        self._action(fichier, "Open workspace…", QKeySequence.Open, self.browse_workspace,
                     "mdi.folder-open-outline")
        self._action(fichier, "Reload tests", QKeySequence.Refresh, self.load_workspace,
                     "mdi.refresh")
        fichier.addSeparator()
        self._action(fichier, "Quit", QKeySequence.Quit, self.close, "mdi.exit-to-app")

        executer = self.menuBar().addMenu("&Run")
        self.act_run = self._action(executer, "Run selected tests", "F5",
                                    self.run_selected, "mdi.play")
        self.act_rerun = self._action(executer, "Re-run failed", "F6",
                                      self.rerun_failed, "mdi.replay")
        self.act_stop = self._action(executer, "Stop", "Esc", self.stop_run, "mdi.stop")

        selection = self.menuBar().addMenu("&Select")
        self._action(selection, "All", QKeySequence.SelectAll,
                     lambda: self.model.set_all_checked(True))
        self._action(selection, "None", "Ctrl+Shift+A",
                     lambda: self.model.set_all_checked(False))
        selection.addSeparator()
        self.act_diverge = self._action(
            selection, "Only where readers disagree", "Ctrl+D",
            self.select_divergent, "mdi.call-split")

        vue = self.menuBar().addMenu("&View")
        self._action(vue, "Find a test", QKeySequence.Find,
                     lambda: self.search.field.setFocus(), "mdi.magnify")
        self._action(vue, "Compare readers side by side", "Ctrl+Shift+D",
                     self._toggle_compare, "mdi.view-split-vertical")

    def _action(self, menu, texte: str, raccourci, slot, glyph: str = ""):
        action = menu.addAction(texte)
        if glyph:
            action.setIcon(icons.icon(glyph, t.TEXT_MUTED))
        if raccourci:
            action.setShortcut(raccourci)
            # Le raccourci est deja affiche par le menu ; l'infobulle sert aux
            # boutons qui declenchent la meme action.
            action.setToolTip(f"{texte}  ({QKeySequence(raccourci).toString()})")
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _connect_service(self) -> None:
        self.service.started.connect(self._on_run_started)
        self.service.line.connect(self.results.output.append)
        self.service.outcome.connect(self._on_outcome)
        self.service.progress.connect(self._on_progress)
        self.service.finished.connect(self._on_run_finished)

    # =====================================================================
    # Workspace
    # =====================================================================

    @pyqtSlot()
    def browse_workspace(self) -> None:
        depart = self.workspace_combo.currentText() or str(Path.home())
        chemin = QFileDialog.getExistingDirectory(self, "Choose a workspace", depart)
        if chemin:
            self.workspace_combo.setCurrentText(chemin)
            self.load_workspace()

    @pyqtSlot()
    def load_workspace(self) -> None:
        chemin = self.workspace_combo.currentText().strip()
        if not chemin:
            self.browse_workspace()
            return
        if not Path(chemin).is_dir():
            ErrorDialog.show_error(self, "Cannot load", "That path is not a folder.",
                                   chemin)
            return
        if self._collector is not None and self._collector.isRunning():
            return

        self.workspace = Workspace.load(chemin)
        self._remember_workspace(chemin)

        self.status_label.setText("Collecting tests…")
        self.load_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indetermine : la duree est inconnue

        self._collector = CollectWorker(
            self.workspace.path, self.workspace.interpreter, self.workspace.env, self)
        self._collector.collected.connect(self._on_collected)
        self._collector.failed.connect(self._on_collect_failed)
        self._collector.start()

    @pyqtSlot(list)
    def _on_collected(self, nodeids: list) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.load_button.setEnabled(True)

        self.model.set_tree(collapse_single_class(build_tree(nodeids)))
        lecteurs = self.workspace.readers if self.workspace else ()
        self.model.set_readers(lecteurs)
        self.results.set_readers(lecteurs)
        self.results.set_log_root(self.workspace.log_root if self.workspace else None)
        self._size_reader_columns()

        if not nodeids:
            self.tree_empty.update_text(
                "No tests collected",
                "pytest found no test in this folder. Check that the files are "
                "named test_*.py and that the interpreter has pytest installed.")
            self.left_stack.setCurrentWidget(self.tree_empty)
        else:
            self.left_stack.setCurrentWidget(self.tree)
            self.tree.expandToDepth(1)
        self.tree_toolbar.setVisible(bool(nodeids))

        nom = Path(self.workspace.path).name if self.workspace else ""
        details = f"{len(nodeids)} tests"
        if lecteurs:
            details += f" · {len(lecteurs)} readers"
        self.status_label.setText(f"{nom} — {details}")
        self.setWindowTitle(f"Runner — {nom}" if nom else "Runner")
        self._update_actions()

    @pyqtSlot(str)
    def _on_collect_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.load_button.setEnabled(True)
        self.status_label.setText("Collection failed")

        # Une phrase, et le detail seulement si on le demande.
        premiere = message.strip().splitlines()[0] if message.strip() else "Unknown error"
        ErrorDialog.show_error(self, "Could not collect the tests", premiere, message)
        self._update_actions()

    def _size_reader_columns(self) -> None:
        """Chaque colonne de lecteur prend la largeur de son titre.

        Une largeur fixe tronquait les noms (`smo11Secur`), qui sont justement
        ce qui distingue une colonne de l'autre.
        """
        entete = self.tree.header()
        for colonne in range(1, self.model.columnCount()):
            entete.setSectionResizeMode(colonne, QHeaderView.ResizeToContents)

    def _remember_workspace(self, chemin: str) -> None:
        recents = [chemin] + [p for p in self.settings.value(K_RECENT, [], type=list)
                              if p != chemin]
        recents = recents[:8]
        self.settings.setValue(K_RECENT, recents)
        self.settings.setValue(K_LAST, chemin)

        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        self.workspace_combo.addItems(recents)
        self.workspace_combo.setCurrentText(chemin)
        self.workspace_combo.blockSignals(False)

    # =====================================================================
    # Run
    # =====================================================================

    @pyqtSlot()
    def run_selected(self) -> None:
        self._start(self.model.checked_nodeids())

    @pyqtSlot()
    def rerun_failed(self) -> None:
        echecs = self.model.failed_nodeids()
        if not echecs:
            self.status_label.setText("No failed test to re-run")
            return
        self._start(echecs)

    def _start(self, nodeids: list) -> None:
        if self.workspace is None or not nodeids or self.service.busy:
            return

        requete = RunRequest(
            workspace=self.workspace.path,
            interpreter=self.workspace.interpreter,
            nodeids=tuple(nodeids),
            readers=self.workspace.readers,
            config_path=self.workspace.config_path,
        )
        self.service.start(requete, self.workspace.env)

    @pyqtSlot()
    def stop_run(self) -> None:
        if self.service.busy:
            self.service.cancel()
            self.status_label.setText("Stopping…")

    @pyqtSlot(object)
    def _on_run_started(self, request: RunRequest) -> None:
        self.model.clear_statuses()
        self.results.begin_run()

        self.progress.setVisible(True)
        self.progress.setRange(0, max(1, request.total_tests))
        self.progress.setValue(0)
        for pastille in self.pills.values():
            pastille.set_value(0)

        self._seconds = 0
        self.elapsed_label.setText("0s")
        self._elapsed.start()
        self.status_label.setText(f"Running {len(request.nodeids)} tests…")
        self._update_actions()

    @pyqtSlot(object)
    def _on_outcome(self, outcome) -> None:
        connu = self.model.apply_outcome(outcome.nodeid, outcome.status,
                                         outcome.reader_index)
        if not connu:
            # Collecte non reproductible : le test a tourne sous un identifiant
            # que l'arbre ne connait pas. Le signaler vaut mieux que le perdre.
            self.status_label.setText(f"Unexpected test id: {outcome.nodeid}")

        pastille = self.pills.get(outcome.status)
        if pastille is not None:
            pastille.set_value(pastille.value() + 1)

    @pyqtSlot(int, int)
    def _on_progress(self, faits: int, total: int) -> None:
        self.progress.setValue(faits)
        restants = max(0, total - faits)
        self.status_label.setText(f"Running… {restants} left")

    @pyqtSlot(list)
    def _on_run_finished(self, rapports: list) -> None:
        self._elapsed.stop()
        self.progress.setVisible(False)

        annule = any(r.cancelled for r in rapports)
        echecs = sum(r.failed for r in rapports)
        if annule:
            resume = "Run stopped"
        elif echecs:
            resume = f"{echecs} failed"
        else:
            resume = "All tests passed"
        self.status_label.setText(f"{resume} · {self._seconds}s")
        # La duree est deja dans le resume : la laisser aussi a cote
        # l'afficherait deux fois.
        self.elapsed_label.clear()
        self._update_actions()

    def _tick(self) -> None:
        self._seconds += 1
        self.elapsed_label.setText(f"{self._seconds}s")

    # =====================================================================
    # Interactions de l'arbre
    # =====================================================================

    @pyqtSlot(QModelIndex)
    def _on_tree_clicked(self, index: QModelIndex) -> None:
        nodeid = self.model.data(index.siblingAtColumn(0), NODEID_ROLE)
        if nodeid:
            self.results.show_logs_for(
                nodeid, self.workspace.readers if self.workspace else ())

    @pyqtSlot(int, int)
    def _on_selection_changed(self, coches: int, total: int) -> None:
        self.selection_label.setText(f"{coches} of {total} tests selected")
        self._update_actions()

    @pyqtSlot(int)
    def _on_reader_selected(self, index: int) -> None:
        lecteurs = self.workspace.readers if self.workspace else ()
        if 0 <= index < len(lecteurs):
            self.status_label.setText(f"Showing {lecteurs[index].name}")

    @pyqtSlot()
    def select_divergent(self) -> None:
        """Ne garde coches que les tests sur lesquels les lecteurs different.

        C'est la question qui motive un run multi-lecteur : la reponse doit
        etre a un raccourci, pas a un tri manuel.
        """
        divergents = self.model.divergent_nodeids()
        if not divergents:
            self.status_label.setText("Every reader agrees so far")
            return
        self.model.set_all_checked(False)
        for nodeid in divergents:
            index = self.model.index_for_nodeid(nodeid)
            if index.isValid():
                self.model.setData(index, Qt.Checked, Qt.CheckStateRole)
        self.status_label.setText(f"{len(divergents)} tests where readers disagree")

    def _toggle_compare(self) -> None:
        courant = self.results.tabs.currentWidget()
        if hasattr(courant, "toggle_compare"):
            courant.toggle_compare()

    # ----------------------------------------------------------- recherche

    @pyqtSlot(str)
    def _on_search(self, texte: str) -> None:
        requete = texte.strip().lower()
        self._matches = []
        if requete:
            for nodeid in self._all_nodeids():
                if requete in nodeid.lower():
                    self._matches.append(nodeid)
        self._match_index = 0 if self._matches else -1
        if self._matches:
            self._reveal(self._matches[0])
        self.search.set_matches(self._match_index + 1, len(self._matches))

    def _all_nodeids(self) -> list:
        return [nodeid for nodeid in self.model._by_nodeid]  # noqa: SLF001

    def _goto_match(self, pas: int) -> None:
        if not self._matches:
            return
        self._match_index = (self._match_index + pas) % len(self._matches)
        self._reveal(self._matches[self._match_index])
        self.search.set_matches(self._match_index + 1, len(self._matches))

    def _reveal(self, nodeid: str) -> None:
        index = self.model.index_for_nodeid(nodeid)
        if not index.isValid():
            return
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index, QAbstractItemView.PositionAtCenter)

    # =====================================================================
    # Etat des actions, persistance
    # =====================================================================

    def _update_actions(self) -> None:
        charge = self.workspace is not None
        occupe = self.service.busy
        coches, _ = self.model.counts()

        self.run_button.setEnabled(charge and coches > 0 and not occupe)
        self.stop_button.setEnabled(occupe)
        self.act_run.setEnabled(self.run_button.isEnabled())
        self.act_stop.setEnabled(occupe)
        self.act_rerun.setEnabled(charge and not occupe
                                  and bool(self.model.failed_nodeids()))
        self.act_diverge.setEnabled(len(self.model.readers) > 1)

    def _restore(self) -> None:
        geometrie = self.settings.value(K_GEOMETRY)
        if geometrie is not None:
            self.restoreGeometry(geometrie)
        etat = self.settings.value(K_STATE)
        if etat is not None:
            self.restoreState(etat)
        tailles = self.settings.value(K_SPLIT_MAIN)
        if tailles is not None:
            self.split.restoreState(tailles)

        recents = self.settings.value(K_RECENT, [], type=list)
        self.workspace_combo.addItems(recents)
        dernier = self.settings.value(K_LAST, "", type=str)
        if dernier:
            self.workspace_combo.setCurrentText(dernier)

        colonnes = self.settings.value(K_TREE_COLS)
        if colonnes is not None:
            self.tree.header().restoreState(colonnes)

    def closeEvent(self, event) -> None:
        self.settings.setValue(K_GEOMETRY, self.saveGeometry())
        self.settings.setValue(K_STATE, self.saveState())
        self.settings.setValue(K_SPLIT_MAIN, self.split.saveState())
        self.settings.setValue(K_TREE_COLS, self.tree.header().saveState())

        if self.service.busy:
            self.service.cancel()
            self.service.wait(3000)
        super().closeEvent(event)
