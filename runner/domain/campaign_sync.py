"""Compare une campagne a une collecte reussie, sans deviner les suppressions."""
from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from runner.domain.disabled_tests import parameter_base


def workspace_key(path):
    return os.path.normcase(str(Path(path).resolve())).replace('\\', '/').rstrip('/') if path else ''


def validate_tracking(profile):
    from runner.domain.execution_profile import ProfileValidationError, MAX_MANIFEST_BYTES, validate_step_groups
    ids, tracking = profile.step_ids, profile.tracking
    def fail():
        raise ProfileValidationError('Invalid campaign tracking metadata.')
    if not isinstance(ids, list) or (ids and (len(ids) != len(profile.sequence)
            or any(not isinstance(i, str) or not i or len(i) > 120 or any(c in i for c in '\x00\n\r') for i in ids)
            or len(set(ids)) != len(ids))):
        fail()
    if not isinstance(tracking, dict):
        fail()
    if not tracking:
        return
    if set(tracking) != {'workspace', 'sources', 'members'} or not ids:
        fail()
    if not isinstance(tracking['workspace'], str) or len(tracking['workspace']) > 4096:
        fail()
    sources, members = tracking['sources'], tracking['members']
    if not isinstance(sources, list) or not isinstance(members, dict) or len(sources) > 10000:
        fail()
    seen = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {'id', 'kind', 'selector', 'recursive', 'excluded', 'group', 'anchor'}:
            fail()
        identifier = source['id']
        if not isinstance(identifier, str) or not identifier or len(identifier) > 120 or identifier in seen:
            fail()
        seen.add(identifier)
        if source['kind'] not in ('folder', 'file', 'test') or type(source['recursive']) is not bool:
            fail()
        selector = source['selector']
        if not isinstance(selector, str) or not selector or len(selector) > 4096 or any(c in selector for c in '\x00\n\r'):
            fail()
        path = selector.split('::')[0].replace('\\', '/')
        if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path:
            fail()
        if not isinstance(source['excluded'], list) or any(not isinstance(n, str) or len(n) > 8192 for n in source['excluded']):
            fail()
        if not isinstance(source['anchor'], str) or len(source['anchor']) > 120:
            fail()
        validate_step_groups([source['group']], 1)
    positions = dict(zip(ids, profile.sequence))
    for identifier, member in members.items():
        if identifier not in positions or not isinstance(member, dict) or set(member) != {'source', 'nodeid'}:
            fail()
        if not isinstance(member['source'], str) or member['source'] not in seen or not isinstance(member['nodeid'], str):
            fail()
        if positions[identifier] != member['nodeid']:
            fail()
    try:
        if len(json.dumps(tracking, allow_nan=False).encode()) > MAX_MANIFEST_BYTES:
            fail()
    except (ValueError, TypeError, RecursionError):
        fail()


def ensure_ids(profile):
    if not profile.step_ids:
        profile.step_ids = [str(uuid.uuid4()) for _ in profile.sequence]


def matches(source, nodeid):
    path = nodeid.split('::')[0].replace('\\', '/')
    selector = source['selector'].replace('\\', '/')
    if source['kind'] == 'test':
        return parameter_base(nodeid) == selector
    if source['kind'] == 'file':
        return path == selector
    folder = selector.rstrip('/')
    relative = path if folder == '.' else path[len(folder) + 1:] if path.startswith(folder + '/') else None
    return relative is not None and (source['recursive'] or '/' not in relative)


def follow(profile, positions, kind, selector, workspace, *, recursive=True):
    """Une regle par bloc ajoute ; deux copies T0/T1 restent independantes."""
    ensure_ids(profile)
    positions = list(positions)
    clusters = []
    groups = profile.step_groups or [{} for _ in profile.sequence]
    for position in positions:
        if not clusters or groups[position] != groups[clusters[-1][-1]]:
            clusters.append([])
        clusters[-1].append(position)
    if len(clusters) > 1:
        for cluster in clusters:
            follow(profile, cluster, kind, selector, workspace, recursive=recursive)
        return
    if not profile.tracking:
        profile.tracking = dict(workspace=workspace_key(workspace), sources=[], members={})
    if profile.tracking['workspace'] != workspace_key(workspace):
        raise ValueError('Choose the original source environment before changing tracking.')
    if not positions:
        return
    identifier = str(uuid.uuid4())
    first, last = min(positions), max(positions)
    source = dict(id=identifier, kind=kind, selector=selector, recursive=recursive,
                  excluded=[], group=copy.deepcopy(profile.step_groups[first] if profile.step_groups else {}),
                  anchor=profile.step_ids[last])
    profile.tracking['sources'].append(source)
    reassigned = {profile.tracking['members'][profile.step_ids[p]]['source'] for p in positions
                  if profile.step_ids[p] in profile.tracking['members']}
    for position in positions:
        profile.tracking['members'][profile.step_ids[position]] = dict(source=identifier, nodeid=profile.sequence[position])
    used = {m['source'] for m in profile.tracking['members'].values()}
    profile.tracking['sources'] = [s for s in profile.tracking['sources'] if s['id'] not in reassigned or s['id'] in used]
    prune_sources(profile)


