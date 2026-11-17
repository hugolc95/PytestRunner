"""Une fonction devenue parametree reste un appel a la meme place du scenario."""
import copy
import uuid

from runner.domain.disabled_tests import parameter_base


def proposals(profile, available, base_moves):
    families = {}
    for nodeid in available:
        families.setdefault(parameter_base(nodeid), []).append(nodeid)
    groups = profile.step_groups or [{} for _ in profile.sequence]
    members = profile.tracking.get('members', {})
    sources = {s['id']: s for s in profile.tracking.get('sources', [])}
    calls = []
    for position, nodeid in enumerate(profile.sequence):
        source = members.get(profile.step_ids[position], {}).get('source') if profile.step_ids else None
        base = base_moves.get(position, parameter_base(nodeid))
        key = base, groups[position], source
        if (not calls or calls[-1]['key'] != key or nodeid == parameter_base(nodeid)
                or nodeid in calls[-1]['seen']):
            calls.append(dict(key=key, positions=[], seen=set()))
        calls[-1]['positions'].append(position)
        calls[-1]['seen'].add(nodeid)
    updates = {}
    for call in calls:
        base, group, source_id = call['key']
        positions = call['positions']
        old = [profile.sequence[p] for p in positions]
        source = sources.get(source_id, {})
        old_base = parameter_base(old[0])
        excluded = {base + n[len(old_base):] if parameter_base(n) == old_base else n
                    for n in source.get('excluded', [])}
        cases = [n for n in families.get(base, []) if n not in excluded and parameter_base(n) not in excluded]
        whole_test = len(old) == 1 and old[0] == parameter_base(old[0]) and old[0] not in available
        if not cases or (not whole_test and not source_id) or not any(n not in old for n in cases):
            continue
        # Un cas explicitement choisi reste fixe. Un ancien appel sans []
        # designe la fonction complete, meme dans une campagne sans suivi.
        updates[positions[0]] = dict(positions=positions, cases=cases, base=base,
                                    source=source_id, whole_test=whole_test,
                                    excluded=sorted(n for n in excluded if parameter_base(n) == base))
    return updates


def rows(profile, update, decisions, transfer, members, sources, workspace):
    positions = update['positions']
    patches = profile.step_overrides or [{} for _ in profile.sequence]
    groups = profile.step_groups or [{} for _ in profile.sequence]
    source = sources.get(update['source'], {})
    first = positions[0]
    if update['whole_test']:
        if decisions.get(first) != 'parameters':
            return None
        values = [(n, profile.step_ids[first] if i == 0 else str(uuid.uuid4()),
                   copy.deepcopy(patches[first]), copy.deepcopy(groups[first]))
                  for i, n in enumerate(update['cases'])]
    else:
        values = []
        for p in positions:
            decision = decisions.get(p, profile.sequence[p])
            if decision == 'remove':
                continue
            nodeid = profile.sequence[p] if decision == 'keep' else decision
            patch = patches[p] if nodeid == profile.sequence[p] or p in transfer else {}
            values.append((nodeid, profile.step_ids[p], copy.deepcopy(patch), copy.deepcopy(groups[p])))
        present = {v[0] for v in values}
        common = patches[first] if source.get('kind') == 'test' and all(patches[p] == patches[first] for p in positions) else {}
        ranks = {n: i for i, n in enumerate(update['cases'])}
        for nodeid in update['cases']:
            if nodeid in present:
                continue
            measured = [(i, ranks[v[0]]) for i, v in enumerate(values) if v[0] in ranks]
            ordered = all(a[1] <= b[1] for a, b in zip(measured, measured[1:]))
            slot = next((i for i, rank in measured if rank > ranks[nodeid]), len(values)) if ordered else len(values)
            values.insert(slot, (nodeid, str(uuid.uuid4()), copy.deepcopy(common), copy.deepcopy(groups[first])))
    if not values:
        return None
    old_ids = {profile.step_ids[p] for p in positions}
    owned = {i for i, m in members.items() if m['source'] == update['source']}
    reuse = source.get('kind') == 'test' and owned == old_ids
    identifier = source['id'] if reuse else str(uuid.uuid4())
    rule = dict(id=identifier, kind='test', selector=update['base'], recursive=True,
                excluded=copy.deepcopy(update['excluded']),
                group=copy.deepcopy(groups[first]), anchor=values[-1][1])
    if not profile.tracking:
        profile.tracking = dict(workspace=workspace, sources=[], members=members)
    if not reuse:
        profile.tracking['sources'].append(rule)
    else:
        source.update(rule)
        rule = source
    sources[identifier] = rule
    for old_id in old_ids:
        members.pop(old_id, None)
    for nodeid, step_id, _, _ in values:
        members[step_id] = dict(source=identifier, nodeid=nodeid)
    return values
