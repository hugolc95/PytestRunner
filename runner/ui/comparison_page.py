"""Persistent multi-run comparison, shared by navigation and history shortcuts."""
from collections import Counter
from html import escape
import json
from pathlib import Path

import yaml
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QCheckBox, QTreeView, QSplitter, QTextBrowser, QTabWidget, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox, QLineEdit, QHeaderView,
    QFileDialog, QMessageBox, QStackedWidget, QSizePolicy, QLayout,
)
from runner.domain.models import Status, worst
from runner.domain.tree import build_tree
from runner.domain.failures import index_failures, failure_for
from runner.ui.history_execution_tree import HistoryExecutionModel
from runner.ui.history_dashboard import group_entries
from runner.ui import icons, tokens as t
from runner.ui.comparison_export import export_comparison_xlsx

NODE = Qt.UserRole + 31


def records_by_reader(group):
    readers = {}
    for entry in group.entries:
        tests = readers.setdefault(entry.reader, {})
        for nodeid, verdict in HistoryExecutionModel.records(entry):
            tests.setdefault(nodeid, []).append(Status.__members__.get(verdict, Status.PENDING))
    return readers


def verdict(values):
    if not values:
        return None
    result = worst(values)
    return Status.PENDING if Status.PENDING in values and not result.is_bad else result


def configuration(group):
    """Compare recorded values, never today's workspace configuration."""
    snapshot = next((e.replay_profile for e in group.entries if e.replay_profile is not None), None)
    if snapshot is None:
        return None
    result = {}
    def flatten(value, path):
        if isinstance(value, dict) and value:
            for key, child in value.items():
                flatten(child, f"{path}.{key}" if path else str(key))
        else:
            result[path] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    try:
        flatten(yaml.safe_load(snapshot.get('configuration_text', '')) or {}, 'YAML')
    except yaml.YAMLError:
        result['YAML'] = 'Unreadable archived YAML'
    flatten(snapshot.get('execution', {}), 'Execution')
    flatten(snapshot.get('reports', {}), 'Reports')
    return result


