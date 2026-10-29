"""Dialogues des profils : modifications locales jusqu'a Apply / Create."""

from __future__ import annotations

import copy
import uuid

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from runner.domain.execution_profile import ProfileValidationError, validate_step_overrides
from runner.ui import icons, tokens as t


def yaml_fields(mapping, prefix=()):
    if len(prefix) > 30:
        raise ProfileValidationError("The YAML configuration is nested too deeply.")
    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        path = (*prefix, key)
        if isinstance(value, dict) and value:
            yield from yaml_fields(value, path)
        else:
            yield path, value


def format_value(value):
    if isinstance(value, str):
        return value
    return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).split("\n...")[0].strip()


class StepParametersDialog(QDialog):
    def __init__(self, nodeid, base, patch, parent=None, *, group=False, inherited_label="Profile", patches=None, origins=None):
        super().__init__(parent)
        self.setWindowTitle("Group YAML parameters" if group else "Test YAML parameters")
        self.resize(860, 640)
        self.patch = copy.deepcopy(patch)
        self.controls = {}
        self.changed_paths = set()
        self._changed_values = {}
        self._batch = patches is not None
        self._scope = 'group' if group else ('test selection' if self._batch else 'test')
        self._batch_initializing = True
        self._errors = set()
        self._hints = {}
        self._references = {}
        self._defined_by = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        title = QLabel(nodeid.split("::")[-1])
        title.setTextFormat(Qt.PlainText)
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        root.addWidget(title)
        location = QLabel(nodeid)
        location.setTextFormat(Qt.PlainText)
        location.setObjectName("Muted")
        location.setWordWrap(True)
        root.addWidget(location)
        note = QLabel("Set defaults for this group and its subgroups. A test with its own value keeps that value."
                      if group else "The value on the right is what this test will use. Choose Custom value to change it here. "
                      "The original YAML file stays unchanged.")
        note.setWordWrap(True)
        if self._batch:
            self.setWindowTitle('Test selection YAML parameters')
            note.setText(f'Edit {len(patches)} test occurrences. Only parameters changed here are applied to all of them. '
                         'Mixed values stay unchanged until you choose a value. Group parameters and the original YAML file stay unchanged.')
        root.addWidget(note)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a YAML parameter or origin…")
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 1)
        self.custom_only = QCheckBox('Custom values only')
        self.custom_only.setToolTip('Show explicit overrides on this test or group. Mixed fields are included if any selected test overrides them. '
                                    'Values inherited from groups are hidden.')
        filters.addWidget(self.custom_only)
        root.addLayout(filters)
        scroll = QScrollArea()
        self._parameter_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 12, 12, 12)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(14)
        for column, text in enumerate(('Parameter', 'Use value from', 'Group default' if group else 'Value used')):
            header = QLabel(text)
            header.setObjectName('Muted')
            grid.addWidget(header, 0, column)
        fields = dict(yaml_fields(base))
        self._inherited_paths = set(fields)
        custom = dict(yaml_fields(patch))
        if self._batch:
            for value in patches:
                for path, original in yaml_fields(value):
                    custom.setdefault(path, original)
        batch_values = [dict(yaml_fields(value)) for value in patches] if self._batch else []
        fields.update({path: value for path, value in custom.items() if path not in fields})
        self._has_fields = bool(fields)
        self._initial_custom_paths = set(custom)
        self._origins = {path: (origins or {}).get(path, inherited_label) for path in fields}
        readers = [path for path in fields if path[-1].lower() in ("reader", "lecteur")]
        managed = min(readers, key=len) if readers else None
        self._rows = []
        for index, (path, original) in enumerate(fields.items()):
            label = QLabel(" · ".join(path))
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            mode = QComboBox()
            origin = self._origins[path]
            mode.addItems(["Profile value" if origin == "Profile" else "Inherited value", "Custom value"])
            mode.setAccessibleName("Value source for " + ".".join(path))
            mode.setCurrentIndex(int(path in custom))
            value = custom.get(path, original)
            if isinstance(original, bool):
                editor = QComboBox()
                editor.addItems(["false", "true"])
                editor.setCurrentIndex(int(bool(value)))
            elif isinstance(original, str) and "proto" in path[-1].lower():
                editor = QComboBox()
                editor.setEditable(True)
                editor.addItems(["T0", "T1"])
                editor.setCurrentText(str(value))
            else:
                editor = QLineEdit(format_value(value))
            editor.setAccessibleName("Value for " + ".".join(path))
            editor.setEnabled(bool(mode.currentIndex()))
            reference = ('Without this customization: ' + format_value(original) + ' — ' + origin
                         if path in self._inherited_paths else 'Without this customization: not defined')
            defined_by = 'Defined by: ' + origin if path in self._inherited_paths else 'Not defined in the inherited configuration'
            if path == managed:
                reference = defined_by = 'Assigned by the readers selected in Run Tests'
            hint = QLabel(reference if mode.currentIndex() == 1 else defined_by)
            hint.setTextFormat(Qt.PlainText)
            hint.setObjectName("Muted")
            hint.setWordWrap(True)
            self._hints[path] = hint
            self._references[path] = reference
            self._defined_by[path] = defined_by
            error = QLabel()
            error.setTextFormat(Qt.PlainText)
            error.setStyleSheet("color: #e65770;")
            error.setWordWrap(True)
            error.hide()
            box = QWidget()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(editor)
            layout.addWidget(hint)
            layout.addWidget(error)
            grid.addWidget(label, index + 1, 0, Qt.AlignTop)
            grid.addWidget(mode, index + 1, 1, Qt.AlignTop)
            grid.addWidget(box, index + 1, 2)
            if path == managed:
                mode.setEnabled(False)
                editor.setEnabled(False)
                mode.setToolTip("The reader is chosen in Run Tests, not per test.")
            self.controls[path] = mode, editor
            self._rows.append((path, label, mode, box))
            callback = lambda *args, p=path, o=original, m=mode, e=editor, err=error: self._change(p, o, m, e, err)
            mode.currentIndexChanged.connect(callback)
            if isinstance(editor, QComboBox):
                editor.currentTextChanged.connect(callback)
            else:
                editor.textChanged.connect(callback)
            if self._batch and path != managed:
                first = batch_values[0]
                mixed = any((path in value) != (path in first) or
                            (path in value and (type(value[path]) is not type(first[path]) or value[path] != first[path]))
                            for value in batch_values[1:])
                if mixed:
                    mode.blockSignals(True)
                    mode.addItem('Mixed values — unchanged')
                    mode.setCurrentIndex(2)
                    mode.blockSignals(False)
                    editor.setEnabled(False)
                    hint.setText('Settings differ across these tests. They stay unchanged until you choose a source.\n' + reference)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(len(fields) + 1, 1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.empty = QLabel("No matching parameters.")
        self.empty.setObjectName("Muted")
        self.empty.setVisible(not fields)
        root.addWidget(self.empty)
        self.validation_summary = QLabel()
        self.validation_summary.setWordWrap(True)
        self.validation_summary.setObjectName('Muted')
        self.validation_summary.linkActivated.connect(self._show_invalid_parameter)
        self.validation_summary.hide()
        root.addWidget(self.validation_summary)
        self.replace_existing = QCheckBox("Apply custom parameters to all tests, replacing their overrides")
        self.replace_existing.setToolTip("Only parameters customized here are replaced. Other parameters are preserved.")
        if group:
            root.addWidget(self.replace_existing)
        else:
            self.replace_existing.hide()
        footer = QHBoxLayout()
        self.reset_button = QPushButton("Reset all to inherited values" if group or inherited_label != "Profile"
                                       else "Reset all to profile values")
        self.reset_button.setAutoDefault(False)
        self.reset_button.clicked.connect(self.reset)
        footer.addWidget(self.reset_button)
        footer.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.Apply)
        self.apply_button.setObjectName("Primary")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        root.addLayout(footer)
        if not fields:
            self.empty.setText("No YAML parameters available. Choose a profile YAML file "
                               "or load a local configuration first.")
            self.empty.setWordWrap(True)
            self.apply_button.setEnabled(False)
            self.reset_button.setEnabled(False)
        self.search.textChanged.connect(self._filter_fields)
        self.custom_only.toggled.connect(self._filter_fields)
        self._batch_initializing = False
        self.changed_paths.clear()
        self.custom_only.setEnabled(bool(fields))
        self._filter_fields()

    def _filter_fields(self, *_):
        if self._batch_initializing:
            return
        any_visible = False
        customized = 0
        hidden_errors = 0
        text = self.search.text().casefold()
        for path, *widgets in self._rows:
            mode = self.controls[path][0]
            custom = mode.currentIndex() == 1 or (mode.currentIndex() == 2 and path in self._initial_custom_paths)
            customized += int(custom)
            visible = (text in ('.'.join(path) + ' ' + self._origins[path]).casefold()
                       and (not self.custom_only.isChecked() or custom))
            any_visible |= visible
            hidden_errors += int(path in self._errors and not visible)
            for widget in widgets:
                widget.setVisible(visible)
        if self._has_fields:
            self.empty.setText(f'No custom parameters on this {self._scope}. Turn off Custom values only to see inherited values.'
                               if self.custom_only.isChecked() and not customized else 'No parameters match these filters.')
            self.empty.setWordWrap(True)
        self.empty.setVisible(not any_visible)
        self.validation_summary.setText(f'{hidden_errors} invalid parameter' + ('s are' if hidden_errors != 1 else ' is')
                                        + ' hidden by these filters. '
                                        + f'<a href="show" style="color: {t.ACCENT};">Show the first invalid parameter</a>.')
        self.validation_summary.setVisible(bool(hidden_errors))

    def _show_invalid_parameter(self, *_):
        if not self._errors:
            return
        self.search.clear()
        self.custom_only.setChecked(False)
        path = next(path for path in self.controls if path in self._errors)
        editor = self.controls[path][1]
        self._parameter_scroll.ensureWidgetVisible(editor)
        editor.setFocus()

    def _change(self, path, original, mode, editor, error):
        if self._batch and mode.currentIndex() == 2:
            self.changed_paths.discard(path)
            self._changed_values.pop(path, None)
            self._errors.discard(path)
            editor.setEnabled(False)
            error.hide()
            self.apply_button.setEnabled(not self._errors)
            self._hints[path].setText('Settings differ across these tests. They stay unchanged until you choose a source.\n'
                                      + self._references[path])
            self._filter_fields()
            return
        if self._batch and not self._batch_initializing:
            self.changed_paths.add(path)
        custom = mode.currentIndex() == 1
        self._hints[path].setText(self._references[path] if custom else self._defined_by[path])
        editor.setEnabled(custom)
        try:
            if custom:
                text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
                value = text if isinstance(original, str) else yaml.safe_load(text)
                if original is not None and type(value) is not type(original):
                    raise ValueError(f"Expected {type(original).__name__}, using YAML syntax.")
                validate_step_overrides([{path[-1]: value}], 1)
                self._changed_values[path] = copy.deepcopy(value)
                target = self.patch
                for key in path[:-1]:
                    if not isinstance(target.get(key), dict):
                        target[key] = {}
                    target = target[key]
                target[path[-1]] = value
            else:
                target = self.patch
                parents = []
                for key in path[:-1]:
                    if not isinstance(target.get(key), dict):
                        break
                    parents.append((target, key))
                    target = target[key]
                else:
                    target.pop(path[-1], None)
                    for parent, key in reversed(parents):
                        if not parent.get(key):
                            parent.pop(key, None)
                editor.blockSignals(True)
                if isinstance(editor, QComboBox):
                    if path in self._inherited_paths:
                        editor.setCurrentText(format_value(original))
                    else:
                        editor.setCurrentIndex(-1)
                else:
                    editor.setText(format_value(original) if path in self._inherited_paths else "")
                    editor.setPlaceholderText("Not set in profile")
                editor.blockSignals(False)
            self._errors.discard(path)
            error.hide()
        except (ValueError, yaml.YAMLError) as exc:
            self._errors.add(path)
            error.setText(str(exc))
            error.show()
        self.apply_button.setEnabled(not self._errors)
        self._filter_fields()

    def accept(self):
        if not self._errors:
            super().accept()

    def reset(self):
        for path, (mode, _) in self.controls.items():
            if mode.isEnabled():
                if self._batch:
                    self.changed_paths.add(path)
                mode.setCurrentIndex(0)

    def apply_to_patch(self, patch):
        """Conserve les champs mixtes non touches lors d'une modification collective."""
        result = copy.deepcopy(patch)
        for path in sorted(self.changed_paths, key=lambda value: (len(value), value)):
            mode, _ = self.controls[path]
            target = result
            parents = []
            for key in path[:-1]:
                if not isinstance(target.get(key), dict):
                    if mode.currentIndex() != 1:
                        break
                    target[key] = {}
                parents.append((target, key))
                target = target[key]
            else:
                if mode.currentIndex() == 1:
                    target[path[-1]] = copy.deepcopy(self._changed_values[path])
                else:
                    target.pop(path[-1], None)
                    for parent, key in reversed(parents):
                        if not parent[key]:
                            parent.pop(key)
        return result


