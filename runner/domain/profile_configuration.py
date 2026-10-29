"""Valeurs YAML effectives et provenance, identiques a la fusion du runner."""
import copy
import yaml

from runner.domain.execution_profile import merge_configuration


def fields(mapping, prefix=()):
    for key, value in mapping.items():
        path = (*prefix, key)
        if isinstance(value, dict) and value:
            yield from fields(value, path)
        else:
            yield path, value


def configuration_details(base, groups=(), test_patch=None):
    effective = copy.deepcopy(base)
    origins = {path: 'Profile' for path, _ in fields(effective)}
    exceptions = {}

    def apply(patch, source, check):
        nonlocal effective
        before = dict(fields(effective))
        touched = []
        def writes(target, changes, prefix=()):
            for key, value in changes.items():
                path = (*prefix, key)
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    writes(target[key], value, path)
                else:
                    touched.append(path)
        writes(effective, patch)
        effective = merge_configuration(effective, patch)
        after = dict(fields(effective))
        for path in list(origins):
            if path not in after:
                origins.pop(path)
                exceptions.pop(path, None)
        for path, value in after.items():
            if not any(path[:len(parent)] == parent for parent in touched):
                continue
            previous_source = origins.get(path, 'Profile')
            origins[path] = source
            if check and path in before and (value != before[path] or type(value) is not type(before[path])):
                exceptions[path] = {'path': path, 'value': copy.deepcopy(value),
                                    'inherited': copy.deepcopy(before[path]), 'source': source,
                                    'inherited_source': previous_source}

    names = []
    for index, group in enumerate(groups):
        names.append(group['name'])
        apply(group.get('configuration_overrides', {}), 'Group: ' + ' / '.join(names), index > 0)
    if test_patch is not None:
        apply(test_patch, 'This test', bool(groups))
    rows = [{'path': path, 'value': copy.deepcopy(value), 'source': origins[path],
             'exception': exceptions.get(path)} for path, value in fields(effective)]
    return effective, rows, list(exceptions.values())


def exception_text(exception):
    path = '.'.join(map(str, exception['path']))
    return (f"{path}: {exception['value']} ({exception['source']}; inherited "
            f"{exception['inherited']} from {exception['inherited_source']})")


def _value_text(value):
    if isinstance(value, str):
        text = value if value else '""'
    elif value is None:
        text = 'null'
    elif isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, (int, float)):
        text = str(value)
    else:
        text = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).split('\n...')[0].strip()
    return text.replace('\n', ' ')[:240]


def configuration_annotation(base, groups=(), test_patch=None):
    """Decrit aussi les personnalisations normales, pas seulement les exceptions."""
    groups = list(groups)
    own_group = groups[-1] if test_patch is None and groups else None
    parents = groups[:-1] if own_group else groups
    patch = own_group.get('configuration_overrides', {}) if own_group else (test_patch or {})
    inherited, inherited_details, _ = configuration_details(base, parents)
    effective, rows, exceptions = configuration_details(base, groups, test_patch)
    own = []
    summaries = []
    custom_entries = []
    for path, value in fields(patch):
        name = '.'.join(map(str, path))
        missing = object()
        old = inherited
        for key in path:
            old = old.get(key, missing) if isinstance(old, dict) else missing
        if old is not missing and type(old) is type(value) and old == value:
            own.append(f'{name}: {_value_text(value)} (explicit; same as inherited)')
        else:
            before = _value_text(old) if old is not missing else '(not set)'
            own.append(f'{name}: {before} → {_value_text(value)}')
        sources = list(dict.fromkeys(row['source'] for row in inherited_details
                                    if row['path'][:len(path)] == path))
        origin = sources[0] if len(sources) == 1 else 'Inherited settings'
        actual = effective
        for key in path:
            actual = actual.get(key, value) if isinstance(actual, dict) else value
        label = 'Group default' if own_group else 'Value used'
        previous = _value_text(old) + ' — ' + origin if old is not missing else 'Not defined'
        summary = f'{name}\n  {label}: {_value_text(actual)}\n  Inherited value: {previous}'
        if old is not missing and type(old) is type(value) and old == value:
            summary += '\n  Same as inherited; explicitly saved here.'
        summaries.append(summary)
        custom_entries.append({'parameter': name, 'value': _value_text(actual),
                               'inherited': _value_text(old) if old is not missing else 'Not defined',
                               'origin': origin if old is not missing else '',
                               'same': old is not missing and type(old) is type(value) and old == value})
    own_source = 'Group: ' + ' / '.join(g['name'] for g in groups) if own_group else 'This test'
    inherited_rows = [f"{'.'.join(map(str, row['path']))}: {_value_text(row['value'])} ({row['source']})"
                      for row in rows if row['source'].startswith('Group: ') and row['source'] != own_source]
    sections = []
    if own:
        sections.append(('Customized on this group' if own_group else 'Customized on this test')
                        + '\n' + '\n\n'.join(summaries))
    if inherited_rows:
        label = 'Group default' if own_group else 'Value used'
        sections.append('From groups\n' + '\n\n'.join(
            f"{'.'.join(map(str, row['path']))}\n  {label}: {_value_text(row['value'])}\n  Defined by: {row['source']}"
            for row in rows if row['source'].startswith('Group: ') and row['source'] != own_source))
    texts = [exception_text(value) for value in exceptions]
    return {'state': 'custom' if own else ('inherited' if inherited_rows else ''),
            'count': len(own) if own else len(inherited_rows), 'own': own,
            'inherited': inherited_rows, 'exceptions': texts,
            'custom_summary': summaries,
            'scope': 'group' if own_group else 'test',
            'custom_entries': custom_entries,
            'inherited_entries': [{'parameter': '.'.join(map(str, row['path'])),
                                   'value': _value_text(row['value']), 'origin': row['source']}
                                  for row in rows if row['source'].startswith('Group: ') and row['source'] != own_source],
            'tooltip': '\n\n'.join(sections)}


def aggregate_annotations(annotations, inherited=None):
    """Un dossier indique les tests personnalises sans se faire passer pour un patch."""
    customized = [value for value in annotations if value['own']]
    result = copy.deepcopy(inherited or configuration_annotation({}))
    result['exceptions'] = list(dict.fromkeys(text for value in annotations for text in value['exceptions']))
    if customized:
        changes = list(dict.fromkeys(text for value in customized for text in value['custom_summary']))
        entries, seen = [], set()
        for value in customized:
            for entry in value['custom_entries']:
                key = tuple(entry.items())
                if key not in seen:
                    seen.add(key)
                    entries.append(copy.deepcopy(entry))
        result.update(state='descendants', count=len(customized),
                      customized_tests=len(customized), total_tests=len(annotations),
                      custom_entries=entries,
                      tooltip=f'{len(customized)} of {len(annotations)} tests have customized YAML.\n'
                      + '\n'.join(changes) + ('\n\n' + result['tooltip'] if result['tooltip'] else ''))
    return result
