from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTextEdit, QSplitter, QComboBox, QSizePolicy, QTabWidget, QFrame, QDialog, QCheckBox,
    QToolButton, QApplication
)

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtWidgets import QLabel, QHBoxLayout
from PyQt5.QtWidgets import QLineEdit


import os
import re
import time
from pathlib import Path

from gui_qt.test_tree_view import TestTreeView, short_reader_label
from gui_qt.config.config_editor import ConfigEditor
from gui_qt.campaign_window import CampaignPanel
from gui_qt.history_window import HistoryWindow
from gui_qt.flaky_window import FlakyTestsDialog
from gui_qt.dialogs import (show_scrollable_error, open_test_log_for, open_config_editor,
                            remembered_config_path)
from gui_qt.detail_panel import DetailPanel


from core.test_discovery import collect_tests
from core.test_tree import build_test_tree
from core.pytest_executor import (PytestOutputParser, compact_output_line,
                                  pytest_nodeid_args)
from core.reader_plugin import CONFIG_PATH_ENV, reader_plugin
from core.reader_switch import ActiveReader, restore_interrupted_reader
from core.run_history import RunHistoryManager, history_dir, new_run_id
from core.workspace_config import (READER_KEYS, config_file_declaring, console_path_levels,
                                   discover_config_files, import_mode_args, load_config,
                                   reader_env, reader_mode_for, readers_for,
                                   show_test_classes)
from core.python_interpreter import (
    check_ready_to_run,
    interpreter_source,
    probe_interpreter,
    resolve_interpreter,
    subprocess_flags,
)
from gui_qt.interpreter_dialog import InterpreterDialog

from gui_qt.styles import styles
from gui_qt.status_icons import forget_status_icons
from gui_qt.styles.styles import (
    theme_toggle_button,
    primary_button,
    neutral_button,
    success_button,
    danger_button,
    info_button,
    separator_style,
    toolbar_button,
    tree_style,
    console_style,
)


_COLLECTED_RE = re.compile(r"collected (\d+) items")

_SUMMARY_PATTERNS = {
    "PASSED": r"(\d+)\s+passed",
    "FAILED": r"(\d+)\s+failed",
    "SKIPPED": r"(\d+)\s+skipped",
    "ERROR": r"(\d+)\s+error",
}


def _parse_summary_counts(sortie: str) -> dict:
    """Compteurs lus dans le resume final pytest d'UNE seule sortie.

    A la difference du total agrege sur tous les lecteurs (utilise pour les
    cartes), sert a donner a chaque lecteur son propre resultat dans
    l'historique des executions.
    """
    counts = {}
    for key, pattern in _SUMMARY_PATTERNS.items():
        matches = re.findall(pattern, sortie, re.IGNORECASE)
        if matches:
            counts[key] = int(matches[-1])
    return counts


def blend_color(base: str, strong: str, ratio: float) -> str:
    """
    Blend two hex colors based on ratio (0.0 -> base, 1.0 -> strong)
    """
    ratio = max(0.0, min(1.0, ratio))

    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    b = hex_to_rgb(base)
    s = hex_to_rgb(strong)

    blended = tuple(
        int(b[i] + (s[i] - b[i]) * ratio)
        for i in range(3)
    )

    return rgb_to_hex(blended)


class PytestWorker(QThread):
    stdout_signal = pyqtSignal(str)
    stderr_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, str)
    # Emis (nodeid, status) des qu'un resultat de test est lu, sans attendre le
    # paquet de lignes suivant : c'est ce qui rend l'arbre vivant pendant le run.
    test_status_signal = pyqtSignal(str, str)
    # Emis avec le nombre de tests annonce par pytest ("collected N items").
    collected_signal = pyqtSignal(int)

    def __init__(self, nodeids, workspace, junit_xml_path=None, parallel=False,
                 interpreter=None, targets=None, reader="", config_path="",
                 write_reader_to_config=False):
        super().__init__()
        # Lecteur de ce run, et comment le transmettre aux tests. En mode
        # sequentiel il est ecrit dans la cle `Reader` de la configuration le
        # temps du run. En parallele, le fichier est rendu virtuellement
        # different pour ce process par un plugin injecte (core/reader_plugin.py),
        # sans jamais toucher au vrai fichier ni au code de test.
        self.reader = reader
        self.config_path = config_path
        self.write_reader_to_config = write_reader_to_config
        self._plugin_args: list[str] = []
        self._plugin_dir = ""
        self.nodeids = nodeids
        # Cibles reellement passees a pytest : repliees en chemins de dossier ou
        # de fichier quand tout le sous-arbre est selectionne. Beaucoup plus
        # rapide que d'enumerer chaque nodeid (mesure : 5,61 s -> 3,43 s sur
        # 6000 tests). A defaut, on retombe sur les nodeids.
        self.targets = targets if targets is not None else nodeids
        self.workspace = workspace
        self.junit_xml_path = junit_xml_path
        self.parallel = parallel
        self.interpreter = interpreter
        self._process = None
        self._stopped = False

    def run(self):
        python = self.interpreter or resolve_interpreter(workspace=self.workspace)

        # Le fichier d'arguments doit survivre jusqu'a la fin du processus pytest :
        # tout le run se deroule donc dans ce bloc. ActiveReader ecrit le lecteur
        # dans la configuration pour la duree du run et remet ensuite la valeur
        # d'origine ; en mode parallele il ne fait rien, le lecteur passant alors
        # par le plugin injecte, qui rend le fichier virtuellement different sans
        # y ecrire.
        config = self.config_path if self.write_reader_to_config else None
        plugin_config = "" if self.write_reader_to_config else self.config_path

        with ActiveReader(config, self.reader), \
                reader_plugin(plugin_config) as (plugin_args, plugin_dir), \
                pytest_nodeid_args(self.targets) as nodeid_args:
            self._plugin_args = plugin_args
            self._plugin_dir = plugin_dir
            self._run_pytest(python, nodeid_args)

    def _run_pytest(self, python, nodeid_args):
        import subprocess

        command = [
            python,
            # -u : pytest n'attend pas de remplir un tampon pour ecrire, les
            # premiers resultats arrivent donc nettement plus tot.
            "-u",
            "-m", "pytest",
            *nodeid_args,
            *self._plugin_args,
            # Pas de --import-mode impose : voir core/workspace_config.py.
            *import_mode_args(self.workspace),
            "--tb=short",
            "-v",
        ]

        if self.parallel:
            # Necessite pytest-xdist. La sortie -v change de format quand -n est
            # utilise ; parse_test_status_line() gere les deux formats.
            command.extend(["-n", "auto"])

        if self.junit_xml_path:
            # Option native de pytest : aucune dependance supplementaire requise.
            command.append(f"--junitxml={self.junit_xml_path}")

        # Merge stderr into stdout to keep correct order and avoid deadlocks.
        # Le Popen est protege : sans ca, un chemin d'interpreteur invalide fait
        # mourir le thread sans emettre finished_signal, et le GUI reste bloque
        # avec "Run" desactive et "Stop" actif.
        try:
            self._process = subprocess.Popen(
                command,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=self._env(),
                creationflags=subprocess_flags(),
            )
        except (OSError, ValueError) as exc:
            message = (
                f"Could not start the test interpreter:\n  {python}\n"
                f"{type(exc).__name__}: {exc}\n"
                "Check the Settings > Test Python interpreter... menu.\n"
            )
            self.stderr_signal.emit(message)
            self.finished_signal.emit(-1, message)
            return

        stdout_buffer = []
        stdout_size = 0
        stdout_limit = 1_000_000  # on garde la fin de sortie pour le resume pytest
        emit_buffer = []
        emit_size = 0
        last_flush = time.monotonic()
        parser = PytestOutputParser()
        # Raccourcissement des chemins a l'AFFICHAGE seulement : stdout_buffer
        # garde la sortie brute, dont dependent l'historique, le resume final et
        # l'extraction des traces d'echec.
        niveaux = console_path_levels(self.workspace)
        avec_classes = show_test_classes(self.workspace)

        def flush_emit_buffer():
            nonlocal emit_buffer, emit_size, last_flush
            last_flush = time.monotonic()
            if emit_buffer:
                self.stdout_signal.emit("".join(emit_buffer))
                emit_buffer = []
                emit_size = 0

        for line in iter(self._process.stdout.readline, ""):
            if self._stopped:
                break

            # Le statut est analyse ICI, dans le thread de lecture, et remonte
            # immediatement : l'arbre et les compteurs avancent test par test, y
            # compris pour chaque cas parametre. L'analyser cote interface
            # obligeait a attendre un paquet de 50 lignes, d'ou un affichage qui
            # progressait par a-coups.
            parsed = parser.feed(line)
            if parsed:
                self.test_status_signal.emit(parsed[0], parsed[1])
            else:
                collected = _COLLECTED_RE.search(line)
                if collected:
                    self.collected_signal.emit(int(collected.group(1)))

            stdout_buffer.append(line)
            stdout_size += len(line)
            while stdout_size > stdout_limit and stdout_buffer:
                stdout_size -= len(stdout_buffer.pop(0))
            affichee = compact_output_line(line, niveaux, avec_classes)
            emit_buffer.append(affichee)
            emit_size += len(affichee)

            # Le texte de la console reste groupe (des milliers de signaux Qt et
            # d'insertions QTextEdit couteraient cher), mais on vide aussi le
            # tampon toutes les 50 ms pour que la console ne prenne pas de retard
            # visible sur l'arbre quand les tests sont lents.
            if (len(emit_buffer) >= 50 or emit_size >= 8192
                    or time.monotonic() - last_flush >= 0.05):
                flush_emit_buffer()

        flush_emit_buffer()
        self._process.wait()
        exit_code = -1 if self._stopped else self._process.returncode
        self.finished_signal.emit(exit_code, "".join(stdout_buffer))

    def _env(self) -> dict:
        """Environnement du processus : lecteur, et plugin s'il y en a un."""
        env = reader_env(self.workspace, self.reader, self.config_path or None)
        if self._plugin_args:
            env[CONFIG_PATH_ENV] = self.config_path
        if self._plugin_dir:
            ancien = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                self._plugin_dir + (os.pathsep + ancien if ancien else ""))
        return env

    @property
    def stopped(self) -> bool:
        """Vrai si le run a ete interrompu par l'utilisateur."""
        return self._stopped

    def stop(self):
        """Stop pytest execution."""

        self._stopped = True

        if self._process and self._process.poll() is None:
            self._process.terminate()