GROUP_COLORS = (("Blue", "#448aff"), ("Teal", "#00a99d"), ("Purple", "#a675ed"),
                ("Amber", "#d89a17"), ("Pink", "#e26493"), ("Green", "#61a64b"))


class ProfileGroupDialog(QDialog):
    def __init__(self, count, group=None, *, will_reorder=False, parent=None, parent_name="Profile root"):
        super().__init__(parent)
        self.group = copy.deepcopy(group or {})
        self.color = self.group.get("color", GROUP_COLORS[0][1])
        self.setWindowTitle("Edit group" if group else "Create test group")
        self.resize(520, 340)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        context = QLabel("Inside: " + parent_name)
        context.setTextFormat(Qt.PlainText)
        context.setWordWrap(True)
        context.setObjectName("Muted")
        root.addWidget(context)
        title = QLabel(f"{count} test{'s' if count != 1 else ''} in this group")
        root.addWidget(title)
        root.addWidget(QLabel("Group name"))
        self.name_edit = QLineEdit(self.group.get("name", ""))
        self.name_edit.setMaxLength(80)
        self.name_edit.setPlaceholderText("e.g. Card preparation")
        root.addWidget(self.name_edit)
        root.addWidget(QLabel("Short description"))
        self.description_edit = QLineEdit(self.group.get("description", ""))
        self.description_edit.setMaxLength(300)
        self.description_edit.setPlaceholderText("e.g. Connect the reader and check the card before personalization")
        root.addWidget(self.description_edit)
        root.addWidget(QLabel("Group color"))
        palette = QHBoxLayout()
        self.color_buttons = []
        for name, color in GROUP_COLORS:
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setIcon(icons.icon("mdi.circle", color))
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setFixedSize(38, 34)
            button.setChecked(color == self.color)
            button.clicked.connect(lambda checked=False, c=color: self._set_color(c))
            palette.addWidget(button)
            self.color_buttons.append(button)
        palette.addStretch()
        root.addLayout(palette)
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.PlainText)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(48)
        root.addWidget(self.preview)
        if will_reorder:
            note = QLabel("The selected tests will be placed together at the first selected position, "
                          "keeping their relative order. Other tests keep their relative order.")
            note.setWordWrap(True)
            root.addWidget(note)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Save group" if group else "Create group")
        self.save_button.setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.name_edit.textChanged.connect(self._refresh)
        self.description_edit.textChanged.connect(self._refresh)
        self._refresh()
        self.name_edit.setFocus()

    def _set_color(self, color):
        self.color = color
        self._refresh()

    def _refresh(self):
        self.save_button.setEnabled(bool(self.name_edit.text().strip()))
        self.preview.setText((self.name_edit.text().strip() or "Group preview") + "\n" +
                             (self.description_edit.text().strip() or "Short description"))
        self.preview.setStyleSheet(f"border-left: 3px solid {self.color}; padding: 6px 12px;")

    def metadata(self):
        result = copy.deepcopy(self.group)
        result.update({"id": self.group.get("id", str(uuid.uuid4())), "name": self.name_edit.text().strip(),
                       "color": self.color, "description": self.description_edit.text().strip()})
        return result

    def accept(self):
        if self.name_edit.text().strip():
            super().accept()


