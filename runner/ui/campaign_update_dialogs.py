"""Parcours courant court ; les choix par occurrence restent accessibles sur demande."""
import copy
from pathlib import PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QRadioButton)
from PySide6.QtWidgets import QSizePolicy, QHeaderView

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ProfileValidationError, group_path
from runner.ui import icons


class CampaignReviewDialog(QDialog):
    def __init__(self, profile, plan, parent=None, *, locked=False):
        super().__init__(parent)
        self.profile, self.plan, self.locked = profile, plan, locked
        self.result_profile = None
        self.request_collection = False
        self.custom = None
        self.setWindowTitle('Update campaign')
        self.setMinimumSize(760, 480)
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel(profile.name)
        title.setObjectName('PageTitle')
        title.setTextFormat(Qt.PlainText)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        title.setToolTip(profile.name)
        layout.addWidget(title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.summary)
        self.diagnosis = QLabel()
        self.diagnosis.setWordWrap(True)
        self.diagnosis.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.diagnosis.setObjectName('Muted')
        layout.addWidget(self.diagnosis)
        self.include_new = QCheckBox('Include the new tests and parameter cases')
        self.include_new.setChecked(True)
        self.include_new.setVisible(bool(plan.additions or plan.parameter_updates))
        self.include_new.setText('Include new cases' if plan.parameter_updates and not plan.additions else 'Include new tests and cases')
        layout.addWidget(self.include_new)
        self.remove_missing = QCheckBox('Also remove tests that could not be matched')
        layout.addWidget(self.remove_missing)
        self.remove_missing.setToolTip('By default, unmatched tests and their settings stay in the campaign. They are left out of runs until found again.')
        self.details_button = QPushButton('Full paths')
        self.details_button.setCheckable(True)
        layout.addWidget(self.details_button, alignment=Qt.AlignLeft)
        self.details = QTreeWidget()
        self.details.setHeaderLabels(['Test', 'Change'])
        self.details.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.details.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.details.setMinimumHeight(170)
        self.details.setRootIsDecorated(True)
        layout.addWidget(self.details, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.message)
        foot = QHBoxLayout()
        self.advanced = QPushButton('Advanced…')
        self.advanced.setObjectName('Ghost')
        self.advanced.clicked.connect(self._advanced)
        foot.addWidget(self.advanced)
        foot.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.addButton('Update campaign', QDialogButtonBox.AcceptRole)
        self.apply_button.setObjectName('Primary')
        self.apply_button.setDefault(True)
        self.buttons.rejected.connect(self.reject)
        self.apply_button.clicked.connect(self._apply)
        foot.addWidget(self.buttons)
        layout.addLayout(foot)
        self.include_new.toggled.connect(self._changed)
        self.remove_missing.toggled.connect(self._changed)
        self.details_button.toggled.connect(self._show_details)
        self._changed()

    def _choices(self):
        if self.custom:
            return self.custom
        return (list(self.plan.additions) if self.include_new.isChecked() else [],
                sync.recommended_decisions(self.profile, self.plan, remove_unmatched=self.remove_missing.isChecked(),
                                           refresh_cases=self.include_new.isChecked()), [])

    def _changed(self, *_):
        self.custom = None
        self._refresh()

    def _refresh_cases(self):
        return getattr(self, '_custom_refresh_cases', self.include_new.isChecked()) if self.custom else self.include_new.isChecked()

    def _refresh(self):
        additions, decisions, transfer = self._choices()
        try:
            projected = sync.apply(self.profile, self.plan, additions, decisions, transfer=transfer,
                                   refresh_cases=self._refresh_cases())
        except (ValueError, ProfileValidationError):
            projected = None
        self.all_unmatched = bool(self.profile.sequence) and (len(self.plan.missing) == len(self.profile.sequence)
            and not self.plan.path_changes and not self.plan.additions and not self.plan.parameter_updates)
        count = len(projected.sequence) if projected else len(self.profile.sequence)
        changed = bool(projected and (projected.sequence != self.profile.sequence
            or projected.step_overrides != (self.profile.step_overrides or [{} for _ in self.profile.sequence])
            or projected.step_groups != (self.profile.step_groups or [{} for _ in self.profile.sequence])))
        delta = count - len(self.profile.sequence)
        action = f'{delta:+d} tests' if delta else 'Test references updated'
        calls = len(self.plan.parameter_updates) if self._refresh_cases() else 0
        scope = f' · {calls} call' + ('s' if calls != 1 else '') if calls else ''
        self.summary.setText(f'{action}{scope} · {len(self.profile.sequence)} → {count} tests' if changed else 'Nothing to update')
        self.diagnosis.hide()
        unresolved = [p for p, choice in decisions.items() if choice == 'keep']
        self.remove_missing.setVisible(bool(unresolved or self.remove_missing.isChecked()) and not self.all_unmatched)
        self.remove_missing.setText('Remove unavailable tests')
        self.message.setText(f'{len(unresolved)} unavailable tests kept.' if unresolved else '')
        if self.all_unmatched and not self.custom:
            self.summary.setText(f'None of the {len(self.profile.sequence)} tests were found')
            self.message.setText('Check the project and collect again.')
        if self.locked:
            self.message.setText('Campaign running or queued. Update after the run finishes.')
        if count == 0 and changed:
            self.message.setText('Groups and settings are kept. Add tests before running.')
        self.message.setVisible(bool(self.message.text()))
        self.apply_button.setText('Check project' if self.all_unmatched and not self.custom else 'Update campaign')
        self.apply_button.setEnabled(not self.locked and (changed or self.all_unmatched))
        self._fill_details()

    def _fill_details(self):
        from runner.ui import tokens as t
        self.details.clear()
        additions, decisions, _ = self._choices()
        full = self.details_button.isChecked()
        parents = {}
        def parent(entry):
            path = group_path(entry)
            key = tuple(g['id'] for g in path)
            if not key:
                return self.details
            if key not in parents:
                item = QTreeWidgetItem(self.details, [' / '.join(g['name'] for g in path)])
                item.setIcon(0, icons.icon('mdi.folder-outline', path[-1]['color']))
                item.setExpanded(True)
                parents[key] = item
            return parents[key]
        def row(entry, nodeid, change, extra=''):
            label = nodeid if full else nodeid.split('::')[-1]
            item = QTreeWidgetItem(parent(entry), [label, change])
            item.setIcon(0, icons.icon('mdi.function-variant', t.ACCENT))
            item.setToolTip(0, nodeid + ('\n' + extra if extra else ''))
        handled = set()
        for first, update in self.plan.parameter_updates.items():
            if not self._refresh_cases() or update['whole_test'] and decisions.get(first) != 'parameters':
                continue
            handled.update(update['positions'])
            group = self.profile.step_groups[first] if self.profile.step_groups else {}
            kept = {self.profile.sequence[p] if decisions.get(p, 'keep') == 'keep' else decisions[p]
                    for p in update['positions'] if decisions.get(p) != 'remove'}
            target = len(update['cases']) if update['whole_test'] else len(kept | set(update['cases']))
            row(group, update['base'], f'{len(update["positions"])} → {target} cases', '\n'.join(update['cases']))
        sources = {s['id']: s for s in self.profile.tracking.get('sources', [])}
        for source, nodeid in additions:
            row(sources[source]['group'], nodeid, 'Add')
        for position, choice in decisions.items():
            if position in handled:
                continue
            state = 'Not available' if choice == 'keep' else 'Remove' if choice == 'remove' else 'Update'
            group = self.profile.step_groups[position] if self.profile.step_groups else {}
            row(group, self.profile.sequence[position], state,
                choice if choice not in ('keep', 'remove', 'parameters') else '')

    def _show_details(self, _shown):
        self._fill_details()

    def _advanced(self):
        from runner.ui.campaign_sync import AdvancedCampaignReviewDialog
        dialog = AdvancedCampaignReviewDialog(self.profile, self.plan, self, locked=self.locked)
        additions, decisions, transfer = self._choices()
        for key, item in dialog.additions.items():
            item.setCheckState(0, Qt.Checked if key in additions else Qt.Unchecked)
        for position, combo in dialog.decisions.items():
            choice = decisions[position]
            index = combo.findData(choice)
            if index < 0:
                combo.addItem('Update → ' + choice, choice)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
            if position in dialog.transfers:
                dialog.transfers[position].setChecked(position in transfer)
        dialog.refresh_cases.setChecked(self._refresh_cases())
        dialog.apply_button.setText('Use these choices')
        if dialog.exec() == QDialog.Accepted:
            self._custom_refresh_cases = dialog.refresh_cases.isChecked()
            self.custom = ([key for key, item in dialog.additions.items() if item.checkState(0) == Qt.Checked],
                           {p: c.currentData() for p, c in dialog.decisions.items()},
                           [p for p, c in dialog.transfers.items() if c.isChecked() and c.isEnabled()])
            self._refresh()

    def _apply(self):
        if self.locked:
            return
        if self.all_unmatched and not self.custom:
            self.request_collection = True
            self.accept()
            return
        try:
            additions, decisions, transfer = self._choices()
            self.result_profile = sync.apply(self.profile, self.plan, additions, decisions, transfer=transfer, refresh_cases=self._refresh_cases())
        except (ValueError, ProfileValidationError) as exc:
            self.message.setText(str(exc))
            self.message.show()
            return
        self.accept()


