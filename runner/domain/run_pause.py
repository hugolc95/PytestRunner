"""Cooperative pause at pytest protocol boundaries; no process suspension."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

ENV_PAUSE = 'PYTESTRUNNER_PAUSE_DIR'


class RunPause:
    def __init__(self):
        self.directory = TemporaryDirectory(prefix='runner_pause_')
        self.path = Path(self.directory.name)
        self._wake = Event()
        self._wake.set()
        self._waiting = False
        self.token = ''

    def request(self):
        self.token = uuid4().hex
        self._wake.clear()
        try:
            (self.path / ('request-' + self.token)).touch()
        except FileNotFoundError:
            self._wake.set()  # The worker finished during the request.

    def resume(self):
        if self.token:
            (self.path / ('request-' + self.token)).unlink(missing_ok=True)
        self.token = ''
        self._wake.set()

    def cancel(self):
        if not self.path.is_dir():
            return
        try:
            (self.path / 'cancelled').touch()
        except FileNotFoundError:
            return
        self.resume()

    def wait(self):
        self._waiting = True
        try:
            self._wake.wait()
        finally:
            self._waiting = False

    @property
    def paused(self):
        if not self.token:
            return False
        if self._waiting:
            return True
        try:
            states = [file.read_text(encoding='ascii') for file in self.path.glob('worker-*')]
        except OSError:
            return False
        states = [state for state in states if state != 'done']
        return bool(states) and all(state == self.token for state in states)

    def close(self):
        self.directory.cleanup()

    def clear_workers(self):
        for file in self.path.glob('worker-*'):
            file.unlink(missing_ok=True)


# Appended to the standalone reader plugin. Each xdist worker acknowledges
# independently; the controller is paused only after every active worker waits.
PLUGIN_SOURCE = '''
import time as _pause_time

_pause_directory = os.environ.get("PYTESTRUNNER_PAUSE_DIR", "")
_last_pause_state = None


def _pause_state(value):
    global _last_pause_state
    if value == _last_pause_state:
        return
    if _pause_directory:
        path = pathlib.Path(_pause_directory)
        if path.is_dir():
            target = path / ("worker-%s" % os.getpid())
            # A concurrent Windows reader can prevent replace/unlink. A short
            # partial read only delays acknowledgement, so overwrite in place.
            target.write_text(value, encoding="ascii")
            _last_pause_state = value


def _pause_gate():
    if not _pause_directory:
        return
    path = pathlib.Path(_pause_directory)
    while True:
        if not path.is_dir() or (path / "cancelled").exists():
            pytest.exit("Run stopped by Pytest Runner", returncode=2)
        requests = list(path.glob("request-*"))
        if not requests:
            _pause_state("active")
            return
        _pause_state(requests[0].name[len("request-"):])
        _pause_time.sleep(0.05)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    _pause_gate()
    try:
        yield
    finally:
        _pause_state("idle")
    if nextitem is not None:
        _pause_gate()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _pause_state("done")
'''
