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
    if set(tracking) != {'workspace', 'sources', 'members'} or (profile.sequence and not ids):
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


def exclude_removed_fixed_cases(profile, removed):
    """Un fichier suivi ne doit pas elargir une selection precise apres son retrait."""
    if not profile.tracking or not removed:
        return
    from runner.domain.execution_profile import group_path
    members = profile.tracking['members']
    positions = {identifier: p for p, identifier in enumerate(profile.step_ids)}
    groups = profile.step_groups or [{} for _ in profile.sequence]
    def group_key(entry):
        return tuple(g['id'] for g in group_path(entry))
    for position in removed:
        nodeid = profile.sequence[position]
        base = parameter_base(nodeid)
        if base == nodeid or profile.step_ids[position] in members:
            continue
        for source in profile.tracking['sources']:
            if source['kind'] == 'test' or group_key(source['group']) != group_key(groups[position]) or not matches(source, nodeid):
                continue
            followed = any(m['source'] == source['id'] and parameter_base(m['nodeid']) == base
                           and positions[i] not in removed for i, m in members.items())
            if not followed and base not in source['excluded']:
                source['excluded'].append(base)


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
    from runner.domain.execution_profile import group_path
    from runner.domain.execution_profile import group_entry
    entries = list(profile.step_groups) + [r['group'] for r in profile.empty_groups]
    metadata = {g['id']: group_entry(group_path(entry)[:level + 1])
                for entry in entries for level, g in enumerate(group_path(entry))}
    for source in sources.values():
        if source['group'] and source['group']['id'] in metadata:
            source['group'] = copy.deepcopy(metadata[source['group']['id']])


@dataclass
class SyncPlan:
    workspace: str = ''
    available: tuple[str, ...] = ()
    additions: list[tuple[str, str]] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    candidates: dict[int, list[str]] = field(default_factory=dict)
    problem: str = ''
    path_changes: dict[int, str] = field(default_factory=dict)
    source_paths: dict[str, str] = field(default_factory=dict)
    suggestions: dict[int, list[str]] = field(default_factory=dict)
    parameter_updates: dict[int, dict] = field(default_factory=dict)

    @property
    def changed(self):
        return bool(self.additions or self.missing or self.parameter_updates)

    @property
    def summary(self):
        if self.parameter_updates:
            handled = {p for u in self.parameter_updates.values() for p in u['positions']}
            text = f'Parameters changed · {len(self.parameter_updates)} calls'
            if self.additions:
                text += f' · {len(self.additions)} new tests'
            missing = len(set(self.missing) - handled)
            return text + (f' · {missing} unavailable' if missing else '')
        changed = sum(bool(self.candidates.get(p)) for p in self.missing if p not in self.path_changes)
        unavailable = len(self.missing) - changed - len(self.path_changes)
        parts = []
        for count, label in ((len(self.additions), 'new tests/cases'), (len(self.path_changes), 'updated locations'),
                             (changed, 'changed cases'), (unavailable, 'not found')):
            if count:
                parts.append(f'{count} {label}')
        return ' · '.join(parts) or 'Up to date'


def location_matches(sequence, available):
    """Meme chemin relatif et meme symbole Python ; aucun rapprochement par nom seul."""
    by_symbol = {}
    for nodeid in available:
        path, _, symbol = nodeid.partition('::')
        by_symbol.setdefault(symbol, []).append((tuple(path.replace('\\', '/').split('/')), nodeid))
    result = {}
    present = set(available)
    for position, nodeid in enumerate(sequence):
        if nodeid in present:
            continue
        path, _, symbol = nodeid.partition('::')
        parts = tuple(path.replace('\\', '/').split('/'))
        candidates = [n for other, n in by_symbol.get(symbol, [])
                      if parts[-min(len(parts), len(other)):] == other[-min(len(parts), len(other)):]]
        if len(candidates) == 1:
            result[position] = candidates[0]
    # Deux fichiers differents ne doivent pas fusionner vers la meme cible.
    targets = {}
    for position, candidate in result.items():
        targets.setdefault(candidate, set()).add(sequence[position])
    return {p: n for p, n in result.items() if len(targets[n]) == 1}


