"""Fenetre principale : assemblage des zones, aucun travail metier ici.

Chaque slot se contente de traduire un geste en appel de service ou en mise a
jour de modele. Rien de bloquant : la collecte et les runs vivent dans des
QThread, la fenetre ne fait qu'ecouter leurs signaux.
"""

from __future__ import annotations

import http.server
import os
import shutil
import socketserver
import subprocess
import threading
import time
from functools import partial
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSettings, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from runner.domain import history
from runner.domain import interpreter as interpreter_mod
from runner.domain.models import Kind, Reader, RunRequest, Status
from runner.domain.source import path_of as source_path
from runner.domain.stress import MODE_N_TIMES, MODE_UNTIL_FAIL, StressAttempt, StressSummary
from runner.domain.tree import build_tree, collapse_single_class
from runner.domain.workspace import (
    MODE_SEQUENTIEL,
    Workspace,
    fichiers_config,
)
from runner.services.allure_service import AllureReportWorker
from runner.services.interpreter_service import ProbeWorker
from runner.services.run_service import CollectWorker, RunService
from runner.services.stress_service import StressRunWorker
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
from runner.ui.run_n_times_dialog import RunNTimesDialog
from runner.ui.tree_model import NODE_ROLE, NODEID_ROLE, TestTreeModel
from runner.ui.widgets import (
    SCOPE_FAILURES,
    SCOPE_TESTS,
    CompassRing,
    EmptyState,
    ErrorDialog,
    LiveDot,
    ReaderBar,
    ReaderHeaderView,
    RemainingPill,
    SearchBar,
    StatusPill,
)

ORG, APP = "PytestRunner", "Runner"
WINDOW_TITLE = "Pytest Runner"

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
# Fichier de configuration retenu, par workspace. Un projet peut en
# compter plusieurs, et le premier trouve n'est pas forcement le bon.
K_CONFIG = "workspace/config"


def _environnement_pour_allure() -> dict:
    """L'environnement du processus, avec `JAVA_HOME` corrige si besoin.

    Poste Windows frequent : plusieurs JDK installes au fil du temps ont
    chacun ajoute leur chemin a `JAVA_HOME` au lieu de le remplacer, la
    laissant contenir une liste `chemin1;chemin2` comme le ferait `PATH`.
    `allure` veut UN SEUL dossier et refuse de demarrer sinon -- inutile de
    faire corriger la variable systeme a la main quand un des chemins listes
    est deja un JDK valide.
    """
    env = dict(os.environ)
    valeur = env.get("JAVA_HOME", "")
    chemins = [c for c in valeur.split(os.pathsep) if c.strip()]
    if len(chemins) > 1:
        valide = next((c for c in chemins if Path(c).is_dir()), None)
        if valide:
            env["JAVA_HOME"] = valide
    return env


class _GestionnaireAllure(http.server.SimpleHTTPRequestHandler):
    """Sert le rapport Allure, sans jamais journaliser sur `sys.stderr`.

    Cette appli est empaquetee `console=False` (PytestRunner.spec) : sous
    Windows, `sys.stderr` y vaut `None`. Le `log_message()` par defaut de
    `BaseHTTPRequestHandler` y ecrit -- et il est appele DEPUIS
    `send_response()`, donc AVANT que les en-tetes ou le corps ne partent.
    L'exception qui en resulte coupe la reponse a ce moment precis : le
    navigateur voit une connexion ouverte puis fermee sans un seul octet
    (ERR_EMPTY_RESPONSE), pas une erreur pytest ni allure.
    """

    def log_message(self, format, *args):
        pass


