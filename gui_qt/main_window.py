from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTextEdit, QSplitter, QComboBox, QSizePolicy, QTabWidget, QCheckBox
)

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtWidgets import QLabel, QHBoxLayout
from PyQt5.QtWidgets import QLineEdit


import os
import re
import time

from gui_qt.test_tree_view import TestTreeView
from gui_qt.config.config_editor import ConfigEditor
from gui_qt.config.config_loader import find_config_yaml
from gui_qt.config.config_dialog import ConfigDialog
from gui_qt.campaign_window import CampaignPanel
from gui_qt.history_window import HistoryWindow
from gui_qt.flaky_window import FlakyTestsDialog
from gui_qt.dialogs import show_scrollable_error


from core.test_discovery import collect_tests
from core.test_tree import build_test_tree
from core.pytest_executor import parse_test_status_line
from core.run_history import RunHistoryManager, history_dir, new_run_id

from gui_qt.styles.styles import (
    primary_button,
    neutral_button,
    success_button,
    danger_button,
    toolbar_button,
    tree_style,
    console_style,
)


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

    def __init__(self, nodeids, workspace, junit_xml_path=None, parallel=False):
        super().__init__()
        self.nodeids = nodeids
        self.workspace = workspace
        self.junit_xml_path = junit_xml_path
        self.parallel = parallel
        self._process = None
        self._stopped = False

    def run(self):
        import subprocess
        import sys

        command = [
            sys.executable,
            "-m", "pytest",
            *self.nodeids,
            "--import-mode=importlib",
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

        # Merge stderr into stdout to keep correct order and avoid deadlocks
        self._process = subprocess.Popen(
            command,
            cwd=self.workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        stdout_buffer = []
        stdout_size = 0
        stdout_limit = 1_000_000  # on garde la fin de sortie pour le resume pytest
        emit_buffer = []
        emit_size = 0

        def flush_emit_buffer():
            nonlocal emit_buffer, emit_size
            if emit_buffer:
                self.stdout_signal.emit("".join(emit_buffer))
                emit_buffer = []
                emit_size = 0

        for line in iter(self._process.stdout.readline, ""):
            if self._stopped:
                break
            stdout_buffer.append(line)
            stdout_size += len(line)
            while stdout_size > stdout_limit and stdout_buffer:
                stdout_size -= len(stdout_buffer.pop(0))
            emit_buffer.append(line)
            emit_size += len(line)
            # Evite des milliers de signaux Qt et des QTextEdit.append() en rafale.
            if len(emit_buffer) >= 50 or emit_size >= 8192:
                flush_emit_buffer()

        flush_emit_buffer()
        self._process.wait()
        exit_code = -1 if self._stopped else self._process.returncode
        self.finished_signal.emit(exit_code, "".join(stdout_buffer))

    def stop(self):
        """Stop pytest execution."""

        self._stopped = True

        if self._process and self._process.poll() is None:
            self._process.terminate()




class WorkspaceLoadWorker(QThread):
    loaded_signal = pyqtSignal(object, int, str)
    error_signal = pyqtSignal(str)

    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace

    def run(self):
        try:
            nodeids = collect_tests(self.workspace)
            roots = build_test_tree(nodeids, self.workspace)
            self.loaded_signal.emit(roots, len(nodeids), self.workspace)
        except Exception as exc:
            self.error_signal.emit(str(exc))


class SummaryCard(QLabel):
    clicked = pyqtSignal(str)

    def __init__(self, title: str, base_color: str, strong_color: str):
        super().__init__()

        self.title = title
        self.base_color = base_color
        self.strong_color = strong_color
        self.status = title.lower()  # "passed", "failed", "skipped", "error"

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(110)
        self.setMaximumHeight(56)  # 🔥 empêche l’étirement vertical

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

    def update_value(self, value: int, max_value: int = 100):
        ratio = min(value / max_value, 1.0)

        background = blend_color(
            self.base_color,
            self.strong_color,
            ratio
        )

        self.setStyleSheet(f"""
        QLabel {{
            background-color: {background};
            border-radius: 10px;
            color: #222;
            border: 1px solid transparent;
        }}

        QLabel[active="true"] {{
            border: 2px solid #333;
        }}
        """)

        self.setText(
            f"<div style='font-size:18px; font-weight:bold'>{value}</div>"
            f"<div style='font-size:11px; opacity:0.8'>{self.title}</div>"
        )


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
        self._build_mode_menu()
        self._build_reports_menu()

        self.resize(900, 700)
        self.total_tests = 0
        self.done_tests = 0
        self.failed_nodeids: set[str] = set()

        self.test_counts = {
            "PASSED": 0,
            "FAILED": 0,
            "SKIPPED": 0,
            "ERROR": 0,
        }
        self.settings = QSettings("MyCompany", "PyTestRunner")

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

        self.run_button = QPushButton("Run Selected Tests")
        self.stop_button = QPushButton("Stop Test")
        self.rerun_failed_button = QPushButton("Re-run Failed")
        self.parallel_checkbox = QCheckBox("Parallel (-n auto)")

        self.run_button.setStyleSheet(success_button())
        self.stop_button.setStyleSheet(danger_button())
        self.rerun_failed_button.setStyleSheet(danger_button())

        self.rerun_failed_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.run_button.setEnabled(False)

        self.run_button.clicked.connect(self.run_selected_tests)
        self.stop_button.clicked.connect(self.stop_tests)
        self.rerun_failed_button.clicked.connect(self.run_failed_tests)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(12000)
        self._console_pending: list[str] = []
        self._console_flush_timer = QTimer(self)
        self._console_flush_timer.setInterval(50)
        self._console_flush_timer.timeout.connect(self._flush_console_output)

        self.tree = TestTreeView()
        self.tree.run_requested.connect(self.run_specific_nodeids)
        self.tree.open_file_requested.connect(self.open_test_file)

        self.tree.setStyleSheet(tree_style())
        self.console.setStyleSheet(console_style())

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

        action_bar.addSpacing(90)  # séparation visuelle |

        # Test actions
        action_bar.addWidget(self.run_button)
        action_bar.addWidget(self.stop_button)
        action_bar.addWidget(self.rerun_failed_button)
        action_bar.addWidget(self.parallel_checkbox)

        # action_bar.addStretch()

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
        splitter.addWidget(self.console)

        splitter.setStretchFactor(0, 2)  # tree
        splitter.setStretchFactor(1, 3)  # console

        layout.addWidget(splitter)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        layout.addWidget(self.progress)

        # ---- Modern Summary Cards ----
        self.card_passed = SummaryCard(
            "PASSED",
            base_color="#c8e6c9",  # soft green
            strong_color="#2e7d32"
        )

        self.card_failed = SummaryCard(
            "FAILED",
            base_color="#ffcdd2",  # soft red
            strong_color="#c62828"
        )

        self.card_skipped = SummaryCard(
            "SKIPPED",
            base_color="#ffe0b2",  # soft orange
            strong_color="#ef6c00"
        )

        self.card_error = SummaryCard(
            "ERROR",
            base_color="#e1bee7",  # soft purple
            strong_color="#6a1b9a"
        )

        self.active_summary_filter = None

        self.card_passed.clicked.connect(self.on_summary_clicked)
        self.card_failed.clicked.connect(self.on_summary_clicked)
        self.card_skipped.clicked.connect(self.on_summary_clicked)
        self.card_error.clicked.connect(self.on_summary_clicked)

        # ---- Compact Summary Container ----
        summary_widget = QWidget()
        summary_widget.setFixedHeight(70)
        summary_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        summary_layout = QHBoxLayout(summary_widget)
        summary_layout.setContentsMargins(6, 6, 6, 6)
        summary_layout.setSpacing(10)

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

    def _build_mode_menu(self):
        mode_menu = self.menuBar().addMenu("Mode")

        workspace_action = mode_menu.addAction("Workspace Mode")
        workspace_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))

        campaign_action = mode_menu.addAction("Campaign Mode")
        campaign_action.triggered.connect(lambda: self.tabs.setCurrentIndex(1))

    def _build_reports_menu(self):
        reports_menu = self.menuBar().addMenu("Rapports")
        history_action = reports_menu.addAction("Historique des executions...")
        history_action.triggered.connect(self.open_history_window)

        flaky_action = reports_menu.addAction("Tests instables (flaky)...")
        flaky_action.triggered.connect(self.open_flaky_window)

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

    def _queue_console_output(self, text: str):
        if not text:
            return
        self._console_pending.append(text)
        if not self._console_flush_timer.isActive():
            self._console_flush_timer.start()

    def _flush_console_output(self):
        if not self._console_pending:
            self._console_flush_timer.stop()
            return

        text = "".join(self._console_pending)
        self._console_pending.clear()

        self.console.moveCursor(QTextCursor.End)
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def _on_stdout(self, text: str):
        # Ne pas écrire dans QTextEdit ligne par ligne: sur de gros environnements,
        # cela peut faire planter Qt sous Windows avec 0xC0000409.
        self._queue_console_output(text)

        for line in text.splitlines():
            self._parse_pytest_output_line(line)

    def _parse_pytest_output_line(self, line: str):
        # Detect "collected X items"
        collected_match = re.search(r"collected (\d+) items", line)
        if collected_match:
            self.total_tests = int(collected_match.group(1))
            self.done_tests = 0
            self.progress.setMaximum(self.total_tests)
            self.progress.setValue(0)
            return

        # Only count/color REAL per-test result lines (gere aussi le format
        # pytest-xdist quand l'execution parallele est activee).
        parsed = parse_test_status_line(line)
        if not parsed:
            return

        nodeid, status = parsed

        if status == "FAILED":
            self.failed_nodeids.add(nodeid)

        self.done_tests += 1
        if self.progress.maximum() > 0:
            self.progress.setValue(min(self.done_tests, self.progress.maximum()))

        if status in self.test_counts:
            self.test_counts[status] += 1

        self.tree.update_single_test(nodeid, status, self.workspace or "")

    def _on_stderr(self, text: str):
        self._queue_console_output(text)

    def _on_finished(self, exit_code: int, stdout: str):
        self._flush_console_output()
        self._queue_console_output(f"\nPytest finished with exit code {exit_code}\n")
        self._flush_console_output()
        self.tree.set_last_output(stdout)

        # Les compteurs sont mis a jour au fil de l'eau depuis les lignes pytest.
        # Si pytest fournit un resume final, il reste prioritaire.
        patterns = {
            "PASSED": r"(\d+)\s+passed",
            "FAILED": r"(\d+)\s+failed",
            "SKIPPED": r"(\d+)\s+skipped",
            "ERROR": r"(\d+)\s+error",
        }

        for key, pattern in patterns.items():
            matches = re.findall(pattern, stdout, re.IGNORECASE)
            if matches:
                self.test_counts[key] = int(matches[-1])

        total = max(self.total_tests, 1)

        self.card_passed.update_value(self.test_counts["PASSED"], total)
        self.card_failed.update_value(self.test_counts["FAILED"], total)
        self.card_skipped.update_value(self.test_counts["SKIPPED"], total)
        self.card_error.update_value(self.test_counts["ERROR"], total)

        self.progress.setValue(self.progress.maximum())

        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(bool(self.failed_nodeids))

        # ---- Enregistrement dans l'historique des executions ----
        duration = (time.time() - self._run_started_at) if self._run_started_at else 0.0
        self.history_manager.add_run(
            run_id=self._current_run_id or new_run_id(),
            workspace=self.workspace or "",
            duration_seconds=duration,
            exit_code=exit_code,
            counts=self.test_counts,
            nodeids=self._current_run_nodeids,
            failed_nodeids=sorted(self.failed_nodeids),
            output_text=stdout,
            junit_xml_path=self._current_junit_path or "",
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

        self.workspace_combo.clear()
        self.workspace_combo.addItems(recent)

    def open_config(self):
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        config_path = find_config_yaml(self.workspace)

        if not config_path:
            QMessageBox.information(self, "Info", "No config.yaml found.")
            return

        dialog = ConfigDialog(config_path, self)
        dialog.exec_()

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

        # Collecte + construction de l'arbre logique dans un thread.
        # Important: le modele Qt est toujours rempli dans le thread UI
        # via _on_workspace_loaded, pour eviter les crashs natifs Qt.
        self.workspace_loader = WorkspaceLoadWorker(workspace)
        self.workspace_loader.loaded_signal.connect(self._on_workspace_loaded)
        self.workspace_loader.error_signal.connect(self._on_workspace_load_error)
        self.workspace_loader.start()

    def _on_workspace_loaded(self, roots, count: int, workspace: str):
        self.workspace = workspace
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
            "Erreur de chargement du workspace",
            message,
            intro="pytest n'a pas pu collecter les tests de ce workspace :",
        )

    def stop_tests(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self.console.append("\n⛔ Test execution stopped by user. ⛔\n")
            self.stop_button.setEnabled(False)
            self.progress.setValue(self.progress.maximum())

    def _launch_worker(self, nodeids: list[str], intro_message: str):
        """
        Point d'entree unique pour demarrer un run pytest, quelle que soit son
        origine (bouton "Run Selected", "Re-run Failed", ou menu contextuel de
        l'arbre). Centraliser ce code evite de reintroduire le bug deja corrige
        une fois (compteurs/cartes non remis a zero entre deux runs).
        """
        self.console.clear()
        self.console.append(intro_message)

        self.tree.reset_result_colors()
        self.done_tests = 0
        self.progress.reset()
        self.progress.setValue(0)
        self.progress.setMaximum(len(nodeids))

        self.test_counts = {k: 0 for k in self.test_counts}
        self.card_passed.update_value(0)
        self.card_failed.update_value(0)
        self.card_skipped.update_value(0)
        self.card_error.update_value(0)

        self.total_tests = len(nodeids)

        self._current_run_id = new_run_id()
        self._current_junit_path = os.path.join(history_dir(), f"{self._current_run_id}.xml")
        self._run_started_at = time.time()
        self._current_run_nodeids = list(nodeids)

        self.worker = PytestWorker(
            nodeids=nodeids,
            workspace=self.workspace,
            junit_xml_path=self._current_junit_path,
            parallel=self.parallel_checkbox.isChecked(),
        )

        self.worker.stdout_signal.connect(self._on_stdout)
        self.worker.stderr_signal.connect(self._on_stderr)
        self.worker.finished_signal.connect(self._on_finished)

        self.run_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.failed_nodeids.clear()

        self.worker.start()

    def run_selected_tests(self):
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        nodeids = self.tree.get_selected_nodeids()
        if not nodeids:
            QMessageBox.warning(self, "Warning", "No tests selected.")
            return

        self._launch_worker(nodeids, "Running pytest...\n")

    def run_failed_tests(self):
        if not self.failed_nodeids:
            QMessageBox.information(self, "Info", "Aucun test en echec a relancer.")
            return

        nodeids = sorted(self.failed_nodeids)
        self._launch_worker(nodeids, "Re-running failed tests...\n")

    def run_specific_nodeids(self, nodeids: list[str]):
        """Appele par le menu clic-droit de l'arbre ("Lancer ce test / ces tests")."""
        if not self.workspace:
            QMessageBox.warning(self, "Warning", "No workspace loaded.")
            return

        if not nodeids:
            QMessageBox.information(self, "Info", "Aucun test executable trouve sous cet element.")
            return

        self._launch_worker(nodeids, f"Running {len(nodeids)} test(s) selectionne(s) via le menu contextuel...\n")

    def open_test_file(self, relative_path: str):
        """Ouvre le fichier source d'un test avec l'application par defaut de Windows."""
        if not self.workspace:
            return

        full_path = os.path.join(self.workspace, relative_path)
        if not os.path.isfile(full_path):
            QMessageBox.warning(self, "Fichier introuvable", f"Impossible de trouver :\n{full_path}")
            return

        try:
            os.startfile(full_path)
        except AttributeError:
            # os.startfile n'existe que sous Windows ; ce projet est distribue
            # exclusivement pour Windows 32 bits, mais on securise quand meme.
            QMessageBox.information(
                self,
                "Non supporte",
                f"Ouverture automatique non disponible sur cette plateforme.\nChemin : {full_path}",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le fichier :\n{exc}")




