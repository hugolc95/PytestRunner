"""Suivre le YAML source sans ecraser les reglages propres a un run."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from runner.domain.config_file import valider


@dataclass(frozen=True)
class SourceState:
    source: str = ''
    changed: bool = False
    local_changed: bool = False
    updated: bool = False
    problem: str = ''


def _metadata(copy):
    return Path(copy).with_name(Path(copy).name + '.source.json')


def _baseline(copy, source):
    try:
        data = json.loads(_metadata(copy).read_text(encoding='utf-8'))
        digest = data.get('digest', '')
        if data.get('source') == str(Path(source).resolve()) and isinstance(digest, str) and len(digest) == 64:
            return digest
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def _write(path, content):
    """Remplacer d'un bloc, avec un temporaire propre a cette ecriture."""
    path = Path(path)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def _remember(copy, source, digest):
    data = dict(source=str(Path(source).resolve()), digest=digest)
    _write(_metadata(copy), json.dumps(data).encode('utf-8'))


def remember_source(copy, source, ancestor=None):
    """Une duplication herite de la reference, pas des modifications locales."""
    direct = ancestor is None or Path(ancestor).resolve() == Path(source).resolve()
    digest = sha256(Path(copy).read_bytes()).hexdigest() if direct else _baseline(ancestor, source)
    if digest is None:
        try:
            digest = sha256(Path(source).read_bytes()).hexdigest()
        except OSError:
            return
    _remember(copy, source, digest)


def sync_source(copy, source, *, allow_update=True, force=False, keep=False, local_edits=False):
    copy, source = Path(copy), Path(source)
    name = str(source.resolve())
    if copy.resolve() == source.resolve():
        return SourceState()
    try:
        source_content = source.read_bytes()
    except OSError as exc:
        return SourceState(name, problem=f'Source file unavailable: {exc}')
    content = copy.read_bytes()
    digest, current = sha256(source_content).hexdigest(), sha256(content).hexdigest()
    baseline = _baseline(copy, source)
    if keep:
        # Le choix porte sur CETTE version de la source : ne pas redemander
        # au prochain Reload, mais detecter les prochaines sauvegardes IDE.
        _remember(copy, source, digest)
        return SourceState(name, local_changed=current != digest or local_edits)
    # Sans reference (anciennes sessions), une copie differente reste locale.
    changed = digest != baseline if baseline else current != digest
    local = local_edits or (current != baseline if baseline else current != digest)
    if current == digest:
        if baseline != digest and (allow_update or force):
            _remember(copy, source, digest)
        return SourceState(name, local_changed=local_edits)
    if not force and (not changed or local or not allow_update):
        return SourceState(name, changed=changed, local_changed=local)
    try:
        valid, error = valider(source_content.decode('utf-8-sig'))
    except UnicodeError as exc:
        valid, error = False, str(exc)
    if not valid:
        return SourceState(name, changed=True, local_changed=local,
                           problem=f'Source YAML is invalid: {error}')
    _write(copy, source_content)
    _remember(copy, source, digest)
    return SourceState(name, updated=True)
