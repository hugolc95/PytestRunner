"""Derniere version restauree apres redemarrage, sans ecraser un edit plus recent."""
import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path


def fingerprint(profile):
    value = asdict(profile)
    value.pop('source', None)
    count = len(value['sequence'])
    value['step_overrides'] = value.get('step_overrides') or [{} for _ in range(count)]
    value['step_groups'] = value.get('step_groups') or [{} for _ in range(count)]
    value['name'] = value['name'].strip()
    value['description'] = value['description'].strip()
    if value.get('empty_groups') and not value.get('step_ids'):
        value['step_ids'] = [f'step-{i:05d}' for i in range(1, len(value['sequence']) + 1)]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def digest(store, identifier):
    try:
        return hashlib.sha256(store._path(identifier).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _directory(store, identifier):
    return store.root / '.updates' / store._path(identifier).stem


def _atomic(path, text):
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record(store, profile, before, expected):
    from runner.domain.execution_profile import export_profile, ProfileValidationError
    if digest(store, profile.profile_id) != expected:
        raise ProfileValidationError('This campaign changed on disk. Reload it before applying the update. Your edits have been kept.')
    directory = _directory(store, profile.profile_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'undo.json'
    previous_record = path.read_text(encoding='utf-8') if path.exists() else None
    backup = export_profile(before, directory / (str(uuid.uuid4()) + '.pytest-profile'))
    value = dict(before=fingerprint(before), after=fingerprint(profile), backup=backup.name)
    _atomic(path, json.dumps(value))
    try:
        store.save(profile)
    except Exception:
        if previous_record is None:
            path.unlink(missing_ok=True)
        else:
            _atomic(path, previous_record)
        raise
    try:
        older = sorted((p for p in directory.glob('*.pytest-profile') if p != backup), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for path in older[4:]:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def previous(store, identifier):
    from runner.domain.execution_profile import inspect_profile, ProfileValidationError
    directory = _directory(store, identifier)
    try:
        value = json.loads((directory / 'undo.json').read_text(encoding='utf-8'))
        name = value['backup']
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.pytest-profile'):
            return None
        current = inspect_profile(store._path(identifier)).profile
        before = inspect_profile(directory / name).profile
        if fingerprint(current) != value['after'] or fingerprint(before) != value['before']:
            return None
        return before
    except (OSError, ValueError, KeyError, TypeError, ProfileValidationError):
        return None


def restore(store, identifier):
    from runner.domain.execution_profile import ProfileValidationError
    before = previous(store, identifier)
    if before is None:
        raise ProfileValidationError('A newer edit exists, or the previous version is unavailable. The current campaign has been kept.')
    store.save(before)
    return before
