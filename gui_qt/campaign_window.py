from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSettings
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QSplitter,
    QLineEdit,
    QComboBox,
    QLabel,
    QTreeView,
    QProgressBar,
    QSizePolicy,
    QMenu,
    QDialog,
    QCheckBox,
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QBrush

from core.campaign import Campaign, CampaignScenario, CampaignTest, load_campaign, command_to_display
from core.failure_report import extract_failure_traceback
from core.pytest_executor import parse_test_status_line
from core.run_history import RunHistoryManager, new_run_id, history_dir
from gui_qt.config.config_loader import find_config_yaml
from gui_qt.config.config_dialog import ConfigDialog
from gui_qt.dialogs import show_scrollable_error, open_test_log_for
from gui_qt.styles.styles import primary_button, neutral_button, success_button, danger_button, toolbar_button, tree_style, console_style
from gui_qt.status_icons import STATUS_PRIORITY, STATUS_COLORS, status_icon


KIND_ROLE = Qt.UserRole
SCENARIO_INDEX_ROLE = Qt.UserRole + 1
TEST_INDEX_ROLE = Qt.UserRole + 2
REPEAT_INDEX_ROLE = Qt.UserRole + 3
STATUS_ROLE = Qt.UserRole + 4
NODEID_ROLE = Qt.UserRole + 5


@dataclass
class CampaignSelection:
    scenario_index: int
    test_index: int | None = None
    repeat_index: int | None = None
    kind: str = "scenario"


