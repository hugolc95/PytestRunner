"""Conserve le point de travail malgre la reconstruction de la sequence."""
from collections import Counter, defaultdict
from uuid import uuid4

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractItemView

from runner.domain.models import Kind
from runner.domain.disabled_tests import parameter_base
from runner.ui.tree_model import NODEID_ROLE
from runner.ui.profile_group_delegate import GROUP_ROLE

STEP_ID_ROLE = Qt.UserRole + 40
VIEW_ID_ROLE = Qt.UserRole + 41
KIND_ROLE = Qt.UserRole + 25


def rows(page):
    leaves = page._step_items()
    ids = page._step_ids()
    _, ranges = page._sequence_ranges()
    result = []
    for item, start, end in ranges:
        nodeid = item.data(0, NODEID_ROLE)
        metadata = item.data(0, GROUP_ROLE) or {}
        kind = item.data(0, KIND_ROLE)
        if nodeid:
            kind, target = 'step', ids[start]
        elif metadata:
            kind, target = 'named', metadata['id']
        else:
            first = leaves[start]
            nodeid = first.data(0, NODEID_ROLE)
            path = nodeid.split('::')[0].replace('\\', '/').split('/')
            below = 0
            parent = first.parent()
            while parent is not None and parent is not item:
                if parent.data(0, KIND_ROLE) == kind and not parent.data(0, GROUP_ROLE):
                    below += 1
                parent = parent.parent()
            if kind == Kind.FOLDER.value:
                target = '/'.join(path[:len(path) - 1 - below])
            elif kind == Kind.MODULE.value:
                target = '/'.join(path)
            elif kind == Kind.CLASS.value:
                parts = parameter_base(nodeid).split('::')
                target = '::'.join(parts[:len(parts) - 1 - below])
            else:
                target = parameter_base(nodeid)
        identifier = item.data(0, VIEW_ID_ROLE)
        if not identifier:
            identifier = str(uuid4())
            item.setData(0, VIEW_ID_ROLE, identifier)
        result.append((item, dict(id=identifier, kind=kind, target=target, steps=ids[start:end],
                                  expanded=item.isExpanded(), selected=item.isSelected())))
    return result


def capture(page):
    tree = page.sequence_list
    items = rows(page)
    current = tree.currentItem()
    top = tree.itemAt(QPoint(0, 0))
    return dict(rows=[record for _, record in items],
                current=next((record['id'] for item, record in items if item is current), None),
                top=next((record['id'] for item, record in items if item is top), None),
                offset=tree.visualItemRect(top).top() if top is not None else 0,
                vertical=tree.verticalScrollBar().value(), horizontal=tree.horizontalScrollBar().value())


def merged(historic, current):
    if not historic:
        return current
    records = {record['id']: record for record in historic['rows']}
    records.update({record['id']: record for record in current['rows']})
    return dict(current, rows=list(records.values()), fallback=historic)


def restore(page, view):
    if view is None:
        return
    tree = page.sequence_list
    direct, by_step = defaultdict(list), defaultdict(list)
    for record in view['rows']:
        key = record['kind'], record['target']
        if record['kind'] in ('step', 'named'):
            direct[key].append(record)
        for identifier in record['steps']:
            by_step[key, identifier].append(record)
    old_by_id = {record['id']: record for record in view['rows']}
    restored, used = {}, set()
    for item, record in rows(page):
        key = record['kind'], record['target']
        candidates = direct.get(key, [])
        if len(candidates) == 1:
            previous = candidates[0]
        else:
            votes = Counter(old['id'] for identifier in record['steps']
                            for old in by_step.get((key, identifier), ()))
            previous = old_by_id[votes.most_common(1)[0][0]] if votes else None
        if previous is None:
            continue
        identifier = previous['id']
        # Une ancienne branche peut se scinder ; ses deux morceaux gardent
        # leur ouverture, mais un seul reprend son ancrage de defilement.
        if identifier not in used:
            item.setData(0, VIEW_ID_ROLE, identifier)
            restored[identifier] = item
            used.add(identifier)
        item.setExpanded(previous['expanded'])
    sources = [view, view.get('fallback') or {}]
    current = next((restored.get(source.get('current')) for source in sources
                    if source.get('current') in restored), None)
    if current is not None:
        tree.setCurrentItem(current)
    tree.clearSelection()
    for source in sources:
        selected = [restored[record['id']] for record in source.get('rows', [])
                    if record['selected'] and record['id'] in restored]
        if selected:
            for item in selected:
                item.setSelected(True)
            break
    tree.doItemsLayout()
    top = next((restored.get(source.get('top')) for source in sources if source.get('top') in restored), None)
    if top is not None:
        tree.scrollToItem(top, QAbstractItemView.PositionAtTop)
        if tree.verticalScrollMode() == QAbstractItemView.ScrollPerPixel:
            tree.verticalScrollBar().setValue(tree.verticalScrollBar().value() - view.get('offset', 0))
    else:
        tree.verticalScrollBar().setValue(view['vertical'])
    tree.horizontalScrollBar().setValue(view['horizontal'])