class CampaignSourcesDialog(QDialog):
    def __init__(self, profile, positions, available, workspace, parent=None):
        super().__init__(parent)
        self.profile = copy.deepcopy(profile)
        sync.ensure_ids(self.profile)
        self.positions, self.available, self.workspace = list(positions), list(available), workspace
        self.setWindowTitle('Campaign contents')
        self.setMinimumSize(720, 460)
        self.resize(720, 460)
        layout = QVBoxLayout(self)
        title = QLabel('Campaign contents')
        title.setObjectName('PageTitle')
        layout.addWidget(title)
        self.scope = QLabel(f'{len(self.positions)} selected tests')
        self.scope.setWordWrap(True)
        self.scope.setObjectName('Muted')
        layout.addWidget(self.scope)
        self.fixed = QRadioButton('Keep selected cases')
        self.following = QRadioButton('Include new tests and cases')
        layout.addWidget(self.fixed)
        layout.addWidget(self.following)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.folders = QTreeWidget()
        self.folders.setHeaderLabels(['Folders / files in this campaign', 'Found now'])
        self.folders.setColumnWidth(0, 475)
        self.folders.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.folders.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.folders.setMinimumHeight(100)
        self.folders.setMaximumHeight(250)
        layout.addWidget(self.folders)
        self.include_existing = QCheckBox('Include other tests already here')
        self.include_existing.setChecked(True)
        layout.addWidget(self.include_existing)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.use_project = QPushButton('Use this project for the campaign')
        self.use_project.clicked.connect(self._use_project)
        layout.addWidget(self.use_project)
        foot = QHBoxLayout()
        self.advanced = QPushButton('Advanced…')
        self.advanced.clicked.connect(self._advanced)
        foot.addWidget(self.advanced)
        foot.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Save campaign')
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        foot.addWidget(buttons)
        layout.addStretch(1)
        layout.addLayout(foot)
        self.choices = []
        self._load_choices()
        self.fixed.toggled.connect(self._mode)
        self.following.toggled.connect(self._mode)
        self._mode()

    def _load_choices(self):
        self.folders.clear()
        self.choices = []
        tracking = self.profile.tracking
        selected = {self.profile.step_ids[p] for p in self.positions}
        members = tracking.get('members', {})
        covered = set()
        for source in tracking.get('sources', []):
            positions = [p for p in self.positions if members.get(self.profile.step_ids[p], {}).get('source') == source['id']]
            if positions or not self.profile.sequence or len(self.positions) == len(self.profile.sequence) and not any(m['source'] == source['id'] for m in members.values()):
                self._choice(source['kind'], source['selector'], positions, source)
                covered.update(positions)
        locations = sync.location_matches(self.profile.sequence, self.available)
        grouped = {}
        for position in self.positions:
            if position in covered:
                continue
            nodeid = locations.get(position, self.profile.sequence[position])
            path = PurePosixPath(nodeid.split('::')[0])
            kind, selector = ('file', str(path)) if str(path.parent) == '.' else ('folder', str(path.parent))
            groups = self.profile.step_groups[position] if self.profile.step_groups else {}
            key = tuple(g['id'] for g in group_path(groups)), kind, selector
            grouped.setdefault(key, []).append(position)
        for (_, kind, selector), positions in grouped.items():
            self._choice(kind, selector, positions)
        active = any(choice['source'] for choice in self.choices)
        self.following.setEnabled(active or any(c['count'] for c in self.choices))
        self.following.setChecked(active)
        self.fixed.setChecked(not active)
        self.folders.setFixedHeight(min(180, max(85, 34 + len(self.choices) * 30)))

    def _choice(self, kind, selector, positions, source=None):
        rule = source or dict(kind=kind, selector=selector, recursive=True)
        count = sum(sync.matches(rule, n) for n in self.available)
        groups = source['group'] if source and not positions else self.profile.step_groups[positions[0]] if self.profile.step_groups and positions else {}
        path = group_path(groups)
        caption = selector.split('::')[-1] if kind == 'test' else selector if selector != '.' else 'Project folder'
        label = (path[-1]['name'] + ' · ' if path else '') + caption
        item = QTreeWidgetItem(self.folders, [label, str(count)])
        item.setIcon(0, icons.icon('mdi.folder-outline' if kind == 'folder' else 'mdi.function-variant' if kind == 'test' else 'mdi.file-code-outline', path[-1]['color'] if path else None))
        item.setCheckState(0, Qt.Checked)
        item.setToolTip(0, selector + ('\nIncludes subfolders' if rule['recursive'] and kind == 'folder' else ''))
        self.choices.append(dict(kind=kind, selector=selector, positions=positions, source=source, item=item, count=count))

    def _mode(self, *_):
        follow = self.following.isChecked()
        self.folders.setVisible(follow)
        self.include_existing.setVisible(follow and any(not c['source'] for c in self.choices))
        self.advanced.setVisible(follow or bool(self.profile.tracking))
        self.description.setText('New tests are proposed after collection.' if follow else '')
        self.message.setText('')
        foreign = bool(self.profile.tracking and self.profile.tracking['workspace'] != sync.workspace_key(self.workspace))
        self.use_project.setVisible(foreign)
        if foreign:
            self.message.setText('Campaign linked to another project.')
        elif not self.profile.sequence and not self.profile.tracking:
            self.message.setText('Add tests to choose folders to follow.')
        elif not self.following.isEnabled():
            self.message.setText('Tests not found. Check the project first.')

    def _use_project(self):
        self.profile.tracking['workspace'] = sync.workspace_key(self.workspace)
        self._mode()

    def _save(self):
        result = copy.deepcopy(self.profile)
        members = result.tracking.get('members', {})
        for choice in self.choices:
            source = choice['source']
            chosen = self.following.isChecked() and choice['item'].checkState(0) == Qt.Checked
            if source and not chosen:
                identifiers = {result.step_ids[p] for p in choice['positions']}
                owned = {i for i, m in members.items() if m['source'] == source['id']}
                if owned <= identifiers:
                    result.tracking['sources'] = [s for s in result.tracking['sources'] if s['id'] != source['id']]
                else:
                    rule = next(s for s in result.tracking['sources'] if s['id'] == source['id'])
                    rule['excluded'].extend(result.sequence[p] for p in choice['positions'])
                for identifier in identifiers:
                    members.pop(identifier, None)
        sync.prune_sources(result)
        try:
            for choice in self.choices:
                if self.following.isChecked() and choice['item'].checkState(0) == Qt.Checked and not choice['source']:
                    sync.follow(result, choice['positions'], choice['kind'], choice['selector'], self.workspace)
                    if not self.include_existing.isChecked():
                        source = result.tracking['sources'][-1]
                        own = {result.sequence[p] for p in choice['positions']}
                        source['excluded'] = [n for n in self.available if n not in own and sync.matches(source, n)]
            sync.validate_tracking(result)
        except (ValueError, ProfileValidationError) as exc:
            self.message.setText(str(exc))
            return
        self.profile = result
        self.accept()

    def _advanced(self):
        from runner.ui.campaign_sync import AdvancedCampaignSourcesDialog
        dialog = AdvancedCampaignSourcesDialog(self.profile, self.positions, self.available, self.workspace, self)
        if dialog.exec() == QDialog.Accepted:
            self.profile = dialog.profile
            self._load_choices()
            self._mode()