class WorkspaceLoadWorker(QThread):
    loaded_signal = pyqtSignal(object, int, str)
    error_signal = pyqtSignal(str)

    def __init__(self, workspace, interpreter=None):
        super().__init__()
        self.workspace = workspace
        self.interpreter = interpreter

    def run(self):
        try:
            # Le probe est fait ICI, dans le thread de chargement, pour que les
            # lancements de tests suivants puissent verifier l'interpreteur sans
            # lancer de processus depuis le thread UI (sinon : gel de l'interface).
            if self.interpreter:
                probe_interpreter(self.interpreter)

            nodeids = collect_tests(self.workspace, interpreter=self.interpreter)
            roots = build_test_tree(nodeids, self.workspace,
                                    show_classes=show_test_classes(self.workspace))
            self.loaded_signal.emit(roots, len(nodeids), self.workspace)
        except Exception as exc:
            self.error_signal.emit(str(exc))


class SummaryCard(QLabel):
    clicked = pyqtSignal(str)

    def __init__(self, title: str):
        super().__init__()

        self.title = title
        self.status = title.lower()  # "passed", "failed", "skipped", "error"
        # Derniere valeur affichee, pour pouvoir se redessiner apres un
        # changement de theme sans que l'appelant ait a la fournir.
        self._value = 0
        self._max_value = 100

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(96)
        # Une pastille sur une ligne : quatre nombres n'ont pas besoin de la
        # hauteur de quatre lignes de console.
        self.setFixedHeight(26)

        self.setProperty("active", False)

        self.update_value(0)

    def mousePressEvent(self, event):
        self.clicked.emit(self.status)
        super().mousePressEvent(event)

    def set_active(self, active: bool):
        self.setProperty("active", active)
        # Force repaint safely
        self.setStyle(self.style())
        self.update()

    def restyle(self):
        """Redessine la carte avec la palette courante."""
        self.update_value(self._value, self._max_value)

    def update_value(self, value: int, max_value: int = 100):
        self._value = value
        self._max_value = max_value

        base_color, strong_color = styles.card_colors(self.title.upper())
        ratio = min(value / max_value, 1.0) if max_value else 0.0
        background = blend_color(base_color, strong_color, ratio)
        palette = styles.palette()

        self.setStyleSheet(f"""
        QLabel {{
            background-color: {background};
            border-radius: 6px;
            color: {palette['card_text']};
            border: 1px solid transparent;
            padding: 0px 10px;
        }}

        QLabel[active="true"] {{
            border: 2px solid {palette['card_active_border']};
        }}
        """)

        self.setText(
            f"<span style='font-size:13px; font-weight:bold'>{value}</span>"
            f"<span style='font-size:11px; opacity:0.75'>&nbsp;&nbsp;{self.title}</span>"
        )


DETACHED_GEOMETRY_KEY = "detail_panel_geometry"


