"""Embedded editor for reusable and portable execution profiles."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
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
from runner.domain.tree import SequenceGroup, build_tree, group_hierarchically
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import ErrorDialog

# `sequence_list` is a tree: a group occupies one collapsed row by default,
# and expanding it reveals one child row per nodeid it collapsed -- each
# child can then be dragged out to any position, before or after any other
# row, just like a top-level one. NODEID_ROLE (shared with the source tree
# in `AddTestsDialog`) holds a leaf's own nodeid; only leaves carry it --
# a row with children gets its members from those children instead.
#
# `_LABEL_ROLE` holds a top-level row's label with no step number, so
# `_renumber()` can prefix the current position without recomputing it.
_LABEL_ROLE = Qt.UserRole + 1

_NOM_COMPTE = {
    Kind.TEST: "parameter cases",
    Kind.CLASS: "tests",
    Kind.MODULE: "tests",
    Kind.FOLDER: "tests",
}


def _label_for_group(groupe: SequenceGroup) -> str:
    if len(groupe.nodeids) == 1:
        return groupe.nodeids[0]
    quoi = _NOM_COMPTE.get(groupe.kind, "tests")
    return f"{groupe.name}   ({len(groupe.nodeids)} {quoi})"


def _short_nodeid(nodeid: str) -> str:
    """Garde la partie utile a l'ecran; le nodeid complet reste en tooltip."""
    parts = nodeid.replace("\\", "/").split("::")
    if len(parts) > 2:
        return "::".join(parts[-2:])
    return parts[-1]


def _group_item(groupe: SequenceGroup) -> QTreeWidgetItem:
    label = _label_for_group(groupe)
    item = QTreeWidgetItem([label])
    item.setData(0, _LABEL_ROLE, label)
    if len(groupe.nodeids) == 1:
        item.setData(0, NODEID_ROLE, groupe.nodeids[0])
        item.setToolTip(0, groupe.nodeids[0])
    else:
        for nodeid in groupe.nodeids:
            child = QTreeWidgetItem(item, [_short_nodeid(nodeid)])
            child.setData(0, NODEID_ROLE, nodeid)
            child.setToolTip(0, nodeid)
    return item


