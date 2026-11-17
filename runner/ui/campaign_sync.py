"""Revue explicite des changements, partagee entre l'editeur et Run Tests."""
from __future__ import annotations

import copy
from pathlib import PurePosixPath

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QDialog, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QComboBox, QCheckBox,
    QInputDialog, QListWidget, QLineEdit, QMessageBox, QRadioButton)

from runner.domain import campaign_sync as sync
from runner.domain.execution_profile import ProfileValidationError, group_path
from runner.domain.disabled_tests import parameter_base
from runner.ui import icons, tokens as t
from PySide6.QtGui import QAction, QKeySequence
from runner.ui.widgets import ErrorDialog


class CampaignNotice(QFrame):
    review = Signal()
    undo = Signal()
    tracking = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ProfileNotice')
        self.setProperty('warning', True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        self.symbol = QLabel()
        self.symbol.setPixmap(icons.icon('mdi.update').pixmap(20, 20))
        layout.addWidget(self.symbol)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.label, 1)
        self.sources = QPushButton('Contents…')
        self.sources.clicked.connect(self.tracking)
        layout.addWidget(self.sources)
        self.undo_button = QPushButton('Undo update')
        self.undo_button.clicked.connect(self.undo)
        layout.addWidget(self.undo_button)
        self.button = QPushButton('Review changes…')
        self.button.setObjectName('Primary')
        self.button.clicked.connect(self.review)
        layout.addWidget(self.button)
        self.hide()

    def show_plan(self, plan, *, can_undo=False, empty_action=''):
        warning = bool(plan.problem or plan.changed)
        if self.property('warning') != warning:
            self.setProperty('warning', warning)
            self.style().unpolish(self)
            self.style().polish(self)
        self.symbol.setPixmap(icons.icon('mdi.update' if warning else 'mdi.check-circle-outline').pixmap(20, 20))
        tone = t.status_color('skipped') if plan.problem or len(plan.missing) > len(plan.path_changes) else t.ACCENT
        self.setStyleSheet(f'QFrame#ProfileNotice {{background:{t.rgba(tone, .07)};border:none;border-left:2px solid {tone};border-radius:4px;}}')
        self.label.setText(plan.problem or ('Campaign update available · ' + plan.summary if plan.changed else 'Campaign updated and reloaded.'))
        self.button.setVisible(plan.changed and not plan.problem)
        if plan.missing and not plan.additions and not plan.path_changes and not plan.problem:
            self.label.setText(f'{len(plan.missing)} campaign tests not found · available tests can still run. Check the project and collection settings.')
            self.button.setText('Check campaign…')
        else:
            self.button.setText('Review changes…')
        self.undo_button.setVisible(can_undo)
        self.setVisible(bool(plan.problem or plan.changed or empty_action))
        if empty_action:
            self.label.setText('No tests currently available. Group settings are kept.')
            self.symbol.setPixmap(icons.icon('mdi.information-outline').pixmap(20, 20))
            self.button.setVisible(True)
            self.button.setText(empty_action)


