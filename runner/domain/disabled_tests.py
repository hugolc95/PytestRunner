"""Persistent, workspace-scoped test exclusions, independent of run selections."""
from __future__ import annotations

import getpass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4


class DisabledTestsError(ValueError):
    pass


def workspace_key(workspace: str) -> str:
    return os.path.normcase(str(Path(workspace).resolve()))


def parameter_base(nodeid: str) -> str:
    path, separator, qualified = nodeid.partition('::')
    return path + separator + qualified.split('[', 1)[0] if separator else path


def activation_record(records: dict, nodeid: str, *, skip_exact=False):
    """The most specific decision wins, including an explicit enabled exception."""
    nodeid = nodeid.replace('\\', '/')
    if not skip_exact and nodeid in records:
        return records[nodeid]
    parts = parameter_base(nodeid).split('::')
    while parts:
        target = '::'.join(parts)
        record = records.get(target) if not (skip_exact and target == nodeid) else None
        if record:
            return record
        parts.pop()
    folder = nodeid.split('::', 1)[0]
    while '/' in folder:
        folder = folder.rsplit('/', 1)[0]
        if folder in records:
            return records[folder]
    return None


def matching_record(records: dict, nodeid: str):
    record = activation_record(records, nodeid)
    return record if record and not record.get('enabled', False) else None


class DisabledTestsStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, workspace: str) -> Path:
        key = sha256(workspace_key(workspace).encode('utf-8')).hexdigest()
        return self.root / f'{key}.json'

    def _read(self, workspace: str) -> dict:
        path = self.path(workspace)
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('version') != 1
                    or data.get('workspace') != workspace_key(workspace)
                    or not isinstance(data.get('disabled'), dict)
                    or not isinstance(data.get('events'), list)):
                raise ValueError('Invalid activation registry')
            for nodeid, record in data['disabled'].items():
                if (not isinstance(nodeid, str) or not nodeid.strip()
                        or not isinstance(record, dict)
                        or not all(isinstance(record.get(k), str) and record[k].strip()
                                   for k in ('nodeid', 'author', 'date'))
                        or not isinstance(record.get('reason'), str)
                        or type(record.get('enabled', False)) is not bool
                        or record['nodeid'] != nodeid):
                    raise ValueError('Invalid disabled test entry')
            return data
        except FileNotFoundError:
            return {'version': 1, 'workspace': workspace_key(workspace), 'disabled': {}, 'events': []}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise DisabledTestsError(f'Could not read test activation settings: {path}\n{exc}') from exc

    def records(self, workspace: str) -> dict:
        return self._read(workspace)['disabled']

    def _write(self, workspace: str, data: dict) -> None:
        target = self.path(workspace)
        temporary = target.with_name(f'{target.stem}.{uuid4().hex}.tmp')
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(target)
        except OSError as exc:
            raise DisabledTestsError(f'Could not save test activation settings: {exc}') from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def disable(self, workspace: str, nodeid: str, reason: str = '') -> None:
        nodeid = nodeid.strip().replace('\\', '/')
        reason = reason.strip()
        if not nodeid or len(reason) > 4000 or '\n' in nodeid:
            raise DisabledTestsError('Choose an element. The optional reason is limited to 4000 characters.')
        data = self._read(workspace)
        data['disabled'] = {key: value for key, value in data['disabled'].items()
                            if not (value.get('enabled', False) and key != nodeid
                                    and activation_record({nodeid: {'nodeid': nodeid}}, key))}
        record = dict(nodeid=nodeid, reason=reason, author=getpass.getuser(),
                      date=datetime.now(timezone.utc).isoformat())
        data['disabled'][nodeid] = record
        data['events'] = (data['events'] + [dict(action='disable', **record)])[-1000:]
        self._write(workspace, data)

    def enable(self, workspace: str, nodeid: str) -> None:
        nodeid = nodeid.strip().replace('\\', '/')
        data = self._read(workspace)
        record = data['disabled'].pop(nodeid, None)
        parent = matching_record(data['disabled'], nodeid)
        if record is None and parent is None:
            return
        date = datetime.now(timezone.utc).isoformat()
        author = getpass.getuser()
        reason = (record or parent)['reason']
        if parent:
            data['disabled'][nodeid] = dict(nodeid=nodeid, reason=reason,
                                            author=author, date=date, enabled=True)
        data['events'] = (data['events'] + [dict(
            action='enable', nodeid=nodeid, reason=reason, author=author, date=date)])[-1000:]
        self._write(workspace, data)

    def set_many(self, workspace: str, targets: list[str], *, enabled: bool, reasons=None):
        """Apply a list operation atomically, with parents handled before their children."""
        data = self._read(workspace)
        targets = sorted(set(targets), key=len)
        date = datetime.now(timezone.utc).isoformat()
        author = getpass.getuser()
        reasons = reasons or {}
        for target in targets:
            previous = data['disabled'].pop(target, None)
            parent = matching_record(data['disabled'], target)
            reason = reasons.get(target, (previous or parent or {}).get('reason', ''))
            if not enabled or parent:
                data['disabled'][target] = dict(nodeid=target, reason=reason, author=author,
                                                date=date, enabled=enabled)
            data['events'].append(dict(action='enable' if enabled else 'disable', nodeid=target,
                                       reason=reason, author=author, date=date))
        data['events'] = data['events'][-1000:]
        self._write(workspace, data)