def _source_at_location(source, old, new):
    old_path, new_path = old.split('::')[0], new.split('::')[0]
    if source['kind'] == 'file':
        return new_path if source['selector'] == old_path else None
    if source['kind'] == 'test':
        return parameter_base(new) if source['selector'] == parameter_base(old) else None
    folder = source['selector'].rstrip('/')
    relative = old_path if folder == '.' else old_path[len(folder) + 1:] if old_path.startswith(folder + '/') else None
    if relative and (new_path == relative or new_path.endswith('/' + relative)):
        return new_path[:-len(relative)].rstrip('/') or '.'
    return None


def _relocated_exclusions(source, selector):
    previous = source['selector']
    remapped = []
    for excluded in source['excluded']:
        if source['kind'] == 'folder':
            path, _, symbol = excluded.partition('::')
            relative = path if previous == '.' else path[len(previous) + 1:] if path.startswith(previous + '/') else None
            remapped.append((('' if selector == '.' else selector + '/') + relative + '::' + symbol) if relative else excluded)
        else:
            remapped.append(excluded.replace(previous, selector, 1) if excluded.startswith(previous) else excluded)
    return remapped


def recommended_decisions(profile, plan, *, remove_unmatched=False, refresh_cases=True):
    """Resoudre les references certaines ; garder les cas ambigus et leur YAML."""
    result = {}
    members = profile.tracking.get('members', {})
    sources = {s['id']: s for s in profile.tracking.get('sources', [])}
    patches = profile.step_overrides or [{} for _ in profile.sequence]
    positions = {identifier: p for p, identifier in enumerate(profile.step_ids)}
    function_defaults = set()
    refreshed_positions = {p for update in plan.parameter_updates.values() for p in update['positions']}
    for source in sources.values():
        owned = [positions[i] for i, m in members.items() if m['source'] == source['id']]
        if source['kind'] == 'test' and owned and all(patches[p] == patches[owned[0]] for p in owned):
            function_defaults.add(source['id'])
    for position in plan.missing:
        if refresh_cases and any(u['whole_test'] and position == p for p, u in plan.parameter_updates.items()):
            result[position] = 'parameters'
            continue
        if position in plan.path_changes:
            result[position] = plan.path_changes[position]
            continue
        patch = profile.step_overrides[position] if profile.step_overrides else {}
        source = members.get(profile.step_ids[position], {}).get('source') if profile.step_ids else None
        cases = plan.candidates.get(position, [])
        # Les valeurs communes a la fonction suivent ses nouveaux cas. Une
        # exception propre a un ancien cas reste a confirmer explicitement.
        if cases and source and (not patch or source in function_defaults and position in refreshed_positions) and refresh_cases:
            result[position] = 'remove'
        else:
            result[position] = 'remove' if remove_unmatched else 'keep'
    return result


def content_description(profile, positions, group_id=''):
    from runner.domain.execution_profile import group_path
    positions = set(positions)
    identifiers = {profile.step_ids[p] for p in positions} if profile.step_ids else set()
    members = profile.tracking.get('members', {})
    source_ids = {m['source'] for i, m in members.items() if i in identifiers}
    sources = [s for s in profile.tracking.get('sources', []) if s['id'] in source_ids or
               group_id and group_id in [g['id'] for g in group_path(s['group'])]]
    if not sources:
        return 'Fixed selection · new tests are not added.\nCheckboxes choose the next run only.'
    labels = list(dict.fromkeys(s['selector'] for s in sources))
    text = 'Includes new tests from ' + ', '.join(labels[:2])
    if len(labels) > 2:
        text += f' and {len(labels) - 2} other locations'
    fixed = sum(i not in members for i in identifiers)
    if fixed:
        text += f' · {fixed} individually selected tests stay fixed'
    exclusions = sum(len(s['excluded']) for s in sources)
    if exclusions:
        text += f'\n{exclusions} intentional exclusion' + (' is kept.' if exclusions == 1 else 's are kept.')
    return text + '\nCheckboxes choose the next run only.'


