"""Embedded editor for reusable and portable execution profiles."""

from __future__ import annotations

import uuid
import copy
import yaml
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, Signal, QSize
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QComboBox,
    QToolButton,
    QStyledItemDelegate,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
)
from runner.domain.models import Kind
from runner.domain.tree import build_tree, build_sequence_tree, group_hierarchically
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import ErrorDialog

_OVERRIDES_ROLE = Qt.UserRole + 20
_ERROR_ROLE = Qt.UserRole + 21
_DRAFT_ROLE = Qt.UserRole + 22
_LABEL_ROLE = Qt.UserRole + 23
_EDITOR_ROLE = Qt.UserRole + 24
_KIND_ROLE = Qt.UserRole + 25


def _short_nodeid(nodeid: str) -> str:
    """Garde la partie utile a l'ecran; le nodeid complet reste en tooltip."""
    parts = nodeid.replace("\\", "/").split("::")
    if len(parts) > 2:
        return "::".join(parts[-2:])
    return parts[-1]


class StepDelegate(QStyledItemDelegate):
    """Des lignes compactes ; seul l'editeur YAML prend plusieurs lignes."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if not index.data(_EDITOR_ROLE):
            size.setHeight(max(30, size.height()))
        return size


class SequenceTree(QTreeWidget):
    order_changed = Signal()

    def __init__(self, can_move, parent=None):
        super().__init__(parent)
        self._can_move = can_move

    def dropEvent(self, event):
        if not self._can_move():
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
        self._dirty = False
        self._building = False
        self._reorder_timer = QTimer(self)
        self._reorder_timer.setSingleShot(True)
        self._reorder_timer.timeout.connect(self._settle_sequence_order)
        self._build_ui()
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
        self.sequence_list = SequenceTree(self._valid_editing, self)
        self.sequence_list.setObjectName("ProfileSequence")
        self.sequence_list.setProperty("variableRowHeights", True)
        self.sequence_list.setHeaderHidden(True)
        self.sequence_list.setItemDelegate(StepDelegate(self.sequence_list))
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
        self.sequence_list.setToolTip("Select a group to manage it, or a test to edit its YAML parameters.")
        self.sequence_list.currentItemChanged.connect(self._show_step_editor)
        self.sequence_list.itemExpanded.connect(self._expand_step_editor)
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
        self._refresh_step_editor()

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
        self.config_edit.setProperty("fullPath", "")
        self.name_edit.setText(profile.name)
        self.description_edit.setPlainText(profile.description)
        self.config_edit.setText(profile.configuration_name)
        self._rebuild_sequence(profile.sequence, profile.step_overrides)
        self.repetitions.setValue(profile.execution.repetitions)
        self.rerun_failures.setValue(profile.execution.rerun_failures)
        self.stop_after_failure.setChecked(profile.execution.stop_after_failure)
        self.save_logs.setChecked(profile.reports.save_complete_logs)
        self._building = False
        self._dirty = False
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
        self._dirty = True
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def use_local_configuration(self) -> None:
        self.config_edit.clear()
        self.config_edit.setProperty("fullPath", "")
        self._mark_dirty()
        self._refresh_step_editor()

    def _profile_from_editor(self, new_id: bool = False) -> ExecutionProfile:
        current = self.current_profile()
        config_name = self.config_edit.text().strip()
        config_text = current.configuration_text if current and config_name else ""
        chosen = self.config_edit.property("fullPath") or ""
        if chosen and Path(chosen).is_file():
            config_name = Path(chosen).name
            config_text = Path(chosen).read_text(encoding="utf-8")
        sequence = self._flatten_sequence()
        if any(item.data(0, _ERROR_ROLE) for item in self._step_items()):
            raise ProfileValidationError("Correct the highlighted step parameters before saving or running.")
        return ExecutionProfile(
            profile_id=str(uuid.uuid4()) if new_id or current is None else current.profile_id,
            name=self.name_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
            sequence=sequence,
            step_overrides=self._step_patches(),
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
        self.refresh()
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

    def choose_config(self) -> None:
        start = self._workspace_config or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose profile configuration", start,
            "YAML files (*.yml *.yaml)")
        if path:
            self.config_edit.setText(Path(path).name)
            self.config_edit.setProperty("fullPath", path)
            self._mark_dirty()
            self._refresh_step_editor()

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
            elif not item.data(0, _EDITOR_ROLE):
                for i in range(item.childCount()):
                    visit(item.child(i))
        for i in range(self.sequence_list.topLevelItemCount()):
            visit(self.sequence_list.topLevelItem(i))
        return items

    def _step_patches(self):
        return [copy.deepcopy(item.data(0, _OVERRIDES_ROLE) or {}) for item in self._step_items()]

    def _append_tests(self, nodeids: list[str]) -> None:
        # Chaque ajout reste un bloc : deux dossiers choisis separement ne
        # fusionnent pas et une occurrence repetee ne disparait jamais.
        self._add_sequence_groups(nodeids, [{} for _ in nodeids])
        self._mark_dirty()

    def _step_item(self, nodeid, patch, label=None):
        item = QTreeWidgetItem()
        item.setData(0, NODEID_ROLE, nodeid)
        item.setData(0, _LABEL_ROLE, label or _short_nodeid(nodeid))
        item.setData(0, _OVERRIDES_ROLE, copy.deepcopy(patch))
        item.setIcon(0, icons.kind_icon(Kind.TEST))
        item.setToolTip(0, nodeid)
        # Steps may move between rows, but cannot become children of other steps.
        item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
        child = QTreeWidgetItem(item)
        child.setData(0, _EDITOR_ROLE, True)
        child.setFlags(Qt.ItemIsEnabled)
        return item

    @staticmethod
    def _group_item(label, kind):
        item = QTreeWidgetItem()
        item.setData(0, _LABEL_ROLE, label)
        item.setData(0, _KIND_ROLE, kind.value)
        item.setIcon(0, icons.kind_icon(kind))
        item.setToolTip(0, label)
        return item

    def _add_sequence_groups(self, nodeids, patches):
        patches = iter(patches)
        def make_node(node):
            if node.nodeid:
                return self._step_item(node.nodeid, next(patches), node.name)
            item = self._group_item(node.name, node.kind)
            for child in node.children:
                item.addChild(make_node(child))
            return item
        for group in group_hierarchically(nodeids):
            if len(group.nodeids) == 1:
                item = self._step_item(group.nodeids[0], next(patches))
            else:
                item = self._group_item(group.name, group.kind)
                roots = build_sequence_tree(group.nodeids)
                while len(roots) == 1 and roots[0].children:
                    roots = roots[0].children
                for node in roots:
                    item.addChild(make_node(node))
            self.sequence_list.addTopLevelItem(item)

    def _rebuild_sequence(self, nodeids: list[str], patches=None) -> None:
        self._reorder_timer.stop()
        old_ids, ranges = self._sequence_ranges()
        expanded = {(item.data(0, _LABEL_ROLE), tuple(old_ids[start:end]))
                    for item, start, end in ranges
                    if not self._building and item.isExpanded() and not item.data(0, NODEID_ROLE)}
        blocked = self.sequence_list.blockSignals(True)
        try:
            self._parameter_controls = {}
            self.sequence_list.clear()
            self._add_sequence_groups(nodeids, patches or [{} for _ in nodeids])
            new_ids, ranges = self._sequence_ranges()
            for item, start, end in ranges:
                if not item.data(0, NODEID_ROLE) and (
                        item.data(0, _LABEL_ROLE), tuple(new_ids[start:end])) in expanded:
                    item.setExpanded(True)
        finally:
            self.sequence_list.blockSignals(blocked)
        self._renumber()

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
            if item.data(0, _EDITOR_ROLE):
                return
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

    def _expand_groups(self):
        blocked = self.sequence_list.blockSignals(True)
        try:
            _, ranges = self._sequence_ranges()
            for item, _, _ in ranges:
                if not item.data(0, NODEID_ROLE):
                    item.setExpanded(True)
        finally:
            self.sequence_list.blockSignals(blocked)

    def duplicate_steps(self) -> None:
        if not self._valid_editing():
            return
        nodeids, selected = self._selected_ranges()
        patches = self._step_patches()
        if not selected:
            return
        edit = len(selected) == 1 and bool(selected[0][0].data(0, NODEID_ROLE))
        for _, start, end in sorted(selected, key=lambda row: row[1], reverse=True):
            nodeids[end:end] = nodeids[start:end]
            patches[end:end] = copy.deepcopy(patches[start:end])
        self._rebuild_sequence(nodeids, patches)
        _, start, end = min(selected, key=lambda row: row[1])
        self._focus_range(end, end - start, edit=edit)
        self._mark_dirty()

    def remove_steps(self) -> None:
        nodeids, selected = self._selected_ranges()
        removed = {i for _, start, end in selected for i in range(start, end)}
        if not removed:
            return
        if any(item.data(0, _ERROR_ROLE) for i, item in enumerate(self._step_items()) if i not in removed):
            self._valid_editing()
            return
        patches = self._step_patches()
        self._rebuild_sequence([value for i, value in enumerate(nodeids) if i not in removed],
                               [value for i, value in enumerate(patches) if i not in removed])
        self._mark_dirty()

    def _move_step(self, direction):
        if not self._valid_editing():
            return
        current = self.sequence_list.currentItem()
        if current is None or current.data(0, _EDITOR_ROLE):
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
        nodeids, patches = self._flatten_sequence(), self._step_patches()
        # Echange les plages contigues, avec leurs patches YAML, sans trier.
        left, middle, right = (other_start, start, end) if direction < 0 else (start, end, other_end)
        for values in (nodeids, patches):
            values[left:right] = values[middle:right] + values[left:middle]
        target = other_start if direction < 0 else other_end - (end - start)
        self._rebuild_sequence(nodeids, patches)
        self._focus_range(target, end - start, edit=edit)
        self._mark_dirty()

    def _on_sequence_reordered(self, *_args):
        # Le drop Qt doit finir avant de reconstruire ses index natifs.
        self._reorder_timer.start(0)

    def _settle_sequence_order(self):
        current = self.sequence_list.currentItem()
        _, ranges = self._sequence_ranges()
        selected = next(((start, end - start) for item, start, end in ranges
                         if item is current), None)
        nodeids, patches = self._flatten_sequence(), self._step_patches()
        self._rebuild_sequence(nodeids, patches)
        if selected:
            self._focus_range(*selected)
        self._mark_dirty()

    @staticmethod
    def _yaml_fields(mapping, prefix=()):
        if len(prefix) > 30:
            raise ProfileValidationError("The YAML configuration is nested too deeply.")
        for key, value in mapping.items():
            if not isinstance(key, str):
                continue
            path = (*prefix, key)
            if isinstance(value, dict) and value:
                yield from ExecutionProfilesPage._yaml_fields(value, path)
            else:
                yield path, value

    def _renumber(self):
        _, ranges = self._sequence_ranges()
        for item, start, end in ranges:
            label = item.data(0, _LABEL_ROLE) or ''
            number = f"{start + 1:02d}" if end - start == 1 else f"{start + 1:02d}–{end:02d}"
            if item.data(0, NODEID_ROLE):
                suffix = ' · Custom YAML' if item.data(0, _OVERRIDES_ROLE) else ''
            else:
                noun = ('parameter case' if end - start == 1 else 'parameter cases') if (
                    item.data(0, _KIND_ROLE) == Kind.TEST.value) else ('test' if end - start == 1 else 'tests')
                suffix = f" · {end - start} {noun}"
            item.setText(0, f"{number}  {label}{suffix}")

    def _base_configuration(self):
        chosen = self.config_edit.property("fullPath") or ""
        current = self.current_profile()
        if chosen:
            text = Path(chosen).read_text(encoding="utf-8-sig")
        elif self.config_edit.text() and current:
            text = current.configuration_text
        elif self._workspace_config:
            text = Path(self._workspace_config).read_text(encoding="utf-8-sig")
        else:
            return {}
        base = yaml.safe_load(text)
        if not isinstance(base, dict):
            raise ProfileValidationError("The YAML configuration must contain a mapping.")
        return base

    def _expand_step_editor(self, item):
        if not self._building and item.data(0, NODEID_ROLE):
            self.sequence_list.setCurrentItem(item)
            self._show_step_editor(item)

    def _refresh_step_editor(self):
        self._show_step_editor(self.sequence_list.currentItem())

    def _show_step_editor(self, item, previous=None):
        if self._building:
            return
        self.sequence_list.blockSignals(True)
        for step in self._step_items():
            if step is not item:
                step.setExpanded(False)
                self.sequence_list.removeItemWidget(step.child(0), 0)
        self.sequence_list.blockSignals(False)
        self._parameter_controls = {}
        if item is None or not item.data(0, NODEID_ROLE):
            return
        panel = QFrame()
        panel.setObjectName("Surface")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        heading = QHBoxLayout()
        title = QLabel("YAML parameters · this occurrence")
        heading.addWidget(title, 1)
        reset = QToolButton()
        reset.setIcon(icons.icon("mdi.restore"))
        reset.setToolTip("Reset this step to the profile configuration")
        reset.clicked.connect(lambda: self._reset_step(item))
        heading.addWidget(reset)
        layout.addLayout(heading)
        note = QLabel("Unchecked parameters inherit the profile configuration.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        try:
            base = self._base_configuration()
        except (OSError, UnicodeError, yaml.YAMLError, ProfileValidationError) as exc:
            base = {}
            note.setText(f"Configuration unavailable: {exc}")
        patch = item.data(0, _OVERRIDES_ROLE) or {}
        try:
            fields = dict(self._yaml_fields(base))
        except ProfileValidationError as exc:
            fields = {}
            note.setText(str(exc))
        custom = dict(self._yaml_fields(patch))
        fields.update({key: value for key, value in custom.items() if key not in fields})
        drafts = item.data(0, _DRAFT_ROLE) or {}
        reader_fields = [path for path in fields if path[-1].lower() in ("reader", "lecteur")]
        managed_reader = min(reader_fields, key=len) if reader_fields else None
        search = QLineEdit()
        search.setPlaceholderText("Find a YAML parameter…")
        search.setClearButtonEnabled(True)
        if len(fields) > 6:
            layout.addWidget(search)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self._parameter_controls = {}
        cells = []
        for index, (path, original) in enumerate(fields.items()):
            cell = QWidget()
            box = QVBoxLayout(cell)
            box.setContentsMargins(0, 0, 0, 0)
            toggle = QCheckBox(" · ".join(path))
            toggle.setToolTip("Customize this YAML parameter for this occurrence only")
            toggle.setChecked(path in custom or path in drafts)
            box.addWidget(toggle)
            value = custom.get(path, original)
            if isinstance(original, bool):
                editor = QComboBox()
                editor.addItems(["false", "true"])
                editor.setCurrentIndex(int(bool(value)))
            elif isinstance(original, str) and original.upper() in ("T0", "T1") and "proto" in path[-1].lower():
                editor = QComboBox()
                editor.setEditable(True)
                editor.addItems(["T0", "T1"])
                editor.setCurrentText(str(value))
            else:
                editor = QLineEdit(self._format_value(value))
            editor.setAccessibleName(" · ".join(path))
            editor.setEnabled(toggle.isChecked())
            if path in drafts:
                editor.setText(drafts[path]) if isinstance(editor, QLineEdit) else editor.setCurrentText(drafts[path])
            if path == managed_reader:
                toggle.setEnabled(False)
                editor.setEnabled(False)
            box.addWidget(editor)
            origin = QLabel("Inherited from profile" if path not in custom else
                            f"Profile: {self._format_value(original)}")
            origin.setObjectName("Muted")
            origin.setWordWrap(True)
            if path == managed_reader:
                origin.setText("Assigned by the readers selected in Run Tests")
            box.addWidget(origin)
            error = QLabel()
            error.setObjectName("ProfileParameterError")
            error.setWordWrap(True)
            error.hide()
            if path in drafts:
                error.setText("Invalid value. Correct it or uncheck this parameter.")
                error.show()
            box.addWidget(error)
            self._parameter_controls[path] = (toggle, editor)
            callback = lambda *args, p=path, o=original, c=toggle, e=editor, n=origin, err=error: self._change_parameter(item, p, o, c, e, n, err)
            toggle.toggled.connect(callback)
            if isinstance(editor, QComboBox):
                editor.currentTextChanged.connect(callback)
            else:
                editor.textChanged.connect(callback)
            grid.addWidget(cell, index // 2, index % 2)
            cells.append((path, cell))
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        def filter_fields(text):
            visible = 0
            for path, cell in cells:
                matches = text.casefold() in ".".join(path).casefold()
                cell.setVisible(matches)
                if matches:
                    grid.addWidget(cell, visible // 2, visible % 2)
                    visible += 1
            layout.invalidate()
            child.setSizeHint(0, QSize(0, panel.sizeHint().height()))
        search.textChanged.connect(filter_fields)
        if not fields:
            choose = QPushButton("Choose configuration YAML…")
            choose.clicked.connect(self.choose_config)
            layout.addWidget(choose)
        child = item.child(0)
        child.setSizeHint(0, QSize(0, panel.sizeHint().height()))
        self.sequence_list.setItemWidget(child, 0, panel)
        self.sequence_list.blockSignals(True)
        item.setExpanded(True)
        self.sequence_list.blockSignals(False)

    @staticmethod
    def _format_value(value):
        if isinstance(value, str):
            return value
        return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).split("\n...")[0].strip()

    def _change_parameter(self, item, path, original, toggle, editor, origin, error):
        editor.setEnabled(toggle.isChecked())
        patch = copy.deepcopy(item.data(0, _OVERRIDES_ROLE) or {})
        errors = set(item.data(0, _ERROR_ROLE) or [])
        drafts = dict(item.data(0, _DRAFT_ROLE) or {})
        try:
            if toggle.isChecked():
                text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
                value = text if isinstance(original, str) else yaml.safe_load(text)
                if original is not None and type(value) is not type(original):
                    raise ValueError(f"Expected {type(original).__name__}, using YAML syntax.")
                from runner.domain.execution_profile import validate_step_overrides
                validate_step_overrides([{path[-1]: value}], 1)
                target = patch
                for key in path[:-1]:
                    target = target.setdefault(key, {})
                target[path[-1]] = value
                origin.setText(f"Profile: {self._format_value(original)}")
            else:
                target = patch
                parents = []
                for key in path[:-1]:
                    parents.append((target, key))
                    target = target.get(key, {})
                target.pop(path[-1], None)
                for parent, key in reversed(parents):
                    if not parent.get(key):
                        parent.pop(key, None)
                editor.blockSignals(True)
                if isinstance(editor, QComboBox):
                    editor.setCurrentText(self._format_value(original))
                else:
                    editor.setText(self._format_value(original))
                editor.blockSignals(False)
                origin.setText("Inherited from profile")
            errors.discard(path)
            drafts.pop(path, None)
            error.hide()
            item.setData(0, _OVERRIDES_ROLE, patch)
        except (ValueError, yaml.YAMLError) as exc:
            errors.add(path)
            drafts[path] = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
            error.setText(str(exc))
            error.show()
        item.setData(0, _ERROR_ROLE, list(errors))
        item.setData(0, _DRAFT_ROLE, drafts)
        child = item.child(0)
        panel = self.sequence_list.itemWidget(child, 0)
        if panel:
            child.setSizeHint(0, QSize(0, panel.sizeHint().height()))
        self._mark_dirty()

    def _reset_step(self, item):
        item.setData(0, _OVERRIDES_ROLE, {})
        item.setData(0, _ERROR_ROLE, [])
        item.setData(0, _DRAFT_ROLE, {})
        self._mark_dirty()
        self._show_step_editor(item)

    def _valid_editing(self):
        if any(item.data(0, _ERROR_ROLE) for item in self._step_items()):
            self._show_notice("Correct invalid step parameters before moving or duplicating steps.", warning=True)
            return False
        return True

    def _options_changed(self) -> None:
        self._mark_dirty()
        self._update_summary()

    def _mark_dirty(self, *_args) -> None:
        if self._building:
            return
        self._dirty = True
        self._renumber()
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