class ConfirmGroupMoveDialog(QDialog):
    def __init__(self, count, sources, destination, changes=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle('Confirm group change')
        self.resize(540, 340)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        title = QLabel(f'Move {count} test{"s" if count != 1 else ""} to another group?')
        title.setObjectName('PageTitle')
        root.addWidget(title)
        for label, value in (('From', ', '.join(sources)), ('To', destination)):
            text = QLabel(label + ': ' + value)
            text.setTextFormat(Qt.PlainText)
            text.setWordWrap(True)
            root.addWidget(text)
        note = QLabel('The tests will inherit the destination group YAML. '
                      'Their own YAML overrides and the configuration of moved subgroups are preserved.')
        note.setWordWrap(True)
        root.addWidget(note)
        if changes:
            preview = QLabel('Effective parameter changes:\n' + '\n'.join(changes))
            preview.setTextFormat(Qt.PlainText)
            preview.setWordWrap(True)
            root.addWidget(preview)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.move_button = buttons.button(QDialogButtonBox.Ok)
        self.move_button.setText('Move tests')
        self.move_button.setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        self.move_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class EffectiveConfigurationDialog(QDialog):
    def __init__(self, nodeid, configuration, rows, readers=(), parent=None):
        from PySide6.QtWidgets import QPlainTextEdit, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView
        from runner.domain.profile_configuration import exception_text
        super().__init__(parent)
        self.setWindowTitle('Effective test YAML')
        self.resize(1000, 650)
        self.configuration = copy.deepcopy(configuration)
        self.rows = copy.deepcopy(rows)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        title = QLabel(nodeid.split('::')[-1])
        title.setTextFormat(Qt.PlainText)
        title.setObjectName('PageTitle')
        root.addWidget(title)
        location = QLabel(nodeid)
        location.setTextFormat(Qt.PlainText)
        location.setWordWrap(True)
        location.setObjectName('Muted')
        root.addWidget(location)
        note = QLabel('Final values after merging the profile, groups and this test. '
                      'Choose the reader to preview its launch configuration.')
        note.setWordWrap(True)
        root.addWidget(note)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a parameter, value or origin…')
        self.search.setClearButtonEnabled(True)
        controls.addWidget(self.search, 1)
        self.reader_combo = QComboBox()
        self.reader_combo.addItems(list(readers) or ['Reader assigned at launch'])
        self.reader_combo.setToolTip('Readers currently selected in Run Tests')
        controls.addWidget(self.reader_combo)
        root.addLayout(controls)
        self.tabs = QTabWidget()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Parameter', 'Effective value', 'Origin'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 210)
        self.tabs.addTab(self.table, 'Values and origins')
        self.yaml_view = QPlainTextEdit()
        self.yaml_view.setReadOnly(True)
        self.tabs.addTab(self.yaml_view, 'Effective YAML')
        root.addWidget(self.tabs, 1)
        self.status = QLabel()
        root.addWidget(self.status)
        footer = QHBoxLayout()
        copy_button = QPushButton('Copy effective YAML')
        copy_button.clicked.connect(self._copy)
        footer.addWidget(copy_button)
        footer.addStretch()
        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        self.search.textChanged.connect(self._filter)
        self.reader_combo.currentIndexChanged.connect(self._refresh)
        self._reader_names = list(readers)
        self._exception_text = exception_text
        self._item_type = QTableWidgetItem
        self._refresh()

    def _refresh(self, *_):
        values = copy.deepcopy(self.configuration)
        rows = copy.deepcopy(self.rows)
        readers = [row for row in rows if isinstance(row['path'][-1], str)
                   and row['path'][-1].lower() in ('reader', 'lecteur')]
        if readers:
            row = min(readers, key=lambda row: len(row['path']))
            row['value'] = self.reader_combo.currentText() if self._reader_names else '<selected reader>'
            row['source'] = 'Run Tests: selected reader'
            row['exception'] = None
            target = values
            for key in row['path'][:-1]:
                target = target[key]
            target[row['path'][-1]] = row['value']
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, text in enumerate(('.'.join(map(str, row['path'])), format_value(row['value']), row['source'])):
                item = self._item_type(text)
                if row['exception']:
                    item.setToolTip(self._exception_text(row['exception']))
                    if column == 0:
                        item.setIcon(icons.icon('mdi.tune', '#d89a17'))
                self.table.setItem(index, column, item)
        self.yaml_view.setPlainText(yaml.safe_dump(values, allow_unicode=True, sort_keys=False))
        count = sum(bool(row['exception']) for row in rows)
        self.status.setText(f'{len(rows)} parameters · {count} value' + ('s' if count != 1 else '') + ' differing from inheritance')
        self._filter(self.search.text())

    def _filter(self, text):
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, text.casefold() not in ' '.join(
                self.table.item(row, col).text() for col in range(3)).casefold())

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.yaml_view.toPlainText())


