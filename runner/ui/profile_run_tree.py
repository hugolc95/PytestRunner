"""Interactions de l'arbre des profils, avec les memes gestes que All tests."""
import copy
import json
from dataclasses import replace

from PySide6.QtCore import QObject, QPersistentModelIndex, QModelIndex, Qt
from PySide6.QtWidgets import QApplication, QDialog, QListWidgetItem, QMenu

from runner.domain import failures
from runner.domain.diagnostics import PREFIX
from runner.domain.models import Kind, Reader, Status
from runner.domain.source import path_of as source_path
from runner.ui import icons
from runner.ui.tree_columns import TreeColumnLayout


class ProfileColumns(TreeColumnLayout):
    SETTINGS_KEY = 'tree/profile_column_widths'


class ProfileRunTree(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.group = QPersistentModelIndex()
        tree = window.profile_tree
        tree.setProperty('profileRunTree', True)
        tree.setAllColumnsShowFocus(True)
        tree.setSelectionMode(window.tree.selectionMode())
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self.show_menu)
        header = tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(window._menu_entete_arbre)
        window.profile_tree_columns = ProfileColumns(tree, window.settings, window.profile_tree_column_fitter,
            lambda column: window._default_column_width(tree, window.profile_model, column))
        window.profile_results.test_chosen.connect(self.reveal)
        window.profile_results.reader_selected.connect(window._on_reader_selected)
        window.profile_model.selection_changed.connect(self.selection_changed)

    def selection_changed(self, *_):
        w = self.window
        active = w.profile_tree_button.isChecked()
        checked, total = (w.profile_model if active else w.model).counts()
        noun = 'occurrences' if active else 'tests'
        w.selection_label.setText(f'{checked} of {total} {noun} selected')
        w._update_actions()

    def failure(self, key, reader, indexes=None):
        w = self.window
        if key not in w.profile_model.locations:
            return None
        nodeid = w.profile_model.locations[key][2]
        report = w._profile_reports.get((key, reader))
        if report is not None:
            indexes = indexes if indexes is not None else {}
            if id(report) not in indexes:
                indexes[id(report)] = failures.index_failures(report.output)
            return failures.failure_for(indexes[id(report)], nodeid)
        records = list(w._profile_live_details.get((key, reader), {}).get('records', {}).values())
        failed = [record for record in records if record['kind'] == 'test']
        if failed:
            return failures.failure_for(failures.index_failures('\n'.join(PREFIX + json.dumps(d) for d in failed)), nodeid)
        if records:
            return failures.Failure(nodeid, kind='skip', body=records[-1]['body'])
        return None

    def show_group(self, index):
        self.group = QPersistentModelIndex(index.siblingAtColumn(0))
        self.refresh_group()

    def refresh_group(self):
        w = self.window
        if not self.group.isValid() or not w.profile_tree_button.isChecked():
            return
        index = QModelIndex(self.group)
        model = w.profile_model
        counts, bad = model.subtree_summary(index)
        row = index.internalPointer()
        keys = model.leaf_nodeids_under(index)
        path = []
        parent = index.parent()
        while parent.isValid():
            path.append(str(parent.data()))
            parent = parent.parent()
        readers = model.readers or (Reader('', 0),)
        durations = model.reader_durations(row)
        cache = {}
        details = {(key, reader): self.failure(key, reader, cache) for key, reader in bad}
        source = None
        jump = ''
        if row.node.kind is not Kind.FOLDER and keys and w.workspace:
            nodeid = model.locations[keys[0]][2]
            source = source_path(w.workspace.path, nodeid)
            jump = nodeid if row.node.kind is Kind.TEST else ''
        panel = w.profile_results
        w.profile_selection_label.hide()
        panel.set_readers(model.readers)
        panel.show_group(' / '.join(reversed(path)), row.node.name, model.readers, counts, bad, source, jump,
                         durations=durations, failure_details=details)
        panel.source.edit_button.setEnabled(False)
        for position in range(panel.detail.failures.count()):
            item = panel.detail.failures.item(position)
            key = item.data(Qt.UserRole)
            if key in model.locations:
                step, attempt, nodeid = model.locations[key]
                label = nodeid.split('::')[-1] + f' · Occurrence {step + 1}' + (f' · Retry {attempt}' if attempt else '')
                item.setText(label)
                from runner.ui.detail_panel import ISSUE_ROLE
                issue = item.data(ISSUE_ROLE)
                if issue:
                    item.setData(ISSUE_ROLE, (issue[0], label, issue[2], issue[3]))
                item.setToolTip(nodeid)

    def reveal(self, key):
        self.window._reveal_search_match(key)

    def launch(self, keys, repetitions=1, stop=False):
        w = self.window
        profile = w._active_execution_profile
        if profile is None or w.service.busy or not w.workspace:
            return
        positions = list(dict.fromkeys(w.profile_model.locations[key][0] for key in keys if key in w.profile_model.locations
                                      and w.profile_model._by_nodeid[key] not in w.profile_model._blocked_rows))
        if not positions:
            return
        positions.sort()
        indices = [position % len(profile.sequence) for position in positions]
        snapshot = copy.deepcopy(profile)
        snapshot.sequence = [profile.sequence[i] for i in indices]
        snapshot.step_overrides = [copy.deepcopy(profile.step_overrides[i]) for i in indices] if profile.step_overrides else []
        snapshot.step_groups = [copy.deepcopy(profile.step_groups[i]) for i in indices] if profile.step_groups else []
        snapshot.execution = replace(snapshot.execution, repetitions=repetitions, stop_after_failure=stop,
                                     rerun_failures=0 if stop else snapshot.execution.rerun_failures)
        snapshot.name = (profile.name[:100] + ' · Selection')
        context = w.run_tabs.new_run(w) if w.run_tabs else w
        context._open_collected_profile(snapshot)
        context.run_selected()

    def menu(self, index):
        w = self.window
        model = w.profile_model
        index = index.siblingAtColumn(0)
        keys = model.leaf_nodeids_under(index)
        menu = QMenu(w)
        if not keys:
            return menu
        key = index.internalPointer().node.nodeid
        single = key in model.locations
        blocked = index.internalPointer() in model._blocked_rows
        active = w.service.busy or w._stress_worker is not None
        action = menu.addAction(icons.icon('mdi.play'), 'Run only this test' if single else 'Run only this',
                               lambda: self.launch(keys))
        action.setEnabled(not active and not blocked)
        if single:
            action = menu.addAction(icons.icon('mdi.repeat'), 'Run until it fails…',
                                   lambda: self.launch(keys, w.STRESS_CAP_UNTIL_FAIL, True))
            action.setEnabled(not active and not blocked)
            action = menu.addAction(icons.icon('mdi.layers-triple-outline'), 'Run N times…', lambda: self.repeat(keys))
            action.setEnabled(not active and not blocked)
            menu.addSeparator()
            nodeid = model.locations[key][2]
            menu.addAction('Copy nodeid', lambda: QApplication.clipboard().setText(nodeid))
            failure = None
            for reader in model.readers or (Reader('', 0),):
                candidate = self.failure(key, reader.index)
                if candidate is not None and candidate.kind != 'skip':
                    failure = candidate
                    break
            action = menu.addAction('Copy failure trace', lambda: QApplication.clipboard().setText(f'{failure.title}\n\n{failure.body}'))
            action.setEnabled(failure is not None and failure.kind != 'skip')
        if index.internalPointer().node.kind is not Kind.FOLDER:
            menu.addSeparator()
            menu.addAction('Open file', lambda: w.profile_results.show_tab(1))
        target = model.activation_target(index)
        if target:
            w.disabled_tests.add_menu_action(menu, target, group=not single)
        if hasattr(w, 'tree_results'):
            w.tree_results.refresh()
            menu.addSeparator()
            menu.addAction(w.tree_results.action)
        return menu

    def repeat(self, keys):
        from runner.ui.main_window import RunNTimesDialog
        dialog = RunNTimesDialog(20, self.window)
        if dialog.exec() == QDialog.Accepted:
            self.launch(keys, dialog.count())

    def show_menu(self, point):
        tree = self.window.profile_tree
        index = tree.indexAt(point)
        if index.isValid():
            tree.setCurrentIndex(index)
            menu = self.menu(index)
            if menu.actions():
                menu.exec(tree.viewport().mapToGlobal(point))

    def matching_failures(self, text):
        w = self.window
        needle = text.strip().casefold()
        if not needle:
            return []
        cache, matches = {}, []
        for key in w.profile_model.locations:
            for reader in w.profile_model.readers or (Reader('', 0),):
                failure = self.failure(key, reader.index, cache)
                if failure is not None and needle in failure.body.casefold():
                    matches.append((key, failure))
                    break
        return matches

    def failed_keys(self):
        model = self.window.profile_model
        latest = {}
        for key, (position, attempt, _) in model.locations.items():
            for reader, status in model._by_nodeid[key].statuses.items():
                previous = latest.get((position, reader))
                if previous is None or attempt >= previous[0]:
                    latest[position, reader] = (attempt, status)
        positions = sorted({position for (position, _), (_, status) in latest.items() if status.is_bad})
        return [model.key(position) for position in positions]

    def fill_failure_matches(self, matches):
        w = self.window
        w.failure_results.clear()
        if not matches and w.search.field.text().strip():
            item = QListWidgetItem('No failure output matches this search.')
            item.setFlags(Qt.NoItemFlags)
            w.failure_results.addItem(item)
        for key, failure in matches:
            position, attempt, nodeid = w.profile_model.locations[key]
            item = QListWidgetItem(nodeid.split('::')[-1] + f' · Occurrence {position + 1}\n' + failure.headline)
            item.setData(Qt.UserRole, key)
            item.setToolTip(nodeid + '\n' + failure.headline)
            w.failure_results.addItem(item)
        w.failure_results.setVisible(bool(w.search.field.text().strip()))