def prune_sources(profile):
    """Conserve les sources vides : elles peuvent retrouver des tests apres mise a jour."""
    if not profile.tracking:
        return
    if not profile.tracking['sources']:
        profile.tracking = {}
        return
    known = {s['id'] for s in profile.tracking['sources']}
    identifiers = set(profile.step_ids)
    profile.tracking['members'] = {i: m for i, m in profile.tracking['members'].items()
                                    if i in identifiers and m['source'] in known}


def reconcile(profile):
    """Une suppression volontaire devient une exclusion propre a sa source."""
    if not profile.tracking:
        return
    sources = {s['id']: s for s in profile.tracking['sources']}
    positions = {i: n for n, i in enumerate(profile.step_ids)}
    groups = profile.step_groups or [{} for _ in profile.sequence]
    active = {}
    for identifier, member in profile.tracking['members'].items():
        source = sources.get(member['source'])
        if source is None:
            continue
        if identifier not in positions:
            if member['nodeid'] not in source['excluded']:
                source['excluded'].append(member['nodeid'])
            continue
        position = positions[identifier]
        member['nodeid'] = profile.sequence[position]
        active[identifier] = member
    # Un deplacement de groupe entier emporte le suivi. Un seul test deplace
    # hors du bloc devient une selection fixe pour ne pas dupliquer le dossier.
    for source in sources.values():
        ids = [i for i, m in active.items() if m['source'] == source['id']]
        contexts = [groups[positions[i]] for i in ids]
        if contexts and all(g == contexts[0] for g in contexts):
            source['group'] = copy.deepcopy(contexts[0])
        else:
            for identifier in ids:
                if groups[positions[identifier]] != source['group']:
                    source['excluded'].append(active.pop(identifier)['nodeid'])
    profile.tracking['members'] = active


@dataclass
class SyncPlan:
    available: tuple[str, ...] = ()
    additions: list[tuple[str, str]] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    candidates: dict[int, list[str]] = field(default_factory=dict)
    problem: str = ''

    @property
    def changed(self):
        return bool(self.additions or self.missing)

    @property
    def summary(self):
        changed = sum(bool(self.candidates.get(position)) for position in self.missing)
        return (f'{len(self.additions)} new test(s)/case(s) · {changed} changed parameter case(s) · '
                f'{len(self.missing) - changed} unavailable occurrence(s)')


def compare(profile, available, workspace='', *, complete=True):
    plan = SyncPlan()
    if not complete:
        plan.problem = 'Collection incomplete — campaign unchanged. Collect successfully before reviewing changes.'
        return plan
    if profile.tracking and profile.tracking['workspace'] != workspace_key(workspace):
        plan.problem = 'Different source environment — campaign unchanged. Open the original workspace or explicitly rebind its sources.'
        return plan
    available = list(dict.fromkeys(available))
    plan.available = tuple(available)
    present = set(available)
    by_base = {}
    for nodeid in available:
        by_base.setdefault(parameter_base(nodeid), []).append(nodeid)
    for position, nodeid in enumerate(profile.sequence):
        if nodeid not in present:
            plan.missing.append(position)
            plan.candidates[position] = by_base.get(parameter_base(nodeid), [])
    if profile.tracking:
        existing_by_source = {}
        for member in profile.tracking['members'].values():
            existing_by_source.setdefault(member['source'], set()).add(member['nodeid'])
        for source in profile.tracking['sources']:
            existing = existing_by_source.get(source['id'], set())
            excluded = set(source['excluded'])
            plan.additions.extend((source['id'], nodeid) for nodeid in available
                                  if nodeid not in existing and nodeid not in excluded and matches(source, nodeid))
    return plan