def compare(profile, available, workspace='', *, complete=True):
    from runner.domain.execution_profile import group_path
    def group_key(entry):
        return tuple(g['id'] for g in group_path(entry))
    plan = SyncPlan(workspace=workspace_key(workspace))
    if not complete:
        plan.problem = 'Collection incomplete — campaign unchanged. Collect successfully before reviewing changes.'
        return plan
    if profile.tracking and profile.tracking['workspace'] != workspace_key(workspace):
        plan.problem = 'Different project selected. Open the original project in Run Tests, or choose Contents to link this campaign to the current project.'
        return plan
    available = list(dict.fromkeys(available))
    plan.available = tuple(available)
    plan.path_changes = location_matches(profile.sequence, available)
    present = set(available)
    by_base = {}
    by_symbol = {}
    for nodeid in available:
        by_base.setdefault(parameter_base(nodeid), []).append(nodeid)
        by_symbol.setdefault(nodeid.partition('::')[2], []).append(nodeid)
    base_moves = location_matches([parameter_base(n) for n in profile.sequence], list(dict.fromkeys(parameter_base(n) for n in available)))
    from runner.domain.campaign_parameters import proposals
    plan.parameter_updates = proposals(profile, available, base_moves)
    for position, nodeid in enumerate(profile.sequence):
        if nodeid not in present:
            plan.missing.append(position)
            plan.candidates[position] = by_base.get(parameter_base(nodeid), [])
            if not plan.candidates[position] and position in base_moves:
                plan.candidates[position] = by_base.get(base_moves[position], [])
            if position not in plan.path_changes:
                possible = by_symbol.get(nodeid.partition('::')[2], [])
                if possible:
                    plan.suggestions[position] = possible[:8]
    if profile.tracking:
        existing_by_source = {}
        positions = {identifier: p for p, identifier in enumerate(profile.step_ids)}
        locations = {}
        for identifier, member in profile.tracking['members'].items():
            updated = plan.path_changes.get(positions[identifier], member['nodeid'])
            existing_by_source.setdefault(member['source'], set()).add(updated)
            if updated in present:
                locations.setdefault(member['source'], []).append((member['nodeid'], updated))
            elif positions[identifier] in base_moves:
                locations.setdefault(member['source'], []).append((parameter_base(member['nodeid']), base_moves[positions[identifier]]))
        for source in profile.tracking['sources']:
            source = copy.deepcopy(source)
            targets = {_source_at_location(source, old, new) for old, new in locations.get(source['id'], [])}
            if len(targets) == 1 and None not in targets:
                target = next(iter(targets))
                if target != source['selector']:
                    plan.source_paths[source['id']] = target
                    source['excluded'] = _relocated_exclusions(source, target)
                    source['selector'] = target
            existing = existing_by_source.get(source['id'], set())
            excluded = set(source['excluded'])
            managed = {u['base'] for u in plan.parameter_updates.values() if u['source'] == source['id']}
            if source['kind'] != 'test':
                groups = profile.step_groups or [{} for _ in profile.sequence]
                managed.update(u['base'] for first, u in plan.parameter_updates.items()
                               if group_key(groups[first]) == group_key(source['group']))
                managed.update(base_moves.get(p, parameter_base(n)) for p, n in enumerate(profile.sequence)
                               if n != parameter_base(n) and profile.step_ids[p] not in profile.tracking['members']
                               and group_key(groups[p]) == group_key(source['group']))
            managed.update(s['selector'] for s in profile.tracking['sources'] if s['kind'] == 'test' and group_key(s['group']) == group_key(source['group']) and s['id'] != source['id'])
            plan.additions.extend((source['id'], nodeid) for nodeid in available
                                  if nodeid not in existing and nodeid not in excluded and parameter_base(nodeid) not in excluded
                                  and parameter_base(nodeid) not in managed and matches(source, nodeid))
    return plan


