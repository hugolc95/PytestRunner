"""Projection Qt des groupes sans occurrence executable."""
import copy

from PySide6.QtCore import Qt

from runner.domain.execution_profile import group_path, group_entry
from runner.domain.models import Kind
from runner.ui.tree_model import NODEID_ROLE
from runner.ui import icons

GROUP_ROLE = Qt.UserRole + 26


def capture(page):
    result = []
    count = 0
    def visit(item):
        nonlocal count
        start = count
        if item.data(0, NODEID_ROLE):
            count += 1
        for i in range(item.childCount()):
            visit(item.child(i))
        metadata = item.data(0, GROUP_ROLE)
        if metadata and count == start and not any(item.child(i).data(0, GROUP_ROLE) for i in range(item.childCount())):
            result.append(dict(position=start, group=group_entry(page._item_group_path(item, include_self=True))))
    for i in range(page.sequence_list.topLevelItemCount()):
        visit(page.sequence_list.topLevelItem(i))
    return result


def add(page, records):
    root = page.sequence_list.invisibleRootItem()
    positions = {id(item): i for i, item in enumerate(page._step_items())}
    empty_positions = {}
    def first(item):
        if id(item) in positions:
            return positions[id(item)], True
        values = [first(item.child(i)) for i in range(item.childCount())]
        real = [p for p, has_tests in values if has_tests]
        return (min(real), True) if real else (empty_positions.get(id(item), 10**9), False)
    for record in records:
        parent = root
        path = group_path(record['group'])
        for level, group in enumerate(path):
            item = next((parent.child(i) for i in range(parent.childCount())
                         if (parent.child(i).data(0, GROUP_ROLE) or {}).get('id') == group['id']), None)
            if item is None:
                item = page._group_item(group['name'], Kind.FOLDER)
                item.setData(0, GROUP_ROLE, group_entry(path[:level + 1]))
                item.setIcon(0, icons.icon('mdi.folder-outline', group['color']))
                slot = parent.childCount()
                for i in range(parent.childCount()):
                    position, real = first(parent.child(i))
                    if position > record['position'] or real and position == record['position']:
                        slot = i
                        break
                parent.insertChild(slot, item)
                empty_positions[id(item)] = record['position']
            parent = item


def change_metadata(records, identifier, transform):
    result = copy.deepcopy(records)
    for record in result:
        record['group'] = group_entry([transform(g) if g['id'] == identifier else g for g in group_path(record['group'])])
    return result