class CampaignTreeView(QTreeView):
    # Emis avec (nb coches, total) a chaque changement de selection des cases a cocher.
    selection_changed = pyqtSignal(int, int)
    # Emis avec le nodeid d'un test dont on veut ouvrir le fichier .log.
    open_log_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Campaign"])
        self.setModel(self.model)
        self.setUniformRowHeights(True)
        self._updating = False
        self.model.itemChanged.connect(self._on_item_changed)

        # Feuilles executables (items "test" sans repeat, ou items "repeat").
        self._leaf_items: list[QStandardItem] = []
        # Nodeid pytest (normalise) -> items en attente d'un resultat (FIFO, pour gerer les repeats).
        self._nodeid_to_items: dict[str, list[QStandardItem]] = {}
        # scenario_index -> item "setup" (pour colorer son statut apres execution).
        self._setup_items: dict[int, QStandardItem] = {}
        # Sortie console complete du dernier run, pour "Voir la trace d'echec".
        self._last_output: str = ""

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _norm(self, value: str) -> str:
        # Sous Windows, pytest affiche parfois les nodeids avec des antislashs
        # meme si campaign.yml les declare avec des slashs (ou l'inverse) : on
        # normalise pour que le lookup par nodeid fonctionne dans tous les cas.
        return str(value).replace("\\", "/").strip()

    def load_campaign(self, campaign: Campaign):
        self.model.blockSignals(True)
        self.model.clear()
        self.model.setHorizontalHeaderLabels([campaign.name])
        self._leaf_items.clear()
        self._nodeid_to_items.clear()
        self._setup_items.clear()
        root = self.model.invisibleRootItem()

        for scenario_index, scenario in enumerate(campaign.scenarios):
            scenario_item = self._make_item(scenario.name, "scenario", scenario_index)
            root.appendRow(scenario_item)

            if scenario.setup:
                setup_item = self._make_item(
                    "setup: " + command_to_display(scenario.setup),
                    "setup",
                    scenario_index,
                )
                setup_item.setCheckable(False)
                scenario_item.appendRow(setup_item)
                self._setup_items[scenario_index] = setup_item

            for test_index, test in enumerate(scenario.tests):
                label = test.name or test.nodeid
                if test.repeat > 1:
                    test_item = self._make_item(f"{label}  x{test.repeat}", "test", scenario_index, test_index)
                    scenario_item.appendRow(test_item)
                    for repeat_index in range(test.repeat):
                        repeat_item = self._make_item(
                            f"run #{repeat_index + 1}",
                            "repeat",
                            scenario_index,
                            test_index,
                            repeat_index,
                        )
                        repeat_item.setData(test.nodeid, NODEID_ROLE)
                        test_item.appendRow(repeat_item)
                        self._leaf_items.append(repeat_item)
                        self._nodeid_to_items.setdefault(self._norm(test.nodeid), []).append(repeat_item)
                else:
                    test_item = self._make_item(label, "test", scenario_index, test_index)
                    test_item.setData(test.nodeid, NODEID_ROLE)
                    scenario_item.appendRow(test_item)
                    self._leaf_items.append(test_item)
                    self._nodeid_to_items.setdefault(self._norm(test.nodeid), []).append(test_item)

        self.model.blockSignals(False)
        self.set_all_checked(True)
        # Ne pas deployer automatiquement la campagne.
        # Sur de gros fichiers campaign.yml, expandToDepth ralentit fortement le chargement.
        self.collapseAll()
        self._emit_selection_changed()

    def _make_item(
        self,
        text: str,
        kind: str,
        scenario_index: int,
        test_index: int | None = None,
        repeat_index: int | None = None,
    ) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        item.setCheckable(True)
        item.setAutoTristate(False)
        item.setTristate(True)
        item.setCheckState(Qt.Checked)
        item.setData(kind, KIND_ROLE)
        item.setData(scenario_index, SCENARIO_INDEX_ROLE)
        if test_index is not None:
            item.setData(test_index, TEST_INDEX_ROLE)
        if repeat_index is not None:
            item.setData(repeat_index, REPEAT_INDEX_ROLE)
        return item

    # -----------------------------
    # Checkbox state management
    # -----------------------------

    def set_all_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            for row in range(self.model.rowCount()):
                item = self.model.item(row)
                item.setCheckState(state)
                self._update_children(item, state)
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()
        self._emit_selection_changed()

    def _on_item_changed(self, item: QStandardItem):
        if self._updating:
            return
        self._updating = True
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            state = item.checkState()
            if state in (Qt.Checked, Qt.Unchecked):
                self._update_children(item, state)
            self._update_parents(item)
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self._updating = False
            self.viewport().update()
        self._emit_selection_changed()

    def _emit_selection_changed(self):
        total = len(self._leaf_items)
        selected = sum(1 for item in self._leaf_items if item.checkState() == Qt.Checked)
        self.selection_changed.emit(selected, total)

    def _update_children(self, item: QStandardItem, state):
        stack = [item.child(row) for row in range(item.rowCount())]
        while stack:
            child = stack.pop()
            if child.isCheckable():
                child.setCheckState(state)
            for row in range(child.rowCount()):
                stack.append(child.child(row))

    def _update_parents(self, item: QStandardItem):
        parent = item.parent()
        while parent is not None:
            checked = unchecked = partial = 0
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if not child.isCheckable():
                    continue
                state = child.checkState()
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.Unchecked:
                    unchecked += 1
                else:
                    partial += 1
            total = checked + unchecked + partial
            if total == 0:
                parent = parent.parent()
                continue
            if checked == total:
                parent.setCheckState(Qt.Checked)
            elif unchecked == total:
                parent.setCheckState(Qt.Unchecked)
            else:
                parent.setCheckState(Qt.PartiallyChecked)
            parent = parent.parent()

    def get_selected_runs(self) -> list[CampaignSelection]:
        selections: list[CampaignSelection] = []
        stack = [self.model.item(row) for row in range(self.model.rowCount())]

        while stack:
            item = stack.pop()
            if item.isCheckable() and item.checkState() == Qt.Unchecked:
                continue

            kind = item.data(KIND_ROLE)
            scenario_index = item.data(SCENARIO_INDEX_ROLE)
            test_index = item.data(TEST_INDEX_ROLE)
            repeat_index = item.data(REPEAT_INDEX_ROLE)

            if kind == "repeat" and item.checkState() == Qt.Checked:
                selections.append(CampaignSelection(scenario_index, test_index, repeat_index, kind="repeat"))
                continue

            if kind == "test" and item.rowCount() == 0 and item.checkState() == Qt.Checked:
                selections.append(CampaignSelection(scenario_index, test_index, None, kind="test"))
                continue

            for row in range(item.rowCount() - 1, -1, -1):
                stack.append(item.child(row))

        return selections

    # -----------------------------
    # Results / coloring
    # -----------------------------

    def reset_result_colors(self):
        self.setUpdatesEnabled(False)
        try:
            stack = [self.model.item(row) for row in range(self.model.rowCount())]
            while stack:
                item = stack.pop()
                item.setData(None, STATUS_ROLE)
                item.setData(None, Qt.ForegroundRole)
                item.setIcon(QIcon())
                font = item.font()
                font.setBold(False)
                item.setFont(font)
                for row in range(item.rowCount()):
                    stack.append(item.child(row))
        finally:
            self.setUpdatesEnabled(True)
            self.viewport().update()

    def update_next_for_nodeid(self, nodeid: str, status: str) -> bool:
        """Applique le statut au prochain item en attente pour ce nodeid (FIFO, pour gerer les repeats)."""
        items = self._nodeid_to_items.get(self._norm(nodeid))
        if not items:
            return False
        item = items.pop(0)
        self._apply_status(item, status)
        self._propagate_status_to_parents(item)
        return True

    def update_setup_status(self, scenario_index: int, status: str):
        """Colore le noeud 'setup' d'un scenario selon le resultat de son script
        (PASSED = vert, FAILED = rouge), et remonte le statut au scenario parent."""
        item = self._setup_items.get(scenario_index)
        if item is None:
            return
        self._apply_status(item, status)
        self._propagate_status_to_parents(item)

    def _apply_status(self, item: QStandardItem, status: str):
        item.setData(status, STATUS_ROLE)
        color = STATUS_COLORS.get(status)
        if color:
            item.setForeground(QBrush(color))
        item.setIcon(status_icon(status))

        font = item.font()
        font.setBold(status in ("FAILED", "ERROR"))
        item.setFont(font)

    def _propagate_status_to_parents(self, item: QStandardItem):
        parent = item.parent()
        while parent is not None:
            worst = self._worst_child_status(parent)
            if worst:
                self._apply_status(parent, worst)
            else:
                parent.setData(None, STATUS_ROLE)
                parent.setData(None, Qt.ForegroundRole)
                parent.setIcon(QIcon())
                font = parent.font()
                font.setBold(False)
                parent.setFont(font)
            parent = parent.parent()

    def _worst_child_status(self, item: QStandardItem) -> str | None:
        worst_status = None
        worst_priority = 0
        for row in range(item.rowCount()):
            child = item.child(row)
            status = child.data(STATUS_ROLE)
            priority = STATUS_PRIORITY.get(status, 0)
            if priority > worst_priority:
                worst_priority = priority
                worst_status = status
        return worst_status

    # -----------------------------
    # Status / text filter
    # -----------------------------

    def filter_by_status(self, status: str):
        target = status.upper()
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._filter_item(root.child(row), target)

    def clear_status_filter(self):
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._set_row_hidden(root.child(row), False)
            self._clear_filter_recursive(root.child(row))

    def _clear_filter_recursive(self, item: QStandardItem):
        for row in range(item.rowCount()):
            child = item.child(row)
            self._set_row_hidden(child, False)
            self._clear_filter_recursive(child)

    def _filter_item(self, item: QStandardItem, target: str) -> bool:
        visible = item.data(STATUS_ROLE) == target
        for row in range(item.rowCount()):
            child_visible = self._filter_item(item.child(row), target)
            visible = visible or child_visible
        self._set_row_hidden(item, not visible)
        return visible

    def filter_by_text(self, text: str):
        query = text.lower()
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._filter_item_by_text(root.child(row), query)

    def _filter_item_by_text(self, item: QStandardItem, query: str) -> bool:
        visible = query in item.text().lower()
        for row in range(item.rowCount()):
            child_visible = self._filter_item_by_text(item.child(row), query)
            visible = visible or child_visible
        self._set_row_hidden(item, not visible)
        return visible

    def _set_row_hidden(self, item: QStandardItem, hidden: bool):
        parent = item.parent()
        if parent is None:
            parent_index = QModelIndex()
        else:
            parent_index = parent.index()
        self.setRowHidden(item.row(), parent_index, hidden)

    # -----------------------------
    # Menu contextuel (clic-droit)
    # -----------------------------

    def set_last_output(self, text: str):
        """Memorise la sortie console du dernier run pour l'action 'Voir la trace d'echec'."""
        self._last_output = text or ""

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return

        item = self.model.itemFromIndex(index)
        own_nodeid = item.data(NODEID_ROLE)
        own_status = item.data(STATUS_ROLE)

        menu = QMenu(self)
        open_log_action = menu.addAction("Ouvrir le log de ce test")
        open_log_action.setEnabled(bool(own_nodeid))
        view_trace_action = menu.addAction("Voir la trace d'echec")
        view_trace_action.setEnabled(bool(own_nodeid) and own_status in ("FAILED", "ERROR"))

        chosen = menu.exec_(self.viewport().mapToGlobal(pos))
        if chosen is view_trace_action and own_nodeid:
            self._show_failure_trace(own_nodeid)
        elif chosen is open_log_action and own_nodeid:
            self.open_log_requested.emit(own_nodeid)

    def _show_failure_trace(self, nodeid: str):
        trace = extract_failure_traceback(self._last_output, nodeid)
        if not trace:
            QMessageBox.information(
                self,
                "Trace introuvable",
                "Impossible de retrouver la trace d'echec de ce test dans la sortie du dernier run.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Trace d'echec - {nodeid}")
        dialog.resize(800, 500)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(console_style())
        text_edit.setPlainText(trace)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        dialog.exec_()


