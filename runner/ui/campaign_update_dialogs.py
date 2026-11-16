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
        self.resize(690, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel(profile.name)
        title.setObjectName('PageTitle')
        title.setTextFormat(Qt.PlainText)
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
        self.include_new.setVisible(bool(plan.additions))
        layout.addWidget(self.include_new)
        self.remove_missing = QCheckBox('Also remove tests that could not be matched')
        layout.addWidget(self.remove_missing)
        self.remove_missing.setToolTip('By default, unmatched tests and their settings stay in the campaign. They are left out of runs until found again.')
        self.details_button = QPushButton('Show changes')
        self.details_button.setCheckable(True)
        layout.addWidget(self.details_button, alignment=Qt.AlignLeft)
        self.details = QTreeWidget()
        self.details.setHeaderLabels(['Change', 'Campaign test'])
        self.details.setColumnWidth(0, 160)
        self.details.setMaximumHeight(250)
        self.details.hide()
        layout.addWidget(self.details)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.message)
        layout.addStretch(1)
        foot = QHBoxLayout()
        self.advanced = QPushButton('Advanced choices…')
        self.advanced.setObjectName('Ghost')
        self.advanced.clicked.connect(self._advanced)
        foot.addWidget(self.advanced)
        foot.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.addButton('Update campaign', QDialogButtonBox.AcceptRole)
        self.apply_button.setObjectName('Primary')
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

    def _refresh(self):
        additions, decisions, _ = self._choices()
        unresolved = [p for p, choice in decisions.items() if choice == 'keep']
        updated = sum(choice not in ('keep', 'remove') for choice in decisions.values())
        removed = sum(choice == 'remove' for choice in decisions.values())
        consumed = set()
        for position, choice in decisions.items():
            identifier = self.profile.step_ids[position] if self.profile.step_ids else ''
            source = self.profile.tracking.get('members', {}).get(identifier, {}).get('source')
            if choice not in ('keep', 'remove'):
                consumed.add((source, choice))
        added = len(set(additions) - consumed)
        count = len(self.profile.sequence) + added - removed
        self.all_unmatched = (len(self.plan.missing) == len(self.profile.sequence) and not self.plan.path_changes and not self.plan.additions)
        actions = []
        for number, label in ((added, 'new tests/cases'), (updated, 'test locations updated'), (removed, 'removed from campaign')):
            if number:
                actions.append(f'{number} {label}')
        self.summary.setText((' · '.join(actions) or 'Your campaign selection is kept') + f'\n{count} tests/cases after update')
        if self.all_unmatched and not self.custom:
            self.summary.setText(f'None of the {len(self.profile.sequence)} campaign tests were found in the current collection.')
            self.diagnosis.setText(f'{len(self.plan.available)} tests were collected in the current environment. Check the selected project and collection settings first. Your campaign is kept intact.')
        elif self.plan.path_changes:
            self.diagnosis.setText('The file names, test names and parameters match. Only their collection paths changed. Each test keeps its YAML settings.')
        else:
            self.diagnosis.setText('New cases use their group settings. Your group order, colours, descriptions and existing results are retained.')
        self.remove_missing.setVisible(bool(unresolved or self.remove_missing.isChecked()) and not self.all_unmatched)
        self.message.setText((f'{len(unresolved)} unmatched tests will stay in the campaign with their settings. They will not run until found again.' if unresolved and not self.all_unmatched else
                              'Campaign unchanged.' if self.all_unmatched and not self.custom else ''))
        if self.locked:
            self.message.setText('This campaign is running or queued. You can inspect the changes; update it after the run finishes.')
        elif removed:
            overrides = sum(bool(self.profile.step_overrides[p]) for p, decision in decisions.items()
                            if decision == 'remove' and self.profile.step_overrides)
            if overrides:
                self.message.setText(f'{overrides} test-specific YAML setting(s) will also be removed. The update can be undone.')
        self.apply_button.setText('Collect again' if self.all_unmatched and not self.custom else 'Update campaign')
        self.apply_button.setEnabled(not self.locked and (count > 0 or self.all_unmatched))
        if count == 0 and not self.all_unmatched:
            self.message.setText('This would leave the campaign empty. Keep unmatched tests or add current tests instead.')
        self.message.setVisible(bool(self.message.text()))
        if self.details.isVisible():
            self._fill_details()

    def _fill_details(self):
        self.details.clear()
        additions, decisions, _ = self._choices()
        for _, nodeid in additions:
            QTreeWidgetItem(self.details, ['Add', nodeid]).setToolTip(1, nodeid)
        for position, choice in decisions.items():
            state = 'Keep · not run' if choice == 'keep' else 'Remove from campaign' if choice == 'remove' else 'Update location' if position in self.plan.path_changes else 'Replace'
            row = QTreeWidgetItem(self.details, [state, self.profile.sequence[position]])
            row.setToolTip(1, self.profile.sequence[position] + ('\n→ ' + choice if choice not in ('keep', 'remove') else ''))

    def _show_details(self, shown):
        self.details.setVisible(shown)
        self.details_button.setText('Hide changes' if shown else 'Show changes')
        if shown:
            self._fill_details()
        self.adjustSize()

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
        dialog.apply_button.setText('Use these choices')
        if dialog.exec() == QDialog.Accepted:
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
            self.result_profile = sync.apply(self.profile, self.plan, additions, decisions, transfer=transfer)
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
        self.resize(700, 310)
        layout = QVBoxLayout(self)
        title = QLabel('Which tests should this campaign include?')
        title.setObjectName('PageTitle')
        layout.addWidget(title)
        self.scope = QLabel(f'{len(self.positions)} selected tests/cases · settings for this campaign only')
        self.scope.setWordWrap(True)
        self.scope.setObjectName('Muted')
        layout.addWidget(self.scope)
        self.fixed = QRadioButton('Keep only the tests I selected')
        self.following = QRadioButton('Include new tests from these folders or files')
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
        self.include_existing = QCheckBox('Also include tests already present in these folders')
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
            if positions:
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
        self.folders.setFixedHeight(min(250, max(85, 34 + len(self.choices) * 30)))

    def _choice(self, kind, selector, positions, source=None):
        rule = source or dict(kind=kind, selector=selector, recursive=True)
        count = sum(sync.matches(rule, n) for n in self.available)
        groups = self.profile.step_groups[positions[0]] if self.profile.step_groups else {}
        path = group_path(groups)
        label = (path[-1]['name'] + ' · ' if path else '') + (selector if selector != '.' else 'Project folder')
        item = QTreeWidgetItem(self.folders, [label, str(count)])
        item.setIcon(0, icons.icon('mdi.folder-outline' if kind == 'folder' else 'mdi.file-code-outline', path[-1]['color'] if path else None))
        item.setCheckState(0, Qt.Checked)
        item.setToolTip(0, selector + ('\nIncludes subfolders' if rule['recursive'] and kind == 'folder' else ''))
        self.choices.append(dict(kind=kind, selector=selector, positions=positions, source=source, item=item, count=count))

    def _mode(self, *_):
        follow = self.following.isChecked()
        self.folders.setVisible(follow)
        self.include_existing.setVisible(follow and any(not c['source'] for c in self.choices))
        self.advanced.setVisible(follow or bool(self.profile.tracking))
        self.description.setText('New tests found here will be proposed after collection. Your group settings apply to them.' if follow else
                                 'Your selection stays as it is. New tests elsewhere are not added.')
        self.message.setText('If you removed tests intentionally, those exclusions are kept. Advanced settings let you restore them.' if follow and self.profile.tracking else '')
        foreign = bool(self.profile.tracking and self.profile.tracking['workspace'] != sync.workspace_key(self.workspace))
        self.use_project.setVisible(foreign)
        if foreign:
            self.message.setText('This campaign is linked to another project. Choose whether to use the current project before saving changes.')
        elif not self.following.isEnabled():
            self.message.setText('These campaign tests were not found in the current collection. Check the selected project or update their locations first.')
        self.adjustSize()

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
