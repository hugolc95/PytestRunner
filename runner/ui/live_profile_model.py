"""An execution occurrence is a row, never a shared nodeid's last verdict."""

from collections import Counter

from PySide6.QtCore import Qt, QModelIndex

from runner.domain.models import Kind, Status, TestNode, worst
from runner.domain.tree import build_sequence_tree
from runner.ui.tree_model import TestTreeModel, _Row, NODEID_ROLE


class LiveProfileModel(TestTreeModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.locations = {}
        self._group_counts = {}
        self._stopped = False
        self._interrupted = set()

    @staticmethod
    def key(position, attempt=0):
        return f'{position}:{attempt}'

    def set_readers(self, readers):
        """Change status columns without resetting expanded execution rows."""
        readers = tuple(readers)
        if readers == self.readers:
            return
        old_count = self.columnCount()
        new_count = 1 + max(1, len(readers))
        if new_count > old_count:
            self.beginInsertColumns(QModelIndex(), old_count, new_count - 1)
        elif new_count < old_count:
            self.beginRemoveColumns(QModelIndex(), new_count, old_count - 1)
        self._readers = readers
        if new_count > old_count:
            self.endInsertColumns()
        elif new_count < old_count:
            self.endRemoveColumns()
        self.headerDataChanged.emit(Qt.Horizontal, 1, new_count - 1)
        self.layoutChanged.emit()

    def prepare(self, profile, readers):
        self.locations = {}
        self._group_counts = {}
        self._stopped = False
        self._interrupted = set()
        self.sequence_length = len(profile.sequence)
        self.repetitions = max(1, profile.execution.repetitions)
        roots = []
        for repetition in range(self.repetitions):
            children = build_sequence_tree(profile.sequence)
            leaves = [leaf for child in children for leaf in child.leaves()]
            for step, leaf in enumerate(leaves):
                position = repetition * self.sequence_length + step
                key = self.key(position)
                self.locations[key] = (position, 0, leaf.nodeid)
                leaf.nodeid = key
                leaf.name = f'{position + 1} · {leaf.name}'
            roots.append(TestNode(name=f'Repetition {repetition + 1} / {self.repetitions}',
                                  kind=Kind.FOLDER, children=children))
        self.set_tree(roots)
        self.set_readers(tuple(readers))

    def apply_execution(self, position, attempt, reader, nodeid, status):
        key = self.key(position, attempt)
        if key not in self._by_nodeid:
            base = self._by_nodeid.get(self.key(position))
            if base is None:
                return
            parent = base.parent
            siblings = parent.children if parent else self._roots
            insertion = base.row + 1
            while insertion < len(siblings) and self.locations.get(siblings[insertion].node.nodeid, (None,))[0] == position:
                insertion += 1
            parent_index = self.createIndex(parent.row, 0, parent) if parent else self.parent(self.index_for_nodeid(self.key(position)))
            self.beginInsertRows(parent_index, insertion, insertion)
            node = TestNode(name=f'{position + 1} · Retry {attempt} · {nodeid.split("::")[-1]}', kind=Kind.TEST, nodeid=key)
            row = _Row(node, parent, insertion)
            siblings.insert(insertion, row)
            for i in range(insertion + 1, len(siblings)):
                siblings[i].row = i
            self._by_nodeid[key] = row
            self.locations[key] = (position, attempt, nodeid)
            self.endInsertRows()
        row = self._by_nodeid[key]
        previous = row.statuses.get(reader)
        if previous is status:
            return
        row.statuses[reader] = status
        columns = [r.index for r in self.readers] or [0]
        if reader not in columns:
            return
        column = columns.index(reader) + 1
        index = self.createIndex(row.row, column, row)
        self.dataChanged.emit(index, index)
        parent = row.parent
        while parent:
            counts = self._group_counts.setdefault((parent, reader), Counter())
            if previous is not None:
                counts[previous] -= 1
            counts[status] += 1
            value = worst(s for s, count in counts.items() if count > 0)
            if parent.agg.get(reader) != value:
                parent.agg[reader] = value
                index = self.createIndex(parent.row, column, parent)
                self.dataChanged.emit(index, index)
            parent = parent.parent

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable if index.isValid() else Qt.NoItemFlags

    def finish(self):
        self._stopped = True
        for key, row in self._by_nodeid.items():
            for reader, status in list(row.statuses.items()):
                if status is Status.RUNNING:
                    self._interrupted.add((key, reader))
                    position, attempt, nodeid = self.locations[key]
                    self.apply_execution(position, attempt, reader, nodeid, Status.PENDING)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role == Qt.CheckStateRole:
            return None
        row = index.internalPointer()
        if role == NODEID_ROLE:
            return self.locations.get(row.node.nodeid, (0, 0, ''))[2]
        if index.column() > 0:
            readers = [r.index for r in self.readers] or [0]
            reader = readers[index.column() - 1]
            if role == Qt.ToolTipRole:
                if (row.node.nodeid, reader) in self._interrupted:
                    return 'Interrupted'
                if self._stopped and self.status_for(row, reader) is Status.PENDING:
                    return 'Not run'
            return self._data_colonne_statut(row, reader, role)
        if role == Qt.ToolTipRole and row.node.nodeid in self.locations:
            return self.locations[row.node.nodeid][2]
        return super().data(index, role)
