"""Embedded editor for reusable and portable execution profiles."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
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
from runner.domain.tree import build_tree
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel


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
        root.setContentsMargins(t.SPACE_6, t.SPACE_6, t.SPACE_6, t.SPACE_6)
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
        splitter.setSizes([220, 500, 320])
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
        self.sequence_list = QListWidget()
        self.sequence_list.setObjectName("ProfileSequence")
        self.sequence_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.sequence_list.setDefaultDropAction(Qt.MoveAction)
        self.sequence_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
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
        self.sequence_list.model().rowsMoved.connect(self._mark_dirty)
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
        self.config_button = QPushButton("Choose YAML file…")
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Description"))
        layout.addWidget(self.description_edit)
        layout.addWidget(QLabel("Configuration YAML"))
        layout.addWidget(self.config_edit)
        layout.addWidget(self.config_button)

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
            item = QListWidgetItem(f"{profile.name}\n{len(profile.sequence)} steps")
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
        self.sequence_list.clear()
        for index, nodeid in enumerate(profile.sequence, 1):
            item = QListWidgetItem(f"{index:>3}   {nodeid}")
            item.setData(Qt.UserRole, nodeid)
            self.sequence_list.addItem(item)
        self.repetitions.setValue(profile.execution.repetitions)
        self.rerun_failures.setValue(profile.execution.rerun_failures)
        self.stop_after_failure.setChecked(profile.execution.stop_after_failure)
        self.generate_allure.setChecked(profile.reports.generate_allure)
        self.save_logs.setChecked(profile.reports.save_complete_logs)
        self._building = False
        self._dirty = False
        self._update_summary()

    def new_profile(self) -> None:
        config_name, config_text = "", ""
        if self._workspace_config and Path(self._workspace_config).is_file():
            config_path = Path(self._workspace_config)
            config_name = config_path.name
            try:
                config_text = config_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                config_name, config_text = "", ""
        profile = ExecutionProfile(
            name="New execution profile", sequence=[],
            configuration_name=config_name, configuration_text=config_text)
        self._profiles.append(profile)
        item = QListWidgetItem(f"{profile.name}\n0 steps · Unsaved")
        item.setData(Qt.UserRole, profile.profile_id)
        self.profile_list.addItem(item)
        self.profile_list.setCurrentRow(self.profile_list.count() - 1)
        self._dirty = True
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _profile_from_editor(self, new_id: bool = False) -> ExecutionProfile:
        current = self.current_profile()
        config_name = self.config_edit.text().strip()
        config_text = current.configuration_text if current else ""
        chosen = self.config_edit.property("fullPath") or ""
        if chosen and Path(chosen).is_file():
            config_name = Path(chosen).name
            config_text = Path(chosen).read_text(encoding="utf-8")
        sequence = [self.sequence_list.item(index).data(Qt.UserRole)
                    for index in range(self.sequence_list.count())]
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
            QMessageBox.critical(self, "Could not save profile", str(exc))
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
            QMessageBox.critical(self, "Could not save profile", str(exc))
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
        for nodeid in nodeids:
            index = self.sequence_list.count() + 1
            item = QListWidgetItem(f"{index:>3}   {nodeid}")
            item.setData(Qt.UserRole, nodeid)
            self.sequence_list.addItem(item)
        self._mark_dirty()

    def duplicate_steps(self) -> None:
        rows = sorted(self.sequence_list.row(item)
                      for item in self.sequence_list.selectedItems())
        for row in rows:
            nodeid = self.sequence_list.item(row).data(Qt.UserRole)
            item = QListWidgetItem(nodeid)
            item.setData(Qt.UserRole, nodeid)
            self.sequence_list.insertItem(row + 1, item)
        self._renumber()
        self._mark_dirty()

    def remove_steps(self) -> None:
        for item in self.sequence_list.selectedItems():
            self.sequence_list.takeItem(self.sequence_list.row(item))
        self._renumber()
        self._mark_dirty()

    def _renumber(self) -> None:
        for index in range(self.sequence_list.count()):
            item = self.sequence_list.item(index)
            item.setText(f"{index + 1:>3}   {item.data(Qt.UserRole)}")

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
        count = self.sequence_list.count()
        total = count * self.repetitions.value()
        dirty = " · Unsaved changes" if self._dirty else ""
        self.summary.setText(
            f"{count} sequence steps × {self.repetitions.value()} repetitions "
            f"= {total} executions{dirty}")
        enabled = bool(count and self.config_edit.text().strip())
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
            QMessageBox.critical(self, "Could not export profile", str(exc))
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
            QMessageBox.critical(
                self, "Invalid execution profile",
                f"The profile was rejected and was not added.\n\n{exc}")
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
            QMessageBox.critical(self, "Could not import profile", str(exc))
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
            QMessageBox.warning(self, "Profile is not ready", str(exc))
            return
        missing = [nodeid for nodeid in profile.sequence
                   if self._available_nodeids and nodeid not in self._available_nodeids]
        if missing:
            QMessageBox.warning(
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