class AddTestsDialog(QDialog):
    """Test picker where each Add action creates one sequence occurrence."""

    tests_added = Signal(list)

    def __init__(self, nodeids: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add tests to sequence")
        self.resize(690, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        layout.setSpacing(t.SPACE_2)

        copy = QLabel(
            "Select tests and add them in sequence order. You can add the "
            "same test as many times as needed.")
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
        self.tree.setColumnHidden(1, True)
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
        self.add_again_button.clicked.connect(self._add)
        self.done_button.clicked.connect(self.accept)

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())
        if text.strip():
            self.tree.expandAll()

    def _add(self) -> None:
        selected = self.model.checked_nodeids()
        if selected:
            self.tests_added.emit(selected)
            self.model.set_all_checked(False)

    def _add_clicked_test(self, proxy_index) -> None:
        source_index = self.proxy.mapToSource(proxy_index).siblingAtColumn(0)
        nodeid = self.model.data(source_index, NODEID_ROLE)
        if nodeid:
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
        splitter.setSizes([190, 440, 270])
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
        self.sequence_list = QTreeWidget()
        self.sequence_list.setObjectName("ProfileSequence")
        self.sequence_list.setHeaderHidden(True)
        # Collapsed by default (a `QTreeWidgetItem` starts collapsed unless
        # told otherwise) -- expanding a group reveals its member rows so any
        # one of them can be dragged out to its own spot in the run order.
        self.sequence_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.sequence_list.setDefaultDropAction(Qt.MoveAction)
        self.sequence_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sequence_list.setAccessibleName("Ordered test sequence")
        self.sequence_list.setAccessibleDescription(
            "Expand a group, then drag a row to reorder it.")
        self.sequence_list.setToolTip(
            "Expand a group to see its tests. Drag a row to change the order.")
        layout.addWidget(self.sequence_list, 1)
        actions = QHBoxLayout()
        self.add_tests_button = QPushButton("Add tests")
        self.add_tests_button.setIcon(icons.icon("mdi.plus"))
        self.duplicate_button = QPushButton("Duplicate")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("Ghost")
        actions.addWidget(self.add_tests_button)
        actions.addWidget(self.duplicate_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.add_tests_button.clicked.connect(self.add_tests)
        self.duplicate_button.clicked.connect(self.duplicate_steps)
        self.remove_button.clicked.connect(self.remove_steps)
        self.sequence_list.model().rowsMoved.connect(self._on_sequence_reordered)
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
        self.generate_allure = QCheckBox("Generate Allure report")
        self.save_logs = QCheckBox("Save complete logs")
        layout.addWidget(self.stop_after_failure)
        layout.addWidget(QLabel("Reports"))
        layout.addWidget(self.generate_allure)
        layout.addWidget(self.save_logs)
        layout.addStretch(1)

        self.config_button.clicked.connect(self.choose_config)
        self.name_edit.textChanged.connect(self._mark_dirty)
        self.description_edit.textChanged.connect(self._mark_dirty)
        self.repetitions.valueChanged.connect(self._options_changed)
        self.rerun_failures.valueChanged.connect(self._mark_dirty)
        self.stop_after_failure.toggled.connect(self._mark_dirty)
        self.generate_allure.toggled.connect(self._mark_dirty)
        self.save_logs.toggled.connect(self._mark_dirty)
        return frame

    def set_workspace_context(self, nodeids: list[str], config_path: str) -> None:
        self._available_nodeids = list(nodeids)
        self._workspace_config = config_path or ""
        self.add_tests_button.setEnabled(bool(nodeids))

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
        self._rebuild_sequence(profile.sequence)
        self.repetitions.setValue(profile.execution.repetitions)
        self.rerun_failures.setValue(profile.execution.rerun_failures)
        self.stop_after_failure.setChecked(profile.execution.stop_after_failure)
        self.generate_allure.setChecked(profile.reports.generate_allure)
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

    def _profile_from_editor(self, new_id: bool = False) -> ExecutionProfile:
        current = self.current_profile()
        config_name = self.config_edit.text().strip()
        config_text = current.configuration_text if current and config_name else ""
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
            configuration_name=config_name,
            configuration_text=config_text,
            execution=ExecutionOptions(
                repetitions=self.repetitions.value(),
                rerun_failures=self.rerun_failures.value(),
                stop_after_failure=self.stop_after_failure.isChecked()),
            reports=ReportOptions(
                generate_allure=self.generate_allure.isChecked(),
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

    def add_tests(self) -> None:
        if not self._available_nodeids:
            self._show_notice("Load a workspace before adding tests.", warning=True)
            return
        dialog = AddTestsDialog(self._available_nodeids, self)
        dialog.tests_added.connect(self._append_tests)
        dialog.exec()

    def _append_tests(self, nodeids: list[str]) -> None:
        self._rebuild_sequence(self._flatten_sequence() + nodeids)
        self._mark_dirty()

    def _rebuild_sequence(self, nodeids: list[str]) -> None:
        self.sequence_list.clear()
        for groupe in group_hierarchically(nodeids):
            self.sequence_list.addTopLevelItem(_group_item(groupe))
        self._renumber()

    def _flatten_sequence(self) -> list[str]:
        """The sequence in its current visual order, tree depth notwithstanding.

        `sequence_list` only ever shows a fresh `group_hierarchically()` render
        of this same list -- the grouping is a display convenience, never the
        stored truth -- so reading it back just walks every row down to its
        leaves (a row with no children IS a leaf, in or out of a group) in the
        order they appear."""
        nodeids: list[str] = []

        def visiter(item: QTreeWidgetItem) -> None:
            if item.childCount() == 0:
                nodeids.append(item.data(0, NODEID_ROLE))
            else:
                for i in range(item.childCount()):
                    visiter(item.child(i))

        for i in range(self.sequence_list.topLevelItemCount()):
            visiter(self.sequence_list.topLevelItem(i))
        return nodeids

    def _sequence_ranges(self):
        """Same walk as `_flatten_sequence()`, but keeping each item's own
        (start, end) slice of the flattened list alongside it -- lets
        `duplicate_steps()`/`remove_steps()` act on whatever the user selected
        (a whole group or one of its members) without caring which it was."""
        nodeids: list[str] = []
        plages: list[tuple[QTreeWidgetItem, int, int]] = []

        def visiter(item: QTreeWidgetItem) -> None:
            debut = len(nodeids)
            if item.childCount() == 0:
                nodeids.append(item.data(0, NODEID_ROLE))
            else:
                for i in range(item.childCount()):
                    visiter(item.child(i))
            plages.append((item, debut, len(nodeids)))

        for i in range(self.sequence_list.topLevelItemCount()):
            visiter(self.sequence_list.topLevelItem(i))
        return nodeids, plages

    @staticmethod
    def _a_un_ancetre_selectionne(item: QTreeWidgetItem, selection: set) -> bool:
        parent = item.parent()
        while parent is not None:
            if parent in selection:
                return True
            parent = parent.parent()
        return False

    def _selected_ranges(self):
        """The (start, end) slice for each selected row, dropping any whose
        ancestor is also selected -- selecting a group and one of its own
        members should duplicate/remove that member once, not twice."""
        nodeids, plages = self._sequence_ranges()
        selection = set(self.sequence_list.selectedItems())
        return nodeids, [plage for plage in plages
                        if plage[0] in selection
                        and not self._a_un_ancetre_selectionne(plage[0], selection)]

    def duplicate_steps(self) -> None:
        nodeids, choisies = self._selected_ranges()
        for _, debut, fin in sorted(choisies, key=lambda p: p[1], reverse=True):
            nodeids[fin:fin] = nodeids[debut:fin]
        self._rebuild_sequence(nodeids)
        self._mark_dirty()

    def remove_steps(self) -> None:
        nodeids, choisies = self._selected_ranges()
        a_retirer = {i for _, debut, fin in choisies for i in range(debut, fin)}
        self._rebuild_sequence(
            [nodeid for i, nodeid in enumerate(nodeids) if i not in a_retirer])
        self._mark_dirty()

    def _on_sequence_reordered(self, *_args) -> None:
        # Deferred for the same reason the tree-view checkbox fix defers its
        # own model signal: this slot runs synchronously from inside Qt's own
        # internal-move drop handling, and rebuilding the tree in there would
        # re-enter that native code before it finishes unwinding. Waiting for
        # the next event-loop turn lets the drop finish first.
        QTimer.singleShot(0, self._settle_sequence_order)

    def _settle_sequence_order(self) -> None:
        try:
            self._rebuild_sequence(self._flatten_sequence())
        except RuntimeError:
            return
        self._mark_dirty()

    def _renumber(self) -> None:
        position = 1
        for index in range(self.sequence_list.topLevelItemCount()):
            item = self.sequence_list.topLevelItem(index)
            count = max(1, item.childCount())
            numero = str(position) if count == 1 else f"{position}-{position + count - 1}"
            item.setText(0, f"{numero:>5}   ↕  {item.data(0, _LABEL_ROLE)}")
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                child.setText(
                    0, f"{position + child_index:>5}   ↕  "
                       f"{_short_nodeid(child.data(0, NODEID_ROLE))}")
            position += count

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
