"""Instantane portable d'un run : occurrences, lecteurs, arbre et diagnostic."""
from collections import Counter, defaultdict
import copy
import json
import re

import yaml

from runner.domain import failures, parsing
from runner.domain.ansi import strip_ansi
from runner.domain.execution_profile import group_path, merge_configuration, profile_group_runs
from runner.domain.models import Kind
from runner.domain.report_capture import read_analysis
from runner.domain.report_timing import archived_timings, valid_duration
from runner.domain.tree import build_sequence_tree, collapse_single_class


NOT_RECORDED = 'Not recorded in this archive.'


def _status(value):
    value = str(value or '').lower()
    return value if value in ('passed', 'failed', 'error', 'skipped', 'notrun') else 'unknown'


def _legacy_attempts(entry, position, sequence, frequencies, by_node, ordered):
    nodeid = sequence[position]
    recorded = entry.executions
    if ordered:
        return [dict(attempt=0, status=recorded[position][1])]
    if frequencies[nodeid] != 1:
        return []
    candidates = [dict(attempt=i, status=status) for i, status in enumerate(by_node.get(nodeid, []))]
    if candidates:
        return candidates
    status = entry.test_statuses.get(nodeid)
    if not status and entry.total >= len(sequence):
        possible = [name for name in ('PASSED', 'FAILED', 'ERROR', 'SKIPPED')
                    if entry.counts.get(name, 0) and (name in ('FAILED', 'ERROR')) == (nodeid in entry.failed_nodeids)]
        status = possible[0] if len(possible) == 1 else None
    return [dict(attempt=0, status=status)] if status else []


def _configuration(entry, saved, step, reader):
    raw = entry.configuration_text()
    if raw is None:
        raw = saved.get('configuration_text') if saved.get('configuration_name') else None
    if raw is None:
        return dict(base='', effective='', origins=[], parameters=[], notice=NOT_RECORDED)
    try:
        base = yaml.safe_load(raw) or {}
        if not isinstance(base, dict):
            raise ValueError('The archived YAML is not a mapping.')
        value = copy.deepcopy(base)
        origins = {}
        def parameter_path(path, key):
            key = str(key)
            segment = '[' + json.dumps(key, ensure_ascii=False) + ']' if any(c in key for c in '.[]') else key
            return path + segment if segment.startswith('[') else f'{path}.{segment}' if path else segment
        def mark(patch, label, path=''):
            for key, item in patch.items():
                name = parameter_path(path, key)
                if isinstance(item, dict):
                    origins.pop(name, None)
                    if item:
                        mark(item, label, name)
                    else:
                        origins[name] = label
                else:
                    for old in tuple(origins):
                        if old == name or old.startswith(name + '.'):
                            del origins[old]
                    origins[name] = label
        mark(base, 'Base ' + (saved.get('configuration_name') or 'configuration YAML'))
        groups = saved.get('step_groups') or []
        patch = saved.get('step_overrides') or []
        for group in group_path(groups[step] if step < len(groups) else {}):
            own = group.get('configuration_overrides', {})
            value = merge_configuration(value, own)
            mark(own, 'Group: ' + group.get('name', ''))
        own = patch[step] if step < len(patch) else {}
        value = merge_configuration(value, own)
        mark(own, 'This occurrence')
        # La virtualisation du lecteur ne change que la cle existante.
        for key in value:
            if str(key).lower() in ('reader', 'lecteur') and reader:
                value[key] = reader
                mark({key: reader}, 'Reader selected at launch')
                break
        parameters = {}
        def flatten(mapping, path=''):
            for key, item in mapping.items():
                name = parameter_path(path, key)
                if isinstance(item, dict) and item:
                    flatten(item, name)
                else:
                    parameters[name] = item
        flatten(value)
        final_origins = {key: origins.get(key, 'Base configuration') for key in parameters}
        return dict(base=raw, effective=yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
                    origins=[dict(parameter=key, source=source) for key, source in final_origins.items()],
                    parameters=[dict(parameter=key, value=parameters[key], source=source) for key, source in final_origins.items()], notice='')
    except (yaml.YAMLError, ValueError, TypeError, AttributeError) as exc:
        return dict(base=raw, effective='', origins=[], parameters=[], notice=f'Archived YAML could not be resolved: {exc}')