def apply(profile, plan, additions, decisions, *, transfer=(), refresh_cases=True):
    """Applique seulement les choix revus, jamais des correspondances approximatives."""
    from runner.domain.execution_profile import validate_profile, ProfileValidationError, group_path
    if plan.problem:
        raise ProfileValidationError(plan.problem)
    result = copy.deepcopy(profile)
    ensure_ids(result)
    exclude_removed_fixed_cases(result, {p for p in plan.missing if decisions.get(p) == 'remove'})
    patches = result.step_overrides or [{} for _ in result.sequence]
    groups = result.step_groups or [{} for _ in result.sequence]
    members = result.tracking.get('members', {})
    sources = {s['id']: s for s in result.tracking.get('sources', [])}
    original_members = copy.deepcopy(members)
    for position in plan.missing:
        if not decisions.get(position):
            raise ProfileValidationError('Choose an action for every unavailable occurrence.')
    parameter_rows, parameter_positions = {}, set()
    if refresh_cases:
        from runner.domain.campaign_parameters import rows as parameter_rows_for
        for first, update in plan.parameter_updates.items():
            values = parameter_rows_for(result, update, decisions, set(transfer) | set(plan.path_changes), members, sources, plan.workspace)
            if values is not None:
                parameter_rows[first] = values
                parameter_positions.update(update['positions'])
    for source_id, selector in plan.source_paths.items():
        source = sources[source_id]
        owned = [p for p, i in enumerate(result.step_ids) if members.get(i, {}).get('source') == source_id and p in plan.path_changes]
        if all(decisions.get(p) == plan.path_changes[p] for p in owned):
            source['excluded'] = _relocated_exclusions(source, selector)
            source['selector'] = selector
    chosen = set(additions)
    if not chosen <= set(plan.additions):
        raise ProfileValidationError('The collection changed. Review this campaign again.')
    inserts, rows, replacements = {}, [], {}
    for position in plan.missing:
        if position in parameter_positions:
            continue
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
    effective_nodes = {p: choice for p, choice in decisions.items() if choice in ranks}
    effective_nodes.update({p: values[0][0] for p, values in parameter_rows.items()})
    empty_slots = {}
    for order, record in enumerate(result.empty_groups):
        for group in group_path(record['group']):
            empty_slots.setdefault(group['id'], (record['position'], order))
    def source_order(source):
        owned = [positions[i] for i, m in original_members.items() if m['source'] == source['id'] and i in positions]
        empty = empty_slots.get(source['group'].get('id'))
        return (min(owned), 1, 0) if owned else (empty[0], 0, empty[1]) if empty else (len(result.sequence), 2, 0)
    for source in sorted(sources.values(), key=source_order):
        owned = sorted(positions[i] for i, m in original_members.items() if m['source'] == source['id'] and i in positions)
        current = [(p, effective_nodes.get(p, replacements.get(p, result.sequence[p]))) for p in owned
                   if decisions.get(p) != 'remove' or p in parameter_rows]
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
                empty = empty_slots.get(source['group'].get('id'))
                slot = empty[0] if empty else positions.get(source['anchor'], -1 if source['anchor'] == '__start__' else len(result.sequence) - 1) + 1
            inserts.setdefault(slot, []).append((source, nodeid))
    def insert(slot):
        for source, new_nodeid in inserts.get(slot, []):
            new_id = str(uuid.uuid4())
            rows.append((new_nodeid, new_id, {}, copy.deepcopy(source['group'])))
            members[new_id] = dict(source=source['id'], nodeid=new_nodeid)
            source['anchor'] = new_id
    for position, (nodeid, identifier, patch, group) in enumerate(zip(result.sequence, result.step_ids, patches, groups)):
        insert(position)
        if position in parameter_positions:
            rows.extend(parameter_rows.get(position, []))
            continue
        keep = True
        if position in plan.missing:
            decision = decisions.get(position, '')
            if decision == 'remove':
                keep = False
            elif decision != 'keep':
                nodeid = decision
                patch = patch if position in transfer or plan.path_changes.get(position) == decision else {}
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
    from runner.domain.empty_groups import retained
    result.empty_groups = retained(profile, result.sequence, result.step_groups, profile.step_ids, result.step_ids)
    retained = set(result.step_ids)
    for source in sources.values():
        if source['anchor'] not in retained:
            old_position = positions.get(source['anchor'], 0)
            source['anchor'] = next((i for i in reversed(profile.step_ids[:old_position]) if i in retained), '__start__')
    prune_sources(result)
    validate_profile(result)
    return result