class DetachedPanelWindow(QWidget):
    """Fenetre d'accueil du panneau Console / Source / Log une fois detache.

    Une fenetre a part se met en plein ecran, ou sur un second ecran : c'est la
    seule facon de donner a une console la place qu'une fenetre partagee avec
    l'arbre ne lui laissera jamais.
    """

    closed = pyqtSignal()

    def __init__(self, contenu: QWidget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Console, Source et Log - PyTest Runner")
        self.setWindowFlags(Qt.Window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(contenu)

    def closeEvent(self, event):
        # Fermer la fenetre detachee doit rendre le panneau, pas le faire
        # disparaitre : sans cela la console serait perdue jusqu'au redemarrage.
        self.closed.emit()
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PyTest Runner (PyQt5)")

        self.history_window = None
        self.history_manager = RunHistoryManager()
        self._current_run_id = None
        self._current_junit_path = None
        self._run_started_at = None
        self._current_run_nodeids: list[str] = []
        # Resultats renvoyes par pytest sans equivalent dans l'arbre : signe
        # que la collecte n'est pas reproductible d'un lancement a l'autre.
        self._unmatched_results: list[str] = []
        self._replaced_cases = 0
        self.workers: list = []
        self._runs_left = 0
        self._run_outputs: list[str] = []
        self.settings = QSettings("MyCompany", "PyTestRunner")
        styles.set_theme(self.settings.value("theme", "light", type=str))
        # main_qt.py pose la feuille de style avant de connaitre le theme
        # memorise : on la repose ici avec la bonne palette.
        _app = QApplication.instance()
        if _app is not None:
            _app.setStyleSheet(styles.app_stylesheet())
        forget_status_icons()

        self._build_mode_menu()
        self._build_reports_menu()
        self._build_settings_menu()
        self._build_theme_button()

        self.resize(900, 700)
        self.total_tests = 0
        self.done_tests = 0
        self.failed_nodeids: set[str] = set()
        # Un historique par lecteur : chacun tourne dans son propre process et
        # merite sa propre ligne (voir _on_finished), donc son propre suivi.
        self._current_readers: list[str] = [""]
        self._current_junit_paths: list[str] = [""]
        self._failed_nodeids_by_reader: list[set[str]] = [set()]
        self._exit_codes: list[int] = [0]

        self.test_counts = {
            "PASSED": 0,
            "FAILED": 0,
            "SKIPPED": 0,
            "ERROR": 0,
        }
        # ---- Workspace selection ----
        self.workspace_combo = QComboBox()
        self.workspace_combo.setEditable(True)
        self.workspace_combo.setInsertPolicy(QComboBox.NoInsert)
        self.workspace_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.workspace_combo.setPlaceholderText("Enter workspace path...")
        recent = self.settings.value("recent_workspaces", [], type=list)

        for path in recent:
            self.workspace_combo.addItem(path)

        last = self.settings.value("last_workspace", "")
        if last:
            if last not in recent:
                self.workspace_combo.insertItem(0, last)
            self.workspace_combo.setCurrentText(last)

        last_workspace = self.settings.value("last_workspace", "")
        if last_workspace:
            self._add_recent_workspace(last_workspace)
            self.workspace_combo.setCurrentText(last_workspace)

        self.browse_button = QPushButton("Browse")
        self.load_button = QPushButton("Load Workspace")
        self.open_config_button = QPushButton("Open Config")

        self.load_button.setStyleSheet(primary_button())
        self.browse_button.setStyleSheet(neutral_button())
        self.open_config_button.setStyleSheet(neutral_button())


        # self.config_editor = ConfigEditor()
        # self.config_editor.setVisible(False)
        self.browse_button.clicked.connect(self.browse_workspace)
        self.load_button.clicked.connect(self.load_workspace)
        self.open_config_button.clicked.connect(self.open_config)

        self.run_button = QPushButton("▶  Run Selected")
        self.stop_button = QPushButton("■  Stop")
        self.rerun_failed_button = QPushButton("↻  Re-run Failed")

        # Un seul bouton plein par barre : celui qu'on vient chercher. Les deux
        # autres restent en contour, reconnaissables a leur couleur sans
        # monopoliser l'attention quand ils ne servent pas.
        self.run_button.setStyleSheet(success_button())
        self.stop_button.setStyleSheet(danger_button())
        self.rerun_failed_button.setStyleSheet(info_button())

        for bouton in (self.run_button, self.stop_button, self.rerun_failed_button,
                       self.load_button, self.open_config_button, self.browse_button):
            bouton.setCursor(Qt.PointingHandCursor)

        self.rerun_failed_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.run_button.setEnabled(False)

        self.run_button.clicked.connect(self.run_selected_tests)
        self.stop_button.clicked.connect(self.stop_tests)
        self.rerun_failed_button.clicked.connect(self.run_failed_tests)

        # Console, Source et Log dans un meme panneau. self.console reste le
        # QTextEdit de l'onglet Console : tout le code d'affichage existant
        # continue de fonctionner sans changement.
        self.details = DetailPanel()
        self.console = self.details.console
        self._console_pending: list[str] = []
        self._console_flush_timer = QTimer(self)
        self._console_flush_timer.setInterval(50)
        self._console_flush_timer.timeout.connect(self._flush_console_output)

        # Regroupe les mises a jour des cartes de resume pendant un run : elles
        # restent vivantes a l'oeil sans etre reconstruites a chaque test.
        self._cards_dirty = False
        self._cards_timer = QTimer(self)
        self._cards_timer.setInterval(100)
        self._cards_timer.timeout.connect(self._refresh_summary_cards)

        self.tree = TestTreeView()
        self.tree.run_requested.connect(self.run_specific_nodeids)
        self.tree.open_file_requested.connect(self.open_test_file)
        self.tree.open_log_requested.connect(self.open_test_log)

        self.tree.setStyleSheet(tree_style())
        self.tree.item_clicked.connect(self._on_tree_item_clicked)
        self.details.detach_requested.connect(self.set_details_detached)
        self._detached_window: DetachedPanelWindow | None = None

        central = QWidget()
        workspace_bar = QHBoxLayout()
        workspace_bar.setSpacing(8)

        workspace_bar.addWidget(self.workspace_combo)
        workspace_bar.addWidget(self.browse_button)
        # workspace_bar.addStretch()

        layout = QVBoxLayout(central)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        # Workspace actions
        action_bar.addWidget(self.load_button)
        action_bar.addWidget(self.open_config_button)

        action_bar.addWidget(self._separator())

        # Test actions
        action_bar.addWidget(self.run_button)
        action_bar.addWidget(self.stop_button)
        action_bar.addWidget(self.rerun_failed_button)

        # Lecteurs : n'apparait que si le workspace en declare plusieurs.
        self._reader_separator = self._separator()
        action_bar.addWidget(self._reader_separator)
        self.reader_bar = QHBoxLayout()
        self.reader_bar.setSpacing(10)
        action_bar.addLayout(self.reader_bar)
        self.reader_checkboxes: list[QCheckBox] = []

        self.diff_button = QPushButton("Differences only")
        self.diff_button.setCheckable(True)
        self.diff_button.setCursor(Qt.PointingHandCursor)
        self.diff_button.setStyleSheet(toolbar_button())
        self.diff_button.setToolTip(
            "Only show tests where the readers disagree.")
        self.diff_button.toggled.connect(self.tree.filter_divergences)
        action_bar.addWidget(self.diff_button)
        self._show_reader_controls(False)

        # Sans cet espace final, la barre repartit toute la largeur de la
        # fenetre entre les boutons : ils s'etiraient sur 250 px chacun et
        # flottaient au milieu. Ils gardent maintenant leur taille naturelle et
        # restent groupes a gauche.
        action_bar.addStretch(1)

        layout.addLayout(workspace_bar)
        layout.addLayout(action_bar)

        tree_toolbar = QHBoxLayout()
        tree_toolbar.setSpacing(6)

        self.btn_select_all = QPushButton("All")
        self.btn_select_none = QPushButton("None")
        self.btn_select_all.clicked.connect(self.select_all_tests)
        self.btn_select_none.clicked.connect(self.select_no_tests)

        self.btn_failed_only = QPushButton("Failed only")
        self.btn_failed_only.setCheckable(True)
        self.btn_failed_only.clicked.connect(lambda: self.on_summary_clicked("failed"))

        self.btn_expand_all = QPushButton("Expand All")
        self.btn_expand_all.clicked.connect(self.tree.expandAll)

        self.btn_collapse_all = QPushButton("Collapse All")
        self.btn_collapse_all.clicked.connect(self.tree.collapseAll)

        self.btn_select_all.setStyleSheet(toolbar_button())
        self.btn_select_none.setStyleSheet(toolbar_button())
        self.btn_failed_only.setStyleSheet(toolbar_button())
        self.btn_expand_all.setStyleSheet(toolbar_button())
        self.btn_collapse_all.setStyleSheet(toolbar_button())

        self.selection_label = QLabel("0 / 0 selected")
        self.selection_label.setAlignment(Qt.AlignRight)
        self.selection_label.setStyleSheet("color: #616161; font-size: 12px;")
        self.tree.selection_changed.connect(self.on_selection_changed)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter tests...")
        self.filter_edit.textChanged.connect(self.on_filter_text_changed)

        tree_toolbar.addWidget(self.btn_select_all)
        tree_toolbar.addWidget(self.btn_select_none)
        tree_toolbar.addWidget(self.btn_failed_only)
        tree_toolbar.addWidget(self.btn_expand_all)
        tree_toolbar.addWidget(self.btn_collapse_all)
        tree_toolbar.addStretch()
        tree_toolbar.addWidget(self.filter_edit)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        left_layout.addLayout(tree_toolbar)
        left_layout.addWidget(self.tree)
        left_layout.addWidget(self.selection_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizes([400, 800])
        self.console.setMinimumWidth(400)
        self.tree.setMinimumWidth(250)

        splitter.addWidget(left_widget)
        splitter.addWidget(self.details)
        self.main_splitter = splitter

        splitter.setStretchFactor(0, 2)  # tree
        splitter.setStretchFactor(1, 3)  # console

        layout.addWidget(splitter)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(20)

        # ---- Modern Summary Cards ----
        self.card_passed = SummaryCard("PASSED")
        self.card_failed = SummaryCard("FAILED")
        self.card_skipped = SummaryCard("SKIPPED")
        self.card_error = SummaryCard("ERROR")

        self.active_summary_filter = None

        self.card_passed.clicked.connect(self.on_summary_clicked)
        self.card_failed.clicked.connect(self.on_summary_clicked)
        self.card_skipped.clicked.connect(self.on_summary_clicked)
        self.card_error.clicked.connect(self.on_summary_clicked)

        # ---- Bandeau de bas de fenetre ----
        # Progression et compteurs sur UNE ligne. Empiles, ils prenaient 104 px
        # de haut sur toute la largeur pour une barre et quatre nombres, autant
        # de moins pour la console.
        summary_widget = QWidget()
        summary_widget.setFixedHeight(32)
        summary_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        summary_layout = QHBoxLayout(summary_widget)
        summary_layout.setContentsMargins(4, 3, 4, 3)
        summary_layout.setSpacing(8)

        summary_layout.addWidget(self.progress, 1)
        summary_layout.addWidget(self.card_passed)
        summary_layout.addWidget(self.card_failed)
        summary_layout.addWidget(self.card_skipped)
        summary_layout.addWidget(self.card_error)

        layout.addWidget(summary_widget)

        self.campaign_panel = CampaignPanel(self, history_manager=self.history_manager)
        self.campaign_panel.history_updated.connect(self._refresh_history_window)

        self.tabs = QTabWidget()
        self.tabs.addTab(central, "Workspace")
        self.tabs.addTab(self.campaign_panel, "Campaign")
        self.setCentralWidget(self.tabs)

        self.workspace_combo.setFocus()

        self.workspace: str | None = None

    def _show_reader_controls(self, visible: bool):
        self._reader_separator.setVisible(visible)
        self.diff_button.setVisible(visible)
        for case in self.reader_checkboxes:
            case.setVisible(visible)

    def refresh_readers(self):
        """Reconstruit les cases a cocher a partir de la configuration.

        Un seul lecteur declare (ou aucun) ne justifie pas de commande : la barre
        reste alors exactement comme avant.
        """
        for case in self.reader_checkboxes:
            self.reader_bar.removeWidget(case)
            case.deleteLater()
        self.reader_checkboxes.clear()

        lecteurs = readers_for(self.workspace, self.config_path())
        if len(lecteurs) > 1:
            for index, nom in enumerate(lecteurs):
                # Nom court : cinq lecteurs ecrits en entier debordent la barre.
                case = QCheckBox(short_reader_label(nom))
                case.setToolTip(nom)
                case.setChecked(True)
                case.setCursor(Qt.PointingHandCursor)
                case.setStyleSheet(f"color:{styles.reader_color(index)};")
                self.reader_bar.addWidget(case)
                self.reader_checkboxes.append(case)

        self._show_reader_controls(len(lecteurs) > 1)

    def reader_config_path(self) -> str:
        """Fichier de configuration ou ecrire le lecteur actif.

        Celui que l'utilisateur a designe s'il porte la cle, sinon celui du
        workspace qui la declare. Se contenter du fichier memorise ne suffisait
        pas : tant que "Ouvrir la configuration" n'avait jamais servi, rien
        n'etait memorise et le lecteur n'etait ecrit nulle part -- tous les runs
        voyaient alors le meme.
        """
        chemin = config_file_declaring(
            self.workspace, READER_KEYS, self.config_path())
        return str(chemin) if chemin else ""

    def selected_readers(self) -> list[str]:
        """Lecteurs coches, ou [] quand le workspace n'en declare pas plusieurs.

        Le nom complet vient de l'infobulle : la case n'affiche qu'un nom court.
        """
        coches = [c.toolTip() for c in self.reader_checkboxes if c.isChecked()]
        if self.reader_checkboxes and not coches:
            # Tout decocher ne doit pas empecher de lancer : on retombe sur le
            # comportement d'un workspace sans lecteurs.
            return []
        return coches

    def set_details_detached(self, detache: bool):
        """Sort le panneau de details dans sa propre fenetre, ou l'y remet."""
        if detache and self._detached_window is None:
            self._detached_window = DetachedPanelWindow(self.details, self)
            self._detached_window.closed.connect(
                lambda: self.details.detach_button.setChecked(False))

            geometrie = self.settings.value(DETACHED_GEOMETRY_KEY)
            if geometrie is not None:
                self._detached_window.restoreGeometry(geometrie)
            else:
                self._detached_window.resize(1100, 700)
            self._detached_window.show()
            self._detached_window.raise_()

        elif not detache and self._detached_window is not None:
            self.settings.setValue(
                DETACHED_GEOMETRY_KEY, self._detached_window.saveGeometry())
            fenetre = self._detached_window
            self._detached_window = None
            # Reinserer AVANT de detruire la fenetre : le panneau serait sinon
            # detruit avec elle, en tant qu'enfant.
            self.main_splitter.insertWidget(1, self.details)
            self.details.show()
            fenetre.close()
            fenetre.deleteLater()

    def _separator(self) -> QFrame:
        """Trait vertical entre deux groupes d'actions.

        Remplace l'espace fixe de 90 px, qui se voyait comme un trou plutot que
        comme une separation et decalait les boutons vers le milieu.
        """
        trait = QFrame()
        trait.setFrameShape(QFrame.VLine)
        trait.setFixedWidth(1)
        # Un peu plus haut que le texte, moins haut que les boutons : le trait
        # separe sans dessiner une colonne dans la barre.
        trait.setFixedHeight(22)
        trait.setStyleSheet(separator_style())
        self._separators = getattr(self, "_separators", [])
        self._separators.append(trait)
        return trait

    def _build_theme_button(self):
        """Bascule clair/sombre, discrete, dans le coin haut-droit.

        QMenuBar accepte un widget dans son coin : le bouton se loge donc a
        l'extremite de la barre de menus, sans occuper de place dans la fenetre
        elle-meme ni decaler les menus.
        """
        self.theme_button = QToolButton()
        self.theme_button.setAutoRaise(True)
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)
        self._refresh_theme_button()
        self.menuBar().setCornerWidget(self.theme_button, Qt.TopRightCorner)

    def _refresh_theme_button(self):
        # L'icone montre le theme vers lequel le clic bascule.
        if styles.is_dark():
            self.theme_button.setText("\u2600")   # soleil : revenir au clair
            self.theme_button.setToolTip("Passer en theme clair")
        else:
            self.theme_button.setText("\u263d")   # lune : passer au sombre
            self.theme_button.setToolTip("Passer en theme sombre")
        self.theme_button.setStyleSheet(theme_toggle_button())

    def toggle_theme(self):
        self.apply_theme("light" if styles.is_dark() else "dark")

    def apply_theme(self, name: str):
        """Change de theme a chaud et memorise le choix.

        Les feuilles de style posees widget par widget ne suivent pas
        automatiquement : chaque zone doit etre repeinte, d'ou les appels a
        restyle().
        """
        styles.set_theme(name)
        self.settings.setValue("theme", styles.current_theme())

        # Les icones de statut sont dessinees puis mises en cache : sans purge,
        # elles garderaient les couleurs de l'ancienne palette.
        forget_status_icons()

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(styles.app_stylesheet())

        self._refresh_theme_button()
        self.restyle()
        self.campaign_panel.restyle()

    def restyle(self):
        """Reapplique les styles de l'onglet Workspace avec la palette courante."""
        self.load_button.setStyleSheet(primary_button())
        self.browse_button.setStyleSheet(neutral_button())
        self.open_config_button.setStyleSheet(neutral_button())
        self.run_button.setStyleSheet(success_button())
        self.stop_button.setStyleSheet(danger_button())
        self.rerun_failed_button.setStyleSheet(info_button())

        for button in (self.btn_select_all, self.btn_select_none, self.btn_failed_only,
                       self.btn_expand_all, self.btn_collapse_all):
            button.setStyleSheet(toolbar_button())

        self.diff_button.setStyleSheet(toolbar_button())
        for index, case in enumerate(self.reader_checkboxes):
            case.setStyleSheet(f"color:{styles.reader_color(index)};")

        for trait in getattr(self, "_separators", []):
            trait.setStyleSheet(separator_style())

        self.tree.setStyleSheet(tree_style())
        self.selection_label.setStyleSheet(styles.muted_label())

        # Console, Source et Log posent leurs couleurs widget par widget et
        # reconstruisent leurs coloriseurs : sans cet appel, ces trois zones
        # gardaient l'ancienne palette jusqu'au prochain run, d'ou une source
        # sombre dans une fenetre claire et une ligne courante surlignee en
        # blanc sur fond noir.
        self.details.restyle()

        for card in (self.card_passed, self.card_failed, self.card_skipped, self.card_error):
            card.restyle()

        # Les couleurs de statut deja posees sur les items de l'arbre viennent de
        # l'ancienne palette : on les recalcule a partir des statuts memorises.
        self.tree.recolor_statuses()

    def _build_mode_menu(self):
        mode_menu = self.menuBar().addMenu("Mode")

        workspace_action = mode_menu.addAction("Workspace Mode")
        workspace_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))

        campaign_action = mode_menu.addAction("Campaign Mode")
        campaign_action.triggered.connect(lambda: self.tabs.setCurrentIndex(1))

    def _build_reports_menu(self):
        reports_menu = self.menuBar().addMenu("Reports")
        history_action = reports_menu.addAction("Run history...")
        history_action.triggered.connect(self.open_history_window)

        flaky_action = reports_menu.addAction("Flaky tests...")
        flaky_action.triggered.connect(self.open_flaky_window)

    def _build_settings_menu(self):
        settings_menu = self.menuBar().addMenu("Settings")
        interpreter_action = settings_menu.addAction("Test Python interpreter...")
        interpreter_action.triggered.connect(self.open_interpreter_dialog)

    def current_interpreter(self, workspace: str | None = None) -> str:
        """Interpreteur effectif pour le workspace donne (config.yml > reglage global)."""
        configured = self.settings.value("test_interpreter", "", type=str)
        return resolve_interpreter(configured=configured, workspace=workspace or self.workspace)

    def open_interpreter_dialog(self):
        configured = self.settings.value("test_interpreter", "", type=str)
        dialog = InterpreterDialog(configured, workspace=self.workspace, parent=self)

        if dialog.exec_() != QDialog.Accepted:
            return

        # Campaign lit la meme cle QSettings au moment de lancer : rien a propager.
        self.settings.setValue("test_interpreter", dialog.interpreter_path())
        self._report_current_interpreter()

    def _report_current_interpreter(self):
        """Affiche dans la console quel interpreteur sera utilise et d'ou il vient."""
        configured = self.settings.value("test_interpreter", "", type=str)
        python = self.current_interpreter()
        source = interpreter_source(configured=configured, workspace=self.workspace)

        if python:
            self._queue_console_output(f"Test interpreter: {python}  [{source}]\n")
        else:
            self._queue_console_output(
                "No Python interpreter configured for the tests "
                "(Settings > Test Python interpreter... menu).\n"
            )

    def open_history_window(self):
        if self.history_window is None:
            self.history_window = HistoryWindow(self.history_manager, self)
        else:
            self.history_window.reload_entries()
        self.history_window.show()
        self.history_window.raise_()
        self.history_window.activateWindow()

    def open_flaky_window(self):
        dialog = FlakyTestsDialog(self.history_manager, self)
        dialog.exec_()

    def _queue_console_output(self, text: str, reader_index: int = 0):
        if not text:
            return
        self._console_pending.append((reader_index, text))
        if not self._console_flush_timer.isActive():
            self._console_flush_timer.start()

    def _flush_console_output(self):
        if not self._console_pending:
            self._console_flush_timer.stop()
            return

        # Regroupe par console : chacune n'est touchee qu'une fois par vidage,
        # meme quand deux lecteurs ecrivent en meme temps.
        paquets: dict[int, list[str]] = {}
        for index, texte in self._console_pending:
            paquets.setdefault(index, []).append(texte)
        self._console_pending.clear()

        for index, morceaux in paquets.items():
            vue = self.details.console_for(index)
            vue.moveCursor(QTextCursor.End)
            vue.insertPlainText("".join(morceaux))
            vue.ensureCursorVisible()

    def _on_stdout(self, text: str, reader_index: int = 0):
        # Ne pas écrire dans QTextEdit ligne par ligne: sur de gros environnements,
        # cela peut faire planter Qt sous Windows avec 0xC0000409.
        # L'analyse des resultats se fait dans le thread de lecture (voir
        # PytestWorker) et arrive par test_status_signal. Ici, que de l'affichage.
        self._queue_console_output(text, reader_index)

    def _on_collected(self, count: int):
        # Chaque processus annonce son propre total : avec plusieurs lecteurs,
        # le travail a accomplir est la somme, pas le dernier chiffre recu.
        lecteurs = max(1, len(getattr(self, "workers", []) or [1]))
        self.total_tests = count * lecteurs
        self.progress.setMaximum(self.total_tests)

    def _on_test_status(self, nodeid: str, status: str, reader_index: int = 0):
        """Un test vient de se terminer : rafraichissement immediat.

        Appele une fois par test, y compris pour chaque cas parametre. L'arbre et
        la barre de progression sont mis a jour tout de suite (0,04 ms par test).
        Les cartes de resume passent par un rafraichissement groupe : chacune
        reconstruit sa feuille de style (0,4 ms), ce qui couterait des secondes
        sur plusieurs milliers de tests.
        """
        if status == "FAILED":
            self.failed_nodeids.add(nodeid)
            if reader_index < len(self._failed_nodeids_by_reader):
                self._failed_nodeids_by_reader[reader_index].add(nodeid)

        self.done_tests += 1
        if self.progress.maximum() > 0:
            self.progress.setValue(min(self.done_tests, self.progress.maximum()))

        if status in self.test_counts:
            self.test_counts[status] += 1

        # create_missing : un test execute mais absent de l'arbre y est ajoute,
        # pour que l'arbre montre ce qui a reellement tourne plutot que de perdre
        # le resultat.
        if not self.tree.update_single_test(
            nodeid, status, self.workspace or "", create_missing=True,
            reader_index=reader_index,
        ):
            self._unmatched_results.append(nodeid)

        self._cards_dirty = True
        if not self._cards_timer.isActive():
            self._cards_timer.start()

    def _warn_about_unmatched_results(self):
        """Note les tests executes qui ne figuraient pas dans l'arbre.

        Ils y ont ete ajoutes au fil du run, et les cas de l'ancienne collecte
        qu'ils remplacent en ont ete retires : l'arbre montre donc exactement ce
        qui a tourne. Le signaler reste utile, car cela veut dire que la collecte
        n'est pas reproductible d'un lancement a l'autre (identifiants de
        parametres calcules a chaque collecte), et donc que la selection faite
        avant le lancement ne portait pas sur ces tests-la.
        """
        if not self._unmatched_results:
            return

        exemples = "\n".join(f"  {nodeid}" for nodeid in self._unmatched_results[:3])
        reste = len(self._unmatched_results) - 3
        if reste > 0:
            exemples += f"\n  ... and {reste} more"

        if self._replaced_cases:
            remplacement = (
                f", added to the tree in place of the "
                f"{self._replaced_cases} case(s) from the previous collection that did "
                "not run.\n"
            )
        else:
            remplacement = ", added to the tree.\n"

        self._queue_console_output(
            f"\n{len(self._unmatched_results)} test(s) ran but were not in the tree"
            f"{remplacement}"
            "Collection is therefore not reproducible: parameter ids change\n"
            "from one collection to the next. For the selection to match what actually "
            "ran,\nfix them with ids= in parametrize, or seed random values in the test.\n"
            f"{exemples}\n"
        )

    def _refresh_summary_cards(self):
        if not self._cards_dirty:
            self._cards_timer.stop()
            return
        self._cards_dirty = False

        total = max(self.total_tests, 1)
        self.card_passed.update_value(self.test_counts["PASSED"], total)
        self.card_failed.update_value(self.test_counts["FAILED"], total)
        self.card_skipped.update_value(self.test_counts["SKIPPED"], total)
        self.card_error.update_value(self.test_counts["ERROR"], total)

    def _on_stderr(self, text: str, reader_index: int = 0):
        self._queue_console_output(text, reader_index)

    def _on_run_finished(self, exit_code: int, stdout: str, reader_index: int = 0):
        """Un des processus vient de finir.

        Le bilan n'est dresse qu'au dernier : les cartes, l'historique et le
        nettoyage de l'arbre portent sur l'ensemble des lecteurs.
        """
        if reader_index < len(self._run_outputs):
            self._run_outputs[reader_index] = stdout
        if reader_index < len(self._exit_codes):
            self._exit_codes[reader_index] = exit_code

        self._runs_left -= 1
        if self._runs_left > 0:
            self._flush_console_output()
            self._queue_console_output(
                f"\nPytest finished with exit code {exit_code}\n", reader_index)
            self._flush_console_output()
            if getattr(self, "_sequential", False):
                self._start_next_worker()
            return

        self._on_finished(exit_code, "\n".join(self._run_outputs), reader_index)

    def _on_finished(self, exit_code: int, stdout: str, reader_index: int = 0):
        self._flush_console_output()
        self._queue_console_output(
            f"\nPytest finished with exit code {exit_code}\n", reader_index)
        self._flush_console_output()
        self.tree.set_last_output(stdout)

        # Les compteurs sont mis a jour au fil de l'eau depuis les lignes pytest.
        # Si pytest fournit un resume final, il reste prioritaire. Avec plusieurs
        # lecteurs, chaque processus ecrit le sien : il faut les ADDITIONNER pour
        # les cartes, qui montrent le total tous lecteurs confondus (l'historique,
        # plus bas, garde lui le detail par lecteur).
        sorties = [s for s in self._run_outputs if s] or [stdout]
        comptes_par_sortie = [_parse_summary_counts(sortie) for sortie in sorties]
        for key in _SUMMARY_PATTERNS:
            valeurs = [comptes[key] for comptes in comptes_par_sortie if key in comptes]
            if valeurs:
                self.test_counts[key] = sum(valeurs)

        self._cards_timer.stop()
        self._cards_dirty = True
        self._refresh_summary_cards()

        # L'arbre ne doit pas garder, a cote des cas qui viennent de tourner, les
        # cas d'une collecte que pytest a lui-meme remplacee : ils ne seront
        # jamais executes sous ce nom. Un run interrompu laisse forcement des cas
        # sans resultat, on n'y touche donc pas.
        if not getattr(getattr(self, "worker", None), "stopped", False):
            self._replaced_cases = self.tree.prune_replaced_cases()
        self._warn_about_unmatched_results()

        self.progress.setValue(self.progress.maximum())

        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(bool(self.failed_nodeids))

        # ---- Enregistrement dans l'historique des executions ----
        # Une ligne par lecteur : chacun a tourne dans son propre process, avec
        # son propre resultat. Un total agrege masquerait lequel a echoue.
        duration = (time.time() - self._run_started_at) if self._run_started_at else 0.0
        lecteurs = self._current_readers or [""]
        plusieurs = len(lecteurs) > 1
        base_run_id = self._current_run_id or new_run_id()
        # La configuration est jointe au run : relire un rapport six mois plus
        # tard sans savoir sous quels reglages il a tourne n'apprend pas
        # grand-chose.
        reglages = self._workspace_settings()

        for index, lecteur in enumerate(lecteurs):
            sortie = self._run_outputs[index] if index < len(self._run_outputs) else stdout
            counts = _parse_summary_counts(sortie)
            failed = (
                sorted(self._failed_nodeids_by_reader[index])
                if index < len(self._failed_nodeids_by_reader)
                else sorted(self.failed_nodeids)
            )
            code = self._exit_codes[index] if index < len(self._exit_codes) else exit_code
            junit = (
                self._current_junit_paths[index]
                if index < len(self._current_junit_paths) else ""
            )
            self.history_manager.add_run(
                run_id=f"{base_run_id}.{index}" if plusieurs else base_run_id,
                workspace=self.workspace or "",
                duration_seconds=duration,
                exit_code=code,
                counts=counts,
                nodeids=self._current_run_nodeids,
                failed_nodeids=failed,
                output_text=sortie,
                junit_xml_path=junit,
                reader=lecteur,
                config=reglages,
            )
        self._refresh_history_window()

    def _refresh_history_window(self):
        if self.history_window is not None:
            self.history_window.reload_entries()

    def _add_recent_workspace(self, path: str):
        if not path:
            return

        recent = self.settings.value("recent_workspaces", [], type=list)

        if path in recent:
            recent.remove(path)

        recent.insert(0, path)
        recent = recent[:5]  # keep last 5

        self.settings.setValue("recent_workspaces", recent)

        # Le texte affiche est remis explicitement : clear() vide aussi la zone
        # de saisie d'un combo editable, et le chemin disparaissait donc de la
        # barre a chaque "Load Workspace", alors qu'il venait d'etre charge.
        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        self.workspace_combo.addItems(recent)
        self.workspace_combo.setCurrentText(path)
        self.workspace_combo.blockSignals(False)

    def open_config(self):
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        open_config_editor(self, self.workspace, self.settings)
        # Le fichier retenu, ou son contenu, vient peut-etre de changer.
        self.refresh_readers()
        # Le fichier retenu vient peut-etre de changer, et c'est lui qui porte
        # LOG_PATH : l'onglet Log doit repartir du bon endroit.
        self.details.set_workspace(self.workspace, self.config_path())

    def config_path(self, workspace: str | None = None) -> str:
        """Fichier de configuration retenu pour ce workspace."""
        return remembered_config_path(workspace or self.workspace or "", self.settings)

    def _workspace_settings(self) -> dict:
        """Contenu du fichier de configuration du workspace, ou {}.

        Joint a chaque entree d'historique pour apparaitre dans le rapport
        HTML : les reglages sous lesquels un run a tourne font partie de son
        resultat.
        """
        chemin = self.config_path()
        candidats = [Path(chemin)] if chemin else []
        candidats.extend(discover_config_files(self.workspace))
        for candidat in candidats:
            if candidat.is_file():
                donnees = load_config(candidat)
                if donnees:
                    return donnees
        return {}

    def select_all_tests(self):
        self.tree.set_all_checked(True)

    def select_no_tests(self):
        self.tree.set_all_checked(False)

    def on_summary_clicked(self, status: str):
        if self.active_summary_filter == status:
            self.active_summary_filter = None
            QTimer.singleShot(0, self.tree.clear_status_filter)
        else:
            self.active_summary_filter = status
            QTimer.singleShot(0, lambda: self.tree.filter_by_status(status))

        # BUG CORRIGE (deja present avant mes modifs) : le code passait
        # `status == "..." and self.active_summary_filter` a set_active(). Quand la
        # condition est vraie, cette expression renvoie la valeur de
        # self.active_summary_filter (une chaine, ex. "passed"), pas un booleen. Or
        # le style Qt QLabel[active="true"] n'est declenche que si la propriete vaut
        # litteralement "true" -> la surbrillance au clic ne s'affichait jamais.
        self.card_passed.set_active(self.active_summary_filter == "passed")
        self.card_failed.set_active(self.active_summary_filter == "failed")
        self.card_skipped.set_active(self.active_summary_filter == "skipped")
        self.card_error.set_active(self.active_summary_filter == "error")
        self.btn_failed_only.setChecked(self.active_summary_filter == "failed")

    def on_selection_changed(self, selected: int, total: int):
        self.selection_label.setText(f"{selected} / {total} selected")

    def on_filter_text_changed(self, text: str):
        query = text.strip()
        if query:
            QTimer.singleShot(0, lambda: self.tree.filter_by_text(query))
        elif self.active_summary_filter:
            QTimer.singleShot(0, lambda: self.tree.filter_by_status(self.active_summary_filter))
        else:
            QTimer.singleShot(0, self.tree.clear_status_filter)

    def browse_workspace(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Workspace",
            self.workspace_combo.currentText() or ""
        )

        if path:
            self._add_recent_workspace(path)
            self.workspace_combo.setCurrentText(path)
            self.settings.setValue("last_workspace", path)

    def load_workspace(self):
        workspace = self.workspace_combo.currentText().strip()

        if not workspace:
            QMessageBox.warning(self, "Warning", "Please enter a workspace path.")
            return

        if not os.path.isdir(workspace):
            QMessageBox.critical(self, "Error", "Invalid workspace path.")
            return

        self.workspace = workspace
        self._add_recent_workspace(workspace)
        self.settings.setValue("last_workspace", workspace)

        self.load_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.console.clear()
        self._queue_console_output(f"Loading workspace: {workspace}\n")
        self._report_current_interpreter()

        # Collecte + construction de l'arbre logique dans un thread.
        # Important: le modele Qt est toujours rempli dans le thread UI
        # via _on_workspace_loaded, pour eviter les crashs natifs Qt.
        self.workspace_loader = WorkspaceLoadWorker(
            workspace, interpreter=self.current_interpreter(workspace)
        )
        self.workspace_loader.loaded_signal.connect(self._on_workspace_loaded)
        self.workspace_loader.error_signal.connect(self._on_workspace_load_error)
        self.workspace_loader.start()

    def _on_tree_item_clicked(self, target: str, nodeid: str):
        """Clic dans l'arbre : charge la source et le log de l'element.

        On ne change pas d'onglet de force : si l'utilisateur regarde la console
        pendant un run, il n'est pas ejecte vers la source a chaque clic.
        """
        self.details.show_for(target or None, nodeid or None)

    def _on_workspace_loaded(self, roots, count: int, workspace: str):
        self.workspace = workspace
        self.details.set_workspace(workspace, self.config_path(workspace))
        self.refresh_readers()

        # Un run precedent interrompu (coupure, plantage) a pu laisser la
        # configuration sur le dernier lecteur essaye. On la remet d'aplomb au
        # chargement, en le disant : le lecteur affiche aurait sinon change sans
        # que personne ne l'ait demande.
        restaure = restore_interrupted_reader(self.reader_config_path())
        if restaure:
            self._queue_console_output(
                f"Reader reset to '{restaure}': a previous run was interrupted "
                "before it could be restored.\n")
        self.details.clear_details()
        self.tree.load_tree(roots)
        self.run_button.setEnabled(count > 0)
        self.load_button.setEnabled(True)
        self._queue_console_output(f"Collected {count} tests.\n")

    def _on_workspace_load_error(self, message: str):
        self.load_button.setEnabled(True)
        self.run_button.setEnabled(False)
        self._queue_console_output("Workspace load failed.\n")
        show_scrollable_error(
            self,
            "Workspace load error",
            message,
            intro="pytest could not collect the tests in this workspace:",
        )

    def stop_tests(self):
        tous = getattr(self, "workers", [])
        if not any(w.isRunning() for w in tous):
            return
        # Tous sont marques, y compris ceux qui n'ont pas encore demarre : en
        # sequentiel, arreter le lecteur courant ne doit pas lancer le suivant.
        for worker in tous:
            worker.stop()
        self.console.append("\n⛔ Test execution stopped by user. ⛔\n")
        self.stop_button.setEnabled(False)
        self.progress.setValue(self.progress.maximum())

    def _launch_worker(self, nodeids: list[str], intro_message: str, targets: list[str] | None = None):
        """
        Point d'entree unique pour demarrer un run pytest, quelle que soit son
        origine (bouton "Run Selected", "Re-run Failed", ou menu contextuel de
        l'arbre). Centraliser ce code evite de reintroduire le bug deja corrige
        une fois (compteurs/cartes non remis a zero entre deux runs).
        """
        interpreter = self.current_interpreter()

        # Verifie l'interpreteur AVANT de reinitialiser l'UI : sinon on efface les
        # resultats precedents pour finalement ne rien lancer.
        problem = check_ready_to_run(interpreter)
        if problem:
            show_scrollable_error(
                self,
                "Test interpreter unusable",
                problem,
                intro="The tests could not be started:",
            )
            return

        # pytest relit les fichiers a chaque lancement : ecrire la frappe encore
        # en attente suffit pour que le run parte du code affiche, sans recharger
        # le workspace.
        self.details.save_source()

        # Un run par lecteur selectionne. Sans lecteur configure, la liste vaut
        # [""] et tout se passe exactement comme avant.
        lecteurs = self.selected_readers() or [""]

        self.details.set_readers(lecteurs if len(lecteurs) > 1 else [])
        self.tree.set_readers(lecteurs if len(lecteurs) > 1 else [])
        for index in range(len(lecteurs)):
            self.details.console_for(index).clear()
        self.console.append(intro_message)

        self.tree.reset_result_colors()
        self.done_tests = 0
        self.progress.reset()
        self.progress.setValue(0)
        self.progress.setMaximum(len(nodeids) * len(lecteurs))

        self.test_counts = {k: 0 for k in self.test_counts}
        self.card_passed.update_value(0)
        self.card_failed.update_value(0)
        self.card_skipped.update_value(0)
        self.card_error.update_value(0)

        self.total_tests = len(nodeids) * len(lecteurs)

        self._current_run_id = new_run_id()
        self._current_junit_path = os.path.join(history_dir(), f"{self._current_run_id}.xml")
        self._run_started_at = time.time()
        self._current_run_nodeids = list(nodeids)

        self.run_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.failed_nodeids.clear()
        self._unmatched_results.clear()
        self._replaced_cases = 0
        self._current_readers = list(lecteurs)
        self._current_junit_paths = [""] * len(lecteurs)
        self._failed_nodeids_by_reader = [set() for _ in lecteurs]
        self._exit_codes = [0] * len(lecteurs)
        self.tree.start_run()

        # Parallele par defaut : le fichier de configuration est rendu
        # virtuellement different pour chaque process par un plugin injecte
        # (core/reader_plugin.py), sans rien ecrire ni toucher au code de test.
        # `reader_mode: sequential` dans la configuration revient a l'ancien
        # enchainement, qui ecrit chaque lecteur dans le fichier a tour de role.
        self._reader_mode = reader_mode_for(self.workspace, self.config_path())
        sequentiel = self._reader_mode != "parallel" and len(lecteurs) > 1

        if sequentiel:
            self._queue_console_output(
                f"{len(lecteurs)} readers will be tested one after another "
                "(reader_mode: sequential).\n"
            )

        self.workers: list[PytestWorker] = []
        self._runs_left = len(lecteurs)
        self._run_outputs: list[str] = [""] * len(lecteurs)
        self._sequential = sequentiel
        self._next_worker = 0

        for index, lecteur in enumerate(lecteurs):
            # Un rapport JUnit par lecteur : un seul chemin verrait les deux
            # processus s'ecraser l'un l'autre.
            junit = self._current_junit_path
            if len(lecteurs) > 1:
                junit = os.path.join(history_dir(), f"{self._current_run_id}.{index}.xml")
            self._current_junit_paths[index] = junit

            worker = PytestWorker(
                nodeids=nodeids,
                workspace=self.workspace,
                junit_xml_path=junit,
                interpreter=interpreter,
                targets=targets,
                reader=lecteur,
                config_path=self.reader_config_path(),
                write_reader_to_config=sequentiel,
            )
            worker.stdout_signal.connect(
                lambda texte, i=index: self._on_stdout(texte, i))
            worker.test_status_signal.connect(
                lambda nodeid, statut, i=index: self._on_test_status(nodeid, statut, i))
            worker.collected_signal.connect(self._on_collected)
            worker.stderr_signal.connect(
                lambda texte, i=index: self._on_stderr(texte, i))
            worker.finished_signal.connect(
                lambda code, sortie, i=index: self._on_run_finished(code, sortie, i))
            self.workers.append(worker)

        # Le dernier worker reste accessible sous `self.worker` : le reste du
        # code (arret, tests) n'a pas a savoir combien il y en a.
        self.worker = self.workers[-1]
        if sequentiel:
            self._start_next_worker()
        else:
            for worker in self.workers:
                worker.start()

    def _start_next_worker(self):
        """Lance le lecteur suivant. Utilise en mode sequentiel uniquement.

        Le worker precedent est attendu avant tout : son signal de fin part de
        l'interieur du bloc qui remet le lecteur d'origine dans la
        configuration. Enchainer sans attendre ferait ecrire au lecteur sortant
        SA restauration par-dessus le lecteur que le suivant vient d'ecrire, et
        les deux runs porteraient le meme lecteur.
        """
        if self._next_worker > 0:
            self.workers[self._next_worker - 1].wait(5000)

        while self._next_worker < len(self.workers):
            worker = self.workers[self._next_worker]
            self._next_worker += 1
            if worker.stopped:
                # Arret demande avant meme d'avoir demarre : on ne relance rien,
                # mais son resultat doit quand meme etre compte comme termine.
                self._on_run_finished(-1, "", self._next_worker - 1)
                return
            self.details.show_reader(self._next_worker - 1)
            worker.start()
            return

    def run_selected_tests(self):
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        nodeids = self.tree.get_selected_nodeids()
        if not nodeids:
            QMessageBox.warning(self, "Warning", "No tests selected.")
            return

        self._launch_worker(nodeids, "Running pytest...\n", targets=self.tree.get_selected_targets())

    def run_failed_tests(self):
        if not self.failed_nodeids:
            QMessageBox.information(self, "Info", "No failed test to re-run.")
            return

        nodeids = sorted(self.failed_nodeids)
        self._launch_worker(nodeids, "Re-running failed tests...\n")

    def run_specific_nodeids(self, nodeids: list[str]):
        """Appele par le menu clic-droit de l'arbre ("Lancer ce test / ces tests")."""
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        if not nodeids:
            QMessageBox.information(self, "Info", "No runnable test found under this item.")
            return

        self._launch_worker(nodeids, f"Running {len(nodeids)} test(s) selected from the context menu...\n")

    def open_test_file(self, relative_path: str):
        """Ouvre le fichier source d'un test avec l'application par defaut de Windows."""
        if not self.workspace:
            return

        full_path = os.path.join(self.workspace, relative_path)
        if not os.path.isfile(full_path):
            QMessageBox.warning(self, "File not found", f"Could not find:\n{full_path}")
            return

        try:
            os.startfile(full_path)
        except AttributeError:
            # os.startfile n'existe que sous Windows ; ce projet est distribue
            # exclusivement pour Windows 32 bits, mais on securise quand meme.
            QMessageBox.information(
                self,
                "Not supported",
                f"Automatic opening is not available on this platform.\nPath: {full_path}",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not open the file:\n{exc}")

    def open_test_log(self, nodeid: str):
        """Ouvre le fichier .log du dernier run pour ce test. A defaut, ouvre le
        dossier racine des logs, sinon informe qu'aucun log n'existe encore."""
        if not self.workspace:
            return
        open_test_log_for(self, self.workspace, nodeid, self.config_path())





    def closeEvent(self, event):
        """Ecrit la frappe encore en attente avant de fermer.

        L'enregistrement automatique attend une pause de saisie : fermer juste
        apres une correction la perdrait sans cela.
        """
        self.details.save_source()
        if self._detached_window is not None:
            self.settings.setValue(
                DETACHED_GEOMETRY_KEY, self._detached_window.saveGeometry())
            self._detached_window.close()
        super().closeEvent(event)
