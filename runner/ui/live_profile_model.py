"""An execution occurrence is a row, never a shared nodeid's last verdict."""

from collections import Counter
import yaml

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QColor

from runner.domain.models import Kind, Status, TestNode, worst
from runner.domain.reader_labels import badge_labels
from runner.domain.tree import build_sequence_tree, collapse_single_class
from runner.domain.execution_profile import profile_group_runs, group_path
from runner.ui import icons
from runner.ui import tokens as t
from runner.ui.profile_group_delegate import GROUP_ROLE, EXCEPTION_ROLE, YAML_ROLE, GROUP_COLOR_ROLE, CONFIG_ISSUES_ROLE, ACTIVE_ROLE
from runner.domain.profile_configuration import configuration_annotation, aggregate_annotations
from runner.ui.tree_model import TestTreeModel, _Row, NODEID_ROLE


class LiveProfileModel(TestTreeModel):
    def _leaf_nodeid(self, row):
        return self.locations.get(row.node.nodeid, (0, 0, row.node.nodeid))[2]

    def _folder_depth(self, row):
        depth = 0
        while row is not None:
            depth += self._hidden_folder_depths.get(id(row.node), 0)
            if (row.node.kind is Kind.FOLDER and id(row.node) not in self._named_groups
                    and id(row.node) not in self._repetition_roots):
                depth += 1
            row = row.parent
        return depth

    def _target_for_row(self, row):
        if id(row.node) in self._named_groups or id(row.node) in self._repetition_roots:
            return ''
        return super()._target_for_row(row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.configuration_base = {}
        self.locations = {}
        self._keys_by_position = {}
        self._named_groups = {}
        self._hidden_folder_depths = {}
        self._repetition_roots = set()
        self._yaml_exceptions = {}
        self._group_exceptions = {}
        self._group_counts = {}
        self._annotations = {}
        self._group_colors = {}
        self._membership = {}
        self._configuration_issues = []
        self._stopped = False
        self._interrupted = set()
        self.previous_results = set()
        self._preparing_by_reader = {}
        self._preparing_rows = Counter()

    @staticmethod
    def key(position, attempt=0):
        return f'{position}:{attempt}'

    def set_readers(self, readers):
        """Change status columns without resetting expanded execution rows."""
        readers = tuple(readers)
        if readers == self.readers:
            return
        old_count = self.columnCount()
        new_count = 2 + max(1, len(readers))
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
        self._preparing_by_reader.clear()
        self._preparing_rows.clear()
        self.locations = {}
        self._keys_by_position = {}
        self._named_groups = {}
        self._hidden_folder_depths = {}
        self._repetition_roots = set()
        self._yaml_exceptions = {}
        self._group_exceptions = {}
        self._group_counts = {}
        self._annotations = {}
        self._group_colors = {}
        self._membership = {}
        self._configuration_issues = []
        self._stopped = False
        self._interrupted = set()
        self.previous_results = set()
        self.sequence_length = len(profile.sequence)
        self.nodeid_counts = Counter(profile.sequence)
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
                nested = collapse_single_class(build_sequence_tree(profile.sequence[start:end]))
                # Un groupe nomme donne deja le contexte : masquer la chaine
                # de dossiers commune, jamais le fichier ni les cas parametres.
                hidden = 0
                if path:
                    while len(nested) == 1 and nested[0].kind is Kind.FOLDER and nested[0].children:
                        nested = nested[0].children
                        hidden += 1
                if hidden:
                    for node in nested:
                        self._hidden_folder_depths[id(node)] = hidden
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
                self._keys_by_position[position] = {key}
                leaf.nodeid = key
            if self.repetitions > 1:
                node = TestNode(name=f'Repetition {repetition + 1} / {self.repetitions}',
                                kind=Kind.FOLDER, children=children)
                self._repetition_roots.add(id(node))
                roots.append(node)
            else:
                roots.extend(children)
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
            node = TestNode(name=f'{base.node.name} · Retry {attempt}', kind=base.node.kind, nodeid=key)
            row = _Row(node, parent, insertion)
            siblings.insert(insertion, row)
            for i in range(insertion + 1, len(siblings)):
                siblings[i].row = i
            self._by_nodeid[key] = row
            self.locations[key] = (position, attempt, nodeid)
            self._keys_by_position.setdefault(position, set()).add(key)
            self._yaml_exceptions[key] = self._yaml_exceptions.get(self.key(position), [])
            self._annotations[id(node)] = self._annotations.get(id(base.node), {})
            self._group_colors[id(node)] = self._group_colors.get(id(base.node), '')
            self._membership[id(node)] = self._membership.get(id(base.node), '')
            self._activation_targets[row] = nodeid
            if base in self._blocked_rows:
                self._blocked_rows.add(row)
                row.checked = False
            self.endInsertRows()
        row = self._by_nodeid[key]
        previous = row.statuses.get(reader)
        if previous is status:
            return
        row.statuses[reader] = status
        if (previous is Status.RUNNING) != (status is Status.RUNNING):
            name = self.createIndex(row.row, 0, row)
            self.dataChanged.emit(name, name, [Qt.DecorationRole, Qt.ForegroundRole, ACTIVE_ROLE])
        columns = [r.index for r in self.readers] or [0]
        if reader not in columns:
            return
        column = columns.index(reader) + 1
        index = self.createIndex(row.row, column, row)
        self.dataChanged.emit(index, index)
        self._repaint_divergence(row)
        parent = row.parent
        while parent:
            was_running = any(self._group_counts.get((parent, index), {}).get(Status.RUNNING, 0) for index in columns)
            counts = self._group_counts.setdefault((parent, reader), Counter())
            if previous is not None:
                counts[previous] -= 1
            counts[status] += 1
            is_running = any(self._group_counts.get((parent, index), {}).get(Status.RUNNING, 0) for index in columns)
            if was_running != is_running:
                name = self.createIndex(parent.row, 0, parent)
                self.dataChanged.emit(name, name, [Qt.DecorationRole, Qt.ForegroundRole, ACTIVE_ROLE])
            value = worst(s for s, count in counts.items() if count > 0)
            if parent.agg.get(reader) != value:
                parent.agg[reader] = value
                index = self.createIndex(parent.row, column, parent)
                self.dataChanged.emit(index, index)
            parent = parent.parent

    def occurrence_keys(self, position):
        return tuple(self._keys_by_position.get(position, ()))

    def set_preparing(self, position, reader):
        """Montrer le demarrage sans effacer le resultat du run precedent."""
        self.clear_preparing(reader)
        row = self._by_nodeid.get(self.key(position))
        rows = []
        while row is not None:
            rows.append(row)
            self._preparing_rows[row] += 1
            row = row.parent
        self._preparing_by_reader[reader] = rows
        self._repaint_activity(rows)

    def clear_preparing(self, reader):
        rows = self._preparing_by_reader.pop(reader, ())
        for row in rows:
            self._preparing_rows[row] -= 1
            if not self._preparing_rows[row]:
                del self._preparing_rows[row]
        self._repaint_activity(rows)

    def _repaint_activity(self, rows):
        for row in rows:
            index = self.createIndex(row.row, 0, row)
            self.dataChanged.emit(index, index, [Qt.DecorationRole, Qt.ForegroundRole, ACTIVE_ROLE])

    def _is_active(self, row):
        if row in self._preparing_rows:
            return True
        if not row.children:
            return Status.RUNNING in row.statuses.values()
        readers = (reader.index for reader in self.readers) if self.readers else (0,)
        return any(self._group_counts.get((row, reader), {}).get(Status.RUNNING, 0) for reader in readers)

    def clear_statuses(self):
        for reader in tuple(self._preparing_by_reader):
            self.clear_preparing(reader)
        self._group_counts.clear()
        self._interrupted.clear()
        self.previous_results.clear()
        super().clear_statuses()

    def clear_occurrence(self, position, reader):
        """Ne remplacer que l'occurrence qui commence, sur le lecteur relance."""
        keys = self.occurrence_keys(position)
        for key in keys:
            row = self._by_nodeid[key]
            old = row.statuses.pop(reader, None)
            parent = row.parent
            while parent is not None:
                counts = self._group_counts.setdefault((parent, reader), Counter())
                if old is not None:
                    counts[old] -= 1
                parent.agg[reader] = worst(status for status, count in counts.items() if count > 0)
                parent = parent.parent
            if reader in self._durations.get(key, {}):
                self.set_duration(key, reader, 0)
                self._durations[key].pop(reader, None)
                self._duration_totals.pop(row, None)
            self._interrupted.discard((key, reader))
            if self.locations[key][1] and not row.statuses:
                parent_index = self.parent(self.index_for_nodeid(key))
                siblings = row.parent.children if row.parent is not None else self._roots
                self.beginRemoveRows(parent_index, row.row, row.row)
                siblings.pop(row.row)
                for index, sibling in enumerate(siblings):
                    sibling.row = index
                self._by_nodeid.pop(key)
                self.locations.pop(key)
                self._keys_by_position[position].discard(key)
                self._activation_targets.pop(row, None)
                self._blocked_rows.discard(row)
                self._durations.pop(key, None)
                self._yaml_exceptions.pop(key, None)
                for metadata in (self._annotations, self._group_colors, self._membership):
                    metadata.pop(id(row.node), None)
                self.endRemoveRows()
        self._emit_layout_changed()

    def is_previous(self, row, reader):
        return (row.node.nodeid, reader) in self.previous_results or super().is_previous(row, reader)

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.locations.get(index.internalPointer().node.nodeid, (0, 0, ''))[1]:
            flags &= ~Qt.ItemIsUserCheckable
        return flags

    def checked_nodeids(self):
        return [key for key in super().checked_nodeids() if self.locations.get(key, (0, 0, ''))[1] == 0]

    def counts(self):
        total = sum(self.locations.get(key, (0, 0, ''))[1] == 0 for key in self._by_nodeid)
        return len(self.checked_nodeids()), total

    def set_checked_nodeids(self, keys):
        super().set_checked_nodeids([self.key(self.locations[key][0]) if key in self.locations else key for key in keys])

    def _check_state(self, row):
        if row in self._blocked_rows:
            return Qt.Unchecked
        if row.is_leaf:
            if self.locations.get(row.node.nodeid, (0, 0, ''))[1]:
                return None
            return Qt.Checked if row.checked else Qt.Unchecked
        if row.check_cache is None:
            states = {self._check_state(child) for child in row.children if child not in self._blocked_rows} - {None}
            row.check_cache = next(iter(states)) if len(states) == 1 else Qt.PartiallyChecked if states else Qt.Unchecked
        return row.check_cache

    def finish(self):
        for reader in tuple(self._preparing_by_reader):
            self.clear_preparing(reader)
        self._stopped = True
        for key, row in self._by_nodeid.items():
            for reader, status in list(row.statuses.items()):
                if status is Status.RUNNING:
                    self._interrupted.add((key, reader))
                    position, attempt, nodeid = self.locations[key]
                    self.apply_execution(position, attempt, reader, nodeid, Status.PENDING)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.internalPointer()
        if index.column() == 0 and role == Qt.CheckStateRole:
            return self._check_state(row)
        if index.column() == self.duration_column:
            return self._data_colonne_duree(row, role)
        if index.column() == 0 and role == ACTIVE_ROLE:
            return self._is_active(row)
        if index.column() == 0 and role in (Qt.DecorationRole, Qt.ForegroundRole):
            if self._is_active(row):
                return icons.status_icon(Status.RUNNING, group=True) if role == Qt.DecorationRole else QColor(t.ACCENT)
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
                if row.node.nodeid in self.locations:
                    position, attempt, _ = self.locations[row.node.nodeid]
                    title += f'\nOccurrence {position + 1} · Repetition {position // self.sequence_length + 1}/{self.repetitions}'
                    if attempt:
                        title += f' · Retry {attempt}'
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
