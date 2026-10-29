"""An execution occurrence is a row, never a shared nodeid's last verdict."""

from collections import Counter
import yaml

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QColor

from runner.domain.models import Kind, Status, TestNode, worst
from runner.domain.reader_labels import badge_labels
from runner.domain.tree import build_sequence_tree
from runner.domain.execution_profile import profile_group_runs, group_path
from runner.ui import icons
from runner.ui.profile_group_delegate import GROUP_ROLE, EXCEPTION_ROLE, YAML_ROLE, GROUP_COLOR_ROLE, CONFIG_ISSUES_ROLE
from runner.domain.profile_configuration import configuration_annotation, aggregate_annotations
from runner.ui.tree_model import TestTreeModel, _Row, NODEID_ROLE


class LiveProfileModel(TestTreeModel):
    def _leaf_nodeid(self, row):
        return self.locations.get(row.node.nodeid, (0, 0, row.node.nodeid))[2]

    def _folder_depth(self, row):
        return max(0, super()._folder_depth(row) - 1)

    # Pas de colonne Duration ici : une ligne est une etape de la sequence,
    # pas un test, et ses durees ne passent pas par ce modele.
    @property
    def duration_column(self) -> int:
        return -1

    def columnCount(self, parent=QModelIndex()) -> int:
        return 1 + max(1, len(self._readers))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.configuration_base = {}
        self.locations = {}
        self._named_groups = {}
        self._yaml_exceptions = {}
        self._group_exceptions = {}
        self._group_counts = {}
        self._annotations = {}
        self._group_colors = {}
        self._membership = {}
        self._configuration_issues = []
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
        self._badges = badge_labels([r.name for r in readers])
        if new_count > old_count:
            self.endInsertColumns()
        elif new_count < old_count:
            self.endRemoveColumns()
        self.headerDataChanged.emit(Qt.Horizontal, 1, new_count - 1)
        self.layoutChanged.emit()

    def prepare(self, profile, readers):
        self.locations = {}
        self._named_groups = {}
        self._yaml_exceptions = {}
        self._group_exceptions = {}
        self._group_counts = {}
        self._annotations = {}
        self._group_colors = {}
        self._membership = {}
        self._configuration_issues = []
        self._stopped = False
        self._interrupted = set()
        self.sequence_length = len(profile.sequence)
        self.repetitions = max(1, profile.execution.repetitions)
        roots = []
        try:
            base = yaml.safe_load(profile.configuration_text) if profile.configuration_text else self.configuration_base
        except yaml.YAMLError as exc:
            base = {}
            self._configuration_issues = ['Profile YAML: ' + str(exc)]
        if not isinstance(base, dict):
            base = {}
            self._configuration_issues = ['Profile YAML: the YAML configuration must contain a mapping.']
        for repetition in range(self.repetitions):
            children = []
            for start, end, entry in profile_group_runs(profile.sequence, profile.step_groups):
                siblings = children
                path = group_path(entry)
                for group in path:
                    last = siblings[-1] if siblings else None
                    previous = self._named_groups.get(id(last))
                    if previous and previous['id'] == group['id']:
                        node = last
                    else:
                        node = TestNode(name=group['name'], kind=Kind.FOLDER)
                        self._named_groups[id(node)] = group
                        siblings.append(node)
                    siblings = node.children
                nested = build_sequence_tree(profile.sequence[start:end])
                if path:
                    while len(nested) == 1 and nested[0].children:
                        nested = nested[0].children
                siblings.extend(nested)
            leaves = [leaf for child in children for leaf in child.leaves()]
            leaf_exceptions = {}
            leaf_annotations = {}
            for step, leaf in enumerate(leaves):
                path = group_path(profile.step_groups[step]) if profile.step_groups else []
                patch = profile.step_overrides[step] if profile.step_overrides else {}
                annotation = configuration_annotation(base, path, patch)
                leaf_annotations[id(leaf)] = annotation
                texts = annotation['exceptions']
                leaf_exceptions[id(leaf)] = texts
                self._yaml_exceptions[self.key(repetition * self.sequence_length + step)] = texts
            def label_groups(nodes, path=()):
                for node in nodes:
                    group = self._named_groups.get(id(node))
                    own_path = [*path, group] if group else list(path)
                    self._group_colors[id(node)] = own_path[-1]['color'] if own_path else ''
                    self._membership[id(node)] = ' / '.join(value['name'] for value in own_path)
                    annotations = [leaf_annotations[id(leaf)] for leaf in node.leaves()]
                    annotation = (configuration_annotation(base, own_path) if group else
                                  leaf_annotations[id(node)] if node.nodeid else
                                  aggregate_annotations(annotations, configuration_annotation(base, own_path, {})))
                    self._annotations[id(node)] = annotation
                    if not node.nodeid:
                        self._group_exceptions[id(node)] = list(dict.fromkeys(
                            text for value in annotations for text in value['exceptions']))
                    if group:
                        count = sum(1 for _ in node.leaves())
                        node.name = f'{group["name"]} · {count} test{"s" if count != 1 else ""}'
                        if group.get('configuration_overrides'):
                            node.name += ' · Custom YAML'
                        warnings = [text for leaf in node.leaves() for text in leaf_exceptions.get(id(leaf), [])]
                        self._group_exceptions[id(node)] = warnings
                        if group['description']:
                            node.name += '\n' + group['description']
                    label_groups(node.children, own_path)
            label_groups(children)
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
            self._yaml_exceptions[key] = self._yaml_exceptions.get(self.key(position), [])
            self._annotations[id(node)] = self._annotations.get(id(base.node), {})
            self._group_colors[id(node)] = self._group_colors.get(id(base.node), '')
            self._membership[id(node)] = self._membership.get(id(base.node), '')
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
        self._repaint_divergence(row)
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
        group = self._named_groups.get(id(row.node))
        annotation = self._annotations.get(id(row.node), {})
        exceptions = self._group_exceptions.get(id(row.node), []) if row.node.children else self._yaml_exceptions.get(row.node.nodeid, [])
        if index.column() == 0:
            if role == YAML_ROLE:
                return annotation
            if role == GROUP_COLOR_ROLE:
                return self._group_colors.get(id(row.node), '')
            if role == CONFIG_ISSUES_ROLE:
                return self._configuration_issues
            if role == EXCEPTION_ROLE:
                return exceptions
            if role == Qt.DisplayRole and not group and row.node.nodeid and annotation.get('state') == 'custom':
                return row.node.name + ' · Custom YAML'
            if role in (Qt.ToolTipRole, Qt.AccessibleDescriptionRole):
                title = group['name'] + '\n' + group['description'] if group else self.locations.get(row.node.nodeid, (0, 0, row.node.name))[2]
                membership = self._membership.get(id(row.node), '')
                if membership:
                    title += '\nGroup: ' + membership
                if self._configuration_issues:
                    title += '\n\nConfiguration problem\n' + '\n'.join(self._configuration_issues)
                if annotation.get('tooltip'):
                    title += '\n\n' + annotation['tooltip']
                if annotation.get('state'):
                    title += '\n\nTo change values for future runs: edit this profile in Execution Profiles.'
                disabled = self.disabled_data(self.locations.get(row.node.nodeid, (0, 0, ''))[2], Qt.ToolTipRole)
                if disabled:
                    title += '\n\n' + disabled
                return title
        if group and index.column() == 0:
            if role == GROUP_ROLE:
                return group
            if role == Qt.DecorationRole:
                return icons.icon('mdi.folder', group['color'])
            if role == Qt.ToolTipRole:
                return group['name'] + '\n' + group['description']
            if role == Qt.BackgroundRole:
                tint = QColor(group['color'])
                tint.setAlpha(24)
                return tint
        if index.column() == 0:
            nodeid = self.locations.get(row.node.nodeid, (0, 0, ''))[2]
            disabled = self.disabled_data(nodeid, role)
            if disabled is not None:
                return disabled
            if role == Qt.DecorationRole:
                return icons.kind_icon(row.node.kind, self._group_colors.get(id(row.node), ''))
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