class MainWindow(QMainWindow):
    """Fenetre unique de l'application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(1100, 640)

        self.settings = QSettings(ORG, APP)
        self.workspace: Workspace | None = None
        self.service = RunService(self)
        self.history = history.History()
        # Identifiant du run en cours : partage par tous ses lecteurs,
        # ce qui permet de les retrouver ensemble dans l'historique.
        self._run_id: str | None = None
        self._build_number: int | None = None
        self._collector: CollectWorker | None = None
        self._allure_prober: ProbeWorker | None = None
        # Dossier des resultats allure-pytest du dernier run demarre, ou ""
        # si son interpreteur ne connait pas le plugin. Le bouton Allure lit
        # cette valeur, il ne la calcule jamais lui-meme.
        self._last_allure_dir = ""
        # Le generateur en cours (auto-regeneration en fin de run, ou clic
        # manuel) et si ce dernier clic attend l'ouverture du navigateur une
        # fois la generation en cours terminee -- voir `_lancer_generation_allure`.
        self._allure_worker: AllureReportWorker | None = None
        self._allure_open_en_attente = False
        # Petit serveur HTTP local qui sert le rapport genere : ouvrir son
        # index.html directement en file:// bloque tous ses appels AJAX
        # (CORS du navigateur), et il ne reste alors qu'un ecran "Loading…"
        # partout. Demarre une fois, reutilise a chaque clic suivant --
        # regenerer le rapport dans le meme dossier suffit, pas besoin de le
        # relancer.
        self._allure_server: socketserver.TCPServer | None = None
        self._allure_server_thread: threading.Thread | None = None
        self._matches: list[str] = []
        self._markers_by_nodeid: dict[str, tuple[str, ...]] = {}
        self._match_index = -1
        # Rejouer un run historique peut demander de charger d'abord son
        # workspace. La requete attend alors la fin de la collecte.
        self._pending_history_run = None
        # Reglage global, distinct de celui qu'un workspace peut imposer dans
        # sa configuration -- celui-la garde toujours la priorite.
        self._interpreter_override = ""
        # Statut dont on ne montre que les tests, ou None pour tout montrer.
        self._status_filter: Status | None = None
        self._elapsed = QTimer(self)
        self._elapsed.setInterval(1000)
        self._elapsed.timeout.connect(self._tick)
        self._seconds = 0

        # Un run long tourne souvent pendant qu'on fait autre chose : la
        # notification systeme le signale sans qu'il faille revenir surveiller
        # la fenetre. `isSystemTrayAvailable()` est faux sous un environnement
        # sans bureau (CI, tests offscreen) -- l'icone reste alors invisible,
        # `showMessage()` ne fait rien, et le reste de l'appli continue
        # normalement.
        self._tray = QSystemTrayIcon(icons.icon("mdi.flask-outline"), self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

        # "Run until it fails" / "Run N times" : un seul test rejoue plusieurs
        # fois, hors du `RunService` normal -- sinon chaque tentative serait
        # archivee dans l'historique et redeclencherait la notification de fin
        # de run, comme si c'etait un vrai run complet.
        self._stress_worker: StressRunWorker | None = None
        self._stress_nodeid = ""
        self._stress_mode = MODE_UNTIL_FAIL
        self._stress_cap = 0
        self._stress_ran = 0
        self._stress_passed = 0
        self._stress_failed: list[StressAttempt] = []

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
        racine = QHBoxLayout(central)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)

        racine.addWidget(self._build_navigation())

        self.pages = QStackedWidget()
        self.workspace_page = QWidget()
        colonne = QVBoxLayout(self.workspace_page)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_2)
        colonne.setSpacing(t.SPACE_3)

        colonne.addWidget(self._build_command_bar())

        self.interpreter_alert = QFrame()
        self.interpreter_alert.setObjectName("InterpreterAlert")
        alerte = QHBoxLayout(self.interpreter_alert)
        alerte.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        self.interpreter_alert_label = QLabel(
            "The configured test interpreter is unavailable.")
        self.interpreter_alert_label.setWordWrap(True)
        self.interpreter_alert_button = QPushButton("Open configuration")
        self.interpreter_alert_button.clicked.connect(
            lambda: self._show_page("configuration"))
        alerte.addWidget(self.interpreter_alert_label, 1)
        alerte.addWidget(self.interpreter_alert_button)
        self.interpreter_alert.setVisible(False)
        colonne.addWidget(self.interpreter_alert)

        # Le choix des lecteurs porte sur le RUN : il partage donc la rangee
        # des actions Run / Stop / Re-run, plutot que d'occuper une ligne a
        # lui seul au-dessus de l'arbre.
        self.readers_bar = ReaderBar()
        self.readers_bar.changed.connect(self._on_readers_changed)
        colonne.addWidget(self._build_run_bar())

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self._build_left())
        self.split.addWidget(self._build_right())
        # 45/55 : a 40/60 les noms de tests parametres etaient tronques alors
        # que la sortie avait de la place a revendre.
        self.split.setStretchFactor(0, 45)
        self.split.setStretchFactor(1, 55)
        colonne.addWidget(self.split, 1)

        self.pages.addWidget(self.workspace_page)
        self.history_page = self._build_history_page()
        self.configuration_page = self._build_configuration_page()
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.configuration_page)
        racine.addWidget(self.pages, 1)

        self.setCentralWidget(central)
        self._build_status_bar()

    def _build_navigation(self) -> QWidget:
        navigation = QFrame()
        navigation.setObjectName("Navigation")
        navigation.setFixedWidth(190)
        colonne = QVBoxLayout(navigation)
        colonne.setContentsMargins(t.SPACE_3, t.SPACE_4, t.SPACE_3, t.SPACE_3)
        colonne.setSpacing(t.SPACE_2)

        titre = QLabel("PYTEST RUNNER")
        titre.setObjectName("NavigationTitle")
        colonne.addWidget(titre)
        colonne.addSpacing(t.SPACE_4)

        self.nav_buttons = {}
        entrees = (
            ("workspace", "Workspace", "mdi.folder-outline"),
            ("history", "Historique", "mdi.history"),
            ("configuration", "Configuration", "mdi.cog-outline"),
        )
        for cle, texte, glyph in entrees:
            bouton = QPushButton(texte)
            bouton.setObjectName("NavigationItem")
            bouton.setCheckable(True)
            bouton.setIcon(icons.icon(glyph, t.TEXT_MUTED))
            bouton.setCursor(Qt.PointingHandCursor)
            bouton.clicked.connect(lambda checked=False, page=cle: self._show_page(page))
            self.nav_buttons[cle] = bouton
            colonne.addWidget(bouton)
        colonne.addStretch(1)
        self.nav_buttons["workspace"].setChecked(True)
        return navigation

    def _page_landing(self, title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
        layout.setSpacing(t.SPACE_3)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)
        copy = QLabel(description)
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        layout.addWidget(copy)
        return page, layout

    def _build_history_page(self) -> QWidget:
        page, layout = self._page_landing(
            "Historique",
            "Retrouvez les exécutions passées, comparez les lecteurs et "
            "relancez une sélection sans modifier le Workspace courant.")
        button = QPushButton("Ouvrir l’historique des exécutions")
        button.setObjectName("Primary")
        button.setIcon(icons.icon("mdi.history", t.ON_ACCENT))
        button.clicked.connect(self.open_history)
        layout.addWidget(button, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_configuration_page(self) -> QWidget:
        page, layout = self._page_landing(
            "Configuration",
            "Configurez ici l’environnement d’exécution et les réglages du "
            "workspace. L’interpréteur de test n’est affiché sur le Workspace "
            "que lorsqu’il nécessite votre attention.")

        self.interpreter_config_button = QPushButton("Configurer l’interpréteur de test…")
        self.interpreter_config_button.setIcon(icons.icon("mdi.language-python", t.TEXT_MUTED))
        self.interpreter_config_button.clicked.connect(self.open_interpreter_dialog)
        layout.addWidget(self.interpreter_config_button, 0, Qt.AlignLeft)

        self.workspace_config_button = QPushButton("Configurer le workspace…")
        self.workspace_config_button.setObjectName("Ghost")
        self.workspace_config_button.setIcon(
            icons.icon("mdi.file-cog-outline", t.TEXT_MUTED))
        self.workspace_config_button.clicked.connect(self.open_config_dialog)
        layout.addWidget(self.workspace_config_button, 0, Qt.AlignLeft)

        self.page_theme_button = QPushButton("Changer de thème")
        self.page_theme_button.setObjectName("Ghost")
        self.page_theme_button.setIcon(icons.icon("mdi.theme-light-dark", t.TEXT_MUTED))
        self.page_theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.page_theme_button, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def _show_page(self, page: str) -> None:
        pages = {
            "workspace": self.workspace_page,
            "history": self.history_page,
            "configuration": self.configuration_page,
        }
        cible = pages.get(page, self.workspace_page)
        self.pages.setCurrentWidget(cible)
        for cle, bouton in self.nav_buttons.items():
            bouton.setChecked(cle == page)
        self.statusBar().setVisible(page == "workspace")

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

        # A cote de Load, avec le workspace : la configuration decrit CE
        # dossier -- ses lecteurs, ses logs, son interpreteur. Sa place est
        # dans le groupe qui parle du workspace, pas dans un menu.
        self.config_button = QPushButton("Config")
        self.config_button.setObjectName("Ghost")
        self.config_button.setIcon(icons.icon("mdi.file-cog-outline", t.TEXT_MUTED))
        self.config_button.setToolTip(
            "Choose or edit this workspace's YAML configuration file")
        self.config_button.clicked.connect(self.open_config_dialog)
        self.config_button.setVisible(False)

        # L'historique parle du workspace lui aussi : ce sont ses runs. Sorti
        # du menu, parce qu'on y va pour comparer au run precedent, ce qui
        # arrive bien plus souvent qu'un detour par la barre de menus.
        self.history_button = QPushButton("History")
        self.history_button.setObjectName("Ghost")
        self.history_button.setIcon(icons.icon("mdi.history", t.TEXT_MUTED))
        self.history_button.setToolTip("Runs already recorded  (Ctrl+H)")
        self.history_button.clicked.connect(self.open_history)
        self.history_button.setVisible(False)

        # A cote de History plutot que dans un menu : c'est le meme geste,
        # juste sur un rapport different -- regarder ce qu'a donne un run deja
        # termine.
        self.allure_button = QPushButton("Allure")
        self.allure_button.setObjectName("Ghost")
        self.allure_button.setIcon(icons.icon("mdi.file-chart-outline", t.TEXT_MUTED))
        self.allure_button.setToolTip("Open the Allure report of the last run")
        self.allure_button.clicked.connect(self.open_allure_report)

        # Les verdicts, dans l'espace vide a droite de cette rangee -- un
        # anneau qui dit la proportion d'un coup d'oeil, le detail par statut
        # juste a cote pour filtrer, comme avant.
        self.compass_ring = CompassRing()
        self.compass_pct = QLabel("—")
        self.compass_pct.setStyleSheet(
            f"color: {t.TEXT}; font-weight: 600; font-size: {t.TEXT_SM + 4}px;")

        self.pills = {
            statut: StatusPill(statut)
            for statut in (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR)
        }
        for pastille in self.pills.values():
            pastille.filter_clicked.connect(self.filter_by_status)

        # Cette barre ne parle que du WORKSPACE : ou il est, et ce qui le
        # decrit. Les actions de run ont leur propre rangee, juste en dessous.
        ligne.addWidget(self.workspace_combo)
        ligne.addWidget(self.browse_button)
        ligne.addWidget(self.load_button)
        ligne.addWidget(self.config_button)
        ligne.addWidget(self.history_button)
        ligne.addWidget(self.allure_button)
        ligne.addStretch(1)
        ligne.addWidget(self.compass_ring)
        ligne.addWidget(self.compass_pct)
        for pastille in self.pills.values():
            ligne.addWidget(pastille)
        return barre

    def _build_run_bar(self) -> QWidget:
        """Lancer, arreter, rejouer -- sur une rangee a eux.

        Ces boutons vivaient au bout de la barre du workspace, a l'oppose de
        l'arbre : on cochait des tests a gauche, puis on traversait toute la
        fenetre pour les lancer, a chaque fois. Les mettre en tete de cette
        meme barre les rapprochait mais les melangeait au chemin du workspace,
        qui ne se touche qu'une fois par session.

        Une rangee a eux, juste au-dessus de l'arbre, resout les deux : ils
        sont a portee, et on voit du premier coup d'oeil ce qui agit sur le
        run et ce qui decrit le projet.
        """
        barre = QWidget()
        ligne = QHBoxLayout(barre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)

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

        ligne.addWidget(self.run_button)
        ligne.addWidget(self.stop_button)
        ligne.addWidget(self.rerun_button)
        # Separe visuellement les actions de leur cible materielle, tout en
        # gardant l'ensemble sur une seule rangee compacte.
        ligne.addSpacing(t.SPACE_6)
        ligne.addWidget(self.readers_bar)
        ligne.addStretch(1)
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
        self.search.scope_changed.connect(self._on_search_scope_changed)

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

        # Resultats de la recherche "In failures" : un extrait par test
        # touche, plutot que de forcer a naviguer un par un avec Entree pour
        # savoir ce qu'on va trouver avant d'y sauter.
        self.failure_results = QListWidget()
        self.failure_results.setObjectName("Failures")
        self.failure_results.setVisible(False)
        self.failure_results.setMaximumHeight(180)
        self.failure_results.itemClicked.connect(self._sur_resultat_echec_clique)
        colonne.addWidget(self.failure_results)

        self.tree = QTreeView()
        self.tree.setHeader(ReaderHeaderView(Qt.Horizontal, self.tree))
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
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu_contextuel_arbre)

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
        self.results.test_chosen.connect(self._goto_test)
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

        # Le pouls qui dit "ca tourne EN CE MOMENT" -- cache et arrete des
        # que `_set_status_idle()` reprend la main.
        self.live_dot = LiveDot()

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("Muted")

        # Le texte et le pouls vivent DANS un badge -- pas juste cote a cote
        # sur le fond nu de la barre d'etat. Sans fond propre, seul le texte
        # colore distinguait un run en cours du repos ; ici c'est toute une
        # forme qui apparait.
        self.live_chip = QWidget()
        # Meme piege que le badge de statut : sans cet attribut, le style
        # natif Windows ignore silencieusement le fond/lisere poses par
        # `setStyleSheet()` sur un QWidget nu.
        self.live_chip.setAttribute(Qt.WA_StyledBackground, True)
        puce = QHBoxLayout(self.live_chip)
        puce.setContentsMargins(t.SPACE_2, t.SPACE_1, t.SPACE_3, t.SPACE_1)
        puce.setSpacing(t.SPACE_2)
        puce.addWidget(self.live_dot)
        puce.addWidget(self.status_label)

        self.elapsed_label = QLabel("")
        self.elapsed_label.setObjectName("Faint")

        # A gauche des verdicts : ce qui reste n'est pas un resultat.
        self.remaining_pill = RemainingPill()

        barre.addWidget(self.live_chip)
        barre.addWidget(self.progress)
        barre.addWidget(self.elapsed_label)
        barre.addPermanentWidget(QLabel(""))
        barre.addPermanentWidget(self.remaining_pill)

    def _build_menus(self) -> None:
        """Menus et raccourcis. Chaque action frequente en a un, visible ici."""
        # Le theme se loge dans le coin de la barre de menus : tout en haut a
        # droite, seul, loin des boutons de run. Un QMenuBar accepte un widget
        # a cet endroit, ce qui evite de lui inventer une barre a lui.
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("Icon")
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.menuBar().setCornerWidget(self.theme_button, Qt.TopRightCorner)
        self.theme_button.setToolTip("Changer de thème")

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
        executer.addSeparator()
        self._action(executer, "Run history…", "Ctrl+H",
                     self.open_history, "mdi.history")

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

        # La navigation principale remplace la barre de menus. Les QAction
        # restent rattachees a la fenetre afin de conserver tous les
        # raccourcis clavier et les comportements existants.
        self.menuBar().hide()

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
        self._set_interpreter_alert(
            "Aucun interpréteur Python de test n’est disponible. "
            "Configurez-le avant de charger ou lancer les tests.")
        return ""

    def _set_interpreter_alert(self, message: str = "") -> None:
        self.interpreter_alert_label.setText(message)
        self.interpreter_alert.setVisible(bool(message))

    def _on_interpreter_probed(self, info) -> None:
        if info.ok and info.pytest_version:
            self._set_interpreter_alert()
            return
        detail = info.error or "pytest n’est pas installé dans cet environnement."
        self._set_interpreter_alert(
            f"L’interpréteur de test configuré est indisponible : {detail}")

    @Slot()
    def open_interpreter_dialog(self) -> None:
        declare = self.workspace.declared_interpreter if self.workspace else ""
        dialogue = InterpreterDialog(self._interpreter_override, declare, self)
        if dialogue.exec() != InterpreterDialog.Accepted:
            return

        nouveau = dialogue.interpreter_path()
        if nouveau != self._interpreter_override:
            self._interpreter_override = nouveau
            self.settings.setValue(K_INTERPRETER, nouveau)
            # Un changement d'interpreteur invalide tout ce que l'arbre montrait
            # jusqu'ici : les nodeids collectes ailleurs peuvent ne plus exister.
            if self.workspace is not None and not self.workspace.declared_interpreter:
                self.load_workspace()
        self._refresh_interpreter_alert()

    def _refresh_interpreter_alert(self) -> None:
        if self.workspace is None:
            self._set_interpreter_alert()
            return
        chemin = self._effective_interpreter()
        if not chemin:
            self._require_interpreter()
            return
        info = interpreter_mod.cached_probe(chemin)
        if info is not None:
            self._on_interpreter_probed(info)

    @Slot()
    def open_history(self) -> None:
        """Les runs passes. Accessible sans workspace charge : on vient
        souvent y chercher ce qu'a donne le run d'hier."""
        from runner.ui.history_dashboard import HistoryWindow

        dialogue = HistoryWindow(self.history, self)
        dialogue.rerun_requested.connect(self._rerun_history)
        dialogue.exec()

    @Slot()
    def open_allure_report(self) -> None:
        """Ouvre le rapport Allure du dernier run demarre.

        Se regenere aussi tout seul apres chaque run (`_on_run_finished`) :
        ce clic n'a donc le plus souvent qu'a ouvrir un rapport deja a jour,
        sans repayer une generation. S'il n'est pas encore pret -- premier
        clic, generation encore en cours -- il attend juste qu'elle finisse.
        """
        if not self._last_allure_dir:
            ErrorDialog.show_error(
                self, "No Allure results",
                "No Allure results are available for the last run.",
                "Make sure allure-pytest is installed in the test "
                'interpreter ("pip install allure-pytest"), then run the '
                "tests again.")
            return
        self._lancer_generation_allure(ouvrir_apres=True)

    def _lancer_generation_allure(self, ouvrir_apres: bool) -> None:
        """Genere le rapport Allure hors du fil de l'interface.

        Un seul rapport, partage par tous les lecteurs d'un run : ce qui les
        distingue A L'INTERIEUR n'est pas le dossier -- c'est le parametre
        "Reader" que le plugin de `reader_isolation.py` pose sur chaque test,
        directement dans le processus pytest.
        """
        dossier_resultats = Path(self._last_allure_dir) if self._last_allure_dir else None
        if (dossier_resultats is None or not dossier_resultats.is_dir()
                or not any(dossier_resultats.iterdir())):
            if ouvrir_apres:
                ErrorDialog.show_error(
                    self, "No Allure results",
                    "No Allure results are available for the last run.",
                    "Make sure allure-pytest is installed in the test "
                    'interpreter ("pip install allure-pytest"), then run the '
                    "tests again.")
            return


        if self._allure_worker is not None and self._allure_worker.isRunning():
            # Deja en cours -- le plus souvent l'auto-regeneration lancee a
            # la fin du run. Pas de deuxieme `allure generate` concurrent sur
            # le meme dossier : juste ouvrir des que celle-la finit.
            self._allure_open_en_attente = self._allure_open_en_attente or ouvrir_apres
            return

        allure_bin = shutil.which("allure")
        if not allure_bin:
            if ouvrir_apres:
                ErrorDialog.show_error(
                    self, "Allure command-line tool not found",
                    "The \"allure\" command was not found on the PATH.",
                    "Install the Allure commandline (requires a JRE) from "
                    "https://allurereport.org/docs/install/ and make sure "
                    '"allure" is on the PATH.')
            return

        self._restaurer_historique_allure(dossier_resultats)
        rapport = self.history.racine / "allure-report" / "latest"
        self._allure_open_en_attente = ouvrir_apres
        self._allure_worker = AllureReportWorker(
            allure_bin, dossier_resultats, rapport, _environnement_pour_allure(), self)
        self._allure_worker.done.connect(
            lambda ok, detail, rapport=rapport: self._sur_allure_genere(ok, detail, rapport))
        self._allure_worker.start()

    @Slot(bool, str)
    def _sur_allure_genere(self, ok: bool, detail: str, rapport: Path) -> None:
        ouvrir = self._allure_open_en_attente
        self._allure_open_en_attente = False
        self._allure_worker = None

        if not ok:
            if ouvrir:
                ErrorDialog.show_error(
                    self, "Could not generate the Allure report",
                    "The \"allure generate\" command failed.", detail)
            return

        self._sauver_historique_allure(rapport)
        if ouvrir:
            port = self._ensure_allure_server(rapport)
            QDesktopServices.openUrl(QUrl(f"http://127.0.0.1:{port}/index.html"))

    def _allure_history_stash(self) -> Path:
        return self.history.racine / "allure-history"

    def _restaurer_historique_allure(self, dossier_resultats: Path) -> None:
        """Recopie l'historique du dernier rapport genere dans les resultats
        bruts, pour qu'Allure y ajoute un point de plus au lieu de repartir
        d'une tendance vide a chaque generation."""
        stash = self._allure_history_stash()
        if not stash.is_dir():
            return
        cible = dossier_resultats / "history"
        if cible.exists():
            shutil.rmtree(cible)
        shutil.copytree(stash, cible)

    def _sauver_historique_allure(self, rapport: Path) -> None:
        """Range l'historique du rapport qui vient d'etre genere, pour la
        prochaine generation."""
        genere = rapport / "history"
        if not genere.is_dir():
            return
        stash = self._allure_history_stash()
        if stash.exists():
            shutil.rmtree(stash)
        stash.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(genere, stash)

    def _ensure_allure_server(self, dossier: Path) -> int:
        """Sert `dossier` en HTTP local, et rend le port choisi.

        Le rapport Allure est une page qui charge ses donnees par requetes
        AJAX -- ouvrir `index.html` directement en `file://` fait bloquer ces
        requetes par le navigateur (CORS), et le rapport reste bloque sur
        "Loading…" partout, chaque autre onglet en 404. `allure serve` existe
        pour ca, mais bloque le terminal jusqu'a Ctrl+C : impossible a piloter
        depuis une appli sans console. Un petit serveur HTTP maison, garde en
        vie pour la session, evite les deux problemes.
        """
        if self._allure_server is not None:
            return self._allure_server.server_address[1]

        gestionnaire = partial(_GestionnaireAllure, directory=str(dossier))
        serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), gestionnaire)
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()

        self._allure_server = serveur
        self._allure_server_thread = fil
        return serveur.server_address[1]

    @Slot(object)
    def _rerun_history(self, group) -> None:
        """Recharge au besoin le workspace, puis rejoue le lancement choisi."""
        if self.service.busy:
            self.status_label.setText("A run is already in progress")
            return
        self._pending_history_run = group
        courant = self.workspace.path if self.workspace else ""
        if courant and Path(courant) == Path(group.workspace):
            self._launch_pending_history_run()
            return
        self.workspace_combo.setCurrentText(group.workspace)
        self.load_workspace()

    def _launch_pending_history_run(self) -> None:
        group = self._pending_history_run
        if group is None or self.workspace is None:
            return
        if Path(self.workspace.path) != Path(group.workspace):
            return

        disponibles = set(self.model.nodeids())
        nodeids = [nodeid for nodeid in group.nodeids if nodeid in disponibles]
        if not nodeids:
            self._pending_history_run = None
            ErrorDialog.show_error(
                self, "Could not re-run history",
                "None of the tests from this run exists in the current collection.")
            return

        declares = self.workspace.readers
        demandes = set(group.reader_names)
        trouves = {reader.name for reader in declares if reader.name in demandes}
        if demandes and declares and not trouves:
            self._pending_history_run = None
            ErrorDialog.show_error(
                self, "Could not re-run history",
                "None of the readers from this run is declared by the workspace.",
                "Recorded: " + ", ".join(sorted(demandes)))
            return

        if len(declares) > 1 and demandes:
            self.readers_bar.select_names(declares, trouves)
        self._pending_history_run = None
        self._start(nodeids)

    @Slot()
    def open_config_dialog(self) -> None:
        """Ouvre le fichier de configuration du workspace charge.

        Recharge la collecte apres un enregistrement : le fichier decide de
        l'interpreteur, des lecteurs et du chemin des logs. Garder a l'ecran un
        arbre collecte avec les reglages d'avant ferait travailler sur des
        informations perimees sans que rien ne le signale.
        """
        from runner.ui.config_dialog import ConfigDialog

        if self.workspace is None:
            ErrorDialog.show_error(
                self, "No configuration file",
                "Load a workspace before choosing its configuration file.", "")
            return

        avant = (self.workspace.config_path, self.workspace.readers,
                 self.workspace.log_root, self.workspace.declared_interpreter,
                 self.workspace.reader_mode)

        racine = self.workspace.path
        if not self.workspace.config_path:
            choisi, _ = QFileDialog.getOpenFileName(
                self, "Choose the workspace configuration", racine,
                "YAML files (*.yml *.yaml)")
            if not choisi:
                return
            self._retenir_config(racine, choisi)
            self.workspace = Workspace.load(racine, self._config_retenue(racine))

        dialogue = ConfigDialog(
            self.workspace.config_path,
            [r.name for r in self.workspace.readers], self,
            candidats=[str(c) for c in fichiers_config(racine)],
            workspace_path=racine)
        dialogue.exec()

        # Le fichier qu'on vient d'editer devient CELUI du workspace : avoir
        # choisi dans la liste ne servirait a rien si le prochain chargement
        # reprenait la detection automatique.
        self._retenir_config(racine, str(dialogue.path))
        self.workspace = Workspace.load(racine, self._config_retenue(racine))

        apres = (self.workspace.config_path, self.workspace.readers,
                 self.workspace.log_root, self.workspace.declared_interpreter,
                 self.workspace.reader_mode)
        if avant != apres:
            self.load_workspace()
        else:
            self._refresh_interpreter_alert()

    @Slot()
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
        self.page_theme_button.setIcon(
            icons.icon("mdi.theme-light-dark", t.TEXT_MUTED))
        for cle, glyph in (
                ("workspace", "mdi.folder-outline"),
                ("history", "mdi.history"),
                ("configuration", "mdi.cog-outline")):
            self.nav_buttons[cle].setIcon(icons.icon(glyph, t.TEXT_MUTED))
        # Ni une icone teintee ni un StatusPill : juste un label dont la
        # couleur ne vient pas de la feuille globale, a rejouer a la main.
        self.compass_pct.setStyleSheet(
            f"color: {t.TEXT}; font-weight: 600; font-size: {t.TEXT_SM + 4}px;")

        for glyphe, bouton in (
                ("mdi.folder-open-outline", self.browse_button),
                ("mdi.file-cog-outline", self.config_button),
                ("mdi.history", self.history_button),
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
        from PySide6.QtWidgets import QWidget

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

    @Slot()
    def browse_workspace(self) -> None:
        depart = self.workspace_combo.currentText() or str(Path.home())
        chemin = QFileDialog.getExistingDirectory(self, "Choose a workspace", depart)
        if chemin:
            self.workspace_combo.setCurrentText(chemin)
            self.load_workspace()

    @Slot()
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

        self.workspace = Workspace.load(chemin, self._config_retenue(chemin))
        self._remember_workspace(chemin)

        python = self._require_interpreter()
        if not python:
            return

        # Sonde en fond si le resultat n'est pas deja connu : lancer un
        # sous-processus a chaque `_start()` gelerait l'interface (voir
        # `interpreter.py`). La collecte qui suit prend de toute facon plus
        # longtemps que ce sondage, le cache est pret bien avant le premier
        # "Run tests".
        if interpreter_mod.cached_probe(python) is None:
            self._allure_prober = ProbeWorker(python, self)
            self._allure_prober.done.connect(self._on_interpreter_probed)
            self._allure_prober.start()
        else:
            self._on_interpreter_probed(interpreter_mod.cached_probe(python))

        self.status_label.setText("Collecting tests…")
        self.load_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indetermine : la duree est inconnue

        self._collector = CollectWorker(
            self.workspace.path, python, self.workspace.env, self)
        self._collector.collected.connect(self._on_collected)
        self._collector.failed.connect(self._on_collect_failed)
        self._collector.start()

    @Slot(object)
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
        self.setWindowTitle(f"{WINDOW_TITLE} — {nom}" if nom else WINDOW_TITLE)
        self._update_actions()
        if self._pending_history_run is not None:
            QTimer.singleShot(0, self._launch_pending_history_run)

    @Slot(str)
    def _on_collect_failed(self, message: str) -> None:
        self._pending_history_run = None
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

    def _config_retenue(self, workspace: str) -> str:
        """Chemin du fichier de configuration choisi pour ce workspace, ou "".

        Range par workspace : on passe d'un projet a l'autre, et le fichier
        retenu pour l'un ne veut rien dire pour l'autre.
        """
        table = self.settings.value(K_CONFIG, {}) or {}
        return str(table.get(workspace, "")) if isinstance(table, dict) else ""

    def _retenir_config(self, workspace: str, chemin: str) -> None:
        table = self.settings.value(K_CONFIG, {}) or {}
        if not isinstance(table, dict):
            table = {}
        config = Path(chemin)
        if not config.is_absolute():
            config = Path(workspace) / config
        try:
            # Relatif au workspace : le projet peut etre deplace ou clone sur
            # un autre PC sans que le choix memorise devienne caduc.
            retenu = str(config.resolve().relative_to(Path(workspace).resolve()))
        except ValueError:
            retenu = str(config.resolve())
        table[workspace] = retenu
        self.settings.setValue(K_CONFIG, table)

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

    @Slot()
    def run_selected(self) -> None:
        self._start(self.model.checked_nodeids())

    @Slot()
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
        self._run_id = history.nouvel_identifiant()
        self._build_number = self.history.next_build_number()
        self._last_allure_dir = self._allure_dir_for(python, self._run_id)
        requete = RunRequest(
            workspace=self.workspace.path,
            interpreter=python,
            nodeids=tuple(nodeids),
            readers=lecteurs,
            config_path=self.workspace.config_path,
            sequential=self.workspace.reader_mode == MODE_SEQUENTIEL,
            run_id=self._run_id,
            junit_dir=str(self.history.racine),
            build_number=self._build_number,
            allure_dir=self._last_allure_dir,
        )
        self.service.start(requete, self.workspace.env)

    def _allure_dir_for(self, python: str, run_id: str) -> str:
        """Ou ecrire les resultats allure-pytest de ce run, ou "" si son
        interpreteur ne connait pas le plugin.

        `cached_probe` ne lance rien : le vrai sondage (couteux, un sous-
        processus) a deja eu lieu en fond pendant `load_workspace`. Un run
        demarre avant que ce sondage finisse se passe simplement d'Allure --
        pas d'attente ici, jamais.
        """
        info = interpreter_mod.cached_probe(python)
        if info is None or not info.has_allure:
            return ""
        dossier = self.history.racine / "allure-results" / run_id
        dossier.mkdir(parents=True, exist_ok=True)
        return str(dossier)

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

    @Slot()
    def stop_run(self) -> None:
        """Arrete ce qui tourne -- un run normal, ou une serie de stress-test.

        Un seul bouton pour les deux : avant, arreter un stress-test passait
        par le bouton d'un bandeau a part, qu'il fallait d'abord retrouver.
        """
        if self.service.busy:
            self.service.cancel()
            self.status_label.setText("Stopping…")
        elif self._stress_worker is not None:
            self._arreter_stress()
            self.status_label.setText("Stopping…")

    def _set_status_live(self, texte: str) -> None:
        """Style "en cours" du label de statut : couleur pleine et gras au
        lieu du gris attenue du repos.

        Le meme traitement sert un run normal ET une serie de stress-test --
        un seul endroit a regarder, plutot qu'un widget dedie a part qui
        finit par se cacher dans un coin qu'on ne regarde plus.
        """
        couleur = t.status_color(Status.RUNNING)
        # Nom d'objet + regle globale (`QLabel#StatusLive` dans theme.py),
        # jamais `setStyleSheet()` directement sur ce label : loge dans le
        # badge `live_chip`, lui-meme dans la barre de statut de la fenetre,
        # une feuille posee ici faisait dessiner a Qt un contour fantome
        # autour de la ligne qui le contient. `unpolish`/`polish` est
        # necessaire ici (et pas ailleurs dans ce fichier) parce que ce
        # label existant change de nom d'objet en cours de vie -- les autres
        # ne font que naitre avec le bon nom.
        self.status_label.setObjectName("StatusLive")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(texte)
        self.live_dot.set_color(couleur)
        self.live_dot.start()
        self.live_chip.setStyleSheet(
            f"background-color: {t.rgba(couleur, 0.12)};"
            f"border: 1px solid {t.rgba(couleur, 0.3)};"
            f"border-radius: {t.RADIUS_PILL}px;")

    def _set_status_idle(self, texte: str) -> None:
        self.status_label.setObjectName("Muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(texte)
        self.live_dot.stop()
        self.live_chip.setStyleSheet("")

    @Slot(object)
    def _on_run_started(self, request: RunRequest) -> None:
        self.model.clear_statuses()
        self.model.clear_stress_annotation()
        self.results.begin_run()

        self.progress.setVisible(True)
        self.progress.setRange(0, max(1, request.total_tests))
        # Les statuts viennent d'etre effaces : le decompte de l'arbre est a
        # zero, et les pastilles s'y alignent comme partout ailleurs.
        self._rafraichir_compteurs()

        # Un filtre pose sur le run precedent masquerait les resultats du
        # nouveau au fur et a mesure qu'ils arrivent.
        self._clear_status_filter()

        self.remaining_pill.set_value(request.total_tests)
        self.remaining_pill.setVisible(True)

        self._seconds = 0
        self.elapsed_label.setText("0s")
        self._elapsed.start()
        self._set_status_live(f"Running {len(request.nodeids)} tests…")
        self._update_actions()

    @Slot(object)
    def _on_outcome(self, outcome) -> None:
        connu = self.model.apply_outcome(outcome.nodeid, outcome.status,
                                         outcome.reader_index)
        if not connu:
            # Collecte non reproductible : le test a tourne sous un identifiant
            # que l'arbre ne connait pas. Le signaler vaut mieux que le perdre.
            self.status_label.setText(f"Unexpected test id: {outcome.nodeid}")

        self._rafraichir_compteurs()
        self.results.update_statuses(outcome.nodeid,
                                     self.model.statuses_for_nodeid(outcome.nodeid))

    def _rafraichir_compteurs(self) -> None:
        """Aligne les pastilles et l'avancement sur l'etat reel de l'arbre.

        Elles s'incrementaient d'un a chaque signal recu, ce qui suppose que
        pytest rapporte chaque test une fois et une seule. Il en rapporte deux
        pour un test rejoue, ou pour une erreur de setup suivie d'un verdict :
        le total affiche depassait alors le nombre de tests, et rien ne le
        remettait d'aplomb avant le run suivant.
        """
        rendus = self.model.status_counts()
        for statut, pastille in self.pills.items():
            pastille.set_value(rendus.get(statut, 0))
        self.compass_ring.set_counts(rendus)
        total = sum(rendus.values())
        passed = rendus.get(Status.PASSED, 0)
        self.compass_pct.setText(f"{round(100 * passed / total)}%" if total else "—")

        faits = self.model.done()
        self.progress.setValue(faits)
        # Pas de `max(0, ...)` ici : la pastille borne deja, et c'est chez elle
        # que la regle a sa place -- « je n'affiche pas un reste negatif » est
        # son invariant, pas celui de la fenetre.
        self.remaining_pill.set_value(self.progress.maximum() - faits)

    @Slot(int, int)
    def _on_progress(self, faits: int, total: int) -> None:
        # Les nombres viennent de l'arbre, pas du compte de signaux porte par
        # le service : c'est la meme raison que pour les pastilles.
        self._rafraichir_compteurs()
        self._set_status_live(f"Running… {self.remaining_pill.value()} left")

    @Slot(list)
    def _on_run_finished(self, rapports: list) -> None:
        self._elapsed.stop()
        self.progress.setVisible(False)

        self.remaining_pill.setVisible(False)
        self._archiver(rapports)

        annule = any(r.cancelled for r in rapports)
        echecs = sum(r.failed for r in rapports)
        if annule:
            resume = "Run stopped"
        elif echecs:
            resume = f"{echecs} failed"
        else:
            resume = "All tests passed"
        self._set_status_idle(f"{resume} · {self._seconds}s")
        # La duree est deja dans le resume : la laisser aussi a cote
        # l'afficherait deux fois.
        self.elapsed_label.clear()
        self.results.refresh_logs()
        self._update_actions()
        if self._last_allure_dir:
            # Auto-regeneration : l'utilisateur n'a jamais besoin de cliquer
            # sur le bouton Allure juste pour rafraichir le HTML apres un run.
            self._lancer_generation_allure(ouvrir_apres=False)
        if not annule:
            self._notifier_fin_de_run(resume)

    def _notifier_fin_de_run(self, resume: str) -> None:
        """Notification systeme : le run a souvent fini pendant qu'on faisait
        autre chose, et rien d'autre ne le signale une fois la fenetre hors
        de vue.

        Les quatre compteurs sont TOUJOURS les quatre, meme a zero : contrairement
        aux pastilles de la barre d'etat, une notification qui disparait ne se
        relit pas -- mieux vaut le zero explicite qu'un compte qu'on devine absent.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        rendus = self.model.status_counts()
        detail = (
            f"{rendus.get(Status.PASSED, 0)} passed · "
            f"{rendus.get(Status.FAILED, 0)} failed · "
            f"{rendus.get(Status.SKIPPED, 0)} skipped · "
            f"{rendus.get(Status.ERROR, 0)} error"
        )
        icone = (QSystemTrayIcon.Critical
                if rendus.get(Status.FAILED, 0) or rendus.get(Status.ERROR, 0)
                else QSystemTrayIcon.Information)
        self._tray.showMessage(resume, detail, icone)

    def _archiver(self, rapports: list) -> None:
        """Depose un run par lecteur dans l'historique.

        Un lecteur, une entree : chacun a ses compteurs, sa sortie et son
        verdict. Un total agrege masquerait lequel a echoue, ce qui est
        justement la question quand on teste la meme suite sur deux lecteurs.

        Un run ANNULE n'est pas archive : ses compteurs sont ceux de ce qui a
        eu le temps de passer, et compares aux runs entiers ils feraient
        passer des tests jamais joues pour des tests instables.
        """
        if self._run_id is None or self.workspace is None:
            return

        joues = list(self.model.nodeids())
        for rapport in rapports:
            if rapport.cancelled:
                continue
            entree = history.RunEntry(
                id=self._run_id,
                timestamp=time.time(),
                workspace=self.workspace.path,
                build_number=self._build_number,
                log_root=str(self.workspace.log_root),
                reader=rapport.reader.name,
                duration=rapport.duration,
                exit_code=rapport.exit_code,
                counts={s.name: n for s, n in rapport.counts.items()},
                nodeids=tuple(joues),
                failed_nodeids=tuple(
                    self.model.failed_nodeids_for(rapport.reader.index)),
                junit_path=rapport.junit_path,
            )
            self.history.add(entree, rapport.output)
        self._run_id = None
        self._build_number = None

    def _tick(self) -> None:
        self._seconds += 1
        self.elapsed_label.setText(f"{self._seconds}s")

    # =====================================================================
    # Interactions de l'arbre
    # =====================================================================

    @Slot(QModelIndex)
    def _on_tree_clicked(self, index: QModelIndex) -> None:
        self._select_test(index)

    @Slot(QModelIndex, QModelIndex)
    def _on_tree_current(self, index: QModelIndex, _precedent: QModelIndex) -> None:
        self._select_test(index)

    def _select_test(self, index: QModelIndex) -> None:
        """Montre la fiche de ce qui est pointe : un test, ou un regroupement.

        Un regroupement ne restait auparavant lie a rien : la fiche gardait le
        test precedent a l'ecran, et l'on croyait lire le dossier qu'on venait
        de cliquer.
        """
        if not index.isValid():
            return
        premiere = index.siblingAtColumn(0)
        nodeid = self.model.data(premiere, NODEID_ROLE)
        if nodeid:
            self.results.show_test(
                nodeid, self.model.statuses_for_nodeid(nodeid),
                self.workspace.path if self.workspace else "",
                self._markers_by_nodeid.get(nodeid, ()),
                self._recent_runs_for(nodeid), self.history.last_seen(nodeid))
            return

        compteurs, echecs = self.model.subtree_summary(premiere)
        chemin, nom = self._situer(premiere)
        source, saut = self._source_du_groupe(premiere)
        nodeids = self.model.leaf_nodeids_under(premiere)
        self.results.show_group(chemin, nom, self.model.readers,
                                compteurs, echecs, source, saut, nodeids)

    def _recent_runs_for(self, nodeid: str) -> dict[int, list[bool]]:
        """Mini-tendance de ce test, par lecteur -- absente des lecteurs qui
        n'ont encore aucun run enregistre pour lui."""
        lecteurs = self.model.readers or (Reader("", 0),)
        resultat = {}
        for lecteur in lecteurs:
            runs = self.history.recent_runs(nodeid, lecteur.name)
            if runs:
                resultat[lecteur.index] = runs
        return resultat

    def _source_du_groupe(self, index: QModelIndex) -> tuple:
        """Fichier a montrer pour ce regroupement, et ou s'y placer.

        Un dossier n'a pas de source. Un module en a une, et on l'ouvre en
        haut. Un noeud de fonction -- un test parametre, qui porte ses cas en
        enfants -- ouvre le fichier ET saute a sa definition : c'est ce qu'on
        attend en cliquant sur un nom de test, parametre ou non.

        Le nodeid manque a un regroupement, mais celui de n'importe laquelle
        de ses feuilles porte le meme fichier avant son premier `::`.
        """
        noeud = self.model.data(index, NODE_ROLE)
        if noeud is None or noeud.kind is Kind.FOLDER or self.workspace is None:
            return None, ""

        temoin = self.model.first_leaf_nodeid(index)
        chemin = source_path(self.workspace.path, temoin)
        if chemin is None:
            return None, ""
        # Le saut se deduit du nodeid : `function_line` y lit le dernier
        # segment. Sur un module on n'en veut pas -- s'ouvrir sur le premier
        # test venu ferait manquer tout ce qui le precede.
        return chemin, (temoin if noeud.kind is Kind.TEST else "")

    def _situer(self, index: QModelIndex) -> tuple[str, str]:
        """Chemin des ancetres, et nom du noeud lui-meme."""
        nom = self.model.data(index) or ""
        ancetres = []
        parent = index.parent()
        while parent.isValid():
            ancetres.append(self.model.data(parent) or "")
            parent = parent.parent()
        return " / ".join(reversed(ancetres)), nom

    @Slot(str)
    def _goto_test(self, nodeid: str) -> None:
        """Un echec clique dans la fiche de groupe : l'arbre y va."""
        index = self.model.index_for_nodeid(nodeid)
        if not index.isValid():
            return
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)

    # =====================================================================
    # Menu contextuel de l'arbre
    # =====================================================================

    # Filet de securite de "Run until it fails" : sans lui, un test qui ne
    # casse jamais tournerait indefiniment, sans que rien ne le dise.
    STRESS_CAP_UNTIL_FAIL = 50

    def _menu_contextuel_arbre(self, point) -> None:
        index = self.tree.indexAt(point)
        if not index.isValid():
            return
        # Meme geste qu'un clic : la fiche affichee suit le noeud sur lequel
        # on vient de faire un clic droit, pas celui d'avant.
        self.tree.setCurrentIndex(index)
        premiere = index.siblingAtColumn(0)
        nodeid = self.model.data(premiere, NODEID_ROLE)

        menu = QMenu(self)
        if nodeid:
            self._construire_menu_test(menu, nodeid)
        else:
            self._construire_menu_groupe(menu, premiere)
        if menu.actions():
            menu.exec_(self.tree.viewport().mapToGlobal(point))

    def _construire_menu_test(self, menu: QMenu, nodeid: str) -> None:
        occupe = self.service.busy or self._stress_worker is not None
        action_run = menu.addAction(
            icons.icon("mdi.play"), "Run only this test",
            lambda: self._start([nodeid]))
        action_run.setEnabled(not occupe)

        action_until = menu.addAction(
            icons.icon("mdi.repeat"), "Run until it fails…",
            lambda: self._lancer_stress(nodeid, MODE_UNTIL_FAIL,
                                        self.STRESS_CAP_UNTIL_FAIL))
        action_until.setEnabled(not occupe)

        action_n_fois = menu.addAction(
            icons.icon("mdi.layers-triple-outline"), "Run N times…",
            lambda: self._demander_run_n_fois(nodeid))
        action_n_fois.setEnabled(not occupe)

        menu.addSeparator()
        menu.addAction(icons.icon("mdi.content-copy"), "Copy nodeid",
                       lambda: QApplication.clipboard().setText(nodeid))

        echec = self._echec_connu_pour(nodeid)
        action_trace = menu.addAction(
            icons.icon("mdi.content-copy"), "Copy failure trace",
            lambda: QApplication.clipboard().setText(f"{echec.title}\n\n{echec.body}"))
        action_trace.setEnabled(echec is not None)

        menu.addSeparator()
        menu.addAction(icons.icon("mdi.file-outline"), "Open file",
                       lambda: self.results.show_tab(ONGLET_SOURCE))

    def _construire_menu_groupe(self, menu: QMenu, index: QModelIndex) -> None:
        occupe = self.service.busy or self._stress_worker is not None
        nodeids = self.model.leaf_nodeids_under(index)
        action_run = menu.addAction(
            icons.icon("mdi.play"), "Run only this",
            lambda: self._start(nodeids))
        action_run.setEnabled(not occupe and bool(nodeids))

        noeud = self.model.data(index, NODE_ROLE)
        if noeud is not None and noeud.kind is not Kind.FOLDER:
            menu.addSeparator()
            menu.addAction(icons.icon("mdi.file-outline"), "Open file",
                           lambda: self.results.show_tab(ONGLET_SOURCE))

    def _echec_connu_pour(self, nodeid: str):
        """Le dernier echec connu de ce test, tous lecteurs confondus.

        Assez pour activer "Copy failure trace" : le menu ne pretend pas
        choisir LE bon lecteur quand plusieurs ont echoue differemment, il
        prend juste le premier qui a quelque chose a montrer.
        """
        for lecteur in (self.model.readers or (Reader("", 0),)):
            echec = self.results.failure_for(nodeid, lecteur.index)
            if echec is not None:
                return echec
        return None

    # =====================================================================
    # "Run until it fails" / "Run N times"
    # =====================================================================

    def _demander_run_n_fois(self, nodeid: str) -> None:
        dialogue = RunNTimesDialog(20, self)
        if dialogue.exec() == QDialog.Accepted:
            self._lancer_stress(nodeid, MODE_N_TIMES, dialogue.count())

    def _lancer_stress(self, nodeid: str, mode: str, cap: int) -> None:
        if (self.workspace is None or self.service.busy
                or self._stress_worker is not None):
            return

        # Meme garde qu'un run normal : une correction encore dans l'editeur
        # ferait rejouer la version d'avant, cap fois, sans que rien ne le dise.
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

        lecteurs = self._readers_to_run() or (Reader("", 0),)
        requete = RunRequest(
            workspace=self.workspace.path, interpreter=python,
            nodeids=(nodeid,), readers=lecteurs,
            config_path=self.workspace.config_path, sequential=True,
        )

        self._stress_nodeid = nodeid
        self._stress_mode = mode
        self._stress_cap = cap
        self._stress_ran = 0
        self._stress_passed = 0
        self._stress_failed = []

        self._stress_worker = StressRunWorker(
            requete, lecteurs, self.workspace.env, mode, cap, self)
        self._stress_worker.attempt_done.connect(self._sur_tentative_stress)
        self._stress_worker.finished_stress.connect(self._sur_fin_stress)

        self._set_status_live(self._stress_detail(mode, nodeid, 0, cap))
        self.model.set_stress_annotation(nodeid, self._stress_compact(mode, 0, cap))
        self.results.detail.show_stress_running(nodeid, mode, cap, 0, 0, 0)
        self._update_actions()
        self._stress_worker.start()

    def _stress_compact(self, mode: str, ran: int, cap: int) -> str:
        """Le texte colle sur la ligne du test dans l'arbre : court expres,
        il partage la ligne avec le nom du test. Le detail complet est dans
        la barre de statut -- voir `_stress_detail`."""
        prefixe = "Stress" if mode == MODE_UNTIL_FAIL else "Run"
        return f"{prefixe} {ran + 1}/{cap}"

    def _stress_detail(self, mode: str, nodeid: str, ran: int, cap: int) -> str:
        court = nodeid.split("::", 1)[-1].replace("::", " › ")
        verbe = "Stress-testing" if mode == MODE_UNTIL_FAIL else "Running"
        mot = "attempt" if mode == MODE_UNTIL_FAIL else "run"
        return f"{verbe} {court} — {mot} {ran + 1} of {cap}"

    def _sur_tentative_stress(self, tentative: StressAttempt) -> None:
        self._stress_ran = tentative.number
        if tentative.ok:
            self._stress_passed += 1
        else:
            self._stress_failed.append(tentative)

        # Le point sur l'arbre suit le verdict propre a CHAQUE lecteur : un
        # flaky qui ne rate que sur l'un d'eux ne doit pas se voir imputer aux
        # autres, qui ont reellement passe cette tentative.
        for resultat in tentative.reports:
            self.model.apply_outcome(
                self._stress_nodeid, resultat.status, resultat.reader.index)

        self._archiver_stress(tentative)

        self._set_status_live(self._stress_detail(
            self._stress_mode, self._stress_nodeid, self._stress_ran, self._stress_cap))
        self.model.set_stress_annotation(
            self._stress_nodeid,
            self._stress_compact(self._stress_mode, self._stress_ran, self._stress_cap))
        self.results.detail.show_stress_running(
            self._stress_nodeid, self._stress_mode, self._stress_cap,
            self._stress_ran, self._stress_passed, len(self._stress_failed))

    def _archiver_stress(self, tentative: StressAttempt) -> None:
        """Depose une tentative dans l'historique, un lecteur = une entree --
        exactement comme un run normal (`_archiver`).

        Sans ca, "Run until it fails" et "Run N times" ne laissaient RIEN
        dans l'onglet History : chaque tentative doit s'y retrouver, avec sa
        propre sortie et son propre JUnit, pour pouvoir la rejouer ou lire ses
        logs plus tard comme n'importe quel autre run.
        """
        if self.workspace is None:
            return
        identifiant = history.nouvel_identifiant()
        for resultat in tentative.reports:
            rapport = resultat.report
            entree = history.RunEntry(
                id=identifiant,
                timestamp=time.time(),
                workspace=self.workspace.path,
                build_number=None,
                log_root=str(self.workspace.log_root),
                reader=resultat.reader.name,
                duration=rapport.duration,
                exit_code=rapport.exit_code,
                counts={s.name: n for s, n in rapport.counts.items()},
                nodeids=(self._stress_nodeid,),
                failed_nodeids=(() if resultat.ok else (self._stress_nodeid,)),
                junit_path=rapport.junit_path,
            )
            self.history.add(entree, rapport.output)

    def _sur_fin_stress(self, resume: StressSummary) -> None:
        self._stress_worker = None
        nodeid = self._stress_nodeid
        court = nodeid.split("::", 1)[-1].replace("::", " › ")

        if resume.cancelled:
            compact = f"Stopped {resume.ran}/{resume.cap}"
            detail = f"Stopped — {court} — {resume.ran} of {resume.cap} runs done"
        elif resume.mode == MODE_UNTIL_FAIL and resume.failed_attempts:
            derniere = resume.failed_attempts[-1]
            compact = f"Failed {derniere.number}/{resume.cap}"
            detail = (f"Stopped — {court} failed — "
                     f"attempt {derniere.number} of {resume.cap}")
        elif resume.mode == MODE_UNTIL_FAIL:
            compact = f"Never failed ({resume.ran})"
            detail = f"Never failed — {court} — {resume.ran} of {resume.cap} attempts"
        else:
            taux = round(100 * resume.passed / resume.ran) if resume.ran else 0
            echecs = len(resume.failed_attempts)
            compact = f"{resume.ran}/{resume.cap} · {taux}%"
            detail = (f"{resume.ran} of {resume.cap} runs complete — {court} — "
                     f"{resume.passed} passed · {echecs} failed · {taux}% pass rate")

        self._set_status_idle(detail)
        self.model.set_stress_annotation(nodeid, compact)
        self.results.detail.show_stress_done(nodeid, resume)
        self._update_actions()

    def _arreter_stress(self) -> None:
        if self._stress_worker is not None:
            self._stress_worker.cancel()

    @Slot(int, int)
    def _on_selection_changed(self, coches: int, total: int) -> None:
        self.selection_label.setText(f"{coches} of {total} tests selected")
        self._update_actions()

    @Slot()
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

    @Slot(int)
    def _on_reader_selected(self, index: int) -> None:
        lecteurs = self.workspace.readers if self.workspace else ()
        if 0 <= index < len(lecteurs):
            self.status_label.setText(f"Showing {lecteurs[index].name}")

    @Slot()
    def _open_markers(self) -> None:
        if not self.markers.isHidden():
            self.markers.toggle_popup()

    @Slot()
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

        self.model.set_checked_nodeids(retenus)

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

    @Slot()
    def clear_marker_filter(self) -> None:
        """Retire le filtre sans toucher a la selection qu'il a produite.

        Decocher au passage ferait perdre un choix qu'on vient peut-etre
        d'affiner a la main ; enlever l'etiquette suffit a dire que le filtre
        ne s'applique plus.
        """
        self.markers.clear()
        self._show_active_filter()
        self.status_label.setText("Marker filter cleared")

    @Slot(object)
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

    @Slot()
    def select_divergent(self) -> None:
        """Ne garde coches que les tests sur lesquels les lecteurs different.

        C'est la question qui motive un run multi-lecteur : la reponse doit
        etre a un raccourci, pas a un tri manuel.
        """
        divergents = self.model.divergent_nodeids()
        if not divergents:
            self.status_label.setText("Every reader agrees so far")
            return
        self.model.set_checked_nodeids(divergents)
        self.status_label.setText(f"{len(divergents)} tests where readers disagree")

    def _toggle_compare(self) -> None:
        courant = self.results.tabs.currentWidget()
        if hasattr(courant, "toggle_compare"):
            courant.toggle_compare()

    # ----------------------------------------------------------- recherche

    @Slot(str)
    def _on_search(self, texte: str) -> None:
        if self.search.scope == SCOPE_FAILURES:
            trouvailles = self._matching_failures(texte)
            self._matches = [nodeid for nodeid, _ in trouvailles]
            self._remplir_resultats_echecs(trouvailles, texte)
        else:
            self._matches = self.model.matching_nodeids(texte)
            self.failure_results.setVisible(False)

        self._match_index = 0 if self._matches else -1
        if self._matches:
            self._reveal(self._matches[0])
        self.search.set_matches(self._match_index + 1, len(self._matches))

    def _on_search_scope_changed(self, scope: str) -> None:
        # `field.clear()` ne redeclenche pas `_on_search` si le champ etait
        # deja vide (aucun texte a supprimer) : sans cette remise a plat, un
        # changement de portee a vide laisserait les resultats de l'autre.
        self._matches = []
        self._match_index = -1
        self.search.set_matches(0, 0)
        self.failure_results.clear()
        self.failure_results.setVisible(False)

    def _matching_failures(self, texte: str) -> list[tuple[str, object]]:
        """Nodeids dont la trace d'echec CONNUE contient `texte`.

        Cherche dans les traces deja extraites pour l'affichage (voir
        `ResultsPanel.failure_for`), pas en relisant la sortie brute a
        chaque frappe.
        """
        aiguille = texte.strip().lower()
        if not aiguille:
            return []
        lecteurs = self.model.readers or (Reader("", 0),)
        trouvailles: list[tuple[str, object]] = []
        for nodeid in self.model.nodeids():
            for lecteur in lecteurs:
                echec = self.results.failure_for(nodeid, lecteur.index)
                if echec is not None and aiguille in echec.body.lower():
                    trouvailles.append((nodeid, echec))
                    break
        return trouvailles

    def _remplir_resultats_echecs(self, trouvailles: list, texte: str) -> None:
        self.failure_results.clear()
        if not texte.strip():
            self.failure_results.setVisible(False)
            return
        if not trouvailles:
            self.failure_results.setVisible(True)
            vide = QListWidgetItem("No failure output matches this search.")
            vide.setFlags(Qt.NoItemFlags)
            self.failure_results.addItem(vide)
            return

        self.failure_results.setVisible(True)
        for nodeid, echec in trouvailles:
            court = nodeid.split("::", 1)[-1].replace("::", " › ")
            extrait = self._extrait_correspondant(echec.body, texte)
            item = QListWidgetItem(f"{court}\n{extrait}" if extrait else court)
            item.setData(Qt.UserRole, nodeid)
            item.setToolTip(nodeid)
            self.failure_results.addItem(item)

    def _extrait_correspondant(self, corps: str, texte: str) -> str:
        """La premiere ligne de la trace qui contient `texte`, tronquee.

        C'est ce qui permet de juger un resultat SANS y sauter d'abord : la
        ligne qui a matche, pas tout le pave de trace.
        """
        aiguille = texte.strip().lower()
        for ligne in corps.splitlines():
            if aiguille in ligne.lower():
                propre = ligne.strip()
                return propre if len(propre) <= 120 else propre[:117] + "…"
        return ""

    def _sur_resultat_echec_clique(self, item: QListWidgetItem) -> None:
        nodeid = item.data(Qt.UserRole)
        if not nodeid:
            return
        self._match_index = self._matches.index(nodeid) if nodeid in self._matches else -1
        self._reveal(nodeid)
        self.search.set_matches(self._match_index + 1, len(self._matches))

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
        # Un stress-test occupe l'interpreteur tout autant qu'un run normal :
        # Run / Re-run doivent s'eteindre pendant qu'il tourne, sous peine de
        # deux processus pytest qui se marchent dessus. Stop les couvre tous
        # les deux desormais -- `stop_run()` sait lequel des deux arreter.
        occupe = self.service.busy or self._stress_worker is not None
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
        # Sans YAML detecte, le meme bouton permet d'en CHOISIR un dans un
        # sous-dossier. Le griser empechait precisement de reparer ce cas.
        editable = charge
        self.act_config.setEnabled(editable)
        self.config_button.setEnabled(editable)
        self.workspace_config_button.setEnabled(editable)

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
        self._refresh_interpreter_alert()

    def closeEvent(self, event) -> None:
        self.results.source.save()
        self.settings.setValue(K_GEOMETRY, self.saveGeometry())
        self.settings.setValue(K_STATE, self.saveState())
        self.settings.setValue(K_SPLIT_MAIN, self.split.saveState())
        self.settings.setValue(K_TREE_COLS, self.tree.header().saveState())

        if self.service.busy:
            self.service.cancel()
            self.service.wait(3000)
        if self._allure_server is not None:
            self._allure_server.shutdown()
            self._allure_server.server_close()
        if self._stress_worker is not None:
            self._stress_worker.cancel()
            self._stress_worker.wait(3000)
        super().closeEvent(event)
