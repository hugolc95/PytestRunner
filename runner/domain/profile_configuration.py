"""Valeurs YAML effectives et provenance, identiques a la fusion du runner."""
import copy

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