class AdvancedCampaignReviewDialog(QDialog):
    def __init__(self, profile, plan, parent=None, *, locked=False):
        super().__init__(parent)
        self.profile, self.plan, self.result_profile = profile, plan, None
        self.locked = locked
        self.setWindowTitle('Update campaign')
        self.resize(1020, 790)
        layout = QVBoxLayout(self)
        title = QLabel(profile.name)
        title.setObjectName('PageTitle')
        title.setTextFormat(Qt.PlainText)
        layout.addWidget(title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Change / campaign occurrence', 'Action', 'Custom YAML'])
        self.tree.setColumnWidth(0, 485)
        self.tree.setColumnWidth(1, 280)
        self.tree.setAlternatingRowColors(False)
        self.tree.setIndentation(16)
        self.tree.setSelectionMode(QTreeWidget.NoSelection)
        layout.addWidget(self.tree, 1)
        self.additions, self.decisions, self.transfers = {}, {}, {}
        sources = {s['id']: s for s in profile.tracking.get('sources', [])}
        roots = {}
        def group(entry, selector=''):
            path = group_path(entry)
            key = tuple(g['id'] for g in path), selector
            if key not in roots:
                label = ' / '.join(g['name'] for g in path) or 'Campaign root'
                item = QTreeWidgetItem([label + (' · ' + selector if selector else '')])
                item.setIcon(0, icons.icon('mdi.folder-outline', path[-1]['color'] if path else t.TEXT_MUTED))
                self.tree.addTopLevelItem(item)
                item.setExpanded(True)
                roots[key] = item
            return roots[key]
        for source_id, nodeid in plan.additions:
            source = sources[source_id]
            item = QTreeWidgetItem(group(source['group'], source['selector']), [('New case · ' if '[' in nodeid else 'New test · ') + nodeid, 'Add to source block', 'Inherited from group'])
            item.setCheckState(0, Qt.Checked)
            item.setIcon(0, icons.icon('mdi.plus-circle-outline', t.status_color('passed')))
            item.setToolTip(0, nodeid + '\nInserted in this source block. Group YAML is inherited.')
            self.additions[source_id, nodeid] = item
        for position in plan.missing:
            entry = profile.step_groups[position] if profile.step_groups else {}
            identifier = profile.step_ids[position] if profile.step_ids else ''
            source_id = profile.tracking.get('members', {}).get(identifier, {}).get('source')
            selector = sources.get(source_id, {}).get('selector', '')
            state = 'Parameter changed' if plan.candidates[position] else 'Unavailable'
            item = QTreeWidgetItem(group(entry, selector), [f'{state} · #{position + 1} · {profile.sequence[position]}'])
            item.setIcon(0, icons.icon('mdi.alert-circle-outline', '#d89a17'))
            item.setToolTip(0, profile.sequence[position])
            combo = QComboBox()
            combo.addItem('Choose an action…', '')
            combo.addItem('Remove this occurrence', 'remove')
            combo.addItem('Keep unavailable', 'keep')
            for candidate in plan.candidates[position]:
                combo.addItem('Replace → ' + candidate.split('::')[-1], candidate)
                combo.setItemData(combo.count() - 1, candidate, Qt.ToolTipRole)
            for candidate in plan.suggestions.get(position, []):
                if combo.findData(candidate) < 0:
                    combo.addItem('Possible move → ' + candidate, candidate)
                    combo.setItemData(combo.count() - 1, 'Suggested only. Confirm the replacement; the campaign has not changed.', Qt.ToolTipRole)
            combo.addItem('Choose another collected test…', '__browse__')
            combo.currentIndexChanged.connect(lambda _=0, c=combo: self._choose(c))
            self.tree.setItemWidget(item, 1, combo)
            self.decisions[position] = combo
            combo.currentIndexChanged.connect(self._replacements_changed)
            if position in plan.path_changes and profile.step_overrides and profile.step_overrides[position]:
                item.setText(2, 'Kept with this test')
            elif profile.step_overrides and profile.step_overrides[position]:
                check = QCheckBox('Transfer override')
                check.setToolTip('Only transfer this occurrence\'s YAML to an explicitly selected replacement. Group YAML is always inherited.')
                check.setEnabled(False)
                combo.currentIndexChanged.connect(lambda _=0, c=combo, w=check: w.setEnabled(c.currentData() not in ('', 'keep', 'remove', '__browse__')))
                self.tree.setItemWidget(item, 2, check)
                self.transfers[position] = check
        self.message = QLabel('Unchecked additions remain excluded from this source until you restore them in Sources.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        preserved = QLabel('Preserved: group order, colours, descriptions, inherited YAML and unchanged occurrences. Historical runs are unchanged.')
        preserved.setWordWrap(True)
        preserved.setObjectName('Muted')
        layout.addWidget(preserved)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.addButton('Update and reload', QDialogButtonBox.AcceptRole)
        self.apply_button.setObjectName('Primary')
        self.apply_button.setEnabled(not locked)
        if locked:
            self.message.setText('This campaign is running or queued. Finish or stop its run before applying an update. You can inspect the changes now.')
        self.buttons.rejected.connect(self.reject)
        self.apply_button.clicked.connect(self._apply)
        layout.addWidget(self.buttons)
        self.tree.itemChanged.connect(lambda _, column: self._replacements_changed() if column == 0 else None)
        self._replacements_changed()

    def _replacements_changed(self, *_):
        # Montrer qu'un cas sert de remplacement evite de faire croire qu'il
        # sera execute deux fois, une fois remplace et une fois ajoute.
        replacements = set()
        for position, combo in self.decisions.items():
            choice = combo.currentData()
            identifier = self.profile.step_ids[position] if self.profile.step_ids else ''
            source = self.profile.tracking.get('members', {}).get(identifier, {}).get('source')
            if source and choice not in ('', 'keep', 'remove', '__browse__'):
                replacements.add((source, choice))
        for key, item in self.additions.items():
            replaced = key in replacements
            item.setText(1, 'Used as replacement' if replaced else 'Add to source block')
            item.setToolTip(1, 'This case will appear once in this source block.' if replaced else '')
        added = sum(item.checkState(0) == Qt.Checked and key not in replacements for key, item in self.additions.items())
        removed = sum(combo.currentData() == 'remove' for combo in self.decisions.values())
        pending = sum(combo.currentData() in ('', '__browse__') for combo in self.decisions.values())
        self.summary.setText(self.plan.summary + f'\nAfter your choices: {len(self.profile.sequence) + added - removed} occurrences · {pending} decision(s) remaining')
        self.apply_button.setEnabled(not self.locked and pending == 0)

    def _choose(self, combo):
        if combo.currentData() != '__browse__':
            return
        chosen, ok = QInputDialog.getItem(self, 'Choose replacement', 'Collected test identifier:', list(self.plan.available), 0, True)
        combo.setCurrentIndex(0)
        if ok and chosen in self.plan.available:
            index = combo.findData(chosen)
            if index < 0:
                combo.insertItem(combo.count() - 1, 'Replace → ' + chosen, chosen)
                index = combo.count() - 2
            combo.setCurrentIndex(index)

    def _apply(self):
        try:
            self.result_profile = sync.apply(self.profile, self.plan,
                [key for key, item in self.additions.items() if item.checkState(0) == Qt.Checked],
                {position: combo.currentData() for position, combo in self.decisions.items()},
                transfer=[position for position, check in self.transfers.items() if check.isChecked() and check.isEnabled()])
        except (ValueError, ProfileValidationError) as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class AdvancedCampaignSourcesDialog(QDialog):
    def __init__(self, profile, positions, available, workspace, parent=None):
        super().__init__(parent)
        self.profile = copy.deepcopy(profile)
        sync.ensure_ids(self.profile)
        self.positions, self.available, self.workspace = list(positions), list(available), workspace
        self.setWindowTitle('Campaign sources and selection tracking')
        self.resize(740, 580)
        layout = QVBoxLayout(self)
        label = QLabel('Follow a complete folder, file or parameterized test. Specific selections stay fixed. Existing profiles are never expanded without your review.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.sources = QListWidget()
        layout.addWidget(self.sources, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.PlainText)
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.fixed = QPushButton('Stop following · keep tests')
        self.restore = QPushButton('Restore excluded tests…')
        actions.addWidget(self.fixed)
        actions.addWidget(self.restore)
        layout.addLayout(actions)
        self.fixed.clicked.connect(self._stop)
        self.restore.clicked.connect(self._restore)
        self.source_path = QLineEdit()
        self.source_path.setPlaceholderText('Followed source path or test identifier')
        layout.addWidget(self.source_path)
        self.source_recursive = QCheckBox('Include subfolders for this source')
        layout.addWidget(self.source_recursive)
        self.edit_source = QPushButton('Update source settings')
        self.edit_source.clicked.connect(self._edit_source)
        layout.addWidget(self.edit_source)
        self.rebind = QPushButton('Rebind sources to the current environment…')
        self.rebind.clicked.connect(self._rebind)
        self.rebind.setVisible(bool(self.profile.tracking and self.profile.tracking['workspace'] != sync.workspace_key(workspace)))
        layout.addWidget(self.rebind)
        self.sources.currentRowChanged.connect(self._details)
        layout.addWidget(QLabel(f'Follow these {len(positions)} campaign occurrence(s):'))
        self.selector = QComboBox()
        selected = [profile.sequence[i] for i in positions]
        options = []
        if selected:
            paths = [n.split('::')[0] for n in selected]
            parent = PurePosixPath(paths[0]).parent
            for folder in [parent, *parent.parents]:
                if all(p.startswith(str(folder) + '/') or str(folder) == '.' for p in paths):
                    options.append(('folder', str(folder)))
            if len(set(paths)) == 1:
                options.append(('file', paths[0]))
            if len({parameter_base(n) for n in selected}) == 1:
                options.append(('test', parameter_base(selected[0])))
        for kind, selector in options:
            self.selector.addItem(f'{kind.title()} · {selector}', (kind, selector))
        layout.addWidget(self.selector)
        self.recursive = QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        layout.addWidget(self.recursive)
        self.keep_excluded = QCheckBox('Keep currently unselected tests excluded (recommended for existing campaigns)')
        self.keep_excluded.setChecked(True)
        layout.addWidget(self.keep_excluded)
        self.selection_summary = QLabel()
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)
        self.selector.currentIndexChanged.connect(self._candidate_count)
        self._candidate_count()
        self.follow_button = QPushButton('Follow this source')
        self.follow_button.setEnabled(bool(options) and bool(workspace))
        self.follow_button.clicked.connect(self._follow)
        layout.addWidget(self.follow_button)
        self.message = QLabel('New tests inherit group YAML. Copies of a whole followed group have independent sources.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        self.sources.clear()
        for source in self.profile.tracking.get('sources', []):
            path = ' / '.join(g['name'] for g in group_path(source['group'])) or 'Campaign root'
            self.sources.addItem(f'{source["kind"].title()} · {source["selector"]} · {path}')
        if self.sources.count():
            self.sources.setCurrentRow(0)
        self._details()

    def _selected(self):
        row = self.sources.currentRow()
        sources = self.profile.tracking.get('sources', [])
        return sources[row] if 0 <= row < len(sources) else None

    def _details(self, *_):
        source = self._selected()
        self.fixed.setEnabled(source is not None)
        self.restore.setEnabled(bool(source and source['excluded']))
        self.details.setText((f'{len(source["excluded"])} intentional exclusion(s) · ' + ('Subfolders included' if source['recursive'] else 'Direct folder only')) if source else 'Fixed selection · no followed source.')
        self.source_path.setText(source['selector'] if source else '')
        self.source_recursive.setChecked(bool(source and source['recursive']))
        self.source_recursive.setEnabled(bool(source and source['kind'] == 'folder'))
        self.edit_source.setEnabled(source is not None)

    def _edit_source(self):
        source = self._selected()
        if source:
            source['selector'] = self.source_path.text().strip()
            source['recursive'] = self.source_recursive.isChecked()
            self._refresh()

    def _rebind(self):
        answer = QMessageBox.question(self, 'Change campaign source environment',
            f'Original: {self.profile.tracking["workspace"]}\nCurrent: {self.workspace}\n\n'
            'Keep the campaign selection and rebind its sources? Review changed paths and compare after a successful collection.',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Yes:
            self.profile.tracking['workspace'] = sync.workspace_key(self.workspace)
            self.rebind.hide()

    def _save(self):
        if self._selected():
            self._edit_source()
        try:
            sync.validate_tracking(self.profile)
        except ProfileValidationError as exc:
            self.message.setText(str(exc))
            return
        self.accept()

    def _stop(self):
        source = self._selected()
        if source:
            self.profile.tracking['sources'].remove(source)
            sync.prune_sources(self.profile)
            self._refresh()

    def _restore(self):
        source = self._selected()
        if not source:
            return
        text, ok = QInputDialog.getItem(self, 'Restore exclusion', 'The test will be proposed at the next review:', source['excluded'], 0, False)
        if ok:
            source['excluded'].remove(text)
            self._details()

    def _follow(self):
        kind, selector = self.selector.currentData()
        previous_sources = {s['id'] for s in self.profile.tracking.get('sources', [])}
        try:
            sync.follow(self.profile, self.positions, kind, selector, self.workspace, recursive=self.recursive.isChecked())
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        if self.keep_excluded.isChecked():
            for source in self.profile.tracking['sources']:
                if source['id'] not in previous_sources:
                    selected = {m['nodeid'] for m in self.profile.tracking['members'].values() if m['source'] == source['id']}
                    source['excluded'] = [n for n in self.available if n not in selected and sync.matches(source, n)]
        self._refresh()
        self.message.setText('Source added to this draft. Save to keep the tracking rule. New additions are reviewed before execution.')

    def _candidate_count(self, *_):
        selection = self.selector.currentData()
        if not selection:
            self.selection_summary.setText('Select a campaign group, folder or test before creating a followed source.')
            return
        kind, selector = selection
        source = dict(kind=kind, selector=selector, recursive=True)
        selected = {self.profile.sequence[i] for i in self.positions}
        extra = sum(n not in selected and sync.matches(source, n) for n in self.available)
        self.selection_summary.setText(f'{extra} collected test(s)/case(s) outside this selection. Keep them excluded, or uncheck the option above to propose them in the update review.')


from runner.ui.campaign_update_dialogs import CampaignReviewDialog, CampaignSourcesDialog


class EditorCampaignSync(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.owner = page.window()
        self.workspace = ''
        self.complete = False
        self.undo_updates = {}
        self._undo_cache = {}
        self.undo_action = QAction('Undo last campaign update', page.sequence_list)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.undo_action.triggered.connect(self.undo)
        page.sequence_list.addAction(self.undo_action)
        self.notice = CampaignNotice(page)
        self.notice.sources.hide()
        page.layout().insertWidget(1, self.notice)
        self.notice.review.connect(self.review)
        self.notice.undo.connect(self.undo)
        self.notice.tracking.connect(page.manage_campaign_sources)

    def has_undo(self, identifier):
        from runner.domain.campaign_revision import previous, fingerprint
        try:
            stat = self.page.store._path(identifier).stat()
            key = identifier, stat.st_mtime_ns, stat.st_size
        except OSError:
            return False
        if key not in self._undo_cache:
            available = previous(self.page.store, identifier) is not None
            if not available and identifier in self.undo_updates:
                from runner.domain.execution_profile import inspect_profile
                try:
                    current = inspect_profile(self.page.store._path(identifier)).profile
                    available = fingerprint(current) == fingerprint(self.undo_updates[identifier][1])
                except (OSError, ProfileValidationError):
                    available = False
            self._undo_cache[key] = available
        return self._undo_cache[key]

    def plan(self, profile):
        return sync.compare(profile, self.page._available_nodeids, self.workspace, complete=self.complete)

    def refresh(self):
        page = self.page
        if page._building:
            return
        if not self.workspace and not page._available_nodeids:
            self.notice.hide()
            return
        for row, profile in enumerate(page._profiles):
            plan = self.plan(profile)
            item = page.profile_list.item(row)
            if item is not None:
                state = ' · Review' if plan.missing or plan.problem else ' · Update' if plan.additions else ''
                item.setText(f'{profile.name}\n{len(profile.sequence)} tests{state}')
                item.setIcon(icons.icon('mdi.update', '#d89a17') if plan.changed else icons.icon('mdi.playlist-edit'))
                item.setToolTip(profile.name + '\n' + (plan.problem or plan.summary))
        profile = page.current_profile()
        if profile is None:
            self.notice.hide()
            return
        try:
            profile = page._profile_from_editor()
        except (ValueError, OSError, UnicodeError):
            self.notice.hide()
            return
        plan = self.plan(profile)
        warning = 'Unavailable in the latest collection. Available campaign tests can still run.'
        from runner.ui.profile_group_delegate import CONFIG_ISSUES_ROLE
        from runner.ui.profile_group_delegate import TRACKING_ROLE
        unavailable = set(plan.missing)
        for position, item in enumerate(page._step_items()):
            issues = [text for text in (item.data(0, CONFIG_ISSUES_ROLE) or []) if text != warning]
            if position in unavailable:
                issues.append(warning)
            item.setData(0, CONFIG_ISSUES_ROLE, issues)
        for item, start, end in page._sequence_ranges()[1]:
            group_id = (item.data(0, Qt.UserRole + 26) or {}).get('id', '')
            mode = sync.content_description(profile, range(start, end), group_id)
            item.setData(0, TRACKING_ROLE, mode)
            plain = item.toolTip(0).split('\n\nCampaign contents:', 1)[0]
            item.setToolTip(0, plain + '\n\nCampaign contents:\n' + mode)
        can_undo = self.has_undo(profile.profile_id)
        self.page.undo_update_button.setVisible(can_undo)
        self.page.undo_update_button.setEnabled(not self._locked(profile) and not self.page._dirty)
        self.undo_action.setEnabled(can_undo and self.page.undo_stack.count() == 0 and not self._locked(profile) and not self.page._dirty)
        empty_action = ('Collect again' if profile.tracking.get('sources') else 'Add tests') if not profile.sequence and not plan.additions else ''
        self.notice.show_plan(plan, can_undo=False, empty_action=empty_action)

    def _locked(self, profile):
        host = self.owner
        contexts = [host]
        if getattr(host, 'run_tabs', None):
            contexts += [entry.context for entry in host.run_tabs.entries]
        return any(getattr(getattr(w, '_active_execution_profile', None), 'profile_id', None) == profile.profile_id
                   and (w.service.busy or w.run_tabs and w.run_tabs.is_locked(w)) for w in contexts if hasattr(w, 'service'))

    def review(self, profile=None):
        page = self.page
        profile = profile or page.current_profile()
        if profile is None:
            return
        if not profile.sequence and not self.plan(profile).additions:
            if profile.tracking.get('sources') and hasattr(self.owner, '_selected_run_context'):
                self.owner._selected_run_context().load_workspace()
            else:
                page.add_tests()
            return
        current = page.current_profile()
        if current and current.profile_id == profile.profile_id:
            if page._dirty:
                answer = QMessageBox.question(page, 'Save campaign edits',
                    'Save your current campaign edits before reviewing collection changes?',
                    QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
                if answer != QMessageBox.Save or not page.save_current():
                    return
            profile = page._profile_from_editor()
        else:
            profile = next((p for p in page.store.list() if p.profile_id == profile.profile_id), profile)
        from runner.domain.campaign_revision import digest, record
        expected = digest(page.store, profile.profile_id)
        if current and current.profile_id == profile.profile_id and expected != getattr(page, '_loaded_disk_digest', expected):
            page.reload_button.show()
            page._show_notice('This campaign changed on disk. Use Reload saved version before updating. Your current editor contents are kept.', warning=True)
            return
        plan = self.plan(profile)
        if plan.problem:
            ErrorDialog.show_error(page, 'Campaign cannot be compared', plan.problem)
            return
        if not plan.changed:
            page._show_notice('Campaign is already up to date.', warning=False)
            return
        dialog = CampaignReviewDialog(profile, plan, page, locked=self._locked(profile))
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.request_collection:
            context = self.owner._selected_run_context() if hasattr(self.owner, '_selected_run_context') else None
            if context is not None and not context.service.busy:
                self.owner._show_page('workspace')
                context.workspace_combo.setFocus()
                context.workspace_combo.showPopup()
            return
        if self._locked(profile):
            ErrorDialog.show_error(page, 'Campaign is running', 'Finish or stop this campaign before applying an update.')
            return
        current_plan = self.plan(profile)
        if current_plan != plan:
            ErrorDialog.show_error(page, 'Collection changed', 'Collect successfully and review the campaign again before applying changes.')
            return
        result = dialog.result_profile
        try:
            record(page.store, result, profile, expected)
        except (OSError, ValueError, ProfileValidationError) as exc:
            ErrorDialog.show_error(page, 'Could not update campaign', str(exc))
            return
        self.undo_updates[result.profile_id] = (copy.deepcopy(profile), copy.deepcopy(result))
        self._publish(result, profile)

    def _publish(self, result, previous):
        page = self.page
        current = page.current_profile()
        for row, profile in enumerate(page._profiles):
            if profile.profile_id == result.profile_id:
                page._profiles[row] = result
        if current and current.profile_id == result.profile_id:
            page._saving_refresh = True
            try:
                page._populate(result)
            finally:
                page._saving_refresh = False
            # La mise a jour sauvegardee a son propre Undo ; l'ancien Undo
            # d'edition ne doit pas restaurer un brouillon anterieur au disque.
            page.undo_stack.clear()
        self.refresh()
        page.campaign_updated.emit(result, previous)
        page._show_update_feedback('Campaign updated', 'Saved and reloaded. Use Undo update to restore the previous campaign, even after restarting the application.')

    def undo(self, profile_id=None):
        page = self.page
        current = page.current_profile()
        identifier = profile_id or (current.profile_id if current else '')
        pair = self.undo_updates.get(identifier)
        from runner.domain.campaign_revision import previous
        if pair:
            before, after = pair
        else:
            before = previous(page.store, identifier)
            after = next((p for p in page.store.list() if p.profile_id == identifier), None)
            if before is None or after is None:
                return
        if self._locked(after) or (current and current.profile_id == identifier and page._dirty):
            ErrorDialog.show_error(page, 'Could not undo update', 'Finish the run and save or undo local edits before restoring the previous campaign.')
            return
        saved = next((p for p in page.store.list() if p.profile_id == identifier), None)
        if saved is not None:
            saved.source = after.source
        if saved != after:
            ErrorDialog.show_error(page, 'Campaign changed since update', 'The campaign was edited after this update. Its newer edits have been kept.')
            return
        try:
            page.store.save(before)
        except (OSError, ProfileValidationError) as exc:
            ErrorDialog.show_error(page, 'Could not undo update', str(exc))
            return
        self.undo_updates.pop(identifier, None)
        self._publish(before, after)
        page._show_update_feedback('Update undone', 'The previous campaign has been restored and saved.')
