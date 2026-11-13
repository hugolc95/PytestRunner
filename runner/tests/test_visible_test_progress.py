"""Verifier le bleu pendant la preparation, setup, call et teardown reels."""
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.domain.models import Status
from runner.domain.workspace import Workspace
from runner.ui import tokens as t
from runner.ui.main_window import MainWindow
from runner.ui.profile_group_delegate import ACTIVE_ROLE


@pytest.mark.parametrize('configuration', ['ini', 'toml', 'none'])
@pytest.mark.parametrize('distributed', [False, True], ids=['serial', 'xdist'])
def test_partial_profile_stays_blue_through_all_phases_without_erasing_old_results(
        qtbot, tmp_path, monkeypatch, configuration, distributed):
    if distributed:
        pytest.importorskip('xdist')
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    suite = tmp_path / 'TSu' / 'Suite'
    (suite / 'tests').mkdir(parents=True)
    options = '-n 2 --color=yes' if distributed else '--color=yes'
    if configuration == 'ini':
        (suite / 'pytest.ini').write_text('[pytest]\naddopts = ' + options + '\n')
    elif configuration == 'toml':
        (suite / 'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = "' + options + '"\n')
    else:
        monkeypatch.setenv('PYTEST_ADDOPTS', options)
    gate = f'''import time
from pathlib import Path
ROOT = Path({str(tmp_path)!r})
def wait_phase(phase):
    (ROOT / (phase + '-entered')).touch()
    deadline = time.monotonic() + 25
    while not (ROOT / (phase + '-release')).exists():
        if time.monotonic() > deadline:
            raise RuntimeError('test driver did not release ' + phase)
        time.sleep(.01)
'''
    (suite / 'conftest.py').write_text(gate + '\nwait_phase("collect")\n')
    (suite / 'tests/test_gate.py').write_text(gate + '''
import pytest
@pytest.fixture
def resource():
    wait_phase('setup')
    yield
    wait_phase('teardown')
def test_card(resource):
    wait_phase('call')
''')
    node = 'TSu/Suite/tests/test_gate.py::test_card'
    w = MainWindow()
    qtbot.addWidget(w)
    w.profiles_page.store = ProfileStore(tmp_path / 'profiles')
    w.workspace = Workspace.load(str(tmp_path))
    w._interpreter_override = sys.executable
    w._on_collected(Collection((node,)))
    group = dict(id='card', name='Card protocol', description='Protocol checks', color='#c8a344')
    w._open_collected_profile(ExecutionProfile('Card', [node, node], '', '', step_groups=[group, group]))
    w._on_profile_execution(0, 0, 0, node, Status.PASSED)
    w._on_profile_execution(1, 0, 0, node, Status.FAILED)
    w.profile_model.set_checked_nodeids(['1:0'])
    def blue():
        index = w.profile_model.index_for_nodeid('1:0')
        assert index.isValid()
        while index.isValid():
            assert index.data(ACTIVE_ROLE)
            assert index.data(Qt.ForegroundRole) == QColor(t.ACCENT)
            index = index.parent()
        assert not w.profile_model.index_for_nodeid('0:0').data(ACTIVE_ROLE)
    try:
        w.run_selected()
        qtbot.waitUntil(lambda: (tmp_path / 'collect-entered').exists(), timeout=20000)
        qtbot.waitUntil(lambda: bool(w.profile_model._preparing_by_reader))
        blue()
        assert w.profile_model.statuses_for_nodeid('1:0')[0] is Status.FAILED
        (tmp_path / 'collect-release').touch()
        for phase in ('setup', 'call', 'teardown'):
            qtbot.waitUntil(lambda: (tmp_path / (phase + '-entered')).exists(), timeout=20000)
            qtbot.waitUntil(lambda: w.profile_model.statuses_for_nodeid('1:0').get(0) is Status.RUNNING)
            blue()
            assert w._completed_executions() == 0
            assert 'Preparing:' not in w.profile_progress_label.text()
            (tmp_path / (phase + '-release')).touch()
        qtbot.waitUntil(lambda: not w.service.busy, timeout=20000)
        qtbot.waitUntil(lambda: w.run_tabs.active is None, timeout=15000)
        assert w.profile_model.statuses_for_nodeid('1:0')[0] is Status.PASSED
        assert not w.profile_model.index_for_nodeid('1:0').data(ACTIVE_ROLE)
        assert w.profile_model.checked_nodeids() == ['1:0']
        assert w.profile_model.statuses_for_nodeid('0:0')[0] is Status.PASSED
    finally:
        for phase in ('collect', 'setup', 'call', 'teardown'):
            (tmp_path / (phase + '-release')).touch()
        w.service.cancel()
        w.service.wait()
        qtbot.waitUntil(lambda: not w.service.busy, timeout=15000)
        if getattr(w, '_archive_worker', None) is not None:
            qtbot.waitUntil(lambda: w._archive_worker is None, timeout=15000)
        w.close()


def test_preparation_is_reader_scoped_and_stopping_restores_previous_verdicts(qapp):
    from runner.ui.live_profile_model import LiveProfileModel
    from runner.domain.models import Reader
    node = 'test_card.py::test_card'
    model = LiveProfileModel()
    model.prepare(ExecutionProfile('Card', [node, node], '', ''), (Reader('A', 0), Reader('B', 2)))
    model.apply_execution(0, 0, 0, node, Status.FAILED)
    model.apply_execution(1, 0, 2, node, Status.PASSED)
    model.set_preparing(0, 0)
    model.set_preparing(1, 2)
    model.clear_preparing(0)
    assert not model.index_for_nodeid('0:0').data(ACTIVE_ROLE)
    assert model.index_for_nodeid('1:0').data(ACTIVE_ROLE)
    model.finish()
    assert not model.index_for_nodeid('1:0').data(ACTIVE_ROLE)
    assert model.statuses_for_nodeid('0:0')[0] is Status.FAILED
    assert model.statuses_for_nodeid('1:0')[2] is Status.PASSED
    assert not model._preparing_rows
