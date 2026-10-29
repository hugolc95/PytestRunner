"""Embedded editor for reusable and portable execution profiles."""

from __future__ import annotations

import uuid
import copy
import yaml
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QToolButton,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from runner.domain.execution_profile import (
    EXTENSION,
    ExecutionOptions,
    ExecutionProfile,
    ProfileStore,
    ProfileValidationError,
    ReportOptions,
    export_profile,
    inspect_profile,
    profile_group_runs,
    group_path, group_entry, inherited_configuration, merge_configuration,
)
from runner.domain.models import Kind
from runner.domain.profile_configuration import configuration_details, exception_text
from runner.domain.tree import build_tree, build_sequence_tree, group_hierarchically
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import ErrorDialog
from runner.ui.profile_dialogs import StepParametersDialog, ProfileGroupDialog, ConfirmGroupMoveDialog, EffectiveConfigurationDialog, MoveToGroupDialog, yaml_fields, format_value
from runner.ui.profile_group_delegate import ProfileGroupDelegate, EXCEPTION_ROLE
from runner.ui.profile_history import ProfileEdit, undoable
from runner.ui.profile_clipboard import SequenceClipboard

_OVERRIDES_ROLE = Qt.UserRole + 20
_LABEL_ROLE = Qt.UserRole + 23
_KIND_ROLE = Qt.UserRole + 25
_GROUP_ROLE = Qt.UserRole + 26


def _short_nodeid(nodeid: str) -> str:
    """Garde la partie utile a l'ecran; le nodeid complet reste en tooltip."""
    parts = nodeid.replace("\\", "/").split("::")
    if len(parts) > 2:
        return "::".join(parts[-2:])
    return parts[-1]


class SequenceTree(QTreeWidget):
    order_changed = Signal()

    def __init__(self, confirm_drop, parent=None):
        super().__init__(parent)
        self.confirm_drop = confirm_drop

    def dropEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        if self.dropIndicatorPosition() != QAbstractItemView.OnItem and target is not None:
            target = target.parent()
        if not self.confirm_drop(target):
            event.ignore()
            return
        super().dropEvent(event)
        if event.isAccepted():
            self.order_changed.emit()


