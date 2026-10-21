"""Compact activation controls, without adding a column or enlarging the run header."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QPlainTextEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from runner.domain.disabled_tests import DisabledTestsError, DisabledTestsStore, activation_record, matching_record, parameter_base, workspace_key
from runner.domain.models import Status
from runner.ui import icons, tokens as t
from runner.ui.tree_model import NODEID_ROLE
from runner.ui.widgets import ErrorDialog


def local_date(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return value


class DisableTestDialog(QDialog):
    def __init__(self, nodeids, selected='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Deactivate tests or group')
        self.resize(620, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Element (folder, file, class, test or parameter case)'))
        self.test = QComboBox()
        self.test.addItems(list(dict.fromkeys(nodeids)))
        self.test.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.test.setMinimumContentsLength(30)
        self.test.setCurrentText(selected or self.test.currentText())
        layout.addWidget(self.test)
        self.all_cases = QCheckBox('Deactivate all parameter cases of this test')
        self.all_cases.setChecked(True)
        layout.addWidget(self.all_cases)
        def scope():
            self.all_cases.setVisible(parameter_base(self.test.currentText()) != self.test.currentText())
        self.test.currentTextChanged.connect(scope)
        scope()
        layout.addWidget(QLabel('Reason (optional)'))
        self.reason = QPlainTextEdit()
        self.reason.setPlaceholderText('For example: destructive test — do not erase the personalised card again.')
        layout.addWidget(self.reason, 1)
        note = QLabel('Applies to this workspace, across configurations and runs. Reactivate manually.')
        note.setObjectName('Faint')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.disable_button = self.buttons.addButton('Deactivate', QDialogButtonBox.AcceptRole)
        self.disable_button.setObjectName('Primary')
        def validate():
            self.disable_button.setEnabled(bool(self.test.currentText())
                                           and len(self.reason.toPlainText().strip()) <= 4000)
        self.reason.textChanged.connect(validate)
        self.test.currentTextChanged.connect(validate)
        validate()
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def target(self):
        nodeid = self.test.currentText()
        return parameter_base(nodeid) if not self.all_cases.isHidden() and self.all_cases.isChecked() else nodeid


class DisabledTestsDialog(QDialog):
    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        self.workspace = controller.workspace
        self.remembered = {}
        self.setWindowTitle('Deactivated tests')
        self.resize(940, 540)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        heading = QLabel('Deactivated tests')
        heading.setObjectName('Title')
        top.addWidget(heading)
        top.addStretch()
        self.counter = QLabel()
        self.counter.setObjectName('Faint')
        top.addWidget(self.counter)
        layout.addLayout(top)
        self.note = QLabel('This workspace · all configurations and runs. Changes are saved immediately.')
        self.note.setObjectName('Faint')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        tools = QHBoxLayout()
        self.enable_all_button = QPushButton('Activate all')
        self.disable_all_button = QPushButton('Deactivate all')
        for button, enabled in ((self.enable_all_button, True), (self.disable_all_button, False)):
            button.setObjectName('Ghost')
            button.clicked.connect(lambda _=False, enabled=enabled: self.set_all(enabled))
            tools.addWidget(button)
        tools.addStretch()
        self.add_button = QPushButton('Deactivate a test or group…')
        self.add_button.setObjectName('Ghost')
        self.add_button.setIcon(icons.icon('mdi.cancel'))
        self.add_button.clicked.connect(self.add_test)
        tools.addWidget(self.add_button)
        layout.addLayout(tools)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(True)
        self.table.setUniformRowHeights(True)
        self.table.setHeaderLabels(['Test or group / reason', 'Date', 'Active'])
        self.table.itemChanged.connect(self._item_changed)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.header().setStretchLastSection(False)
        self.table.header().resizeSection(1, 150)
        self.table.header().resizeSection(2, 130)
        layout.addWidget(self.table, 1)
        footer = QLabel('Checked = active · Unchecked = inactive · Dash = partially active. Group checkboxes apply to all their tests.')
        footer.setObjectName('Faint')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        try:
            current = self.controller.store.records(self.workspace)
        except DisabledTestsError as exc:
            self.note.setText(str(exc))
            self.add_button.setEnabled(False)
            self.enable_all_button.setEnabled(False)
            self.disable_all_button.setEnabled(False)
            return
        self.remembered.update(current)
        disabled_rules = {key: record for key, record in current.items() if not record.get('enabled', False)}
        for nodeid in self.controller.window.model._by_nodeid:
            inherited = matching_record(disabled_rules, nodeid)
            if inherited:
                self.remembered.setdefault(nodeid, dict(inherited, nodeid=nodeid))
        # Keep every intermediate scope, even when it has no saved decision.
        # Include the whole affected module so its checkbox has a visible scope.
        modules = {key.split('::', 1)[0] for key in self.remembered
                   if '::' in key or key.endswith('.py')}
        for nodeid in self.controller.window.model._by_nodeid:
            module = nodeid.split('::', 1)[0]
            if module not in modules:
                continue
            seed = activation_record(current, nodeid)
            if seed is None:
                seed = next(record for key, record in self.remembered.items()
                            if key.split('::', 1)[0] == module)
            parts = parameter_base(nodeid).split('::')
            scopes = ['::'.join(parts[:length]) for length in range(1, len(parts) + 1)]
            for target in [*scopes, nodeid]:
                self.remembered.setdefault(target, dict(seed, nodeid=target))
        affected = sum(bool(matching_record(current, nodeid)) for nodeid in self.controller.window.model._by_nodeid)
        self.counter.setText(f'{affected} tests deactivated')
        editable = self.controller.can_edit(self.workspace)
        self.enable_all_button.setEnabled(editable and bool(self.remembered))
        self.disable_all_button.setEnabled(editable and bool(self.remembered))
        self.add_button.setEnabled(editable and any(target and not matching_record(current, target)
                                                   for target in self.controller.window.model.activation_targets()))
        expanded = {key for key, item in getattr(self, '_items', {}).items() if item.isExpanded()}
        first_render = not hasattr(self, '_items')
        self.table.blockSignals(True)
        self.table.clear()
        self._items = {}
        groups = {key: record for key, record in self.remembered.items()
                  if key not in self.controller.window.model._by_nodeid}
        for nodeid in sorted(self.remembered, key=len):
            record = self.remembered[nodeid]
            active_record = matching_record(current, nodeid)
            kind = 'Test' if nodeid in self.controller.window.model._by_nodeid else 'Group'
            reason = record['reason'].replace('\n', ' ') or 'No reason provided'
            if len(reason) > 160:
                reason = reason[:157] + '…'
            scope = [test for test in self.controller.window.model._by_nodeid
                     if activation_record({nodeid: record}, test)]
            scope_count = len(scope) if kind == 'Group' else 1
            item = QTreeWidgetItem([f"{nodeid.split('::', 1)[-1]}\n{reason} · {kind} · {scope_count} test(s)",
                                    local_date(record['date']), ''])
            item.setData(0, Qt.UserRole, nodeid)
            item.setToolTip(0, f"{nodeid}\n{record['reason']}\n{record['author']} · {local_date(record['date'])}")
            parent = activation_record(groups, nodeid, skip_exact=True)
            if parent and parent['nodeid'] in self._items:
                self._items[parent['nodeid']].addChild(item)
            else:
                self.table.addTopLevelItem(item)
            self._items[nodeid] = item
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | (Qt.ItemIsUserCheckable if editable else Qt.NoItemFlags))
            states = {bool(matching_record(current, test)) for test in scope} if kind == 'Group' else set()
            state = (Qt.PartiallyChecked if len(states) > 1 else
                     Qt.Unchecked if states == {True} or not states and active_record else Qt.Checked)
            item.setCheckState(2, state)
            item.setIcon(0, icons.icon('mdi.cancel' if state != Qt.Checked else 'mdi.check-circle-outline',
                                      t.status_color(Status.SKIPPED if state != Qt.Checked else Status.PASSED)))
            item.setToolTip(2, 'Activate or deactivate all tests and parameter cases in this group.' if kind == 'Group' else
                            'Activate this test only, keeping the rest of its group unchanged.')
            item.setSizeHint(0, QSize(0, 48))
            item.setExpanded(first_render or nodeid in expanded)
        self.table.blockSignals(False)

    def _item_changed(self, item, column):
        if column == 2:
            nodeid = item.data(0, Qt.UserRole)
            self.set_enabled(nodeid, self.remembered[nodeid], item.checkState(2) == Qt.Checked)

    def set_enabled(self, nodeid, record, enabled):
        try:
            if nodeid not in self.controller.window.model._by_nodeid:
                targets = [key for key in self.remembered if activation_record({nodeid: record}, key)]
                self.controller.set_many(targets, enabled=enabled, workspace=self.workspace,
                                         reasons={key: self.remembered[key]['reason'] for key in targets})
            elif enabled:
                self.controller.enable(nodeid, self.workspace)
            else:
                self.controller.disable(nodeid, record['reason'], self.workspace)
        except DisabledTestsError as exc:
            self.note.setText(str(exc))
        QTimer.singleShot(0, self.refresh)

    def set_all(self, enabled):
        try:
            self.controller.set_many(list(self.remembered), enabled=enabled, workspace=self.workspace,
                                     reasons={key: record['reason'] for key, record in self.remembered.items()})
            self.note.setText('All listed elements activated.' if enabled else 'All listed elements deactivated.')
        except DisabledTestsError as exc:
            self.note.setText(str(exc))
        self.refresh()

    def add_test(self):
        self.controller.ask_disable(parent=self)
        self.refresh()


class DisabledTestsController(QObject):
    changed = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        host = window._run_host or window
        self.owner = getattr(host, 'disabled_tests', self)
        self.store = (self.owner.store if self.owner is not self else
                      DisabledTestsStore(window.history.racine.parent / 'disabled-tests'))
        self.owner.changed.connect(self._changed)
        self.records = {}
        self.error = ''
        self.detail_pages = {}
        self.button = window._quiet('mdi.cancel', 'Deactivated tests', self.open_manager)
        self.button.hide()
        toolbar = window.tree_toolbar.layout()
        toolbar.insertWidget(toolbar.indexOf(window.markers) + 1, self.button)
        self.refresh()

    @property
    def workspace(self):
        return self.window.workspace.path if self.window.workspace else ''

    def _changed(self, workspace):
        if self.workspace and workspace_key(self.workspace) == workspace_key(workspace):
            self.refresh()
            if self.window.profile_tree_button.isChecked():
                self.window._refresh_profile_selection()
            else:
                self.window._select_test(self.window.tree.currentIndex())

    def refresh(self):
        try:
            self.records = self.store.records(self.workspace) if self.workspace else {}
            self.error = ''
        except DisabledTestsError as exc:
            self.error = str(exc)
        targets = set(self.window.model.activation_targets()) | set(self.window.profile_model.activation_targets())
        model_records = dict(self.records)
        model_records.update({target: record for target in targets if target
                              and (record := matching_record(self.records, target))})
        self.window.model.set_disabled_tests(model_records)
        self.window.profile_model.set_disabled_tests(model_records)
        rule_count = sum(not record.get('enabled', False) for record in self.records.values())
        self.button.setVisible(bool(rule_count) or bool(self.error))
        self.button.setIcon(icons.icon('mdi.cancel', t.status_color(Status.SKIPPED)))
        self.button.setToolTip(self.error or f'Deactivated tests and groups ({rule_count} rules)')

    def can_edit(self, workspace=None):
        workspace = workspace or self.workspace
        host = self.window._run_host or self.window
        contexts = [entry.context for entry in host.run_tabs.entries] if host.run_tabs else [host]
        for context in contexts:
            if (context.workspace and workspace_key(context.workspace.path) == workspace_key(workspace)
                    and (context.service.busy or context._stress_worker is not None
                         or host.run_tabs and host.run_tabs.entry_for(context).state in ('running', 'finalizing'))):
                return False
        return True

    def restyle(self):
        self.button.setIcon(icons.icon('mdi.cancel', t.status_color(Status.SKIPPED)))
        if self.window.profile_tree_button.isChecked():
            self.window._refresh_profile_selection()
        else:
            index = self.window.tree.currentIndex()
            nodeid = self.window.model.activation_target(index)
            if matching_record(self.records, nodeid):
                self.show_details(nodeid)

    def disable(self, nodeid, reason, workspace=None):
        workspace = workspace or self.workspace
        if not self.can_edit(workspace):
            raise DisabledTestsError('Stop this workspace’s running tests before changing test activation.')
        self.store.disable(workspace, nodeid, reason)
        self.owner.changed.emit(workspace)

    def enable(self, nodeid, workspace=None):
        workspace = workspace or self.workspace
        if not self.can_edit(workspace):
            raise DisabledTestsError('Stop this workspace’s running tests before changing test activation.')
        self.store.enable(workspace, nodeid)
        self.owner.changed.emit(workspace)

    def ask_disable(self, nodeid='', *, parent=None):
        if not self.workspace:
            return
        if not self.can_edit():
            self.show_error('Stop this workspace’s running tests before changing test activation.')
            return
        available = [target for target in self.window.model.activation_targets()
                     if target and not matching_record(self.records, target)]
        if not available:
            return
        dialog = DisableTestDialog(available, nodeid, parent or self.window)
        if dialog.exec() == QDialog.Accepted:
            try:
                self.disable(dialog.target(), dialog.reason.toPlainText())
            except DisabledTestsError as exc:
                self.show_error(str(exc))

    def set_many(self, targets, *, enabled, workspace=None, reasons=None):
        workspace = workspace or self.workspace
        if not self.can_edit(workspace):
            raise DisabledTestsError('Stop this workspace’s running tests before changing test activation.')
        self.store.set_many(workspace, targets, enabled=enabled, reasons=reasons)
        self.owner.changed.emit(workspace)

    def reenable(self, nodeid):
        try:
            records = self.store.records(self.workspace)
            record = matching_record(records, nodeid)
            if record:
                self.enable(nodeid)
        except DisabledTestsError as exc:
            self.show_error(str(exc))

    def open_manager(self):
        if self.workspace:
            dialog = DisabledTestsDialog(self)
            dialog.exec()

    def show_error(self, message):
        ErrorDialog.show_error(self.window, 'Test activation', message)

    def check_launch(self, nodeids, workspace=None, *, strict=False):
        workspace = workspace or self.workspace
        try:
            records = self.store.records(workspace)
        except DisabledTestsError as exc:
            self.show_error(str(exc))
            return []
        blocked = [nodeid for nodeid in nodeids if matching_record(records, nodeid)]
        if blocked and (strict or len(blocked) == len(nodeids)):
            details = '\n'.join(f"{nodeid}\n  {matching_record(records, nodeid)['reason']}" for nodeid in dict.fromkeys(blocked))
            ErrorDialog.show_error(self.window, 'Deactivated tests — run blocked',
                                   'Reactivate these tests or revise the selection/profile before running.', details)
            return []
        if blocked:
            self.window.status_label.setText(f'{len(blocked)} deactivated test(s) excluded before execution.')
        return [nodeid for nodeid in nodeids if not matching_record(records, nodeid)]

    def add_menu_action(self, menu, nodeid, *, group=False):
        record = matching_record(self.records, nodeid)
        menu.addSeparator()
        label = ('Activate group' if record and group else
                 'Activate test' if record else 'Deactivate group…' if group else 'Deactivate test…')
        action = menu.addAction(icons.icon('mdi.cancel'), label,
                                lambda: self.reenable(nodeid) if record else self.ask_disable(nodeid))
        action.setEnabled(self.can_edit())

    def show_details(self, nodeid, panel=None):
        record = matching_record(self.records, nodeid)
        if not record:
            return
        panel = panel or self.window.results
        if panel not in self.detail_pages:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(24, 24, 24, 24)
            page.title = QLabel()
            page.title.setObjectName('Title')
            page.title.setWordWrap(True)
            page.title.setTextFormat(Qt.PlainText)
            page.path_label = QLabel()
            page.path_label.setObjectName('Faint')
            page.path_label.setWordWrap(True)
            page.path_label.setTextFormat(Qt.PlainText)
            layout.addWidget(page.title)
            layout.addWidget(page.path_label)
            layout.addSpacing(20)
            state = QLabel('Deactivated')
            page.state = state
            state.setStyleSheet(f'color:{t.status_color(Status.SKIPPED)};')
            layout.addWidget(state)
            page.reason = QPlainTextEdit()
            page.reason.setReadOnly(True)
            page.reason.setFixedHeight(72)
            page.reason.setStyleSheet(
                f'QPlainTextEdit {{ border:0; background:transparent; padding:0; '
                f'font-family:{t.FONT_UI}; font-size:{t.TEXT_MD}px; }}')
            layout.addWidget(page.reason)
            page.meta = QLabel()
            page.meta.setObjectName('Faint')
            page.meta.setWordWrap(True)
            layout.addWidget(page.meta)
            page.enable = QPushButton('Activate test')
            page.enable.setObjectName('Ghost')
            page.enable.clicked.connect(lambda: self.reenable(page.nodeid))
            layout.addWidget(page.enable, 0, Qt.AlignLeft)
            layout.addStretch()
            panel.detail.stack.addWidget(page)
            self.detail_pages[panel] = page
        page = self.detail_pages[panel]
        page.state.setStyleSheet(f'color:{t.status_color(Status.SKIPPED)};')
        page.nodeid = nodeid
        page.title.setText(nodeid.split('::', 1)[-1])
        page.path_label.setText(nodeid.split('::', 1)[0])
        page.reason.setPlainText(record['reason'] or 'No reason provided')
        page.enable.setText('Activate')
        page.meta.setText(f"{record['author']} · {local_date(record['date'])}\nWorkspace · all configurations and runs")
        page.enable.setEnabled(self.can_edit())
        panel.detail.stack.setCurrentWidget(page)
