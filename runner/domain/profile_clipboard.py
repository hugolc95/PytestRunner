"""Format du presse-papiers : occurrences et hierarchies, jamais du code executable."""
import json

import yaml

from runner.domain.execution_profile import (
    ExecutionProfile, ProfileValidationError, MAX_CONFIG_BYTES, MAX_STEPS, validate_profile,
)

MIME = 'application/x-pytestrunner-profile-sequence+json'
FORMAT = 'pytestrunner-profile-selection'
MAX_BYTES = 8 * 1024 * 1024
KINDS = {'group', 'folder', 'module', 'class', 'parameterized', 'test', 'case'}


def _mapping(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_CONFIG_BYTES:
        raise ProfileValidationError('The copied configuration is too large.')
    try:
        value = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ProfileValidationError('The copied configuration is invalid.') from exc
    if not isinstance(value, dict):
        raise ProfileValidationError('The copied configuration must be a mapping.')
    count = 0
    def visit(item, stack=(), depth=0):
        nonlocal count
        count += 1
        if count > 100_000 or depth > 30 or id(item) in stack:
            raise ProfileValidationError('The copied configuration is nested too deeply.')
        if isinstance(item, (dict, list)):
            for child in item.values() if isinstance(item, dict) else item:
                visit(child, (*stack, id(item)), depth + 1)
    visit(value)
    return value


def decode_selection(data):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ProfileValidationError('The copied selection is too large.')
    try:
        payload = json.loads(data.decode('utf-8'))
        # JSON peut accepter NaN ou des substituts Unicode isoles. Ils ne
        # doivent pas arriver dans le modele Qt ni dans l'historique UTF-8.
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProfileValidationError('The clipboard does not contain a valid test selection.') from exc
    keys = {'format', 'version', 'copy_id', 'owner', 'source', 'bases', 'items'}
    if not isinstance(payload, dict) or set(payload) != keys or payload['format'] != FORMAT or type(payload['version']) is not int or payload['version'] != 1:
        raise ProfileValidationError('Unsupported test selection format.')
    for key in ('copy_id', 'owner', 'source'):
        if not isinstance(payload[key], str) or not payload[key] or len(payload[key]) > 160:
            raise ProfileValidationError('Invalid copied selection metadata.')
    if not isinstance(payload['bases'], list) or not payload['bases'] or len(payload['bases']) > MAX_STEPS:
        raise ProfileValidationError('Invalid copied configuration contexts.')
    # Le YAML reste du texte dans le format transportable. Ses types natifs
    # (dates, cles numeriques) ne sont pas alteres par une conversion JSON.
    for base in payload['bases']:
        _mapping(base)
    items = payload['items']
    if not isinstance(items, list) or not items or len(items) > MAX_STEPS:
        raise ProfileValidationError('The selection contains no test elements.')
    total = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {'kind', 'label', 'sequence', 'patches', 'groups', 'base'}:
            raise ProfileValidationError('Invalid copied element.')
        if not isinstance(item['kind'], str) or item['kind'] not in KINDS or not isinstance(item['label'], str) or len(item['label']) > 16_384:
            raise ProfileValidationError('Invalid copied element type or label.')
        if type(item['base']) is not int or not 0 <= item['base'] < len(payload['bases']):
            raise ProfileValidationError('Invalid copied element configuration.')
        if not isinstance(item['sequence'], list) or not isinstance(item['patches'], list) or not isinstance(item['groups'], list):
            raise ProfileValidationError('Invalid copied sequence.')
        size = len(item['sequence'])
        if size == 0 or len(item['patches']) != size or len(item['groups']) != size:
            raise ProfileValidationError('Copied parameters must match the occurrence count.')
        total += size
        if total > MAX_STEPS:
            raise ProfileValidationError('The copied selection contains too many tests.')
        validate_profile(ExecutionProfile('Clipboard', item['sequence'], '', '',
                                         step_overrides=item['patches'], step_groups=item['groups']))
    return payload


def encode_selection(payload):
    try:
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProfileValidationError('The selection could not be copied.') from exc
    decode_selection(data)
    return data


def inherited_base(payload, item):
    return _mapping(payload['bases'][item['base']])