def apply(profile, plan, additions, decisions, *, transfer=()):
    """Applique seulement les choix revus, jamais des correspondances approximatives."""
    from runner.domain.execution_profile import validate_profile, ProfileValidationError
    if plan.problem:
        raise ProfileValidationError(plan.problem)
    result = copy.deepcopy(profile)
    ensure_ids(result)
    patches = result.step_overrides or [{} for _ in result.sequence]
    groups = result.step_groups or [{} for _ in result.sequence]
    members = result.tracking.get('members', {})
    sources = {s['id']: s for s in result.tracking.get('sources', [])}
    chosen = set(additions)
    if not chosen <= set(plan.additions):
        raise ProfileValidationError('The collection changed. Review this campaign again.')
    inserts, rows, replacements = {}, [], {}
    for position in plan.missing:
        decision = decisions.get(position, '')
        if not decision:
            raise ProfileValidationError('Choose an action for every unavailable occurrence.')
        if decision not in ('keep', 'remove'):
            if decision not in plan.available:
                raise ProfileValidationError('Choose a collected replacement, or keep/remove the missing occurrence.')
            replacements[position] = decision
    consumed = {(members[i]['source'], replacements[p]) for p, i in enumerate(result.step_ids)
                if p in replacements and i in members}
    positions = {i: n for n, i in enumerate(result.step_ids)}
    ranks = {nodeid: n for n, nodeid in enumerate(plan.available)}
    for source in sources.values():
        owned = sorted(positions[i] for i, m in members.items() if m['source'] == source['id'] and i in positions)
        current = [(p, replacements.get(p, result.sequence[p])) for p in owned if decisions.get(p) != 'remove']
        for source_id, nodeid in plan.additions:
            if source_id == source['id'] and (source_id, nodeid) not in chosen and (source_id, nodeid) not in consumed:
                source['excluded'].append(nodeid)
            if source_id != source['id'] or (source_id, nodeid) not in chosen or (source_id, nodeid) in consumed:
                continue
            # Inserer pres de la fonction ou du fichier concerne. Trier tout
            # le bloc casserait l'ordre personnalise des tests deja presents.
            siblings = [(p, n) for p, n in current if parameter_base(n) == parameter_base(nodeid)]
            if not siblings:
                siblings = [(p, n) for p, n in current if n.split('::')[0] == nodeid.split('::')[0]]
            if not siblings:
                siblings = current
            measured = [(p, ranks[n]) for p, n in siblings if n in ranks]
            if measured and all(a[1] <= b[1] for a, b in zip(measured, measured[1:])):
                slot = next((p for p, rank in measured if rank > ranks[nodeid]), measured[-1][0] + 1)
            elif siblings:
                slot = siblings[-1][0] + 1
            else:
                slot = positions.get(source['anchor'], -1 if source['anchor'] == '__start__' else len(result.sequence) - 1) + 1
            inserts.setdefault(slot, []).append((source, nodeid))
    def insert(slot):
        for source, new_nodeid in inserts.get(slot, []):
            new_id = str(uuid.uuid4())
            rows.append((new_nodeid, new_id, {}, copy.deepcopy(source['group'])))
            members[new_id] = dict(source=source['id'], nodeid=new_nodeid)
            source['anchor'] = new_id
    for position, (nodeid, identifier, patch, group) in enumerate(zip(result.sequence, result.step_ids, patches, groups)):
        insert(position)
        keep = True
        if position in plan.missing:
            decision = decisions.get(position, '')
            if decision == 'remove':
                keep = False
            elif decision != 'keep':
                nodeid = decision
                patch = patch if position in transfer else {}
                member = members.get(identifier)
                if member:
                    member['nodeid'] = nodeid
        if keep:
            rows.append((nodeid, identifier, patch, group))
        else:
            member = members.pop(identifier, None)
            if member:
                sources[member['source']]['excluded'].append(nodeid)
    insert(len(result.sequence))
    result.sequence = [r[0] for r in rows]
    result.step_ids = [r[1] for r in rows]
    result.step_overrides = [copy.deepcopy(r[2]) for r in rows]
    result.step_groups = [copy.deepcopy(r[3]) for r in rows]
    retained = set(result.step_ids)
    for source in sources.values():
        if source['anchor'] not in retained:
            old_position = positions.get(source['anchor'], 0)
            source['anchor'] = next((i for i in reversed(profile.step_ids[:old_position]) if i in retained), '__start__')
    prune_sources(result)
    validate_profile(result)
    return result
