"""Last known verdicts for the tree, independent of archived run reports."""
import json
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from runner.domain.disabled_tests import workspace_key
from runner.domain.models import Status


class TreeResultsStore:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, workspace):
        return self.root / (sha256(workspace_key(workspace).encode()).hexdigest() + '.json')

    def read(self, workspace):
        try:
            data = json.loads(self.path(workspace).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        if (not isinstance(data, dict) or data.get('version') != 1
                or data.get('workspace') != workspace_key(workspace)
                or not isinstance(data.get('results'), dict)):
            raise ValueError('Invalid saved tree results')
        for nodeid, readers in data['results'].items():
            if not isinstance(nodeid, str) or not isinstance(readers, dict):
                raise ValueError('Invalid saved tree result')
            for reader, entry in readers.items():
                if (not isinstance(reader, str) or not isinstance(entry, dict)
                        or entry.get('status') not in Status.__members__
                        or not Status[entry['status']].is_final
                        or not isinstance(entry.get('meta'), dict)):
                    raise ValueError('Invalid saved tree verdict')
        return data['results']

    def write(self, workspace, results):
        path = self.path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(dict(version=1, workspace=workspace_key(workspace),
                                                 results=results), ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def merge(self, workspace, results):
        saved = self.read(workspace)
        for nodeid, readers in results.items():
            saved.setdefault(nodeid, {}).update(readers)
        self.write(workspace, saved)