def _tree(sequence, saved, rows):
    length = len(saved.get('sequence') or sequence)
    metadata = saved.get('step_groups') or []
    roots, named = [], {}
    repetitions = max(1, (len(sequence) + max(1, length) - 1) // max(1, length))
    for repetition in range(repetitions):
        part = sequence[repetition * length:(repetition + 1) * length] if length else []
        children = []
        for start, end, group in profile_group_runs(part, metadata[:len(part)] if metadata else []):
            siblings = children
            path = group_path(group)
            for item in path:
                last = siblings[-1] if siblings else None
                previous = named.get(id(last))
                if previous and previous.get('id') == item.get('id'):
                    node = last
                else:
                    from runner.domain.models import TestNode
                    node = TestNode(item.get('name', 'Group'), Kind.FOLDER)
                    named[id(node)] = item
                    siblings.append(node)
                siblings = node.children
            nested = collapse_single_class(build_sequence_tree(part[start:end]))
            if path:
                while len(nested) == 1 and nested[0].kind is Kind.FOLDER and nested[0].children:
                    nested = nested[0].children
            siblings.extend(nested)
        from runner.domain.empty_groups import add_nodes
        add_nodes(children, named, saved.get('empty_groups', []))
        if repetitions > 1:
            from runner.domain.models import TestNode
            roots.append(TestNode(f'Repetition {repetition + 1} / {repetitions}', Kind.FOLDER, children=children))
        else:
            roots.extend(children)
    nodes = {'profile': dict(id='profile', name=saved.get('name') or 'Run', kind='profile', description=saved.get('description', ''), children=[], parent=None, color='')}
    position = 0
    def add(node, parent, ancestors, membership, color):
        nonlocal position
        group = named.get(id(node))
        if group:
            color = group.get('color', '')
            color = color if re.fullmatch(r'#[0-9a-fA-F]{6}', str(color)) else ''
            membership = [*membership, group.get('name', '')]
        if node.nodeid:
            row = rows[position]
            row.update(parents=ancestors, groups=membership, name=node.name)
            node_id = row['id']
            position += 1
            own = dict(row, kind='test', parent=parent, children=[], color=color)
        else:
            node_id = 'n' + str(len(nodes))
            own = dict(id=node_id, name=node.name, kind='group' if group else 'function' if node.kind is Kind.TEST else node.kind.value,
                       description=group.get('description', '') if group else '', parent=parent,
                       children=[], color=color)
        nodes[node_id] = own
        nodes[parent]['children'].append(node_id)
        for child in node.children:
            add(child, node_id, [*ancestors, node_id], membership, color)
    for node in roots:
        add(node, 'profile', ['profile'], [], '')
    return nodes


def report_payload(entries, outputs=None):
    entries = tuple(entries)
    if not entries:
        raise ValueError('No archived run was selected.')
    first = entries[0]
    if any(entry.id != first.id or entry.workspace != first.workspace for entry in entries):
        raise ValueError('An HTML report can only combine readers from the same run.')
    analyses = [read_analysis(entry) for entry in entries]
    saved = next((a.get('campaign_profile') for a in analyses if a.get('campaign_profile')), None)
    saved = saved or next((entry.replay_profile for entry in entries if entry.replay_profile), {}) or {}
    sequence = list(saved.get('sequence') or first.nodeids)
    repeat = (saved.get('execution') or {}).get('repetitions', 1)
    sequence *= max(1, int(repeat)) if saved.get('sequence') else 1
    if not sequence:
        sequence = [nodeid for nodeid, _ in first.executions] or list(dict.fromkeys(n for entry in entries for n in entry.test_statuses))
    readers = [entry.reader or 'Test interpreter' for entry in entries]
    texts = [strip_ansi(outputs[i] if outputs is not None else entry.output()) for i, entry in enumerate(entries)]
    indexes = [failures.index_failures(text) for text in texts]
    durations = [archived_timings(text, sequence) for text in texts]
    archived = [dict(entry.counts) for entry in entries]
    frequencies = Counter(sequence)
    legacy_maps = []
    for entry in entries:
        mapping = defaultdict(list)
        for nodeid, status in entry.executions:
            mapping[nodeid].append(status)
        legacy_maps.append((mapping, len(entry.executions) == len(sequence) and [n for n, _ in entry.executions] == sequence))
    rows = []
    configuration_cache = {}
    used_logs = [set() for _ in entries]
    length = len(saved.get('sequence') or sequence) or 1
    for position, nodeid in enumerate(sequence):
        row = dict(id=f't{position}', index=position, nodeid=nodeid, name=nodeid.split('::')[-1],
                   file=nodeid.partition('::')[0], repetition=position // length + 1,
                   step=position % length + 1, readers=[], parents=[], groups=[], custom=False)
        patch = saved.get('step_overrides') or []
        row['custom'] = bool(patch[position % length]) if position % length < len(patch) else False
        for reader, entry in enumerate(entries):
            analysis = analyses[reader]
            occurrences = analysis.get('occurrences', [])
            captured = occurrences[position] if position < len(occurrences) and occurrences[position].get('nodeid') == nodeid else None
            attempts = copy.deepcopy(captured.get('attempts', [])) if captured is not None else _legacy_attempts(entry, position, sequence, frequencies, *legacy_maps[reader])
            if not attempts and captured is None:
                attempts = [dict(attempt=attempt, status='unknown', duration=duration,
                    duration_source='Recovered from archived pytest timing')
                    for (where, attempt), duration in durations[reader].items()
                    if where == position and attempt is not None]
                attempts.sort(key=lambda attempt: attempt['attempt'])
            for attempt in attempts:
                attempt['status'] = _status(attempt.get('status'))
                records = attempt.get('details') or []
                owned = [record for record in records if record.get('nodeid') == nodeid]
                failure = failures.failure_for(indexes[reader], nodeid) if not owned and frequencies[nodeid] == 1 and len(attempts) == 1 else None
                attempt['trace'] = '\n\n'.join(f"{record.get('phase', '').upper()}\n{record.get('body', '')}" for record in owned)
                attempt['phase'] = next((record.get('phase', '') for record in owned if record.get('kind') == 'test'), '')
                attempt['message'] = next((record.get('message', '') for record in owned if record.get('message')), '')
                if failure:
                    attempt.update(trace=failure.body, phase=failure.phase, message=failure.headline)
                if not valid_duration(attempt.get('duration')):
                    measured = durations[reader].get((position, attempt.get('attempt', 0)))
                    if measured is None and len(attempts) == 1:
                        measured = durations[reader].get((position, None))
                    attempt['duration'] = measured
                    if measured is not None:
                        attempt['duration_source'] = 'Recovered from archived pytest timing'
                if not attempt.get('log') and analysis.get('save_logs', True) and entry.build_number is not None and frequencies[nodeid] == 1:
                    from runner.domain.logs import find_test_log
                    from pathlib import Path
                    if entry.log_root and not attempt.get('log_path'):
                        try:
                            path = find_test_log(Path(entry.log_root), nodeid, entry.reader,
                                                 build_number=entry.build_number, excluded=frozenset(used_logs[reader]))
                            if path is not None:
                                attempt['log'] = path.read_text(encoding='utf-8', errors='replace')
                                attempt['log_path'] = str(path)
                                used_logs[reader].add(path)
                        except OSError:
                            pass
                # Une sortie globale n'est jamais rebaptisee log individuel.
                attempt.setdefault('log', '')
            status = attempts[-1]['status'] if attempts else 'notrun' if captured and captured.get('not_run') else 'unknown'
            groups = saved.get('step_groups') or []
            patches = saved.get('step_overrides') or []
            step = position % length
            configuration_key = (reader, json.dumps([groups[step] if step < len(groups) else {},
                patches[step] if step < len(patches) else {}], sort_keys=True, default=str))
            if configuration_key not in configuration_cache:
                configuration_cache[configuration_key] = _configuration(entry, saved, step, entry.reader)
            row['readers'].append(dict(status=status, attempts=attempts,
                yaml=configuration_cache[configuration_key],
                notice=captured.get('reason', '') if captured is not None else 'Older archive: occurrence-level details were not recorded.'))
        rows.append(row)
    nodes = _tree(sequence, saved, rows)
    nodes['profile']['name'] = first.run_name or first.profile_name or saved.get('name') or 'Test run'
    contexts = []
    for entry, analysis, text in zip(entries, analyses, texts):
        session = next((line for line in text.splitlines() if re.search(r'platform .*Python .*pytest', line)), '')
        contexts.append(dict(reader=entry.reader or 'Test interpreter', exit_code=entry.exit_code,
            interpreter=analysis.get('interpreter') or NOT_RECORDED, atr=analysis.get('atr') or NOT_RECORDED,
            session=session or NOT_RECORDED, commands=analysis.get('commands', []),
            issues=analysis.get('issues', []), app_version=analysis.get('app_version') or NOT_RECORDED))
    counts = Counter(result['status'] for row in rows for result in row['readers'])
    from runner.domain.reader_labels import badge_labels
    return dict(schema=1, id=first.id, title=nodes['profile']['name'], workspace=first.workspace,
                timestamp=max(entry.timestamp for entry in entries), duration=max(entry.duration for entry in entries),
                build=first.build_number, readers=readers, badges=badge_labels(readers), rows=rows, nodes=nodes, counts=dict(counts),
                archived_counts=archived, contexts=contexts, console=texts,
                configuration_name=saved.get('configuration_name', ''),
                coverage=[entry.campaign_coverage for entry in entries],
                complete=bool(sequence) and not counts['notrun'] and not counts['unknown'],
                run_kind=first.run_kind, profile_recorded=bool(saved))
