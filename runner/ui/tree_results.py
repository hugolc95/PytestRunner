"""Tree retention preference, compact clear action and result provenance."""
from datetime import datetime
from pathlib import Path
from time import time_ns

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction

from runner.domain.models import Reader
from runner.domain.tree_results import TreeResultsStore
from runner.ui import icons, tokens as t


class TreeResultsController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        host = window._run_host or window
        owner = getattr(host, 'tree_results', self)
        self.store = owner.store if owner is not self else TreeResultsStore(window.history.racine.parent / 'tree-results')
        self._hidden_previous = {}
        self.button = window._quiet('mdi.eraser', 'Clear tree results — saved History is kept', self.clear)
        self.action = QAction('Clear tree results', window)
        self.action.setToolTip('Clear displayed and retained tree results; saved History is kept')
        self.action.triggered.connect(self.clear)
        toolbar = window.tree_toolbar.layout()
        toolbar.insertWidget(toolbar.indexOf(window.select_all_button), self.button)
        window.model.layoutChanged.connect(self.refresh)
        window.model.dataChanged.connect(self.refresh)
        window.service.finished.connect(self.completed)
        self.collected(False)

    @property
    def enabled(self):
        host = self.window._run_host or self.window
        preferences = getattr(host, 'preferences', None)
        return preferences.values.get('retain_tree_results', True) if preferences else True

    def readers(self):
        return self.window.model.readers or (Reader('', 0),)

    def saved_results(self):
        saved = self.store.read(self.window.workspace.path)
        return {nodeid: {reader.index: entries[reader.name] for reader in self.readers()
                         if reader.name in entries}
                for nodeid, entries in saved.items()}

    def refresh(self, *_):
        w = self.window
        busy = w.service.busy or w._stress_worker is not None
        locked = bool(w.run_tabs and w.run_tabs.is_locked(w))
        has_results = bool(w.model._tally or any(w.model._retained.values()) or
                           any(row.statuses for row in w.profile_model._by_nodeid.values()))
        self.button.setEnabled(has_results and not busy and not locked)
        self.button.setIcon(icons.icon('mdi.eraser', t.TEXT_MUTED))
        self.action.setEnabled(self.button.isEnabled())
        self.action.setIcon(self.button.icon())

    def collected(self, same_workspace, retained=None):
        w = self.window
        if not same_workspace:
            self._hidden_previous = {}
            w._cleared_run_counts = None
            w.model._run_meta = {}
            w.results.set_result_origins({})
        records = retained if same_workspace and retained is not None else {}
        if self.enabled and w.workspace and retained is None:
            try:
                records = self.saved_results()
            except (OSError, ValueError, TypeError) as exc:
                w.status_label.setText(f'Could not restore tree results: {exc}')
        w.model.set_retained_results(records if self.enabled else {})
        self.refresh()

    def start_run(self, request, *, preserve_results=False):
        w = self.window
        retain = self.enabled or preserve_results
        w._cleared_run_counts = None
        if not retain:
            self._hidden_previous = {}
        w.results.set_result_origins({})
        meta = dict(run_id=request.run_id, at=datetime.now().astimezone().isoformat(timespec='seconds'), order=time_ns(),
                    config=Path(request.config_path).name if request.config_path else '')
        w.model.begin_run(retain, meta)
        if retain and w.workspace:
            try:
                previous = w.model.export_results()
                for nodeid, readers in self.saved_results().items():
                    for reader, entry in readers.items():
                        local = previous.get(nodeid, {}).get(reader, {})
                        rank = entry.get('meta', {}).get('order', 0)
                        local_rank = local.get('meta', {}).get('order', 0)
                        if isinstance(rank, int) and isinstance(local_rank, int) and rank >= local_rank:
                            previous.setdefault(nodeid, {})[reader] = entry
                w.model.set_retained_results(previous)
            except (OSError, ValueError, TypeError) as exc:
                w.status_label.setText(f'Could not restore tree results: {exc}')
        if not retain and w.workspace:
            try:
                self.store.write(w.workspace.path, {})
            except OSError as exc:
                w.status_label.setText(f'Could not reset saved tree results: {exc}')
        self.refresh()

    def completed(self, *_):
        w = self.window
        if w.workspace:
            records = {}
            names = {reader.index: reader.name for reader in self.readers()}
            for nodeid, row in w.model._by_nodeid.items():
                for index, status in row.statuses.items():
                    if status.is_final and index in names:
                        records.setdefault(nodeid, {})[names[index]] = dict(status=status.name, meta=dict(w.model._run_meta))
            try:
                self.store.merge(w.workspace.path, records)
            except (OSError, ValueError, TypeError) as exc:
                w.status_label.setText(f'Could not save tree results: {exc}')
        self.refresh()

    def apply_preference(self):
        if not self.enabled:
            self._hidden_previous = dict(self.window.model._retained)
            self.window.model.set_retained_results({})
            self.window.results.set_result_origins({})
        else:
            self.collected(True, self._hidden_previous or None)
            self._hidden_previous = {}
        index = self.window.tree.currentIndex()
        if index.isValid() and not self.window.profile_tree_button.isChecked():
            self.window._select_test(index)
        self.refresh()

    def clear(self):
        self.refresh()
        if not self.button.isEnabled():
            return
        w = self.window
        if w.workspace:
            try:
                self.store.write(w.workspace.path, {})
            except OSError as exc:
                w.status_label.setText(f'Could not clear saved tree results: {exc}')
                return
        w._cleared_run_counts = w._run_status_counts()
        self._hidden_previous = {}
        w.model.clear_statuses()
        w.model.clear_stress_annotation()
        w.profile_model.clear_statuses()
        w._clear_status_filter()
        for panel in (w.results, w.profile_results):
            panel._statuses = {}
            panel._nodeid = ''
            panel.set_result_origins({})
            panel.detail.clear()
        w.view_failures_button.hide()
        w.view_differences_button.hide()
        w.status_label.setText('Tree results cleared · saved History kept')
        w._update_actions()
        self.refresh()

    def show_origin(self, nodeids):
        w = self.window
        previous = {}
        for nodeid in nodeids:
            row = w.model._by_nodeid.get(nodeid)
            if row is None:
                continue
            for reader in self.readers():
                if w.model.is_previous(row, reader.index):
                    meta = w.model.result_source(nodeid, reader.index)
                    label = 'Previous run result'
                    if reader.name:
                        label += ' · ' + reader.name
                    if meta.get('at'):
                        try:
                            when = datetime.fromisoformat(str(meta['at'])).strftime('%d/%m/%Y %H:%M')
                        except ValueError:
                            when = str(meta['at'])
                        label += ' · ' + when
                    if meta.get('config'):
                        label += ' · ' + str(meta['config'])
                    previous.setdefault(reader.index, {})[label] = None
        note = ('\nIncludes results not executed in the latest run.' if len(nodeids) > 1
                else '\nNot executed in the latest run.')
        note += ' Output and logs show the latest run.'
        w.results.set_result_origins({reader: '\n'.join(labels) + note
                                     for reader, labels in previous.items()})
