"""Read-only, virtualized history tree, including repeated executions."""

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from runner.domain.models import Status, worst, TestNode, Kind
from runner.domain.tree import build_sequence_tree, build_tree
from runner.ui.tree_model import TestTreeModel, NODEID_ROLE
from runner.ui import tokens as t


class HistoryExecutionModel(TestTreeModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._original_ids = {}
        self._unknown_label = 'Unknown (older run)'

    @staticmethod
    def records(entry):
        if entry.executions:
            records = list(entry.executions)
        else:
            occurrences = Counter(entry.nodeids)
            records = []
            failed = set(entry.failed_nodeids)
            for nodeid in entry.nodeids:
                # A final per-test verdict cannot describe earlier repetitions.
                status = entry.test_statuses.get(nodeid, '') if occurrences[nodeid] == 1 else ''
                if not status and occurrences[nodeid] == 1 and entry.total >= len(entry.nodeids):
                    candidates = [s for s in Status if s.is_final and entry.count(s)
                                  and s.is_bad == (nodeid in failed)]
                    if len(candidates) == 1:
                        status = candidates[0].name
                records.append((nodeid, status))
        return records

    def set_entry(self, entry):
        self._contexts = {}
        records = self.records(entry)
        roots = build_sequence_tree(nodeid for nodeid, _ in records)
        original_ids = {}
        statuses = {}
        leaves = (leaf for root in roots for leaf in root.leaves())
        for position, (leaf, (nodeid, status)) in enumerate(zip(leaves, records), 1):
            key = str(position)
            original_ids[key] = nodeid
            statuses[key] = Status.__members__.get(status, Status.PENDING)
            leaf.nodeid = key
            leaf.name = f'{position} · {leaf.name}'
        self._original_ids = original_ids
        self.set_tree(roots)
        # Fill once, without 50,000 dataChanged notifications or widgets.
        for key, status in statuses.items():
            self._by_nodeid[key].statuses[0] = status
            self._tally[status] = self._tally.get(status, 0) + 1

        def aggregate(row):
            if row.is_leaf:
                return row.statuses.get(0, Status.PENDING)
            row.agg[0] = worst(aggregate(child) for child in row.children)
            return row.agg[0]

        for root in self._roots:
            aggregate(root)

    def set_entries(self, entries):
        """One global row per test, then readers and repeated attempts underneath."""
        per_reader = []
        order = dict.fromkeys(nodeid for entry in entries for nodeid, _ in self.records(entry))
        for entry in entries:
            grouped = {}
            for nodeid, status in self.records(entry):
                grouped.setdefault(nodeid, []).append(Status.__members__.get(status, Status.PENDING))
            per_reader.append(grouped)
        roots = build_tree(order)
        tests = {leaf.nodeid: leaf for root in roots for leaf in root.leaves()}
        original_ids, contexts, values = {}, {}, {}
        for number, nodeid in enumerate(order, 1):
            key = str(number)
            parent = tests[nodeid]
            parent.nodeid = key
            original_ids[key] = nodeid
            contexts[key] = None
            for reader_index, (entry, records) in enumerate(zip(entries, per_reader)):
                child_key = f"{key}:r{reader_index}"
                results = records.get(nodeid, [Status.PENDING])
                child = TestNode(entry.reader or "No reader", Kind.CASE, child_key)
                original_ids[child_key] = nodeid
                contexts[child_key] = reader_index
                if len(results) > 1:
                    for attempt, status in enumerate(results, 1):
                        attempt_key = f"{child_key}:{attempt}"
                        child.children.append(TestNode(f"Execution {attempt}", Kind.CASE, attempt_key))
                        original_ids[attempt_key] = nodeid
                        contexts[attempt_key] = reader_index
                        values[attempt_key] = status
                else:
                    values[child_key] = results[0]
                parent.children.append(child)
        self._original_ids, self._contexts = original_ids, contexts
        self.set_tree(roots)
        def fill(row):
            if row.is_leaf:
                status = values[row.node.nodeid]
                row.statuses[0] = status
                return status
            statuses = [fill(child) for child in row.children]
            status = worst(statuses)
            if Status.PENDING in statuses and not status.is_bad:
                status = Status.PENDING
            row.agg[0] = status
            return status
        for root in self._roots:
            fill(root)

    def reader_for_index(self, index):
        return self._contexts.get(index.internalPointer().node.nodeid) if index.isValid() else None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable if index.isValid() else Qt.NoItemFlags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return 'Execution / Test' if section == 0 else 'Result'
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.internalPointer()
        if role == Qt.CheckStateRole:
            return None
        if role == NODEID_ROLE:
            return self._original_ids.get(row.node.nodeid, '')
        if role == Qt.ToolTipRole:
            return self._original_ids.get(row.node.nodeid, row.node.name)
        if index.column() == 1:
            status = self.status_for(row, 0)
            if role == Qt.DisplayRole:
                return self._unknown_label if status is Status.PENDING else status.label
            if role == Qt.ForegroundRole:
                return QColor(t.status_color(status))
        return super().data(index, role)