class CampaignWorker(QThread):
    stdout_signal = pyqtSignal(str)
    # Emis (exit_code, sortie console complete) : la sortie sert a l'historique des executions.
    finished_signal = pyqtSignal(int, str)
    error_signal = pyqtSignal(str)
    # Emis (nodeid, status) a chaque ligne de resultat pytest detectee dans la sortie.
    test_status_signal = pyqtSignal(str, str)
    # Emis (scenario_index, status) apres l'execution du script setup d'un scenario.
    setup_status_signal = pyqtSignal(int, str)

    def __init__(
        self,
        campaign: Campaign,
        selections: list[CampaignSelection],
        junit_xml_path: str | None = None,
        parallel: bool = False,
    ):
        super().__init__()
        self.campaign = campaign
        self.selections = selections
        self.junit_xml_path = junit_xml_path
        self.parallel = parallel
        self._stopped = False
        self._process: subprocess.Popen | None = None
        # Sortie console complete (plafonnee), conservee pour l'historique des executions.
        self._output_buffer: list[str] = []
        self._output_size = 0
        self._output_limit = 1_000_000
        # Une campagne lance un batch pytest par scenario : chacun produit son
        # propre rapport JUnit, fusionne en un seul fichier a la fin du run.
        self._junit_parts: list[str] = []

    def stop(self):
        self._stopped = True
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def run(self):
        exit_code = 0
        try:
            self.stdout_signal.emit("Campaign worker started.\n")
            grouped: dict[int, list[CampaignSelection]] = {}
            for selection in self.selections:
                grouped.setdefault(selection.scenario_index, []).append(selection)

            self.stdout_signal.emit(f"Selected campaign runs: {len(self.selections)}\n")

            for scenario_index in sorted(grouped):
                if self._stopped:
                    exit_code = -1
                    break

                scenario = self.campaign.scenarios[scenario_index]
                self.stdout_signal.emit(f"\n===== Scenario: {scenario.name} =====\n")

                if scenario.setup:
                    code = self._run_setup(scenario)
                    self.setup_status_signal.emit(scenario_index, "PASSED" if code == 0 else "FAILED")
                    if code != 0:
                        exit_code = code
                        self.stdout_signal.emit(f"\nSetup failed for scenario '{scenario.name}' with exit code {code}.\n")
                        continue

                nodeids = self._nodeids_for_scenario(scenario, grouped[scenario_index])
                if not nodeids:
                    self.stdout_signal.emit(f"No pytest tests selected for scenario '{scenario.name}'.\n")
                    continue

                self.stdout_signal.emit(
                    f"\n--- pytest batch for scenario: {scenario.name} "
                    f"({len(nodeids)} selected run(s)) ---\n"
                )
                junit_part_path = f"{self.junit_xml_path}.part{scenario_index}.xml" if self.junit_xml_path else None
                code = self._run_pytest_batch(nodeids, junit_part_path)
                if junit_part_path and os.path.isfile(junit_part_path):
                    self._junit_parts.append(junit_part_path)
                if code != 0 and exit_code == 0:
                    exit_code = code

            if self.junit_xml_path and self._junit_parts:
                self._merge_junit_reports(self._junit_parts, self.junit_xml_path)

        except Exception as exc:
            exit_code = -1
            self.error_signal.emit(f"Campaign worker error: {type(exc).__name__}: {exc}\n")

        self.finished_signal.emit(-1 if self._stopped else exit_code, "".join(self._output_buffer))

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        entries = [str(path) for path in self.campaign.pythonpath if str(path).strip()]
        old_pythonpath = env.get("PYTHONPATH")
        if old_pythonpath:
            entries.append(old_pythonpath)

        # Deduplicate while preserving order.
        seen = set()
        clean_entries = []
        for entry in entries:
            norm = os.path.normcase(os.path.abspath(entry)) if os.path.isabs(entry) else os.path.normcase(entry)
            if norm in seen:
                continue
            seen.add(norm)
            clean_entries.append(entry)

        env["PYTHONPATH"] = os.pathsep.join(clean_entries)
        return env

    def _looks_like_pytest_target(self, command: str) -> bool:
        if "::" in command:
            return True
        target = shlex.split(command)[0] if command.strip() else command
        filename = os.path.basename(target.split("::", 1)[0])
        return filename.startswith("test_") and filename.endswith(".py")

    def _run_setup(self, scenario: CampaignScenario) -> int:
        command = scenario.setup
        self.stdout_signal.emit(f"\n--- setup: {command_to_display(command)} ---\n")
        if isinstance(command, list):
            cmd = command
        else:
            assert command is not None
            if self._looks_like_pytest_target(command):
                cmd = [
                    sys.executable,
                    "-m",
                    "pytest",
                    command,
                    "--import-mode=importlib",
                    "--tb=short",
                    "-v",
                ]
            elif command.endswith(".py") and os.path.exists(os.path.join(self.campaign.workspace, command)):
                cmd = [sys.executable, command]
            else:
                cmd = shlex.split(command)
        return self._run_command(cmd)

    def _nodeids_for_scenario(self, scenario: CampaignScenario, selections: list[CampaignSelection]) -> list[str]:
        nodeids: list[str] = []
        for selection in selections:
            if selection.test_index is None:
                continue
            test = scenario.tests[selection.test_index]
            nodeids.append(test.nodeid)
        return nodeids

    def _validate_nodeids(self, nodeids: list[str]) -> int:
        for nodeid in nodeids:
            # Validation lisible avant d'appeler pytest.
            # Pytest accepte un nodeid complet, mais la partie fichier avant "::"
            # doit exister relativement au workspace de la campagne.
            test_file = nodeid.split("::", 1)[0]
            test_path = os.path.join(self.campaign.workspace, test_file)
            if not os.path.exists(test_path):
                self.stdout_signal.emit(
                    "Test file not found for campaign nodeid:\n"
                    f"  nodeid: {nodeid}\n"
                    f"  workspace: {self.campaign.workspace}\n"
                    f"  expected file: {test_path}\n"
                    "Fix campaign.yml workspace or replace the nodeid with one copied from Workspace Mode.\n"
                )
                return 4
        return 0

    def _run_pytest_batch(self, nodeids: list[str], junit_part_path: str | None = None) -> int:
        validation_code = self._validate_nodeids(nodeids)
        if validation_code != 0:
            return validation_code

        unique_count = len(set(nodeids))
        duplicate_count = len(nodeids) - unique_count
        if duplicate_count:
            self.stdout_signal.emit(
                f"Batch contains {duplicate_count} duplicate selected run(s); "
                "--keep-duplicates is enabled.\n"
            )

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *nodeids,
            "--keep-duplicates",
            "--import-mode=importlib",
            "--tb=short",
            "-v",
        ]
        if self.parallel:
            # Necessite pytest-xdist. parse_test_status_line() gere le format
            # de sortie -v specifique a -n (prefixe [gwN]).
            cmd.extend(["-n", "auto"])
        if junit_part_path:
            cmd.append(f"--junitxml={junit_part_path}")
        return self._run_command(cmd)

    def _merge_junit_reports(self, part_paths: list[str], dest_path: str):
        """Fusionne les rapports JUnit XML d'une campagne (un par scenario) en un
        seul fichier, pour rester coherent avec le mode Workspace (un run = un
        rapport). Ne necessite aucune dependance supplementaire (ElementTree)."""
        import xml.etree.ElementTree as ET

        merged_root = ET.Element("testsuites")
        for part_path in part_paths:
            try:
                root = ET.parse(part_path).getroot()
            except Exception:
                continue
            if root.tag == "testsuites":
                merged_root.extend(list(root))
            else:
                merged_root.append(root)

        try:
            ET.ElementTree(merged_root).write(dest_path, encoding="utf-8", xml_declaration=True)
        except Exception as exc:
            self.stdout_signal.emit(f"Unable to merge JUnit reports: {type(exc).__name__}: {exc}\n")
        finally:
            for part_path in part_paths:
                try:
                    os.remove(part_path)
                except OSError:
                    pass

    def _run_command(self, cmd: list[str]) -> int:
        env = self._build_env()
        self.stdout_signal.emit(f"cwd: {self.campaign.workspace}\n")
        self.stdout_signal.emit(f"PYTHONPATH: {env.get('PYTHONPATH', '')}\n")
        self.stdout_signal.emit("$ " + " ".join(shlex.quote(str(part)) for part in cmd) + "\n")
        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=self.campaign.workspace,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.stdout_signal.emit(f"Unable to start command: {type(exc).__name__}: {exc}\n")
            return -1
        assert self._process.stdout is not None
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
            parsed = parse_test_status_line(line)
            if parsed:
                self.test_status_signal.emit(parsed[0], parsed[1])

            self._output_buffer.append(line)
            self._output_size += len(line)
            while self._output_size > self._output_limit and self._output_buffer:
                self._output_size -= len(self._output_buffer.pop(0))

            emit_buffer.append(line)
            emit_size += len(line)
            if len(emit_buffer) >= 50 or emit_size >= 8192:
                flush_emit_buffer()
        flush_emit_buffer()
        if self._stopped:
            self._process.terminate()
            return -1
        self._process.wait()
        return int(self._process.returncode or 0)