class MoveToGroupDialog(QDialog):
    def __init__(self, targets, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Move to group')
        self.resize(620, 390)
        self.targets = targets
        self.details = details
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(QLabel('Destination group'))
        self.target_combo = QComboBox()
        for label, _ in targets:
            self.target_combo.addItem(label)
        root.addWidget(self.target_combo)
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.PlainText)
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.move_button = buttons.button(QDialogButtonBox.Ok)
        self.move_button.setText('Move tests')
        self.move_button.setObjectName('Primary')
        self.move_button.setAutoDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.target_combo.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def target(self):
        return self.targets[self.target_combo.currentIndex()][1]

    def _refresh(self, *_):
        details = self.details(self.target())
        valid = details is not None and bool(details['count'])
        self.move_button.setEnabled(valid)
        if not valid:
            self.preview.setText('Choose a different group. A group cannot be moved inside itself or its subgroups.')
            return
        text = f'Move {details["count"]} test(s) from ' + ', '.join(details['sources']) + '\nTo: ' + details['destination']
        text += '\n\nThe tests inherit the destination YAML. Their own overrides are preserved.'
        if details['changes']:
            text += '\n\nEffective parameter changes:\n' + '\n'.join(details['changes'][:6])
        self.preview.setText(text)

    def accept(self):
        if self.move_button.isEnabled():
            super().accept()


class PasteSequenceDialog(QDialog):
    def __init__(self, count, source, destination, changes=(), missing=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle('Paste test elements')
        self.resize(640, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel(f'Paste {count} test occurrence' + ('s' if count != 1 else '') + '?')
        heading.setObjectName('PageTitle')
        root.addWidget(heading)
        for text in ('From: ' + source, 'Destination: ' + destination,
                     'Structure, colors, descriptions and explicit YAML overrides are kept. '
                     'Inherited values follow the destination profile and group.'):
            label = QLabel(text)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            root.addWidget(label)
        if changes:
            text = 'Effective parameter changes:\n' + '\n'.join(changes[:6])
            if len(changes) > 6:
                text += f'\n+ {len(changes) - 6} other changes'
            label = QLabel(text)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            root.addWidget(label)
        if missing:
            label = QLabel(f'{len(missing)} copied test(s) are not collected in this workspace. '
                           'They can be saved, but cannot run here until available.\n' + '\n'.join(missing[:4]))
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            root.addWidget(label)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.paste_button = buttons.button(QDialogButtonBox.Ok)
        self.paste_button.setText('Paste anyway' if missing else 'Paste')
        self.paste_button.setObjectName('Primary')
        self.paste_button.setAutoDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