class ComparisonPage(QWidget):
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.history = history
        self.groups = []
        self._records = []
        self._failures = {}
        self._test = ''
        self._expanded_traces = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SPACE_4, t.SPACE_4, t.SPACE_4, t.SPACE_4)
        heading = QHBoxLayout()
        copy_box = QVBoxLayout()
        title = QLabel('Compare executions')
        title.setObjectName('PageTitle')
        subtitle = QLabel('Compare results across multiple historical runs.')
        subtitle.setObjectName('Muted')
        copy_box.addWidget(title)
        copy_box.addWidget(subtitle)
        heading.addLayout(copy_box)
        heading.addStretch(1)
        self.export_button = QPushButton('Export Excel')
        self.export_button.setIcon(icons.icon('mdi.file-excel-outline'))
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_excel)
        heading.addWidget(self.export_button)
        layout.addLayout(heading)

        self.selection_row = QHBoxLayout()
        self.selection_row.setSpacing(t.SPACE_2)
        self.choose = QPushButton('+ Add Run')
        self.choose.setObjectName('Primary')
        self.choose.clicked.connect(self.choose_runs)
        self.selection_row.addWidget(self.choose)
        self.selection_row.addStretch(1)
        layout.addLayout(self.selection_row)

        self.selection_label = QLabel('Choose at least two runs from the same workspace.')
        self.selection_label.setWordWrap(True)
        self.selection_label.setObjectName('Muted')
        layout.addWidget(self.selection_label)
        controls = QHBoxLayout()
        self.reference = QComboBox()
        self.reference.setAccessibleName('Reference run')
        self.reader = QComboBox()
        self.reader.setAccessibleName('Comparison reader')
        self.differences = QCheckBox('Differences only')
        self.differences.setChecked(True)
        controls.addWidget(QLabel('Reference'))
        controls.addWidget(self.reference, 1)
        controls.addWidget(QLabel('Reader'))
        controls.addWidget(self.reader, 1)
        controls.addWidget(self.differences)
        layout.addLayout(controls)
        self.tabs = QTabWidget()
        results = QWidget()
        result_layout = QVBoxLayout(results)
        result_layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        result_layout.addWidget(self.summary)
        self.tree = QTreeView()
        self.model = QStandardItemModel(self)
        self.tree.setModel(self.model)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QTreeView.NoEditTriggers)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setStretchLastSection(False)
        self.tree.clicked.connect(self._select_test)
        self.tree.selectionModel().currentChanged.connect(self._select_test)
        self.detail = QTextBrowser()
        self.detail.setMinimumHeight(260)
        self.detail.setOpenExternalLinks(False)
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(self._toggle_trace)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tree)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 2)
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(split)
        self.empty_results = QWidget()
        self.empty_results.setObjectName('ComparisonEmpty')
        empty_layout = QVBoxLayout(self.empty_results)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch()
        empty_content = QWidget()
        empty_content.setObjectName('ComparisonEmptyContent')
        empty_content.setMaximumWidth(560)
        content_layout = QVBoxLayout(empty_content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)
        content_layout.setSizeConstraint(QLayout.SetMinimumSize)
        empty_content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        empty_layout.addWidget(empty_content, 0, Qt.AlignHCenter)
        self.empty_icon = QLabel()
        self.empty_icon.setObjectName('ComparisonEqualIcon')
        self.empty_icon.setFixedSize(48, 48)
        self.empty_title = QLabel()
        self.empty_title.setMinimumHeight(32)
        self.empty_title.setObjectName('PageTitle')
        self.empty_message = QLabel()
        self.empty_message.setWordWrap(True)
        self.empty_scope = QLabel()
        self.empty_scope.setWordWrap(True)
        self.empty_scope.setObjectName('Muted')
        for label in (self.empty_icon, self.empty_title, self.empty_message, self.empty_scope):
            label.setAlignment(Qt.AlignCenter)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            content_layout.addWidget(label, 0, Qt.AlignHCenter if label is self.empty_icon else Qt.Alignment())
            if label is self.empty_icon:
                content_layout.addSpacing(14)
        self.show_all_results = QPushButton('Show all results')
        self.show_all_results.clicked.connect(lambda: self.differences.setChecked(False))
        content_layout.addSpacing(10)
        content_layout.addWidget(self.show_all_results, 0, Qt.AlignHCenter)
        note = QLabel('Configurations are compared separately in the Configuration tab.')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        content_layout.addSpacing(8)
        content_layout.addWidget(note)
        empty_layout.addStretch()
        self.results_stack.addWidget(self.empty_results)
        result_layout.addWidget(self.results_stack)
        self.config_tree = QTreeView()
        self.config_model = QStandardItemModel(self)
        self.config_tree.setModel(self.config_model)
        self.config_tree.setEditTriggers(QTreeView.NoEditTriggers)
        self.config_tree.setUniformRowHeights(True)
        self.tabs.addTab(results, 'Results')
        self.tabs.addTab(self.config_tree, 'Configuration')
        layout.addWidget(self.tabs, 1)
        foot = QLabel('Global verdict = worst recorded result. Repeated executions remain in the details. '
                      'Not run and Unknown are distinct from Skipped.')
        foot.setWordWrap(True)
        foot.setObjectName('Muted')
        layout.addWidget(foot)
        self.reference.currentIndexChanged.connect(self.rebuild)
        self.reader.currentIndexChanged.connect(self.rebuild)
        self.differences.toggled.connect(self.rebuild)
        self.rebuild()

    def _rebuild_selection_row(self):
        while self.selection_row.count():
            item = self.selection_row.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.choose:
                widget.deleteLater()

        for group in self.groups:
            chip = QPushButton(f'{group.display_name}  ×')
            chip.setToolTip(f'Remove {group.display_name} from comparison')
            chip.clicked.connect(lambda _checked=False, run_id=group.id: self._remove_group(run_id))
            self.selection_row.addWidget(chip)

        self.selection_row.addWidget(self.choose)
        self.selection_row.addStretch(1)

    def _remove_group(self, run_id):
        self.set_groups([group for group in self.groups if group.id != run_id])

    def choose_runs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Choose runs to compare')
        dialog.resize(650, 480)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText('Find a run, profile or workspace…')
        listing = QListWidget()
        available = group_entries(self.history.entries())
        for group in available:
            item = QListWidgetItem(f'{group.display_name} · {group.workspace} · {group.id}')
            item.setData(Qt.UserRole, group)
            item.setCheckState(Qt.Checked if any(g.id == group.id for g in self.groups) else Qt.Unchecked)
            listing.addItem(item)
        notice = QLabel()
        notice.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        def selected():
            return [listing.item(i).data(Qt.UserRole) for i in range(listing.count())
                    if listing.item(i).checkState() == Qt.Checked]
        def update():
            groups = selected()
            valid = len(groups) >= 2 and len({g.workspace for g in groups}) == 1
            buttons.button(QDialogButtonBox.Ok).setEnabled(valid)
            notice.setText(f'{len(groups)} runs selected' if valid else
                           'Select at least two runs from the same workspace.')
        listing.itemChanged.connect(update)
        search.textChanged.connect(lambda text: [listing.item(i).setHidden(
            text.casefold() not in listing.item(i).text().casefold()) for i in range(listing.count())])
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        for widget in (search, listing, notice, buttons):
            layout.addWidget(widget)
        update()
        if dialog.exec() == QDialog.Accepted:
            self.set_groups(selected())

    def set_groups(self, groups):
        if groups and len({g.workspace for g in groups}) != 1:
            raise ValueError('Runs must belong to the same workspace.')
        previous_base, previous_reader = self.reference.currentData(), self.reader.currentData()
        self.groups = sorted({g.id: g for g in groups}.values(), key=lambda g: g.timestamp)
        self._records = [records_by_reader(g) for g in self.groups]
        self._failures.clear()
        for combo in (self.reference, self.reader):
            combo.blockSignals(True)
            combo.clear()
        for group in self.groups:
            self.reference.addItem(f'{group.display_name} · {group.id}', group.id)
        self.reference.setCurrentIndex(max(0, self.reference.findData(previous_base)))
        self.reader.addItem('All readers · global result', None)
        for name in sorted({name for record in self._records for name in record}):
            self.reader.addItem(name or 'No reader', name)
        self.reader.setCurrentIndex(max(0, self.reader.findData(previous_reader)))
        for combo in (self.reference, self.reader):
            combo.blockSignals(False)
        self._rebuild_selection_row()
        self.export_button.setEnabled(len(self.groups) >= 2)
        self.selection_label.setText(
            f'{len(self.groups)} runs selected' if self.groups
            else 'Choose at least two runs from the same workspace.')
        self.rebuild()

    def export_excel(self):
        if len(self.groups) < 2:
            return
        suggested = 'pytest_comparison.xlsx'
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export comparison to Excel', suggested, 'Excel workbook (*.xlsx)')
        if not path:
            return
        if not path.lower().endswith('.xlsx'):
            path += '.xlsx'
        try:
            # Read the archived records again instead of exporting a stale UI cache.
            self.refresh()
            self._records = [records_by_reader(group) for group in self.groups]
            export_comparison_xlsx(path, self.groups, self._records, verdict)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, 'Export failed', str(exc))
            return
        confirmation = QMessageBox(self)
        confirmation.setIcon(QMessageBox.Information)
        confirmation.setWindowTitle('Export complete')
        confirmation.setTextFormat(Qt.PlainText)
        confirmation.setText(f'Comparison exported to:\n{path}')
        open_button = confirmation.addButton('Open Excel', QMessageBox.ActionRole)
        confirmation.addButton(QMessageBox.Close)
        confirmation.exec()
        if confirmation.clickedButton() is open_button:
            url = QUrl.fromLocalFile(str(Path(path).resolve()))
            if not QDesktopServices.openUrl(url):
                QMessageBox.warning(
                    self, 'Unable to open Excel',
                    f'The report was saved, but could not be opened automatically.\n'
                    f'Open it manually with Excel or another spreadsheet application:\n{path}')

    def refresh(self):
        available = {g.id: g for g in group_entries(self.history.entries())}
        updated = [available[g.id] for g in self.groups if g.id in available]
        if updated != self.groups:
            self.set_groups(updated)

    def values(self, run, nodeid):
        reader = self.reader.currentData()
        record = self._records[run]
        return [s for name, tests in record.items() if reader is None or name == reader
                for s in tests.get(nodeid, ())]

    def signature(self, run, nodeid):
        reader = self.reader.currentData()
        return tuple((name, tuple(s.name for s in tests.get(nodeid, ())))
                     for name, tests in sorted(self._records[run].items())
                     if reader is None or name == reader)

    def rebuild(self, *_):
        for tree in (self.tree, self.config_tree):
            tree.setStyleSheet(
                f"QTreeView {{background:{t.BG_SURFACE};color:{t.TEXT};"
                f"selection-background-color:{t.BG_HOVER};selection-color:{t.TEXT};}}"
                f"QTreeView::item:selected {{background:{t.BG_HOVER};color:{t.TEXT};}}")
        self.model.clear()
        self.config_model.clear()
        self.detail.clear()
        self.results_stack.setCurrentIndex(0)
        self.empty_results.setStyleSheet(
            f'QWidget#ComparisonEmpty {{background:{t.BG_SURFACE};border:1px solid {t.BORDER};border-radius:8px;}}'
            f'QWidget#ComparisonEmptyContent {{background:transparent;border:none;}}'
            f'QWidget#ComparisonEmpty QLabel {{background:transparent;border:none;margin:0;padding:0;color:{t.TEXT};}}'
            f'QWidget#ComparisonEmpty QLabel#Muted {{color:{t.TEXT_MUTED};}}'
            f'QWidget#ComparisonEmpty QLabel#PageTitle {{font-size:20px;font-weight:600;}}'
            f'QWidget#ComparisonEmpty QLabel#ComparisonEqualIcon {{background:{t.blend(t.ACCENT, t.BG_SURFACE, 0.12)};border-radius:12px;}}')
        if len(self.groups) < 2:
            self.summary.setText('Select two or more runs to build the comparison matrix.')
            return
        base = max(0, self.reference.currentIndex())
        headers = ['Test / parent'] + [g.display_name + (' · Reference' if i == base else '')
                                      for i, g in enumerate(self.groups)]
        self.model.setHorizontalHeaderLabels(headers)
        nodes = list(dict.fromkeys(node for record in self._records for tests in record.values() for node in tests))
        visible = [node for node in nodes if not self.differences.isChecked()
                   or len({self.signature(i, node) for i in range(len(self.groups))}) > 1]
        def fill(parent, node):
            label = QStandardItem(node.name)
            label.setData(node.nodeid, NODE)
            label.setToolTip(node.nodeid or node.name)
            label.setIcon(icons.kind_icon(node.kind))
            leaves = [leaf.nodeid for leaf in node.leaves()]
            row = [label]
            base_values = [s for leaf in leaves for s in self.values(base, leaf)]
            for i in range(len(self.groups)):
                values = [s for leaf in leaves for s in self.values(i, leaf)]
                status = verdict(values)
                text = 'Not run' if status is None else 'Unknown' if status is Status.PENDING else status.label
                if node.nodeid and len(values) > 1:
                    text += f' ({len(values)})'
                item = QStandardItem(text)
                if status is not None:
                    item.setIcon(icons.status_icon(status, group=not bool(node.nodeid)))
                    item.setForeground(QColor(t.status_color(status)))
                if i != base and Counter(values) != Counter(base_values):
                    item.setBackground(QColor(t.BG_RAISED))
                item.setToolTip(', '.join(f'{s.label}: {count}' for s, count in Counter(values).items()) or 'Test not recorded in this run')
                row.append(item)
            parent.appendRow(row)
            for child in node.children:
                fill(label, child)
        for root in build_tree(visible):
            fill(self.model.invisibleRootItem(), root)
        self.tree.setColumnWidth(0, 340)
        self.tree.header().setMinimumSectionSize(150)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        for i in range(len(self.groups)):
            self.tree.header().setSectionResizeMode(i + 1, QHeaderView.Stretch)
        self.tree.expandToDepth(1)
        self.summary.setText(f'{len(visible)} / {len(nodes)} tests · {len(self.groups)} runs · '
                             'Compare the same test across columns; select it for reader details.')
        self._build_config(headers, base)
        if not visible:
            self.results_stack.setCurrentWidget(self.empty_results)
            selected_reader = self.reader.currentData()
            scoped_nodes = [node for node in nodes if any(self.values(i, node) for i in range(len(self.groups)))]
            complete = bool(scoped_nodes) and all(
                self.values(i, node) and all(s.is_final for s in self.values(i, node))
                for node in scoped_nodes for i in range(len(self.groups)))
            if not scoped_nodes:
                title = 'No recorded results'
                message = 'There are no test results to compare for the selected reader scope.'
            elif not complete:
                title = 'No differences in available results'
                message = 'Some results are missing or unknown. Identical results cannot be confirmed.'
            else:
                title = 'No result differences'
                message = (f'The {len(scoped_nodes)} compared tests have identical recorded results '
                           f'across these {len(self.groups)} runs.')
            self.empty_title.setText(title)
            self.empty_message.setText(message)
            scope = 'All readers' if selected_reader is None else selected_reader or 'No reader'
            self.empty_scope.setText(scope + ' · ' + ' ↔ '.join(g.display_name for g in self.groups))
            self.empty_scope.setTextFormat(Qt.PlainText)
            self.empty_icon.setPixmap(icons.icon('mdi.equal' if complete else 'mdi.information-outline', t.ACCENT).pixmap(32, 32))
            self.show_all_results.setVisible(bool(nodes) and self.differences.isChecked())
            self.summary.setText(f'{len(scoped_nodes)} tests compared · {len(self.groups)} runs · {title}')
        if self._test in visible:
            self._show_detail(self._test)

    def _build_config(self, headers, base):
        self.config_model.setHorizontalHeaderLabels(['Recorded setting'] + headers[1:])
        configs = [configuration(g) for g in self.groups]
        keys = sorted({key for config in configs if config for key in config})
        if not keys:
            keys = ['Configuration snapshot']
        for key in keys:
            values = ['Not archived' if config is None else config.get(key, 'Not set') for config in configs]
            if self.differences.isChecked() and len(set(values)) == 1 and all(config is not None for config in configs):
                continue
            row = [QStandardItem(key)]
            for i, value in enumerate(values):
                item = QStandardItem(value)
                item.setToolTip(value)
                if value != values[base]:
                    item.setBackground(QColor(t.BG_RAISED))
                row.append(item)
            self.config_model.appendRow(row)
        for i in range(len(headers)):
            self.config_tree.setColumnWidth(i, 280 if i == 0 else 210)

    def _select_test(self, index, *_):
        node = index.siblingAtColumn(0).data(NODE)
        if node:
            self._test = node
            self._show_detail(node)
        else:
            self.detail.clear()

    def _show_detail(self, node):
        reader = self.reader.currentData()
        base = max(0, self.reference.currentIndex())
        baseline = self.signature(base, node)
        base_status = verdict(self.values(base, node))
        def badge(status):
            label = 'Not run' if status is None else 'Unknown' if status is Status.PENDING else status.label
            color = t.TEXT_MUTED if status is None else t.status_color(status)
            icon = '' if status is None else f'<img src="status:{status.name}" width="14" height="14"> '
            return f'<span style="color:{color};font-weight:600">{icon}{escape(label)}</span>'
        for status in Status:
            self.detail.document().addResource(QTextDocument.ImageResource, QUrl(f'status:{status.name}'),
                                               icons.status_icon(status).pixmap(16, 16).toImage())
        transitions = []
        columns = []
        for i, group in enumerate(self.groups):
            status = verdict(self.values(i, node))
            changed = i != base and self.signature(i, node) != baseline
            color = t.TEXT_MUTED if status is None else t.status_color(status)
            if changed:
                change = (f'{badge(base_status)} &nbsp;→&nbsp; {badge(status)}' if status != base_status
                          else f'{badge(status)} · Reader results or repetitions changed')
                transitions.append(f'{change} &nbsp; <span style="color:{t.TEXT_MUTED}">{escape(group.display_name)} '
                                   f'vs {escape(self.groups[base].display_name)}</span>')
            parts = []
            for entry_index, entry in enumerate(group.entries):
                if reader is not None and reader != entry.reader:
                    continue
                values = self._records[i].get(entry.reader, {}).get(node, ())
                results = ' &nbsp;→&nbsp; '.join(badge(s) for s in values) or badge(None)
                parts.append(f'<p style="color:{t.TEXT_MUTED}">{escape(entry.reader or "No reader")}</p><p>{results}</p>')
                key = (group.id, entry.reader)
                if key not in self._failures:
                    self._failures[key] = index_failures(entry.output())
                failure = failure_for(self._failures[key], node)
                if failure and values:
                    label = 'Skip reason' if failure.kind == 'skip' else 'Failure'
                    if failure.phase:
                        label += f' · {failure.phase.upper()}'
                    parts.append(f'<p style="color:{t.TEXT_MUTED}">{escape(label)}</p>'
                                 f'<p>{escape(failure.body if failure.kind == "skip" else failure.headline)}</p>')
                    if failure.kind != 'skip' and failure.body:
                        trace_key = (node, group.id, entry_index)
                        expanded = trace_key in self._expanded_traces
                        parts.append(f'<p><a style="color:{t.ACCENT}" href="trace:{i}:{entry_index}">'
                                     f'{"Hide" if expanded else "Show"} traceback</a></p>')
                        if expanded:
                            parts.append(f'<pre style="white-space:pre-wrap;background-color:{t.BG_INPUT};'
                                         f'padding:10px">{escape(failure.body)}</pre>')
            tag = (f'<span style="color:{t.ACCENT}">Reference</span>' if i == base else
                   f'<span style="color:{color}">Changed</span>' if changed else '')
            background = t.blend(color, t.BG_SURFACE, 0.09) if changed else t.BG_SURFACE
            border = color if changed else t.BORDER
            columns.append(f'<td valign="top" width="{100 // len(self.groups)}%" '
                           f'style="background-color:{background};border-left:3px solid {border};padding:14px">'
                           f'<b>{escape(group.display_name)}</b> &nbsp;{tag}'
                           f'{"".join(parts) or "<p>Reader not present in this run.</p>"}</td>')
        self.detail.setHtml(
            f'<body style="font-family:Segoe UI;font-size:{t.TEXT_SM}px;color:{t.TEXT};">'
            f'<p style="color:{t.TEXT_MUTED}">TEST DETAILS</p><h3>{escape(node)}</h3>'
            f'{"".join(f"<p>{change}</p>" for change in transitions)}'
            f'<table width="100%" cellspacing="10"><tr>'
            f'{"".join(columns)}</tr></table></body>')

    def _toggle_trace(self, url):
        if url.scheme() != 'trace' or not self._test:
            return
        try:
            run, entry = map(int, url.path().split(':'))
            if not (0 <= run < len(self.groups) and 0 <= entry < len(self.groups[run].entries)):
                return
        except ValueError:
            return
        key = (self._test, self.groups[run].id, entry)
        if key in self._expanded_traces:
            self._expanded_traces.remove(key)
        else:
            self._expanded_traces.add(key)
        scroll = self.detail.verticalScrollBar().value()
        self._show_detail(self._test)
        self.detail.verticalScrollBar().setValue(scroll)

    def restyle(self):
        self.rebuild()