class CampaignPanel(QWidget):
    # Emis apres l'enregistrement d'un run dans l'historique, pour rafraichir
    # la fenetre Historique si elle est ouverte.
    history_updated = pyqtSignal()

    def __init__(self, parent=None, history_manager: RunHistoryManager | None = None):
        super().__init__(parent)
        self.campaign: Campaign | None = None
        self.worker: CampaignWorker | None = None
        self.history_manager = history_manager or RunHistoryManager()
        self.done_count = 0
        self.total_selected = 0
        self.test_counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0, "ERROR": 0}
        self.failed_nodeids: set[str] = set()
        self._current_run_id: str | None = None
        self._current_junit_path: str | None = None
        self._run_started_at: float | None = None
        self._current_run_nodeids: list[str] = []

        self.settings = QSettings("MyCompany", "PyTestRunner")

        self.path_edit = QComboBox()
        self.path_edit.setEditable(True)
        self.path_edit.setInsertPolicy(QComboBox.NoInsert)
        self.path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.path_edit.setPlaceholderText("Select campaign.yml...")

        recent = self.settings.value("recent_campaigns", [], type=list)
        for path in recent:
            self.path_edit.addItem(path)

        last_campaign = self.settings.value("last_campaign", "")
        if last_campaign:
            if last_campaign not in recent:
                self.path_edit.insertItem(0, last_campaign)
            self.path_edit.setCurrentText(last_campaign)

        self.browse_button = QPushButton("Browse")
        self.load_button = QPushButton("Load Campaign")
        self.open_config_button = QPushButton("Open Config")
        self.run_button = QPushButton("Run Selected")
        self.stop_button = QPushButton("Stop")
        self.rerun_failed_button = QPushButton("Re-run Failed")
        self.parallel_checkbox = QCheckBox("Parallel (-n auto)")
        self.all_button = QPushButton("All")
        self.none_button = QPushButton("None")
        self.failed_only_button = QPushButton("Failed only")
        self.failed_only_button.setCheckable(True)
        self.expand_all_button = QPushButton("Expand All")
        self.collapse_all_button = QPushButton("Collapse All")

        self.browse_button.setStyleSheet(neutral_button())
        self.load_button.setStyleSheet(primary_button())
        self.open_config_button.setStyleSheet(neutral_button())
        self.run_button.setStyleSheet(success_button())
        self.stop_button.setStyleSheet(danger_button())
        self.rerun_failed_button.setStyleSheet(danger_button())
        self.all_button.setStyleSheet(toolbar_button())
        self.none_button.setStyleSheet(toolbar_button())
        self.failed_only_button.setStyleSheet(toolbar_button())
        self.expand_all_button.setStyleSheet(toolbar_button())
        self.collapse_all_button.setStyleSheet(toolbar_button())

        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(False)

        self.tree = CampaignTreeView()
        self.tree.setStyleSheet(tree_style())
        self.tree.selection_changed.connect(self.on_selection_changed)
        self.tree.open_log_requested.connect(self.open_test_log)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter tests...")
        self.filter_edit.textChanged.connect(self.on_filter_text_changed)

        self.selection_label = QLabel("0 / 0 selected")
        self.selection_label.setAlignment(Qt.AlignRight)
        self.selection_label.setStyleSheet("color: #616161; font-size: 12px;")

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(12000)
        self.console.setStyleSheet(console_style())
        self._console_pending: list[str] = []
        self._console_flush_timer = QTimer(self)
        self._console_flush_timer.setInterval(50)
        self._console_flush_timer.timeout.connect(self._flush_console_output)
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(QLabel("campaign.yml"))
        top_bar.addWidget(self.path_edit)
        top_bar.addWidget(self.browse_button)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)
        action_bar.addWidget(self.load_button)
        action_bar.addWidget(self.open_config_button)
        action_bar.addSpacing(90)
        action_bar.addWidget(self.run_button)
        action_bar.addWidget(self.stop_button)
        action_bar.addWidget(self.rerun_failed_button)
        action_bar.addWidget(self.parallel_checkbox)

        tree_toolbar = QHBoxLayout()
        tree_toolbar.setSpacing(6)
        tree_toolbar.addWidget(self.all_button)
        tree_toolbar.addWidget(self.none_button)
        tree_toolbar.addWidget(self.failed_only_button)
        tree_toolbar.addWidget(self.expand_all_button)
        tree_toolbar.addWidget(self.collapse_all_button)
        tree_toolbar.addStretch()
        tree_toolbar.addWidget(self.filter_edit)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addLayout(tree_toolbar)
        left_layout.addWidget(self.tree)
        left_layout.addWidget(self.selection_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.console)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addLayout(top_bar)
        layout.addLayout(action_bar)
        layout.addWidget(splitter)
        layout.addWidget(self.progress)

        self.browse_button.clicked.connect(self.browse_campaign)
        self.load_button.clicked.connect(self.load_campaign)
        self.open_config_button.clicked.connect(self.open_config)
        self.run_button.clicked.connect(self.run_selected)
        self.stop_button.clicked.connect(self.stop_campaign)
        self.rerun_failed_button.clicked.connect(self.run_failed)
        self.all_button.clicked.connect(lambda: self.tree.set_all_checked(True))
        self.none_button.clicked.connect(lambda: self.tree.set_all_checked(False))
        self.expand_all_button.clicked.connect(self.tree.expandAll)
        self.collapse_all_button.clicked.connect(self.tree.collapseAll)
        self.failed_only_button.toggled.connect(self.on_failed_only_toggled)

    def _add_recent_campaign(self, path: str):
        if not path:
            return

        recent = self.settings.value("recent_campaigns", [], type=list)
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:5]
        self.settings.setValue("recent_campaigns", recent)

        self.path_edit.clear()
        self.path_edit.addItems(recent)
        self.path_edit.setCurrentText(path)

    def browse_campaign(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select campaign.yml",
            self.path_edit.currentText().strip() or "",
            "YAML files (*.yml *.yaml);;All files (*)",
        )
        if path:
            self.path_edit.setCurrentText(path)

    def load_campaign(self):
        path = self.path_edit.currentText().strip()
        if not path:
            QMessageBox.warning(self, "Warning", "Please select a campaign.yml file.")
            return
        if not os.path.isfile(path):
            QMessageBox.critical(self, "Error", "Invalid campaign.yml path.")
            return
        try:
            self.campaign = load_campaign(path)
            self.tree.load_campaign(self.campaign)
            self._add_recent_campaign(path)
            self.settings.setValue("last_campaign", path)
            self.console.clear()
            self.console.append(f"Loaded campaign: {self.campaign.name}\n")
            if self.campaign.campaign_file:
                self.console.append(f"Campaign file: {self.campaign.campaign_file}\n")
            self.console.append(f"Workspace: {self.campaign.workspace}\n")
            self.console.append("PYTHONPATH entries:\n")
            for entry in self.campaign.pythonpath:
                self.console.append(f"  - {entry}\n")
            self.console.append(f"Scenarios: {len(self.campaign.scenarios)}\n")
            self.run_button.setEnabled(True)
        except Exception as exc:
            show_scrollable_error(
                self,
                "Erreur de chargement de la campagne",
                str(exc),
                intro="Impossible de charger ce fichier campaign.yml :",
            )

    def open_config(self):
        if not self.campaign:
            QMessageBox.warning(self, "Warning", "No campaign loaded.")
            return

        config_path = find_config_yaml(self.campaign.workspace)
        if not config_path:
            QMessageBox.information(self, "Info", "No config.yaml found.")
            return

        dialog = ConfigDialog(config_path, self)
        dialog.exec_()

    def open_test_log(self, nodeid: str):
        if not self.campaign:
            return
        open_test_log_for(self, self.campaign.workspace, nodeid)

    def on_selection_changed(self, selected: int, total: int):
        self.selection_label.setText(f"{selected} / {total} selected")

    def on_filter_text_changed(self, text: str):
        query = text.strip()
        if query:
            self.tree.filter_by_text(query)
        elif self.failed_only_button.isChecked():
            self.tree.filter_by_status("FAILED")
        else:
            self.tree.clear_status_filter()

    def on_failed_only_toggled(self, checked: bool):
        if checked:
            self.tree.filter_by_status("FAILED")
        else:
            self.tree.clear_status_filter()

    def _nodeids_for_selections(self, selections: list[CampaignSelection]) -> list[str]:
        nodeids: list[str] = []
        for selection in selections:
            if selection.test_index is None:
                continue
            test = self.campaign.scenarios[selection.scenario_index].tests[selection.test_index]
            nodeids.append(test.nodeid)
        return nodeids

    def _selections_for_nodeids(self, nodeids: set[str]) -> list[CampaignSelection]:
        """Reconstruit une selection 'test' pour chaque nodeid en echec, quel que soit
        l'etat actuel des cases a cocher dans l'arbre."""
        selections: list[CampaignSelection] = []
        for scenario_index, scenario in enumerate(self.campaign.scenarios):
            for test_index, test in enumerate(scenario.tests):
                if test.nodeid in nodeids:
                    selections.append(CampaignSelection(scenario_index, test_index, None, kind="test"))
        return selections

    def run_selected(self):
        if not self.campaign:
            QMessageBox.warning(self, "Warning", "No campaign loaded.")
            return
        selections = self.tree.get_selected_runs()
        if not selections:
            QMessageBox.warning(self, "Warning", "No campaign tests selected.")
            return

        self._launch_worker(selections, f"Running campaign... selected runs: {len(selections)}\n")

    def run_failed(self):
        if not self.failed_nodeids:
            QMessageBox.information(self, "Info", "Aucun test en echec a relancer.")
            return

        selections = self._selections_for_nodeids(self.failed_nodeids)
        if not selections:
            QMessageBox.information(self, "Info", "Aucun test en echec correspondant trouve dans la campagne.")
            return

        self._launch_worker(selections, f"Re-running {len(selections)} failed test(s)...\n")

    def _launch_worker(self, selections: list[CampaignSelection], intro_message: str):
        self.console.clear()
        self.console.append(intro_message)

        self.tree.reset_result_colors()
        self.done_count = 0
        self.total_selected = len(selections)
        self.progress.setMaximum(self.total_selected)
        self.progress.setValue(0)

        self.test_counts = {k: 0 for k in self.test_counts}
        self.failed_nodeids = set()

        self._current_run_id = new_run_id()
        self._current_junit_path = os.path.join(history_dir(), f"{self._current_run_id}.xml")
        self._run_started_at = time.time()
        self._current_run_nodeids = self._nodeids_for_selections(selections)

        self.worker = CampaignWorker(
            self.campaign,
            selections,
            junit_xml_path=self._current_junit_path,
            parallel=self.parallel_checkbox.isChecked(),
        )
        self.worker.stdout_signal.connect(self._on_stdout)
        self.worker.error_signal.connect(self._on_stdout)
        self.worker.test_status_signal.connect(self._on_test_status)
        self.worker.setup_status_signal.connect(self._on_setup_status)
        self.worker.finished_signal.connect(self._on_finished)
        self.run_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.worker.start()

    def stop_campaign(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.console.append("\nCampaign stopped by user.\n")
            self.stop_button.setEnabled(False)

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
        self._queue_console_output(text)

    def _on_setup_status(self, scenario_index: int, status: str):
        self.tree.update_setup_status(scenario_index, status)

    def _on_test_status(self, nodeid: str, status: str):
        if self.tree.update_next_for_nodeid(nodeid, status):
            self.done_count += 1
            self.progress.setValue(min(self.done_count, self.progress.maximum()))
            if status in self.test_counts:
                self.test_counts[status] += 1
            if status == "FAILED":
                self.failed_nodeids.add(nodeid)

    def _on_finished(self, exit_code: int, output_text: str):
        self._flush_console_output()
        self.progress.setValue(self.progress.maximum())
        self._queue_console_output(f"\nCampaign finished with exit code {exit_code}\n")
        self._flush_console_output()
        self.tree.set_last_output(output_text)
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.rerun_failed_button.setEnabled(bool(self.failed_nodeids))

        duration = (time.time() - self._run_started_at) if self._run_started_at else 0.0
        self.history_manager.add_run(
            run_id=self._current_run_id or new_run_id(),
            workspace=self.campaign.workspace if self.campaign else "",
            duration_seconds=duration,
            exit_code=exit_code,
            counts=self.test_counts,
            nodeids=self._current_run_nodeids,
            failed_nodeids=sorted(self.failed_nodeids),
            output_text=output_text,
            junit_xml_path=self._current_junit_path or "",
            source="campaign",
        )
        self.history_updated.emit()