class AddTestsDialog(QDialog):
    """Test picker where each Add action creates one sequence occurrence."""

    tests_added = Signal(list)

    def __init__(self, nodeids: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add tests or groups")
        self.resize(690, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        layout.setSpacing(t.SPACE_2)

        copy = QLabel(
            "Select a test, a class or a folder. Groups are added together "
            "in selection order, and can be added again.")
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tests…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.model = TestTreeModel(self)
        self.model.set_tree(build_tree(nodeids))
        self.model.set_all_checked(False)
        self._selection_order = []
        self._last_added = []
        self.model.selection_changed.connect(self._remember_selection_order)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterKeyColumn(0)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # `TestTreeModel` reserve toujours une deuxieme colonne pour le statut
        # par lecteur (utile dans l'arbre principal, muette ici -- ce dialogue
        # n'a pas de lecteurs). Sans lecteur, le nom se serrait dans le
        # partage par defaut entre les deux colonnes : une fois l'indentation
        # des dossiers deduite, il ne restait presque plus rien pour le texte
        # ni la case a cocher des feuilles profondement imbriquees -- ni l'un
        # ni l'autre ne tombait plus dans la zone cliquable que Qt calcule
        # pour la case. Cacher cette colonne et etirer la premiere regle les
        # deux : le texte redevient lisible, et la case redevient cliquable.
        for column in range(1, self.model.columnCount()):
            self.tree.setColumnHidden(column, True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.tree, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add selected")
        self.add_button.setObjectName("Primary")
        self.add_button.setIcon(icons.icon("mdi.plus"))
        self.add_again_button = QPushButton("Add selected again")
        self.done_button = QPushButton("Done")
        actions.addWidget(self.add_button)
        actions.addWidget(self.add_again_button)
        actions.addStretch(1)
        actions.addWidget(self.done_button)
        layout.addLayout(actions)

        self.search.textChanged.connect(self._filter)
        self.tree.doubleClicked.connect(self._add_clicked_test)
        self.add_button.clicked.connect(self._add)
        self.add_again_button.clicked.connect(self._add_again)
        self.done_button.clicked.connect(self.accept)
        self.add_button.setEnabled(False)
        self.add_again_button.setEnabled(False)

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())
        if text.strip():
            self.tree.expandAll()

    def _add(self) -> None:
        selected = list(self._selection_order)
        if selected:
            self._last_added = list(selected)
            self.tests_added.emit(selected)
            self.model.set_all_checked(False)

    def _add_again(self):
        if self._selection_order:
            self._add()
        elif self._last_added:
            self.tests_added.emit(list(self._last_added))

    def _remember_selection_order(self, *_):
        selected = self.model.checked_nodeids()
        current = set(selected)
        self._selection_order = [nodeid for nodeid in self._selection_order if nodeid in current]
        previous = set(self._selection_order)
        self._selection_order.extend(nodeid for nodeid in selected if nodeid not in previous)
        self.add_button.setEnabled(bool(selected))
        self.add_again_button.setEnabled(bool(selected or self._last_added))
        self.add_button.setText(f"Add selected ({len(selected)})" if selected else "Add selected")

    def _add_clicked_test(self, proxy_index) -> None:
        source_index = self.proxy.mapToSource(proxy_index).siblingAtColumn(0)
        nodeid = self.model.data(source_index, NODEID_ROLE)
        if nodeid:
            self._last_added = [nodeid]
            self.add_again_button.setEnabled(True)
            self.tests_added.emit([nodeid])


class ExecutionProfilesPage(QWidget):
    """Profile library, sequence editor, import/export and launch hand-off."""

    run_requested = Signal(object)

    def __init__(self, store: ProfileStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._profiles: list[ExecutionProfile] = []
        self._available_nodeids: list[str] = []
        self._workspace_config = ""
        self._preview_readers = []
        self._dirty = False
        self._building = False
        self._configuration_text = ''
        self._history_state = None
        self._edit_depth = 0
        self._history_restoring = False
        self._saving_refresh = False
        self._initial_unsaved = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(50)
        self.undo_stack.indexChanged.connect(self._sync_history_dirty)
        self._reorder_timer = QTimer(self)
        self._reorder_timer.setSingleShot(True)
        self._reorder_timer.timeout.connect(self._settle_sequence_order)
        self._build_ui()
        self.sequence_clipboard = SequenceClipboard(self)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        root.setSpacing(t.SPACE_3)

        heading = QHBoxLayout()
        copy_box = QVBoxLayout()
        title = QLabel("Execution Profiles")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Create, share and reuse ordered test sequences.")
        subtitle.setObjectName("Muted")
        copy_box.addWidget(title)
        copy_box.addWidget(subtitle)
        heading.addLayout(copy_box)
        heading.addStretch(1)
        self.import_button = QPushButton("Import")
        self.import_button.setIcon(icons.icon("mdi.import"))
        self.export_button = QPushButton("Export")
        self.export_button.setIcon(icons.icon("mdi.export"))
        self.new_button = QPushButton("New profile")
        self.new_button.setObjectName("Primary")
        self.new_button.setIcon(icons.icon("mdi.plus"))
        heading.addWidget(self.import_button)
        heading.addWidget(self.export_button)
        heading.addWidget(self.new_button)
        root.addLayout(heading)

        self.notice = QFrame()
        self.notice.setObjectName("ProfileNotice")
        notice_layout = QHBoxLayout(self.notice)
        notice_layout.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        self.notice_label = QLabel()
        self.notice_label.setWordWrap(True)
        notice_layout.addWidget(self.notice_label, 1)
        self.notice.hide()
        root.addWidget(self.notice)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_library())
        splitter.addWidget(self._build_sequence())
        splitter.addWidget(self._build_options())
        splitter.setStretchFactor(0, 20)
        splitter.setStretchFactor(1, 48)
        splitter.setStretchFactor(2, 32)
        splitter.setSizes([170, 650, 240])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.summary = QLabel("No profile selected")
        self.summary.setObjectName("Muted")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("Ghost")
        self.save_as_button = QPushButton("Save as…")
        self.save_button = QPushButton("Save changes")
        self.run_button = QPushButton("Open in Run Tests")
        self.run_button.setObjectName("Run")
        self.run_button.setIcon(icons.icon("mdi.play"))
        footer.addWidget(self.summary)
        footer.addStretch(1)
        footer.addWidget(self.delete_button)
        footer.addWidget(self.save_as_button)
        footer.addWidget(self.save_button)
        footer.addWidget(self.run_button)
        root.addLayout(footer)

        self.import_button.clicked.connect(self.import_profile)
        self.export_button.clicked.connect(self.export_current)
        self.new_button.clicked.connect(self.new_profile)
        self.delete_button.clicked.connect(self.delete_current)
        self.save_button.clicked.connect(self.save_current)
        self.save_as_button.clicked.connect(self.save_as)
        self.run_button.clicked.connect(self.open_in_run_tests)
        self.profile_list.currentRowChanged.connect(self._load_row)

    def _surface(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Surface")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_3, t.SPACE_3, t.SPACE_3)
        layout.setSpacing(t.SPACE_2)
        heading = QLabel(title.upper())
        heading.setObjectName("ProfileSectionTitle")
        layout.addWidget(heading)
        return frame, layout

    def _build_library(self) -> QWidget:
        frame, layout = self._surface("Saved profiles")
        self.profile_list = QListWidget()
        self.profile_list.setObjectName("ProfileLibrary")
        layout.addWidget(self.profile_list, 1)
        return frame

    def _build_sequence(self) -> QWidget:
        frame, layout = self._surface("Test sequence")
        title = layout.takeAt(0).widget()
        header = QHBoxLayout()
        header.addWidget(title)
        self.transfer_label = QLabel()
        self.transfer_label.setTextFormat(Qt.PlainText)
        self.transfer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.transfer_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.transfer_label.hide()
        header.addWidget(self.transfer_label, 1)
        layout.insertLayout(0, header)
        self.sequence_list = SequenceTree(self._confirm_drop, self)
        self.sequence_list.setObjectName("ProfileSequence")
        self.sequence_list.setProperty("variableRowHeights", True)
        self.sequence_list.setHeaderHidden(True)
        self.sequence_list.setItemDelegate(ProfileGroupDelegate(self.sequence_list))
        self.sequence_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.sequence_list.setDefaultDropAction(Qt.MoveAction)
        self.sequence_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sequence_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sequence_list.setIndentation(14)
        self.sequence_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.sequence_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sequence_list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.sequence_list.setAccessibleName("Ordered test sequence")
        self.sequence_list.setAccessibleDescription(
            "Expandable test groups in execution order. Move, duplicate or remove a group or a test.")
        self.sequence_list.setToolTip("Select tests to create a group. Double-click a test to edit its YAML parameters.")
        self.sequence_list.itemSelectionChanged.connect(self._selection_changed)
        self.sequence_list.itemDoubleClicked.connect(self._edit_item)
        self.sequence_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sequence_list.customContextMenuRequested.connect(self._show_context_menu)
        tools = QHBoxLayout()
        self.parameters_button = QPushButton("YAML parameters…")
        self.parameters_button.setIcon(icons.icon("mdi.tune"))
        self.parameters_button.clicked.connect(self.edit_step_parameters)
        self.group_button = QPushButton("Create group…")
        self.group_button.setIcon(icons.icon("mdi.folder-plus-outline"))
        self.group_button.clicked.connect(self.edit_group)
        self.subgroup_button = QToolButton()
        self.subgroup_button.setIcon(icons.icon("mdi.folder-plus-outline"))
        self.subgroup_button.setToolTip("Create a subgroup inside the selected group")
        self.subgroup_button.setAccessibleName("Create subgroup")
        self.subgroup_button.clicked.connect(lambda: self.edit_group(subgroup=True))
        self.ungroup_button = QToolButton()
        self.ungroup_button.setIcon(icons.icon("mdi.folder-remove-outline"))
        self.ungroup_button.setToolTip("Ungroup selected tests (keep the tests and their YAML parameters)")
        self.ungroup_button.clicked.connect(self.ungroup_steps)
        for button in (self.parameters_button, self.group_button, self.subgroup_button, self.ungroup_button):
            tools.addWidget(button)
        self.effective_button = QToolButton()
        self.effective_button.setIcon(icons.icon('mdi.file-eye-outline'))
        self.effective_button.setToolTip('View effective YAML and value origins for this test')
        self.effective_button.setAccessibleName('View effective YAML')
        self.effective_button.clicked.connect(self.show_effective_configuration)
        tools.addWidget(self.effective_button)
        tools.addStretch()
        self.undo_action = self.undo_stack.createUndoAction(self, 'Undo')
        self.redo_action = self.undo_stack.createRedoAction(self, 'Redo')
        for action, glyph, shortcut in ((self.undo_action, 'mdi.undo', QKeySequence.Undo),
                                         (self.redo_action, 'mdi.redo', QKeySequence.Redo)):
            action.setIcon(icons.icon(glyph))
            action.setShortcuts(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.addAction(action)
            button = QToolButton()
            button.setDefaultAction(action)
            tools.addWidget(button)
        layout.addLayout(tools)
        layout.addWidget(self.sequence_list, 1)
        actions = QHBoxLayout()
        self.add_tests_button = QPushButton("Add tests / groups")
        self.add_tests_button.setIcon(icons.icon("mdi.plus"))
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("Ghost")
        actions.addWidget(self.add_tests_button)
        actions.addWidget(self.duplicate_button)
        actions.addWidget(self.remove_button)
        for direction, name in ((-1, "mdi.arrow-up"), (1, "mdi.arrow-down")):
            button = QToolButton()
            button.setIcon(icons.icon(name))
            button.setToolTip("Move test or group up" if direction < 0 else "Move test or group down")
            button.clicked.connect(lambda checked=False, d=direction: self._move_step(d))
            actions.addWidget(button)
        for glyph, tooltip, callback in (
                ("mdi.unfold-more-horizontal", "Expand groups", self._expand_groups),
                ("mdi.unfold-less-horizontal", "Collapse groups", self.sequence_list.collapseAll)):
            button = QToolButton()
            button.setIcon(icons.icon(glyph))
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.add_tests_button.clicked.connect(self.add_tests)
        self.duplicate_button.clicked.connect(self.duplicate_steps)
        self.remove_button.clicked.connect(self.remove_steps)
        self.sequence_list.model().rowsMoved.connect(self._on_sequence_reordered)
        self.sequence_list.order_changed.connect(self._on_sequence_reordered)
        return frame

    def _build_options(self) -> QWidget:
        frame, layout = self._surface("Profile options")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Profile name")
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Description (optional)")
        self.description_edit.setMaximumHeight(78)
        self.config_edit = QLineEdit()
        self.config_edit.setReadOnly(True)
        self.config_edit.setPlaceholderText("Use local Run Tests configuration")
        self.config_button = QPushButton("Choose YAML file…")
        self.local_config_button = QPushButton("Use local configuration")
        self.local_config_button.setToolTip(
            "Do not embed YAML. Use the configuration selected in Run Tests when launching.")
        self.local_config_button.clicked.connect(self.use_local_configuration)
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Description"))
        layout.addWidget(self.description_edit)
        layout.addWidget(QLabel("Configuration YAML"))
        layout.addWidget(self.config_edit)
        layout.addWidget(self.config_button)
        layout.addWidget(self.local_config_button)

        layout.addWidget(QLabel("Execution"))
        self.repetitions = QSpinBox()
        self.repetitions.setRange(1, 10_000)
        self.rerun_failures = QSpinBox()
        self.rerun_failures.setRange(0, 100)
        for label, widget in (("Repetitions", self.repetitions),
                              ("Re-run failures", self.rerun_failures)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            row.addWidget(widget)
            layout.addLayout(row)
        self.stop_after_failure = QCheckBox("Stop after failure")
        self.save_logs = QCheckBox("Save complete logs")
        layout.addWidget(self.stop_after_failure)
        layout.addWidget(QLabel("Reports"))
        layout.addWidget(self.save_logs)
        layout.addStretch(1)

        self.config_button.clicked.connect(self.choose_config)
        self.name_edit.textChanged.connect(self._mark_dirty)
        self.description_edit.textChanged.connect(self._mark_dirty)
        self.repetitions.valueChanged.connect(self._options_changed)
        self.rerun_failures.valueChanged.connect(self._mark_dirty)
        self.stop_after_failure.toggled.connect(self._mark_dirty)
        self.save_logs.toggled.connect(self._mark_dirty)
        return frame

    def set_workspace_context(self, nodeids: list[str], config_path: str) -> None:
        self._available_nodeids = list(nodeids)
        self._workspace_config = config_path or ""
        self.add_tests_button.setEnabled(bool(nodeids))
        self._selection_changed()

    def refresh(self) -> None:
        current_id = self.current_profile().profile_id if self.current_profile() else ""
        self._profiles = self.store.list()
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected = -1
        for index, profile in enumerate(self._profiles):
            item = QListWidgetItem(
                f"{profile.name}\n{len(profile.sequence)} test"
                f"{'s' if len(profile.sequence) != 1 else ''}")
            item.setData(Qt.UserRole, profile.profile_id)
            self.profile_list.addItem(item)
            if profile.profile_id == current_id:
                selected = index
        self.profile_list.blockSignals(False)
        if self._profiles:
            self.profile_list.setCurrentRow(max(0, selected))
        else:
            self.new_profile()

    def current_profile(self) -> ExecutionProfile | None:
        row = self.profile_list.currentRow()
        return self._profiles[row] if 0 <= row < len(self._profiles) else None

    def _load_row(self, row: int) -> None:
        if not 0 <= row < len(self._profiles):
            return
        self._populate(self._profiles[row])

    def _populate(self, profile: ExecutionProfile) -> None:
        self._building = True
        self._configuration_text = profile.configuration_text
        self.config_edit.setProperty("fullPath", "")
        self.name_edit.setText(profile.name)
        self.description_edit.setPlainText(profile.description)
        self.config_edit.setText(profile.configuration_name)
        self._rebuild_sequence(profile.sequence, profile.step_overrides, profile.step_groups)
        self.repetitions.setValue(profile.execution.repetitions)
        self.rerun_failures.setValue(profile.execution.rerun_failures)
        self.stop_after_failure.setChecked(profile.execution.stop_after_failure)
        self.save_logs.setChecked(profile.reports.save_complete_logs)
        if not self._saving_refresh:
            self.undo_stack.clear()
        self._building = False
        self._initial_unsaved = False
        self._dirty = False
        self._history_state = self._editor_state()
        self._update_summary()

    def new_profile(self) -> None:
        profile = ExecutionProfile(
            name="New execution profile", sequence=[],
            configuration_name="", configuration_text="")
        self._profiles.append(profile)
        item = QListWidgetItem(f"{profile.name}\n0 steps · Unsaved")
        item.setData(Qt.UserRole, profile.profile_id)
        self.profile_list.addItem(item)
        self.profile_list.setCurrentRow(self.profile_list.count() - 1)
        self._initial_unsaved = True
        self._dirty = True
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    @undoable('Use local configuration')
    def use_local_configuration(self) -> None:
        self.config_edit.clear()
        self.config_edit.setProperty("fullPath", "")
        self._mark_dirty()
        self._selection_changed()

    def _profile_from_editor(self, new_id: bool = False) -> ExecutionProfile:
        current = self.current_profile()
        config_name = self.config_edit.text().strip()
        config_text = self._configuration_text if config_name else ""
        chosen = self.config_edit.property("fullPath") or ""
        if chosen and Path(chosen).is_file():
            config_name = Path(chosen).name
            config_text = Path(chosen).read_text(encoding="utf-8")
        sequence = self._flatten_sequence()
        return ExecutionProfile(
            profile_id=str(uuid.uuid4()) if new_id or current is None else current.profile_id,
            name=self.name_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
            sequence=sequence,
            step_overrides=self._step_patches(),
            step_groups=self._step_groups(),
            configuration_name=config_name,
            configuration_text=config_text,
            execution=ExecutionOptions(
                repetitions=self.repetitions.value(),
                rerun_failures=self.rerun_failures.value(),
                stop_after_failure=self.stop_after_failure.isChecked()),
            reports=ReportOptions(
                save_complete_logs=self.save_logs.isChecked()),
            source=current.source if current else "local",
        )

    def save_current(self) -> bool:
        try:
            profile = self._profile_from_editor()
            self.store.save(profile)
        except (OSError, UnicodeError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Could not save profile", str(exc))
            return False
        row = self.profile_list.currentRow()
        self._profiles[row] = profile
        self._dirty = False
        self._saving_refresh = True
        try:
            self.refresh()
        finally:
            self._saving_refresh = False
        self._initial_unsaved = False
        self.undo_stack.setClean()
        self._sync_history_dirty()
        self._show_notice("Profile saved.", warning=False)
        return True

    def save_as(self) -> None:
        try:
            profile = self._profile_from_editor(new_id=True)
            profile.name = f"{profile.name} copy"
            profile.source = "local"
            self.store.save(profile)
        except (OSError, UnicodeError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Could not save profile", str(exc))
            return
        self.refresh()

    def delete_current(self) -> None:
        profile = self.current_profile()
        if profile is None:
            return
        answer = QMessageBox.question(
            self, "Delete profile", f'Delete "{profile.name}" from this computer?')
        if answer == QMessageBox.Yes:
            self.store.delete(profile.profile_id)
            self.refresh()

    @undoable('Change profile YAML')
    def choose_config(self) -> None:
        start = self._workspace_config or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose profile configuration", start,
            "YAML files (*.yml *.yaml)")
        if path:
            self.config_edit.setText(Path(path).name)
            self.config_edit.setProperty("fullPath", path)
            self._mark_dirty()
            self._selection_changed()

    def add_tests(self) -> None:
        if not self._available_nodeids:
            self._show_notice("Load a workspace before adding tests.", warning=True)
            return
        dialog = AddTestsDialog(self._available_nodeids, self)
        dialog.tests_added.connect(self._append_tests)
        dialog.exec()

    def _step_items(self):
        items = []
        def visit(item):
            if item.data(0, NODEID_ROLE):
                items.append(item)
            else:
                for i in range(item.childCount()):
                    visit(item.child(i))
        for i in range(self.sequence_list.topLevelItemCount()):
            visit(self.sequence_list.topLevelItem(i))
        return items

    def _step_patches(self):
        return [copy.deepcopy(item.data(0, _OVERRIDES_ROLE) or {}) for item in self._step_items()]

    @undoable('Add tests')
    def _append_tests(self, nodeids: list[str]) -> None:
        # Chaque ajout reste un bloc : deux dossiers choisis separement ne
        # fusionnent pas et une occurrence repetee ne disparait jamais.
        self._add_sequence_groups(nodeids, [{} for _ in nodeids])
        self._mark_dirty()

    def _item_group_path(self, item, *, include_self=False):
        path = []
        parent = item if include_self else item.parent()
        while parent is not None:
            metadata = parent.data(0, _GROUP_ROLE)
            if metadata and not parent.data(0, NODEID_ROLE):
                path.append({key: copy.deepcopy(value) for key, value in metadata.items() if key != 'parents'})
            parent = parent.parent()
        return list(reversed(path))

    def _step_groups(self):
        return [group_entry(self._item_group_path(item)) for item in self._step_items()]

    def _step_item(self, nodeid, patch, label=None, group=None):
        item = QTreeWidgetItem()
        item.setData(0, NODEID_ROLE, nodeid)
        item.setData(0, _LABEL_ROLE, label or _short_nodeid(nodeid))
        item.setData(0, _OVERRIDES_ROLE, copy.deepcopy(patch))
        item.setData(0, _GROUP_ROLE, copy.deepcopy(group or {}))
        item.setIcon(0, icons.kind_icon(Kind.TEST))
        item.setToolTip(0, nodeid)
        # Steps may move between rows, but cannot become children of other steps.
        item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
        return item

    @staticmethod
    def _group_item(label, kind):
        item = QTreeWidgetItem()
        item.setData(0, _LABEL_ROLE, label)
        item.setData(0, _KIND_ROLE, kind.value)
        item.setIcon(0, icons.kind_icon(kind))
        item.setToolTip(0, label)
        return item

    def _add_sequence_groups(self, nodeids, patches, groups=None):
        groups = groups or [{} for _ in nodeids]
        root = self.sequence_list.invisibleRootItem()
        for start, end, metadata in profile_group_runs(nodeids, groups):
            patch_iterator = iter(patches[start:end])
            def make_node(node):
                if node.nodeid:
                    return self._step_item(node.nodeid, next(patch_iterator), node.name, metadata)
                item = self._group_item(node.name, node.kind)
                for child in node.children:
                    item.addChild(make_node(child))
                return item
            parent = root
            path = group_path(metadata)
            for level, group in enumerate(path):
                last = parent.child(parent.childCount() - 1) if parent.childCount() else None
                previous = last.data(0, _GROUP_ROLE) if last is not None else None
                if previous and not last.data(0, NODEID_ROLE) and previous['id'] == group['id']:
                    parent = last
                else:
                    item = self._group_item(group['name'], Kind.FOLDER)
                    item.setData(0, _GROUP_ROLE, group_entry(path[:level + 1]))
                    item.setIcon(0, icons.icon('mdi.folder', group['color']))
                    item.setToolTip(0, group['name'] + '\n' + group['description'])
                    parent.addChild(item)
                    parent = item
            if path:
                roots = build_sequence_tree(nodeids[start:end])
                while len(roots) == 1 and roots[0].children:
                    roots = roots[0].children
                for node in roots:
                    parent.addChild(make_node(node))
            else:
                for group in group_hierarchically(nodeids[start:end]):
                    if len(group.nodeids) == 1:
                        item = self._step_item(group.nodeids[0], next(patch_iterator))
                    else:
                        item = self._group_item(group.name, group.kind)
                        roots = build_sequence_tree(group.nodeids)
                        while len(roots) == 1 and roots[0].children:
                            roots = roots[0].children
                        for node in roots:
                            item.addChild(make_node(node))
                    root.addChild(item)

    def _rebuild_sequence(self, nodeids: list[str], patches=None, groups=None) -> None:
        self._reorder_timer.stop()
        if hasattr(self, 'sequence_clipboard'):
            self.sequence_clipboard.reset_visuals()
        if groups:
            known, aliases, normalized = {}, {}, []
            for entry in groups:
                path = group_path(entry)
                parents = []
                for group in path:
                    identifier = group['id']
                    context = tuple(parents)
                    if identifier in known and known[identifier] != context:
                        group['id'] = aliases.setdefault((identifier, context), str(uuid.uuid4()))
                    else:
                        known[identifier] = context
                    parents.append(group['id'])
                normalized.append(group_entry(path))
            groups = normalized
        old_ids, ranges = self._sequence_ranges()
        expanded = {(item.data(0, _LABEL_ROLE), tuple(old_ids[start:end]))
                    for item, start, end in ranges
                    if not self._building and item.isExpanded() and not item.data(0, NODEID_ROLE)}
        blocked = self.sequence_list.blockSignals(True)
        try:
            self.sequence_list.clear()
            self._add_sequence_groups(nodeids, patches or [{} for _ in nodeids], groups)
            new_ids, ranges = self._sequence_ranges()
            for item, start, end in ranges:
                if not item.data(0, NODEID_ROLE) and (
                        item.data(0, _LABEL_ROLE), tuple(new_ids[start:end])) in expanded:
                    item.setExpanded(True)
        finally:
            self.sequence_list.blockSignals(blocked)
        self._renumber()
        self._selection_changed()

    def _flatten_sequence(self) -> list[str]:
        return [item.data(0, NODEID_ROLE) for item in self._step_items()]

    def _selected_ranges(self):
        nodeids, ranges = self._sequence_ranges()
        selected = {id(item) for item in self.sequence_list.selectedItems()}
        def ancestor_selected(item):
            parent = item.parent()
            while parent is not None:
                if id(parent) in selected:
                    return True
                parent = parent.parent()
            return False
        return nodeids, [(item, start, end) for item, start, end in ranges
                         if id(item) in selected and not ancestor_selected(item)]

    def _sequence_ranges(self):
        nodeids, ranges = [], []
        def visit(item):
            start = len(nodeids)
            nodeid = item.data(0, NODEID_ROLE)
            if nodeid:
                nodeids.append(nodeid)
            else:
                for i in range(item.childCount()):
                    visit(item.child(i))
            if len(nodeids) > start:
                ranges.append((item, start, len(nodeids)))
        for i in range(self.sequence_list.topLevelItemCount()):
            visit(self.sequence_list.topLevelItem(i))
        return nodeids, ranges

    def _focus_range(self, start, count=1, *, edit=False):
        _, ranges = self._sequence_ranges()
        item = next((item for item, first, end in reversed(ranges)
                     if first == start and end == start + count
                     and (not edit or item.data(0, NODEID_ROLE))), None)
        if item is None and start < len(self._step_items()):
            item = self._step_items()[start]
        if item is None:
            return
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        blocked = self.sequence_list.blockSignals(not edit)
        self.sequence_list.setCurrentItem(item)
        self.sequence_list.blockSignals(blocked)
        self.sequence_list.scrollToItem(item)
        self._selection_changed()

    def _expand_groups(self):
        blocked = self.sequence_list.blockSignals(True)
        try:
            _, ranges = self._sequence_ranges()
            for item, _, _ in ranges:
                if not item.data(0, NODEID_ROLE):
                    item.setExpanded(True)
        finally:
            self.sequence_list.blockSignals(blocked)

    @undoable('Duplicate tests / groups')
    def duplicate_steps(self) -> None:
        nodeids, selected = self._selected_ranges()
        patches = self._step_patches()
        groups = self._step_groups()
        if not selected:
            return
        edit = len(selected) == 1 and bool(selected[0][0].data(0, NODEID_ROLE))
        for selected_item, start, end in sorted(selected, key=lambda row: row[1], reverse=True):
            nodeids[end:end] = nodeids[start:end]
            patches[end:end] = copy.deepcopy(patches[start:end])
            copied = copy.deepcopy(groups[start:end])
            identifiers = {}
            root_group = selected_item.data(0, _GROUP_ROLE) if not selected_item.data(0, NODEID_ROLE) else None
            if root_group:
                for i, entry in enumerate(copied):
                    path = group_path(entry)
                    inside = False
                    for group in path:
                        inside |= group['id'] == root_group['id']
                        if inside:
                            group['id'] = identifiers.setdefault(group['id'], str(uuid.uuid4()))
                    copied[i] = group_entry(path)
            groups[end:end] = copied
        self._rebuild_sequence(nodeids, patches, groups)
        _, start, end = min(selected, key=lambda row: row[1])
        self._focus_range(end, end - start, edit=edit)
        self._mark_dirty()

    @undoable('Remove tests / groups')
    def remove_steps(self) -> None:
        nodeids, selected = self._selected_ranges()
        removed = {i for _, start, end in selected for i in range(start, end)}
        if not removed:
            return
        patches = self._step_patches()
        groups = self._step_groups()
        self._rebuild_sequence([value for i, value in enumerate(nodeids) if i not in removed],
                               [value for i, value in enumerate(patches) if i not in removed],
                               [value for i, value in enumerate(groups) if i not in removed])
        self._mark_dirty()

    @undoable('Reorder sequence')
    def _move_step(self, direction):
        current = self.sequence_list.currentItem()
        if current is None:
            return
        parent = current.parent() or self.sequence_list.invisibleRootItem()
        index = parent.indexOfChild(current)
        destination = index + direction
        if not 0 <= destination < parent.childCount():
            return
        _, ranges = self._sequence_ranges()
        by_item = {id(item): (start, end) for item, start, end in ranges}
        start, end = by_item[id(current)]
        other_start, other_end = by_item[id(parent.child(destination))]
        edit = bool(current.data(0, NODEID_ROLE))
        nodeids, patches, groups = self._flatten_sequence(), self._step_patches(), self._step_groups()
        # Echange les plages contigues, avec leurs patches YAML, sans trier.
        left, middle, right = (other_start, start, end) if direction < 0 else (start, end, other_end)
        for values in (nodeids, patches, groups):
            values[left:right] = values[middle:right] + values[left:middle]
        target = other_start if direction < 0 else other_end - (end - start)
        self._rebuild_sequence(nodeids, patches, groups)
        self._focus_range(target, end - start, edit=edit)
        self._mark_dirty()

    def _on_sequence_reordered(self, *_args):
        # Le drop Qt doit finir avant de reconstruire ses index natifs.
        self._reorder_timer.start(0)

    @undoable('Move tests / groups', after_drop=True)
    def _settle_sequence_order(self):
        current = self.sequence_list.currentItem()
        _, ranges = self._sequence_ranges()
        selected = next(((start, end - start) for item, start, end in ranges
                         if item is current), None)
        nodeids, patches, groups = self._flatten_sequence(), self._step_patches(), self._step_groups()
        self._rebuild_sequence(nodeids, patches, groups)
        if selected:
            self._focus_range(*selected)
        self._mark_dirty()

    def _renumber(self):
        _, ranges = self._sequence_ranges()
        steps = self._step_items()
        try:
            base = self._base_configuration()
        except (OSError, UnicodeError, yaml.YAMLError, ProfileValidationError):
            base = {}
        warnings = []
        for step in steps:
            _, _, exceptions = configuration_details(base, self._item_group_path(step),
                                                      step.data(0, _OVERRIDES_ROLE) or {})
            warnings.append([exception_text(value) for value in exceptions])
        for item, start, end in ranges:
            label = item.data(0, _LABEL_ROLE) or ''
            number = f"{start + 1:02d}" if end - start == 1 else f"{start + 1:02d}–{end:02d}"
            metadata = item.data(0, _GROUP_ROLE) or {}
            exceptions = [text for row in warnings[start:end] for text in row]
            item.setData(0, EXCEPTION_ROLE, exceptions)
            count = sum(bool(row) for row in warnings[start:end])
            if item.data(0, NODEID_ROLE):
                suffix = ' · YAML exception' if count else (' · Custom YAML' if item.data(0, _OVERRIDES_ROLE) else '')
                tooltip = item.data(0, NODEID_ROLE)
            else:
                noun = ('parameter case' if end - start == 1 else 'parameter cases') if (
                    item.data(0, _KIND_ROLE) == Kind.TEST.value) else ('test' if end - start == 1 else 'tests')
                suffix = f" · {end - start} {noun}"
                if metadata.get('configuration_overrides'):
                    suffix += ' · Custom YAML'
                if count:
                    suffix += f' · {count} exception' + ('s' if count != 1 else '')
                tooltip = label + ('\n' + metadata['description'] if metadata else '')
            if exceptions:
                tooltip += '\n\nYAML exceptions:\n' + '\n'.join(dict.fromkeys(exceptions))
            item.setToolTip(0, tooltip)
            description = ('\n' + metadata['description']) if metadata and not item.data(0, NODEID_ROLE) and metadata['description'] else ''
            item.setText(0, f"{number}  {label}{suffix}{description}")

    def _base_configuration(self):
        chosen = self.config_edit.property("fullPath") or ""
        current = self.current_profile()
        if chosen:
            text = Path(chosen).read_text(encoding="utf-8-sig")
        elif self.config_edit.text() and current:
            text = self._configuration_text
        elif self._workspace_config:
            text = Path(self._workspace_config).read_text(encoding="utf-8-sig")
        else:
            return {}
        base = yaml.safe_load(text)
        if not isinstance(base, dict):
            raise ProfileValidationError("The YAML configuration must contain a mapping.")
        return base

    def _selection_changed(self):
        selected = self.sequence_list.selectedItems()
        single_test = len(selected) == 1 and bool(selected[0].data(0, NODEID_ROLE))
        named_group = len(selected) == 1 and not selected[0].data(0, NODEID_ROLE) and bool(selected[0].data(0, _GROUP_ROLE))
        self.parameters_button.setEnabled(single_test or named_group)
        self.effective_button.setEnabled(single_test)
        self.subgroup_button.setEnabled(named_group and len(self._item_group_path(selected[0], include_self=True)) < 20)
        self.group_button.setEnabled(bool(selected))
        self.group_button.setText("Edit group…" if named_group else "Create group…")
        def is_grouped(item):
            while item is not None:
                if item.data(0, _GROUP_ROLE):
                    return True
                item = item.parent()
            return False
        self.ungroup_button.setEnabled(any(is_grouped(item) for item in selected))
        self.duplicate_button.setEnabled(bool(selected))
        self.remove_button.setEnabled(bool(selected))
        if hasattr(self, 'sequence_clipboard'):
            self.sequence_clipboard.update_actions()

    def _edit_item(self, item, column=0):
        if item.data(0, NODEID_ROLE):
            self.edit_step_parameters()
        elif item.data(0, _GROUP_ROLE):
            self.edit_group()

    @undoable('Change YAML parameters')
    def edit_step_parameters(self):
        selected = self.sequence_list.selectedItems()
        if len(selected) != 1:
            return
        item = selected[0]
        is_test = bool(item.data(0, NODEID_ROLE))
        own = item.data(0, _GROUP_ROLE) or {}
        if not is_test and not own:
            return
        path = self._item_group_path(item)
        try:
            base = inherited_configuration(self._base_configuration(), path)
            patch = (item.data(0, _OVERRIDES_ROLE) or {}) if is_test else own.get('configuration_overrides', {})
            dialog = StepParametersDialog(item.data(0, NODEID_ROLE) if is_test else own['name'],
                                          base, patch, self, group=not is_test,
                                          inherited_label='Profile' if not path else 'Parent group')
        except (OSError, UnicodeError, yaml.YAMLError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Could not load YAML parameters", str(exc))
            return
        if dialog.exec() != QDialog.Accepted:
            return
        if is_test:
            item.setData(0, _OVERRIDES_ROLE, copy.deepcopy(dialog.patch))
        else:
            self._apply_group_yaml(own['id'], dialog.patch, replace=dialog.replace_existing.isChecked())
        self._mark_dirty()

    @staticmethod
    def _without_parameters(patch, paths):
        result = copy.deepcopy(patch)
        for path in paths:
            target, parents = result, []
            for key in path[:-1]:
                if not isinstance(target.get(key), dict):
                    break
                parents.append((target, key))
                target = target[key]
            else:
                target.pop(path[-1], None)
                for parent, key in reversed(parents):
                    if not parent[key]:
                        parent.pop(key)
        return result

    @undoable('Change group YAML')
    def _apply_group_yaml(self, identifier, patch, *, replace=False):
        groups, patches = self._step_groups(), self._step_patches()
        paths = list(dict(yaml_fields(patch)))
        for index, entry in enumerate(groups):
            path = group_path(entry)
            inside = False
            for group in path:
                if group['id'] == identifier:
                    group['configuration_overrides'] = copy.deepcopy(patch)
                    inside = True
                elif inside and replace:
                    group['configuration_overrides'] = self._without_parameters(group.get('configuration_overrides', {}), paths)
            if inside and replace:
                patches[index] = self._without_parameters(patches[index], paths)
            groups[index] = group_entry(path)
        self._rebuild_sequence(self._flatten_sequence(), patches, groups)
        self._focus_group(identifier)

    def _focus_group(self, identifier):
        _, ranges = self._sequence_ranges()
        item = next((item for item, _, _ in ranges if not item.data(0, NODEID_ROLE)
                     and (item.data(0, _GROUP_ROLE) or {}).get('id') == identifier), None)
        if item is not None:
            self.sequence_list.setCurrentItem(item)
            self.sequence_list.scrollToItem(item)

    @staticmethod
    def _common_group_path(paths):
        prefix = copy.deepcopy(paths[0]) if paths else []
        for path in paths[1:]:
            prefix = prefix[:next((i for i, (left, right) in enumerate(zip(prefix, path))
                                    if left['id'] != right['id']), min(len(prefix), len(path)))]
        return prefix

    def edit_group(self, checked=False, *, subgroup=False):
        nodeids, ranges = self._selected_ranges()
        indices = sorted({i for _, start, end in ranges for i in range(start, end)})
        if not indices:
            return
        selected = self.sequence_list.selectedItems()
        existing = selected[0].data(0, _GROUP_ROLE) if len(selected) == 1 and not selected[0].data(0, NODEID_ROLE) and not subgroup else None
        entries = self._step_groups()
        prefix = self._common_group_path([group_path(entries[i]) for i in indices])
        if existing:
            prefix = self._item_group_path(selected[0])
        elif subgroup:
            prefix = self._item_group_path(selected[0], include_self=True)
        if not existing and len(prefix) >= 20:
            self._show_notice("Groups may contain at most 20 nested levels.", warning=True)
            return
        nonadjacent = indices != list(range(indices[0], indices[-1] + 1))
        dialog = ProfileGroupDialog(len(indices), existing, will_reorder=nonadjacent, parent=self,
                                    parent_name=' / '.join(g['name'] for g in prefix) or 'Profile root')
        if dialog.exec() == QDialog.Accepted:
            self._apply_group(indices, dialog.metadata(), editing=bool(existing), parent_path=prefix)

    @undoable('Edit group')
    def _apply_group(self, indices, metadata, *, editing=False, parent_path=None):
        nodeids, patches, groups = self._flatten_sequence(), self._step_patches(), self._step_groups()
        if editing:
            own = {key: copy.deepcopy(value) for key, value in metadata.items() if key != 'parents'}
            for index, entry in enumerate(groups):
                path = group_path(entry)
                groups[index] = group_entry([own if group['id'] == metadata['id'] else group for group in path])
        else:
            selected = set(indices)
            prefix = parent_path if parent_path is not None else self._common_group_path([group_path(groups[i]) for i in indices])
            outside = {group['id'] for i, entry in enumerate(groups) if i not in selected for group in group_path(entry)}
            identifiers = {}
            for i in indices:
                path = group_path(groups[i])
                common = self._common_group_path([path, prefix])
                suffix = path[len(common):]
                for group in suffix:
                    if group['id'] in outside:
                        group['id'] = identifiers.setdefault(group['id'], str(uuid.uuid4()))
                groups[i] = group_entry(prefix + [copy.deepcopy(metadata)] + suffix)
            order = list(range(indices[0])) + indices + [i for i in range(indices[0], len(nodeids)) if i not in selected]
            nodeids, patches, groups = ([values[i] for i in order] for values in (nodeids, patches, groups))
        self._rebuild_sequence(nodeids, patches, groups)
        self._focus_group(metadata['id'])
        self._mark_dirty()

    @undoable('Ungroup tests')
    def ungroup_steps(self):
        nodeids, ranges = self._selected_ranges()
        groups = self._step_groups()
        for item, start, end in ranges:
            identifier = (item.data(0, _GROUP_ROLE) or {}).get('id') if not item.data(0, NODEID_ROLE) else None
            for index in range(start, end):
                path = group_path(groups[index])
                groups[index] = group_entry([group for group in path if group['id'] != identifier] if identifier else path[:-1])
        self._rebuild_sequence(nodeids, self._step_patches(), groups)
        self._mark_dirty()

    def _drop_details(self, target):
        _, ranges = self._selected_ranges()
        if not ranges:
            return None
        destination = self._item_group_path(target, include_self=True) if target is not None else []
        changed, sources, changes = [], set(), []
        try:
            base = self._base_configuration()
        except (OSError, UnicodeError, yaml.YAMLError, ProfileValidationError):
            base = {}
        groups, patches = self._step_groups(), self._step_patches()
        for item, start, end in ranges:
            ancestor = target
            while ancestor is not None:
                if ancestor is item:
                    return None
                ancestor = ancestor.parent()
            source = self._item_group_path(item)
            if [g['id'] for g in source] == [g['id'] for g in destination]:
                continue
            changed.extend(range(start, end))
            sources.add(' / '.join(g['name'] for g in source) or 'Profile root')
            for index in range(start, end):
                before = group_path(groups[index])
                after = destination + before[len(source):] if not item.data(0, NODEID_ROLE) else destination
                if len(after) > 20:
                    return None
                old = dict(yaml_fields(merge_configuration(inherited_configuration(base, before), patches[index])))
                new = dict(yaml_fields(merge_configuration(inherited_configuration(base, after), patches[index])))
                for key in old.keys() | new.keys():
                    if old.get(key) != new.get(key):
                        text = '.'.join(key) + ': ' + format_value(old.get(key)) + ' → ' + format_value(new.get(key))
                        if text not in changes:
                            changes.append(text)
        return dict(count=len(changed), sources=sorted(sources),
                    destination=' / '.join(g['name'] for g in destination) or 'Profile root', changes=changes)

    def _confirm_drop(self, target):
        details = self._drop_details(target)
        if details is None:
            return False
        if not details['count']:
            self._history_state = self._editor_state()
            return True
        dialog = ConfirmGroupMoveDialog(details['count'], details['sources'], details['destination'],
                                         details['changes'][:6], self)
        accepted = dialog.exec() == QDialog.Accepted
        if accepted:
            self._history_state = self._editor_state()
        return accepted

    def set_preview_readers(self, readers):
        self._preview_readers = list(readers)

    def show_effective_configuration(self):
        selected = self.sequence_list.selectedItems()
        if len(selected) != 1 or not selected[0].data(0, NODEID_ROLE):
            return
        item = selected[0]
        try:
            configuration, rows, _ = configuration_details(self._base_configuration(),
                self._item_group_path(item), item.data(0, _OVERRIDES_ROLE) or {})
        except (OSError, UnicodeError, yaml.YAMLError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, 'Could not preview test configuration', str(exc))
            return
        dialog = EffectiveConfigurationDialog(item.data(0, NODEID_ROLE), configuration, rows,
                                                self._preview_readers, self)
        dialog.exec()

    def _context_menu(self):
        selected = self.sequence_list.selectedItems()
        menu = QMenu(self)
        named = len(selected) == 1 and not selected[0].data(0, NODEID_ROLE) and bool(selected[0].data(0, _GROUP_ROLE))
        single = len(selected) == 1 and bool(selected[0].data(0, NODEID_ROLE))
        action = menu.addAction('Group YAML parameters…' if named else 'Test YAML parameters…', self.edit_step_parameters)
        action.setEnabled(named or single)
        action = menu.addAction('View effective YAML…', self.show_effective_configuration)
        action.setEnabled(single)
        menu.addSeparator()
        menu.addAction(self.sequence_clipboard.copy_action)
        menu.addAction(self.sequence_clipboard.paste_action)
        menu.addAction(self.sequence_clipboard.paste_into_action)
        menu.addSeparator()
        action = menu.addAction('Edit group…' if named else 'Create group…', self.edit_group)
        action.setEnabled(bool(selected))
        if named:
            menu.addAction('Create subgroup…', lambda: self.edit_group(subgroup=True))
        menu.addAction('Duplicate', self.duplicate_steps).setEnabled(bool(selected))
        menu.addAction('Move to…', self.move_to_group).setEnabled(bool(selected))
        menu.addAction('Ungroup', self.ungroup_steps).setEnabled(self.ungroup_button.isEnabled())
        menu.addAction('Remove', self.remove_steps).setEnabled(bool(selected))
        menu.addSeparator()
        menu.addAction(self.undo_action)
        menu.addAction(self.redo_action)
        return menu

    def _show_context_menu(self, position):
        item = self.sequence_list.itemAt(position)
        if item is not None and not item.isSelected():
            self.sequence_list.setCurrentItem(item)
        menu = self._context_menu()
        menu.exec(self.sequence_list.viewport().mapToGlobal(position))

    def copy_elements(self):
        self.sequence_clipboard.copy()

    @undoable('Paste elements')
    def paste_elements(self, *, into_group=False):
        self.sequence_clipboard.paste(into_group=into_group)

    def move_to_group(self):
        targets = [('Profile root', None)]
        _, ranges = self._sequence_ranges()
        for item, _, _ in ranges:
            if item.data(0, _GROUP_ROLE) and not item.data(0, NODEID_ROLE) and self._drop_details(item) is not None:
                targets.append((' / '.join(group['name'] for group in self._item_group_path(item, include_self=True)), item))
        dialog = MoveToGroupDialog(targets, self._drop_details, self)
        if dialog.exec() == QDialog.Accepted:
            self._move_to_target(dialog.target())

    @undoable('Move tests / groups')
    def _move_to_target(self, target):
        details = self._drop_details(target)
        if not details or not details['count']:
            return
        nodeids, selected = self._selected_ranges()
        patches, groups = self._step_patches(), self._step_groups()
        destination = self._item_group_path(target, include_self=True) if target is not None else []
        _, ranges = self._sequence_ranges()
        end = next((end for item, _, end in ranges if item is target), len(nodeids))
        moved = sorted({i for _, start, stop in selected for i in range(start, stop)})
        for item, start, stop in selected:
            source = self._item_group_path(item)
            for i in range(start, stop):
                path = group_path(groups[i])
                groups[i] = group_entry(destination + path[len(source):] if not item.data(0, NODEID_ROLE) else destination)
        moving = set(moved)
        remaining = [i for i in range(len(nodeids)) if i not in moving]
        insertion = sum(i < end for i in remaining)
        order = remaining[:insertion] + moved + remaining[insertion:]
        self._rebuild_sequence(*[[values[i] for i in order] for values in (nodeids, patches, groups)])
        self._focus_range(insertion, len(moved))
        self._mark_dirty()

    def _options_changed(self) -> None:
        self._mark_dirty()
        self._update_summary()

    def _mark_dirty(self, *_args) -> None:
        if self._building:
            return
        self._dirty = True
        self._renumber()
        self._update_summary()
        if self._edit_depth == 0 and not self._history_restoring:
            sender = self.sender()
            merge_key = id(sender) if sender in (self.name_edit, self.description_edit) else None
            self._record_edit(self._history_state, 'Edit profile options', merge_key)

    def _view_state(self):
        expanded, selected, current = [], [], None
        def visit(item, path):
            nonlocal current
            if item.isExpanded():
                expanded.append(path)
            if item.isSelected():
                selected.append(path)
            if item is self.sequence_list.currentItem():
                current = path
            for index in range(item.childCount()):
                visit(item.child(index), (*path, index))
        for index in range(self.sequence_list.topLevelItemCount()):
            visit(self.sequence_list.topLevelItem(index), (index,))
        return dict(expanded=expanded, selected=selected, current=current,
                    scroll=self.sequence_list.verticalScrollBar().value())

    def _editor_state(self):
        return dict(sequence=self._flatten_sequence(), patches=self._step_patches(), groups=self._step_groups(),
                    name=self.name_edit.text(), description=self.description_edit.toPlainText(),
                    config_name=self.config_edit.text(), config_text=self._configuration_text,
                    config_path=self.config_edit.property('fullPath') or '',
                    repetitions=self.repetitions.value(), reruns=self.rerun_failures.value(),
                    stop=self.stop_after_failure.isChecked(), logs=self.save_logs.isChecked(),
                    view=self._view_state())

    def _record_edit(self, before, label, merge_key=None):
        if self._building or self._history_restoring:
            return
        after = self._editor_state()
        self._history_state = copy.deepcopy(after)
        if before is None or {k: v for k, v in before.items() if k != 'view'} == {k: v for k, v in after.items() if k != 'view'}:
            return
        self.undo_stack.push(ProfileEdit(self, before, after, label, merge_key))

    def _restore_editor_state(self, state):
        self._history_restoring = True
        self._building = True
        try:
            self._configuration_text = state['config_text']
            self.name_edit.setText(state['name'])
            self.description_edit.setPlainText(state['description'])
            self.config_edit.setText(state['config_name'])
            self.config_edit.setProperty('fullPath', state['config_path'])
            self.repetitions.setValue(state['repetitions'])
            self.rerun_failures.setValue(state['reruns'])
            self.stop_after_failure.setChecked(state['stop'])
            self.save_logs.setChecked(state['logs'])
            self._rebuild_sequence(state['sequence'], state['patches'], state['groups'])
            view = state['view']
            def find(path):
                item = self.sequence_list.invisibleRootItem()
                for index in path:
                    item = item.child(index) if item is not None else None
                return item
            self.sequence_list.collapseAll()
            self.sequence_list.clearSelection()
            for path in view['expanded']:
                item = find(path)
                if item is not None:
                    item.setExpanded(True)
            if view['current'] is not None:
                self.sequence_list.setCurrentItem(find(view['current']))
            self.sequence_list.clearSelection()
            for path in view['selected']:
                item = find(path)
                if item is not None:
                    item.setSelected(True)
            self.sequence_list.verticalScrollBar().setValue(view['scroll'])
        finally:
            self._building = False
            self._history_restoring = False
        self._history_state = self._editor_state()
        self._selection_changed()
        self._update_summary()

    def _sync_history_dirty(self, *_):
        if not self._building:
            self._dirty = not self.undo_stack.isClean() or self._initial_unsaved
            self._update_summary()

    def _update_summary(self) -> None:
        count = len(self._flatten_sequence())
        groups = self.sequence_list.topLevelItemCount()
        total = count * self.repetitions.value()
        dirty = " · Unsaved changes" if self._dirty else ""
        grouped = (f" in {groups} group{'s' if groups != 1 else ''}"
                   if groups < count else "")
        self.summary.setText(
            f"{count} test{'s' if count != 1 else ''}{grouped} × "
            f"{self.repetitions.value()} repetition"
            f"{'s' if self.repetitions.value() != 1 else ''} = "
            f"{total} execution{'s' if total != 1 else ''}{dirty}")
        enabled = bool(count)
        self.run_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def export_current(self) -> None:
        try:
            profile = self._profile_from_editor()
            suggested = profile.name.replace(" ", "-") + EXTENSION
            path, _ = QFileDialog.getSaveFileName(
                self, "Export execution profile", suggested,
                f"Pytest Runner profiles (*{EXTENSION})")
            if not path:
                return
            target = export_profile(profile, path)
        except (OSError, UnicodeError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Could not export profile", str(exc))
            return
        self._show_notice(f"Profile exported to {target}", warning=False)

    def import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import execution profile", "",
            f"Pytest Runner profiles (*{EXTENSION})")
        if not path:
            return
        try:
            validation = inspect_profile(path, self._available_nodeids)
        except ProfileValidationError as exc:
            ErrorDialog.show_error(
                self, "Invalid execution profile",
                "The profile was rejected and was not added.", str(exc))
            return
        warning = ""
        if validation.missing_steps:
            preview = "\n".join(validation.missing_steps[:5])
            warning = (
                f"\n\n{len(validation.missing_steps)} sequence step(s) are "
                f"not present in the current workspace:\n{preview}")
        answer = QMessageBox.question(
            self, "Validated execution profile",
            "Security checks passed. The profile has not been executed.\n\n"
            f"Name: {validation.profile.name}\n"
            f"Sequence: {len(validation.profile.sequence)} steps\n"
            f"Configuration: {validation.profile.configuration_name}"
            f"{warning}\n\nImport this profile?")
        if answer != QMessageBox.Yes:
            return
        try:
            self.store.import_copy(path, self._available_nodeids)
        except (OSError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Could not import profile", str(exc))
            return
        self.refresh()
        self._show_notice(
            "Profile imported with compatibility warnings."
            if validation.has_warnings else "Profile imported and validated.",
            warning=validation.has_warnings)

    def open_in_run_tests(self) -> None:
        try:
            profile = self._profile_from_editor()
            # A local edit receives the same validation as an external file.
            from runner.domain.execution_profile import validate_profile
            validate_profile(profile)
        except (OSError, UnicodeError, ProfileValidationError) as exc:
            ErrorDialog.show_error(self, "Profile is not ready", str(exc))
            return
        missing = [nodeid for nodeid in profile.sequence
                   if self._available_nodeids and nodeid not in self._available_nodeids]
        if missing:
            ErrorDialog.show_error(
                self, "Profile is not compatible",
                f"{len(missing)} sequence step(s) are missing from this workspace.")
            return
        self.run_requested.emit(profile)

    def _show_notice(self, text: str, warning: bool) -> None:
        self.notice.setProperty("warning", warning)
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice_label.setText(text)
        self.notice.show()
