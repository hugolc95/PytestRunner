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

from runner.domain import interpreter as interpreter_mod
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.tree import build_tree, collapse_single_class
from runner.domain.workspace import MODE_SEQUENTIEL, Workspace
from runner.services.run_service import CollectWorker, RunService
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.interpreter_dialog import InterpreterDialog
from runner.ui.marker_bar import MarkerFilter
from runner.ui.results_panel import (
    ONGLET_DETAIL,
    ONGLET_LOGS,
    ONGLET_OUTPUT,
    ONGLET_SOURCE,
    ResultsPanel,
)
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import (
    EmptyState,
    ErrorDialog,
    ReaderBar,
    RemainingPill,
    SearchBar,
    StatusPill,
)

ORG, APP = "PytestRunner", "Runner"

# Cles QSettings. Regroupees ici : une cle ecrite a la main quelque part finit
# par diverger de celle qu'on relit.
K_GEOMETRY = "window/geometry"
K_STATE = "window/state"
K_SPLIT_MAIN = "window/split_main"
K_RECENT = "workspace/recent"
K_LAST = "workspace/last"
K_TREE_COLS = "tree/columns"
K_INTERPRETER = "interpreter/override"
K_THEME = "window/theme"


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
        self._markers_by_nodeid: dict[str, tuple[str, ...]] = {}
        self._match_index = -1
        # Reglage global, distinct de celui qu'un workspace peut imposer dans
        # sa configuration -- celui-la garde toujours la priorite.
        self._interpreter_override = ""
        # Statut dont on ne montre que les tests, ou None pour tout montrer.
        self._status_filter: Status | None = None
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

        # Sous la barre de commande, pas dans l'arbre : le choix des lecteurs
        # porte sur le RUN, comme les boutons juste au-dessus, et non sur la
        # selection des tests.
        self.readers_bar = ReaderBar()
        self.readers_bar.changed.connect(self._on_readers_changed)
        colonne.addWidget(self.readers_bar)

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

        # Vert et non l'accent bleu : « lancer » et « arreter » sont les deux
        # gestes qu'on cherche sans lire, et vert/rouge est la convention de
        # tous les lanceurs de tests. C'est la seule entorse a la couleur
        # d'accent unique, et elle est deliberee.
        self.run_button = QPushButton("Run tests")
        self.run_button.setObjectName("Run")
        self.run_button.setIcon(icons.icon("mdi.play", t.ON_RUN))
        self.run_button.setToolTip("Run the selected tests  (F5)")
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.clicked.connect(self.run_selected)

        # Sorti du menu : apres un run rouge, relancer les seuls echecs est
        # l'action suivante une fois sur deux. La chercher dans un menu est
        # un pas de trop.
        self.rerun_button = QPushButton("Re-run failed")
        self.rerun_button.setObjectName("Ghost")
        self.rerun_button.setIcon(icons.icon("mdi.replay", t.TEXT_MUTED))
        self.rerun_button.setToolTip("Run only the tests that failed  (F6)")
        self.rerun_button.setCursor(Qt.PointingHandCursor)
        self.rerun_button.clicked.connect(self.rerun_failed)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setIcon(icons.icon("mdi.stop", t.TEXT_MUTED))
        self.stop_button.setToolTip("Stop the current run  (Esc)")
        self.stop_button.clicked.connect(self.stop_run)

        # En haut a droite, a l'ecart des actions : changer de theme n'est pas
        # une etape du travail, c'est un reglage de confort.
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("Icon")
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)

        ligne.addWidget(self.workspace_combo)
        ligne.addWidget(self.browse_button)
        ligne.addWidget(self.load_button)
        ligne.addStretch(1)
        ligne.addWidget(self.theme_button)
        ligne.addWidget(self.rerun_button)
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

        self.markers = MarkerFilter()
        self.markers.filter_changed.connect(self._on_marker_filter)

        outils.addWidget(self.search, 1)
        # Le filtre par marker rejoint la rangee d'icones : il selectionne, tout
        # comme « tout cocher » -- et il ne prend qu'un carre, quel que soit le
        # nombre de markers de la suite.
        outils.addSpacing(t.SPACE_2)
        outils.addWidget(self.markers)
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
        # Au clavier aussi : parcourir l'arbre aux fleches doit mettre a jour
        # la fiche, sinon la souris devient obligatoire pour lire un echec.
        self.tree.selectionModel().currentRowChanged.connect(self._on_tree_current)

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

        # Le compte de selection et le filtre qui l'explique, sur la meme
        # ligne : le resultat se lit la ou le resultat vivait deja, et le
        # filtre ne prend aucune place tant qu'il n'y en a pas.
        pied = QHBoxLayout()
        pied.setContentsMargins(0, 0, 0, 0)
        pied.setSpacing(t.SPACE_2)

        self.selection_label = QLabel("")
        self.selection_label.setObjectName("Faint")

        self.filter_label = QLabel("")
        self.filter_label.setVisible(False)

        self.filter_clear = QPushButton()
        self.filter_clear.setObjectName("IconSm")
        self.filter_clear.setIcon(icons.icon("mdi.close", t.TEXT_MUTED))
        self.filter_clear.setToolTip("Clear the marker filter")
        self.filter_clear.setCursor(Qt.PointingHandCursor)
        self.filter_clear.setVisible(False)
        self.filter_clear.clicked.connect(self.clear_marker_filter)

        pied.addWidget(self.selection_label)
        pied.addStretch(1)
        pied.addWidget(self.filter_label)
        pied.addWidget(self.filter_clear)
        colonne.addLayout(pied)
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
        self.status_label.setObjectName("Muted")

        self.elapsed_label = QLabel("")
        self.elapsed_label.setObjectName("Faint")

        self.pills = {
            statut: StatusPill(statut)
            for statut in (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR)
        }
        for pastille in self.pills.values():
            pastille.clicked.connect(self.filter_by_status)

        # A gauche des verdicts : ce qui reste n'est pas un resultat.
        self.remaining_pill = RemainingPill()

        barre.addWidget(self.status_label)
        barre.addWidget(self.progress)
        barre.addWidget(self.elapsed_label)
        barre.addPermanentWidget(QLabel(""))
        barre.addPermanentWidget(self.remaining_pill)
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
        self.act_config = self._action(
            fichier, "Edit the workspace configuration…", None,
            self.open_config_dialog, "mdi.file-cog-outline")
        self._action(fichier, "Test Python interpreter…", None,
                     self.open_interpreter_dialog, "mdi.language-python")
        fichier.addSeparator()
        self._action(fichier, "Quit", QKeySequence.Quit, self.close, "mdi.exit-to-app")

        executer = self.menuBar().addMenu("&Run")
        self.act_run = self._action(executer, "Run selected tests", "F5",
                                    self.run_selected, "mdi.play")
        self.act_rerun = self._action(executer, "Re-run failed", "F6",
                                      self.rerun_failed, "mdi.replay")
        self.act_stop = self._action(executer, "Stop", "Esc", self.stop_run, "mdi.stop")

        selection = self.menuBar().addMenu("&Select")
        self.act_markers = self._action(
            selection, "Filter by marker…", "Ctrl+M",
            self._open_markers, "mdi.tag-multiple-outline")
        selection.addSeparator()
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
        vue.addSeparator()
        # Les trois vues du panneau de droite, au clavier : c'est le geste le
        # plus repete d'un depouillement de run.
        self._action(vue, "Test detail", "Ctrl+1",
                     lambda: self.results.show_tab(ONGLET_DETAIL),
                     "mdi.text-box-search-outline")
        self._action(vue, "Source", "Ctrl+2",
                     lambda: self.results.show_tab(ONGLET_SOURCE),
                     "mdi.file-code-outline")
        self._action(vue, "Raw output", "Ctrl+3",
                     lambda: self.results.show_tab(ONGLET_OUTPUT), "mdi.console")
        self._action(vue, "Logs", "Ctrl+4",
                     lambda: self.results.show_tab(ONGLET_LOGS),
                     "mdi.file-document-outline")
        vue.addSeparator()
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

    def _effective_interpreter(self) -> str:
        """Interpreteur a utiliser : workspace declare > reglage global > defaut.

        Jamais `sys.executable` tel quel : une fois l'interface empaquetee par
        PyInstaller, cette valeur serait l'exe de l'interface elle-meme. Le
        lancer en sous-processus rouvrirait une copie de l'interface au lieu de
        pytest -- une nouvelle fenetre apparait, sans le moindre arbre puisque
        aucune collecte n'a jamais eu lieu, et rien ne dit pourquoi.
        `interpreter_mod.default()` cherche a la place un vrai Python sur le
        PATH quand l'application est figee.
        """
        if self.workspace is not None and self.workspace.declared_interpreter:
            return self.workspace.declared_interpreter
        if self._interpreter_override:
            return self._interpreter_override
        if self.workspace is not None:
            return self.workspace.interpreter
        return interpreter_mod.default()

    def _require_interpreter(self) -> str:
        """L'interpreteur resolu, ou chaine vide apres avoir explique pourquoi.

        Une chaine vide passee telle quelle a `subprocess` donne une erreur
        illisible (`FileNotFoundError: ''`) ; ici l'utilisateur sait tout de
        suite ou aller la configurer.
        """
        chemin = self._effective_interpreter()
        if chemin:
            return chemin

        ErrorDialog.show_error(
            self, "No Python interpreter",
            "No Python interpreter was found automatically for the tests.",
            "This happens when the application is packaged and no Python is "
            "on the PATH. Set one from File > Test Python interpreter…")
        return ""

    @pyqtSlot()
    def open_interpreter_dialog(self) -> None:
        declare = self.workspace.declared_interpreter if self.workspace else ""
        dialogue = InterpreterDialog(self._interpreter_override, declare, self)
        if dialogue.exec_() != InterpreterDialog.Accepted:
            return

        nouveau = dialogue.interpreter_path()
        if nouveau != self._interpreter_override:
            self._interpreter_override = nouveau
            self.settings.setValue(K_INTERPRETER, nouveau)
            # Un changement d'interpreteur invalide tout ce que l'arbre montrait
            # jusqu'ici : les nodeids collectes ailleurs peuvent ne plus exister.
            if self.workspace is not None and not self.workspace.declared_interpreter:
                self.load_workspace()

    @pyqtSlot()
    def open_config_dialog(self) -> None:
        """Ouvre le fichier de configuration du workspace charge.

        Recharge la collecte apres un enregistrement : le fichier decide de
        l'interpreteur, des lecteurs et du chemin des logs. Garder a l'ecran un
        arbre collecte avec les reglages d'avant ferait travailler sur des
        informations perimees sans que rien ne le signale.
        """
        from runner.ui.config_dialog import ConfigDialog

        if self.workspace is None or not self.workspace.config_path:
            ErrorDialog.show_error(
                self, "No configuration file",
                "This workspace has no YAML configuration file at its root. "
                "Create a config.yml there, then load the workspace again.",
                self.workspace.path if self.workspace else "")
            return

        avant = (self.workspace.readers, self.workspace.log_root,
                 self.workspace.declared_interpreter, self.workspace.reader_mode)

        dialogue = ConfigDialog(self.workspace.config_path,
                                [r.name for r in self.workspace.readers], self)
        dialogue.exec_()

        self.workspace = Workspace.load(self.workspace.path)
        apres = (self.workspace.readers, self.workspace.log_root,
                 self.workspace.declared_interpreter, self.workspace.reader_mode)
        if avant != apres:
            self.load_workspace()

    @pyqtSlot()
    def toggle_theme(self) -> None:
        """Passe de sombre a clair, et retient le choix."""
        self.apply_theme("light" if t.is_dark() else "dark")

    def apply_theme(self, nom: str) -> None:
        """Change de palette a chaud et repeint tout ce qui ne suit pas seul.

        La feuille de style globale se regenere entierement : tout ce qui lit
        un jeton au moment de l'appel suit sans rien faire. Restent les
        couleurs figees a la construction -- icones deja teintees, formats de
        coloration, pastilles dont la teinte depend d'une donnee -- que les
        `restyle()` ci-dessous rejouent.
        """
        from PyQt5.QtWidgets import QApplication

        t.set_theme(nom)
        self.settings.setValue(K_THEME, t.current_theme())

        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(theme.app_stylesheet())

        self._restyle()

    def _restyle(self) -> None:
        """Rejoue les couleurs qui ne viennent pas de la feuille globale."""
        soleil = t.is_dark()
        self.theme_button.setIcon(icons.icon(
            "mdi.weather-sunny" if soleil else "mdi.weather-night", t.TEXT_MUTED))
        self.theme_button.setToolTip(
            "Switch to the light theme" if soleil else "Switch to the dark theme")

        for glyphe, bouton in (
                ("mdi.folder-open-outline", self.browse_button),
                ("mdi.replay", self.rerun_button),
                ("mdi.stop", self.stop_button)):
            bouton.setIcon(icons.icon(glyphe, t.TEXT_MUTED))
        self.run_button.setIcon(icons.icon("mdi.play", t.ON_RUN))

        for glyphe, bouton in (
                ("mdi.checkbox-multiple-marked-outline", self.select_all_button),
                ("mdi.checkbox-multiple-blank-outline", self.select_none_button),
                ("mdi.unfold-more-horizontal", self.expand_button),
                ("mdi.unfold-less-horizontal", self.collapse_button)):
            bouton.setIcon(icons.icon(glyphe, t.TEXT_MUTED))

        self.filter_clear.setIcon(icons.icon("mdi.close", t.TEXT_MUTED))

        # Balayage plutot qu'une liste tenue a la main : c'est en oubliant un
        # widget de cette liste qu'on laisse un ilot de l'ancien theme, et
        # l'oubli ne se voit que sur un ecran precis, dans un etat precis. Les
        # `restyle()` sont idempotents, un double appel ne coute rien.
        from PyQt5.QtWidgets import QWidget

        for enfant in self.findChildren(QWidget):
            rejouer = getattr(enfant, "restyle", None)
            if callable(rejouer):
                rejouer()

        self._show_active_filter()

        # L'arbre redessine ses icones de statut a la demande : il suffit de
        # lui dire que tout a change.
        self.model.layoutChanged.emit()

    def _connect_service(self) -> None:
        self.service.started.connect(self._on_run_started)
        self.service.line.connect(self.results.append_output)
        self.service.outcome.connect(self._on_outcome)
        self.service.progress.connect(self._on_progress)
        self.service.reader_finished.connect(self.results.set_report)
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

        python = self._require_interpreter()
        if not python:
            return

        self.status_label.setText("Collecting tests…")
        self.load_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indetermine : la duree est inconnue

        self._collector = CollectWorker(
            self.workspace.path, python, self.workspace.env, self)
        self._collector.collected.connect(self._on_collected)
        self._collector.failed.connect(self._on_collect_failed)
        self._collector.start()

    @pyqtSlot(object)
    def _on_collected(self, collection) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.load_button.setEnabled(True)

        nodeids = list(collection.nodeids)
        self._markers_by_nodeid = dict(collection.markers)
        self.markers.set_markers(collection.marker_list())
        self._show_active_filter()

        self._clear_status_filter()
        self.remaining_pill.setVisible(False)
        self.model.set_tree(collapse_single_class(build_tree(nodeids)))
        lecteurs = self.workspace.readers if self.workspace else ()
        # Les colonnes montrent TOUS les lecteurs declares, y compris ceux
        # qu'on vient de decocher : les faire disparaitre effacerait de l'ecran
        # les resultats qu'ils portaient au run precedent. Decocher restreint
        # le prochain run, cela ne cache rien.
        self.model.set_readers(lecteurs)
        self.results.set_readers(lecteurs)
        self.readers_bar.set_readers(
            lecteurs,
            sequential=bool(self.workspace)
            and self.workspace.reader_mode == MODE_SEQUENTIEL)
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
        """Chaque colonne de lecteur prend la largeur de son titre, UNE fois.

        La largeur est calculee ici et figee, au lieu d'etre confiee a
        `ResizeToContents`. Ce mode reclame a Qt de re-mesurer chaque ligne de
        la colonne a chaque `dataChanged` -- donc a chaque test qui se termine.
        Mesure sur une suite de 2000 tests : 291 ms par resultat contre 22 ms
        une fois la largeur figee, soit treize fois plus lent. Le fil de
        l'interface saturait, les resultats n'apparaissaient plus au fur et a
        mesure mais par paquets, et tout semblait fige entre deux.

        Le titre reste la reference pour ne pas retomber sur des noms tronques
        (`smo11Secur`) : ce sont eux qui distinguent une colonne de l'autre.
        """
        entete = self.tree.header()
        metriques = entete.fontMetrics()

        for colonne in range(1, self.model.columnCount()):
            titre = self.model.headerData(colonne, Qt.Horizontal, Qt.DisplayRole) or ""
            # De quoi loger le titre, sa marge de section, et l'icone de statut.
            largeur = metriques.horizontalAdvance(str(titre)) + t.SPACE_8
            entete.setSectionResizeMode(colonne, QHeaderView.Fixed)
            entete.resizeSection(colonne, max(largeur, 72))

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

        # Une correction encore dans le tampon de l'editeur ferait relancer la
        # version d'avant, et chercher pourquoi elle n'a rien change.
        if not self.results.source.save():
            ErrorDialog.show_error(
                self, "Could not save the source",
                "The file you edited could not be written, so the run would "
                "use the previous version.",
                str(self.results.source.path() or ""))
            return

        python = self._require_interpreter()
        if not python:
            return

        lecteurs = self._readers_to_run()
        requete = RunRequest(
            workspace=self.workspace.path,
            interpreter=python,
            nodeids=tuple(nodeids),
            readers=lecteurs,
            config_path=self.workspace.config_path,
            sequential=self.workspace.reader_mode == MODE_SEQUENTIEL,
        )
        self.service.start(requete, self.workspace.env)

    def _readers_to_run(self) -> tuple:
        """Les lecteurs coches, dans l'ordre des colonnes.

        Leur `index` est conserve tel quel : c'est lui qui range un resultat
        dans la bonne colonne et la bonne console. Renumeroter les lecteurs
        restants ferait atterrir les verdicts du deuxieme dans la colonne du
        premier des qu'on en decoche un.
        """
        declares = self.workspace.readers if self.workspace else ()
        if len(declares) <= 1:
            return declares
        retenus = set(self.readers_bar.selected_indexes())
        return tuple(l for l in declares if l.index in retenus)

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

        # Un filtre pose sur le run precedent masquerait les resultats du
        # nouveau au fur et a mesure qu'ils arrivent.
        self._clear_status_filter()

        self.remaining_pill.set_value(request.total_tests)
        self.remaining_pill.setVisible(True)

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

        self.results.update_statuses(outcome.nodeid,
                                     self.model.statuses_for_nodeid(outcome.nodeid))

    @pyqtSlot(int, int)
    def _on_progress(self, faits: int, total: int) -> None:
        self.progress.setValue(faits)
        restants = max(0, total - faits)
        self.remaining_pill.set_value(restants)
        self.status_label.setText(f"Running… {restants} left")

    @pyqtSlot(list)
    def _on_run_finished(self, rapports: list) -> None:
        self._elapsed.stop()
        self.progress.setVisible(False)

        self.remaining_pill.setVisible(False)

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
        self._select_test(index)

    @pyqtSlot(QModelIndex, QModelIndex)
    def _on_tree_current(self, index: QModelIndex, _precedent: QModelIndex) -> None:
        self._select_test(index)

    def _select_test(self, index: QModelIndex) -> None:
        """Montre la fiche du test pointe. Un regroupement n'en a pas."""
        if not index.isValid():
            return
        nodeid = self.model.data(index.siblingAtColumn(0), NODEID_ROLE)
        if nodeid:
            self.results.show_test(
                nodeid, self.model.statuses_for_nodeid(nodeid),
                self.workspace.path if self.workspace else "")

    @pyqtSlot(int, int)
    def _on_selection_changed(self, coches: int, total: int) -> None:
        self.selection_label.setText(f"{coches} of {total} tests selected")
        self._update_actions()

    @pyqtSlot()
    def _on_readers_changed(self) -> None:
        """Le prochain run ne parcourra plus les memes lecteurs : le dire."""
        retenus = self._readers_to_run()
        declares = self.workspace.readers if self.workspace else ()
        if len(retenus) == len(declares):
            self.status_label.setText(f"Running on all {len(declares)} readers")
        elif retenus:
            noms = ", ".join(l.short_name for l in retenus)
            self.status_label.setText(f"Running on {noms}")
        else:
            self.status_label.setText("No reader selected")
        self._update_actions()

    @pyqtSlot(int)
    def _on_reader_selected(self, index: int) -> None:
        lecteurs = self.workspace.readers if self.workspace else ()
        if 0 <= index < len(lecteurs):
            self.status_label.setText(f"Showing {lecteurs[index].name}")

    @pyqtSlot()
    def _open_markers(self) -> None:
        if not self.markers.isHidden():
            self.markers.toggle_popup()

    @pyqtSlot()
    def _on_marker_filter(self) -> None:
        """Coche exactement les tests que l'expression retient.

        Un champ vide ne decoche rien : effacer le filtre pour retrouver la
        selection qu'on avait patiemment faite a la main, et la voir disparaitre,
        serait la pire des surprises.
        """
        self._show_active_filter()

        predicat = self.markers.matcher()
        if predicat is None:
            return

        retenus = [nodeid for nodeid, noms in self._markers_by_nodeid.items()
                   if predicat(frozenset(noms))]

        self.model.set_all_checked(False)
        for nodeid in retenus:
            index = self.model.index_for_nodeid(nodeid)
            if index.isValid():
                self.model.setData(index, Qt.Checked, Qt.CheckStateRole)

        if retenus:
            self._reveal(retenus[0])
        self.status_label.setText(
            f"{len(retenus)} tests match “{self.markers.expression()}”"
            if retenus else f"No test matches “{self.markers.expression()}”")

    def _show_active_filter(self) -> None:
        """Rappelle le filtre en cours a cote du compte de selection.

        Le panneau se referme ; sans ce rappel, il ne resterait aucune trace de
        POURQUOI une partie de l'arbre est decochee.
        """
        expression = self.markers.expression()
        self.filter_label.setText(expression)
        self.filter_label.setToolTip(f"Marker filter: {expression}")
        self.filter_label.setStyleSheet(theme.pill_style(t.ACCENT))
        self.filter_label.setVisible(bool(expression))
        self.filter_clear.setVisible(bool(expression))

    @pyqtSlot()
    def clear_marker_filter(self) -> None:
        """Retire le filtre sans toucher a la selection qu'il a produite.

        Decocher au passage ferait perdre un choix qu'on vient peut-etre
        d'affiner a la main ; enlever l'etiquette suffit a dire que le filtre
        ne s'applique plus.
        """
        self.markers.clear()
        self._show_active_filter()
        self.status_label.setText("Marker filter cleared")

    @pyqtSlot(object)
    def filter_by_status(self, status) -> None:
        """Ne montre plus que les tests de ce statut. Recliquer rend tout.

        Le compteur et le filtre sont le meme geste : on lit « 44 failed », on
        veut voir lesquels, on clique dessus.
        """
        self._status_filter = None if self._status_filter is status else status

        for statut, pastille in self.pills.items():
            pastille.set_active(statut is self._status_filter)

        self._apply_status_filter()

        if self._status_filter is None:
            self.status_label.setText("Showing every test")
        else:
            libelle = self._status_filter.label.lower()
            self.status_label.setText(f"Showing only {libelle} tests")

    def _clear_status_filter(self) -> None:
        """Retire le filtre sans rien dire : appele quand le contexte change."""
        if self._status_filter is None:
            return
        self._status_filter = None
        for pastille in self.pills.values():
            pastille.set_active(False)
        self._apply_status_filter()

    def _apply_status_filter(self) -> None:
        """Masque les lignes qui ne menent a aucun test du statut retenu.

        Un dossier reste visible des qu'il CONTIENT un test retenu : le
        masquer couperait le chemin vers ce test, et l'arbre n'aurait plus
        de racine a montrer.
        """
        statut = self._status_filter

        def garder(parent: QModelIndex) -> bool:
            visible_ici = False
            for ligne in range(self.model.rowCount(parent)):
                index = self.model.index(ligne, 0, parent)
                objet = index.internalPointer()

                if statut is None:
                    retenu = True
                    garder(index)
                elif objet.is_leaf:
                    retenu = any(s is statut for s in objet.statuses.values())
                else:
                    retenu = garder(index)

                self.tree.setRowHidden(ligne, parent, not retenu)
                visible_ici = visible_ici or retenu
            return visible_ici

        garder(QModelIndex())

        # Ce qui est masque doit rester atteignable : on ouvre les branches qui
        # menent aux tests retenus, sinon le filtre ne montre qu'une racine.
        if statut is not None:
            self.tree.expandAll()

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

        # Tout decocher dans la barre des lecteurs ne laisse rien a parcourir.
        # Le bouton s'eteint plutot que de repondre par une boite de dialogue :
        # la cause est a l'ecran, juste au-dessus.
        cible = not charge or bool(self._readers_to_run()) or not self.workspace.readers

        self.run_button.setEnabled(charge and coches > 0 and not occupe and cible)
        self.stop_button.setEnabled(occupe)
        self.act_run.setEnabled(self.run_button.isEnabled())
        self.act_stop.setEnabled(occupe)
        rejouable = (charge and not occupe and cible
                     and bool(self.model.failed_nodeids()))
        self.act_rerun.setEnabled(rejouable)
        self.rerun_button.setEnabled(rejouable)
        self.act_diverge.setEnabled(len(self.model.readers) > 1)
        # Sans workspace charge, il n'y a aucun fichier a editer.
        self.act_config.setEnabled(
            charge and bool(self.workspace.config_path))

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

        self._interpreter_override = self.settings.value(K_INTERPRETER, "", type=str)
        self.apply_theme(self.settings.value(K_THEME, "dark", type=str))

    def closeEvent(self, event) -> None:
        self.results.source.save()
        self.settings.setValue(K_GEOMETRY, self.saveGeometry())
        self.settings.setValue(K_STATE, self.saveState())
        self.settings.setValue(K_SPLIT_MAIN, self.split.saveState())
        self.settings.setValue(K_TREE_COLS, self.tree.header().saveState())

        if self.service.busy:
            self.service.cancel()
            self.service.wait(3000)
        super().closeEvent(event)
