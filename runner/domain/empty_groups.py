"""Un groupe vide garde sa place, ses couleurs et ses reglages."""
import copy


def reposition(records, old_ids, new_ids):
    positions = {identifier: p for p, identifier in enumerate(new_ids)}
    result = copy.deepcopy(records)
    for record in result:
        record['position'] = next((positions[i] for i in old_ids[record['position']:] if i in positions), len(new_ids))
    return result


def retained(previous, sequence, groups, old_ids=(), new_ids=()):
    from runner.domain.execution_profile import group_path
    occupied = {g['id'] for entry in groups for g in group_path(entry)}
    records = [(r['position'], 0, copy.deepcopy(r)) for r in previous.empty_groups]
    seen = {r['group']['id'] for r in previous.empty_groups}
    positions = {identifier: p for p, identifier in enumerate(new_ids)}
    def slot(index):
        return next((positions[i] for i in old_ids[index:] if i in positions), len(sequence))
    for index, entry in enumerate(previous.step_groups or []):
        if entry and entry['id'] not in occupied and entry['id'] not in seen:
            records.append((index, 1, dict(position=index, group=copy.deepcopy(entry))))
            seen.add(entry['id'])
    result = []
    for index, _, record in sorted(records, key=lambda r: r[:2]):
        if record['group']['id'] not in occupied:
            record['position'] = slot(index)
            result.append(record)
    return result


def add_nodes(roots, named, records):
    from runner.domain.execution_profile import group_path
    from runner.domain.models import TestNode, Kind
    leaf_positions = {id(leaf): p for p, leaf in enumerate(leaf for root in roots for leaf in root.leaves())}
    empty_positions = {}
    for record in records:
        siblings = roots
        for group in group_path(record['group']):
            node = next((n for n in siblings if named.get(id(n), {}).get('id') == group['id']), None)
            if node is None:
                node = TestNode(group['name'], Kind.FOLDER)
                named[id(node)] = copy.deepcopy(group)
                slot = len(siblings)
                for i, child in enumerate(siblings):
                    leaves = list(child.leaves())
                    position = min((leaf_positions[id(leaf)] for leaf in leaves), default=empty_positions.get(id(child), 10**9))
                    if position > record['position'] or leaves and position == record['position']:
                        slot = i
                        break
                siblings.insert(slot, node)
                empty_positions[id(node)] = record['position']
            siblings = node.children
