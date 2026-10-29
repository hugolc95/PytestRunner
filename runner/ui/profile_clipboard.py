"""Copier/coller une selection figee sans lier les nouvelles occurrences aux originales."""
import copy
import uuid

import yaml
from PySide6.QtCore import QObject, QMimeData, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog

from runner.domain.execution_profile import (
    MAX_STEPS, ExecutionProfile, ProfileValidationError, group_entry, group_path,
    inherited_configuration, merge_configuration, validate_profile,
)
from runner.domain.profile_clipboard import MIME, FORMAT, encode_selection, decode_selection, inherited_base
from runner.domain.profile_configuration import fields
from runner.domain.models import Status
from runner.ui import icons, tokens as t
from runner.ui.profile_dialogs import PasteSequenceDialog, format_value
from runner.ui.profile_group_delegate import TRANSFER_ROLE
from runner.ui.tree_model import NODEID_ROLE

# Roles des donnees de l'editeur ; la decoration de transfert n'en fait pas partie.
_PATCH_ROLE = Qt.UserRole + 20
_LABEL_ROLE = Qt.UserRole + 23
_KIND_ROLE = Qt.UserRole + 25
_GROUP_ROLE = Qt.UserRole + 26


class SequenceClipboard(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.owner = str(uuid.uuid4())
        self.payload = None
        self._clipboard_bytes = None
        self._ready_text = ''
        self._ready_tooltip = ''
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.reset_visuals)
        self.copy_action = QAction(icons.icon('mdi.content-copy'), 'Copy', self)
        self.paste_action = QAction(icons.icon('mdi.content-paste'), 'Paste after selection', self)
        self.paste_into_action = QAction('Paste into this group', self)
        for action, key in ((self.copy_action, QKeySequence.Copy), (self.paste_action, QKeySequence.Paste)):
            action.setShortcuts(key)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            page.sequence_list.addAction(action)
        self.paste_into_action.setShortcut(QKeySequence('Ctrl+Shift+V'))
        self.paste_into_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        page.sequence_list.addAction(self.paste_into_action)
        self.copy_action.triggered.connect(lambda: page.copy_elements())
        self.paste_action.triggered.connect(lambda: page.paste_elements())
        self.paste_into_action.triggered.connect(lambda: page.paste_elements(into_group=True))
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self._clipboard_changed)
        self._clipboard_changed()

    def _all_items(self):
        _, ranges = self.page._sequence_ranges()
        return [item for item, _, _ in ranges]

    def reset_visuals(self):
        self.feedback_timer.stop()
        for item in self._all_items():
            item.setData(0, TRANSFER_ROLE, None)
        self._feedback(self._ready_text, self._ready_tooltip)

    def _feedback(self, text, tooltip='', state='copied'):
        label = self.page.transfer_label
        label.setText(text)
        label.setToolTip(tooltip or text)
        color = t.ACCENT if state == 'copied' else t.status_color(Status.PASSED)
        if state == 'error':
            color = '#d89a17'
        label.setStyleSheet(f'color: {color};')
        label.setVisible(bool(text))
        if state in ('pasted', 'error'):
            self.feedback_timer.start(6000)

    def _clipboard_changed(self):
        mime = self.clipboard.mimeData()
        raw = bytes(mime.data(MIME)) if mime is not None and mime.hasFormat(MIME) else b''
        # Windows peut notifier deux fois le meme contenu. Une notification
        # tardive ne doit pas effacer le repere visuel du copier/coller.
        if raw == self._clipboard_bytes:
            self.update_actions()
            return
        self._clipboard_bytes = raw
        self.payload = None
        self._ready_text = self._ready_tooltip = ''
        if raw:
            try:
                self.payload = decode_selection(raw)
            except (ProfileValidationError, ValueError, UnicodeError):
                pass
        if self.payload:
            total = sum(len(item['sequence']) for item in self.payload['items'])
            size = len(self.payload['items'])
            noun = 'group' if size == 1 and self.payload['items'][0]['kind'] == 'group' else 'element'
            prefix = 'Copied' if self.payload['owner'] == self.owner else 'Clipboard:'
            self._ready_text = f'{prefix} {size} {noun}' + ('s' if size != 1 else '') + f' · {total} test' + ('s' if total != 1 else '')
            self._ready_tooltip = ('Copied from: ' + self.payload['source'] + '\n' +
                                   '\n'.join(item['label'] for item in self.payload['items'][:5]) +
                                   '\nThe clipboard keeps the values at the time of copying.')
        self.reset_visuals()
        self.update_actions()

    def update_actions(self):
        selected = self.page.sequence_list.selectedItems()
        self.copy_action.setEnabled(bool(selected))
        self.paste_action.setEnabled(self.payload is not None)
        named = len(selected) == 1 and not selected[0].data(0, NODEID_ROLE) and bool(selected[0].data(0, _GROUP_ROLE))
        self.paste_into_action.setEnabled(self.payload is not None and named)
        self.paste_action.setText('Paste after selection' if selected else 'Paste at end of profile')

    def copy(self):
        page = self.page
        nodeids, selected = page._selected_ranges()
        if not selected:
            return
        try:
            base = page._base_configuration()
            patches, groups = page._step_patches(), page._step_groups()
            contexts, context_index, items = [], {}, []
            for item, start, end in sorted(selected, key=lambda row: row[1]):
                prefix = page._item_group_path(item)
                inherited = yaml.safe_dump(inherited_configuration(base, prefix), allow_unicode=True, sort_keys=False)
                if inherited not in context_index:
                    context_index[inherited] = len(contexts)
                    contexts.append(inherited)
                nodeid = item.data(0, NODEID_ROLE)
                if nodeid:
                    kind = 'case' if '[' in nodeid.split('::')[-1] and nodeid.endswith(']') else 'test'
                elif item.data(0, _GROUP_ROLE):
                    kind = 'group'
                else:
                    kind = item.data(0, _KIND_ROLE) or 'folder'
                    if kind == 'test':
                        kind = 'parameterized'
                items.append(dict(kind=kind, label=item.data(0, _LABEL_ROLE) or nodeid,
                                  sequence=nodeids[start:end], patches=patches[start:end],
                                  groups=[group_entry(group_path(entry)[len(prefix):]) for entry in groups[start:end]],
                                  base=context_index[inherited]))
            payload = dict(format=FORMAT, version=1, copy_id=str(uuid.uuid4()), owner=self.owner,
                           source=page.name_edit.text().strip() or 'Untitled profile', bases=contexts, items=items)
            encoded = encode_selection(payload)
        except (OSError, UnicodeError, ValueError, RecursionError, yaml.YAMLError, ProfileValidationError) as exc:
            self._feedback('Could not copy', str(exc), 'error')
            return
        mime = QMimeData()
        mime.setData(MIME, encoded)
        mime.setText('\n'.join(nodeid for item in items for nodeid in item['sequence']))
        self.clipboard.setMimeData(mime)
        # setMimeData emet dataChanged : poser les marques APRES son nettoyage.
        for item, _, _ in selected:
            item.setData(0, TRANSFER_ROLE, 'copied')
        self._feedback(self._ready_text, self._ready_tooltip)

    def _destination(self, into_group):
        page = self.page
        nodeids, selected = page._selected_ranges()
        if into_group:
            if not self.paste_into_action.isEnabled():
                raise ProfileValidationError('Select one destination group before pasting inside it.')
            item, _, end = selected[0]
            path = page._item_group_path(item, include_self=True)
            return end, path, 'Inside ' + ' / '.join(group['name'] for group in path)
        if not selected:
            return len(nodeids), [], 'End of profile'
        # Avec plusieurs elements selectionnes, coller apres TOUTE la plage,
        # meme si le focus clavier est reste sur le premier element.
        item, _, end = max(selected, key=lambda row: row[2])
        path = page._item_group_path(item)
        label = item.data(0, _LABEL_ROLE) or item.data(0, NODEID_ROLE)
        return end, path, 'After ' + label + (' in ' + ' / '.join(group['name'] for group in path) if path else '')

    def paste(self, *, into_group=False):
        page = self.page
        if not self.payload:
            self._feedback('Nothing to paste', 'Copy test elements from an execution profile first.', 'error')
            return
        payload = copy.deepcopy(self.payload)
        try:
            insertion, destination, label = self._destination(into_group)
            nodeids, patches, groups = page._flatten_sequence(), page._step_patches(), page._step_groups()
            count = sum(len(item['sequence']) for item in payload['items'])
            if len(nodeids) + count > MAX_STEPS:
                raise ProfileValidationError(f'A profile can contain at most {MAX_STEPS} test occurrences.')
            base = page._base_configuration()
            additions, overrides, memberships = [], [], []
            aliases, changes = {}, []
            for item in payload['items']:
                source_base = inherited_base(payload, item)
                for nodeid, patch, entry in zip(item['sequence'], item['patches'], item['groups']):
                    relative = group_path(entry)
                    old = merge_configuration(inherited_configuration(source_base, relative), patch)
                    for group in relative:
                        group['id'] = aliases.setdefault(group['id'], str(uuid.uuid4()))
                    path = copy.deepcopy(destination) + relative
                    if len(path) > 20:
                        raise ProfileValidationError('Groups may contain at most 20 nested levels.')
                    new = merge_configuration(inherited_configuration(base, path), patch)
                    before, after = dict(fields(old)), dict(fields(new))
                    reader_fields = [key for key in before.keys() | after.keys() if isinstance(key[-1], str) and key[-1].lower() in ('reader', 'lecteur')]
                    managed = min(reader_fields, key=len) if reader_fields else None
                    for key in before.keys() | after.keys():
                        if key == managed:
                            continue
                        if key not in before or key not in after or before[key] != after[key] or type(before[key]) is not type(after[key]):
                            text = '.'.join(map(str, key)) + ': ' + (format_value(before[key]) if key in before else '<not set>')
                            text += ' → ' + (format_value(after[key]) if key in after else '<not set>')
                            if text not in changes:
                                changes.append(text)
                    additions.append(nodeid)
                    overrides.append(copy.deepcopy(patch))
                    memberships.append(group_entry(path))
            missing = list(dict.fromkeys(nodeid for nodeid in additions if page._available_nodeids and nodeid not in page._available_nodeids))
            nodeids[insertion:insertion] = additions
            patches[insertion:insertion] = overrides
            groups[insertion:insertion] = memberships
            validate_profile(ExecutionProfile('Pasted sequence', nodeids, '', '', step_overrides=patches, step_groups=groups))
            if changes or missing:
                dialog = PasteSequenceDialog(count, payload['source'], label, changes, missing, page)
                if dialog.exec() != QDialog.Accepted:
                    return
        except (OSError, UnicodeError, ValueError, RecursionError, yaml.YAMLError, ProfileValidationError) as exc:
            self._feedback('Could not paste', str(exc), 'error')
            return
        page._rebuild_sequence(nodeids, patches, groups)
        self._mark_pasted(insertion, count)
        page._mark_dirty()
        size = len(payload['items'])
        self._feedback(f'Pasted {size} element' + ('s' if size != 1 else '') + f' · {count} test' + ('s' if count != 1 else ''),
                       label + '\nCtrl+Z: undo paste', 'pasted')

    def _mark_pasted(self, start, count):
        page = self.page
        _, ranges = page._sequence_ranges()
        chosen, covered = [], set()
        for item, first, end in reversed(ranges):
            positions = set(range(first, end))
            if first >= start and end <= start + count and not covered.intersection(positions):
                chosen.append((first, item))
                covered.update(positions)
        chosen.sort(key=lambda row: row[0])
        tree = page.sequence_list
        blocked = tree.blockSignals(True)
        try:
            tree.clearSelection()
            if chosen:
                tree.setCurrentItem(chosen[0][1])
            tree.clearSelection()
            for _, item in chosen:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                item.setSelected(True)
                item.setData(0, TRANSFER_ROLE, 'pasted')
        finally:
            tree.blockSignals(blocked)
        if chosen:
            tree.scrollToItem(chosen[0][1])
        page._selection_changed()
