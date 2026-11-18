"""Fin de run : pas de parcours par test, ni de selection bloquee par le disque."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import Qt

from runner.domain.execution import Collection
from runner.domain.history import History, RunEntry
from runner.domain.log_index import RunLogIndex
from runner.domain.logs import find_test_log
from runner.domain.report_capture import persist_analysis, read_analysis
from runner.domain.workspace import Workspace


def log(root, reader, name, *, build=42, incremental=False):
    folder = root / '20261118'
    if not incremental:
        folder /= f'Run_{build:04d}'
    folder /= reader
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + (f'_B{build:04d}_001' if incremental else '') + '.log')
    path.write_text(f'{reader}: {name}', encoding='utf-8')
    return path


def entry(root, *, run_id='run-one', reader='Reader A', nodes=('test_x.py::test_f[SHA512]',)):
    return RunEntry(run_id, 1, str(root), reader=reader, build_number=42,
        log_root=str(root), nodeids=nodes, analysis_data=dict(schema=1, save_logs=True,
            occurrences=[dict(nodeid=node, attempts=[dict(attempt=0, status='PASSED')])
                         for node in nodes]))


@pytest.mark.parametrize('incremental', [False, True])
def test_index_keeps_reader_build_and_parameter_identity(tmp_path, incremental):
    root = tmp_path / 'logs'
    expected = log(root, 'Reader A', 'test_f[SHA512]', incremental=incremental)
    log(root, 'Reader A', 'test_f[SHA512_256]', incremental=incremental)
    log(root, 'Cosmo Reader A', 'test_f[SHA512]', incremental=incremental)
    log(root, 'Reader A', 'test_f[SHA512]', build=41, incremental=incremental)
    index = RunLogIndex(root, 42)
    node = 'test_x.py::test_f[SHA512]'
    assert index.find(node, 'Reader A') == expected
    assert index.find(node, 'Reader A') == find_test_log(root, node, 'Reader A', build_number=42)
    assert index.find(node, 'Missing reader') is None
    assert index.find('test_x.py::test_absent', 'Reader A') is None


@pytest.mark.parametrize('manifest', ['valid', 'other-reader', 'old-build', 'broken', 'invalid-value'])
def test_index_manifest_fallbacks(tmp_path, manifest):
    expected = log(tmp_path, 'Reader A', 'test_f[SHA512]')
    other = log(tmp_path, 'Reader B', 'arbitrary-name')
    old = log(tmp_path, 'Reader A', 'arbitrary-name', build=41)
    target = dict(valid=expected, **{'other-reader': other, 'old-build': old,
                                   'invalid-value': 99}).get(manifest)
    node = 'test_x.py::test_f[SHA512]'
    (tmp_path / 'last_run_index.json').write_text(
        '{broken' if manifest == 'broken' else json.dumps({'prefix/' + node: str(target) if isinstance(target, Path) else target}))
    assert RunLogIndex(tmp_path, 42).find(node, 'Reader A') == expected


def test_index_visits_each_directory_and_reads_manifest_once(tmp_path, monkeypatch):
    from runner.domain import log_index
    node = 'test_x.py::test_f[SHA512]'
    expected = log(tmp_path, 'Reader A', 'test_f[SHA512]')
    second = log(tmp_path, 'Reader A', 'test_f[SHA512]_002')
    manifest = tmp_path / 'last_run_index.json'
    manifest.write_text(json.dumps({node: str(expected)}))
    visits, reads = [], []
    real_scan, real_read = log_index.os.scandir, Path.read_text
    def scan(path):
        visits.append(Path(path))
        return real_scan(path)
    def read(path, *args, **kwargs):
        if path == manifest:
            reads.append(path)
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(log_index.os, 'scandir', scan)
    monkeypatch.setattr(Path, 'read_text', read)
    index = RunLogIndex(tmp_path, 42)
    assert index.find(node, 'Reader A') == expected
    assert index.find(node, 'Reader A', excluded={expected}) == second
    assert index.find(node, 'Reader A', excluded={expected, second}) is None
    for number in range(30):
        assert index.find(f'test_x.py::test_missing_{number}', 'Reader A') is None
    # run_directories decouvre aussi les dossiers, une seule fois par index.
    from collections import Counter
    assert max(Counter(visits).values()) <= 2
    assert reads == [manifest]


def test_archive_handles_repeated_steps_and_does_not_mutate_live_snapshot(tmp_path):
    root = tmp_path / 'logs'
    first = log(root, 'Reader A', 'test_f[SHA512]')
    second = log(root, 'Reader A', 'test_f[SHA512]_002')
    original = entry(root, nodes=('test_x.py::test_f[SHA512]',) * 3)
    destination = tmp_path / 'history'
    destination.mkdir()
    saved = persist_analysis(original, destination)
    attempts = [row['attempts'][0] for row in read_analysis(saved)['occurrences']]
    assert {attempt['log_path'] for attempt in attempts[:2]} == {str(first), str(second)}
    assert attempts[2]['log_path'] == ''
    assert all('log' not in row['attempts'][0] for row in original.analysis_data['occurrences'])


def test_archive_without_logs_does_not_scan(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Logs disabled: no filesystem scan should run')
    monkeypatch.setattr(RunLogIndex, 'find', unexpected)
    original = entry(tmp_path)
    original.analysis_data['save_logs'] = False
    saved = persist_analysis(original, tmp_path)
    assert 'disabled' in read_analysis(saved)['occurrences'][0]['attempts'][0]['log_notice']


def test_numeric_parameter_logs_are_not_consumed_by_prefix_cases(tmp_path):
    root = tmp_path / 'logs'
    nodes = tuple(f'test_x.py::test_f[{number}]' for number in range(38))
    expected = [log(root, 'Reader A', f'test_f[{number}]') for number in range(38)]
    saved = persist_analysis(entry(root, nodes=nodes), tmp_path)
    rows = read_analysis(saved)['occurrences']
    assert [row['attempts'][0]['log_path'] for row in rows] == [str(path) for path in expected]


def test_unrelated_folder_brackets_do_not_hide_sanitized_parameter_logs(tmp_path):
    root = tmp_path / 'logs'
    path = log(root, 'Reader A/suite[nightly]', 'test_f_SHA512')
    assert RunLogIndex(root, 42).find('test_x.py::test_f[SHA512]', 'Reader A') == path


def test_shared_log_is_read_once_and_stays_explicitly_shared(tmp_path, monkeypatch):
    path = log(tmp_path / 'logs', 'Reader A', 'test_f[SHA512]')
    original = entry(tmp_path, nodes=('test_x.py::test_f[SHA512]',) * 2)
    for row in original.analysis_data['occurrences']:
        row['attempts'][0]['log_path'] = str(path)
    real = Path.read_text
    reads = []
    def read(source, *args, **kwargs):
        if source == path:
            reads.append(source)
        return real(source, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    saved = persist_analysis(original, tmp_path)
    rows = read_analysis(saved)['occurrences']
    assert rows[1]['attempts'][0]['log_shared']
    assert rows[0]['attempts'][0]['log'] == rows[1]['attempts'][0]['log']
    assert reads == [path]


def test_archive_attach_preserves_new_runs_renames_and_deletions(tmp_path):
    a, b = History(tmp_path), History(tmp_path)
    original = a.add(replace(entry(tmp_path), analysis_data=None))
    b.add(RunEntry('newer', 2, str(tmp_path)))
    a.rename_run(original.id, 'Renamed while saving')
    b.set_locked(original.id, True)
    a.attach_archive([replace(original, analysis_file='saved.analysis.json')])
    stored = History(tmp_path)
    assert stored.find('newer') is not None
    assert stored.find(original.id).locked
    assert stored.find(original.id).run_name == 'Renamed while saving'
    assert stored.find(original.id).analysis_file == 'saved.analysis.json'
    b.remove_run(original.id)
    orphan = tmp_path / 'deleted.analysis.json'
    orphan.write_text('late capture')
    a.attach_archive([replace(original, analysis_file=str(orphan))])
    assert History(tmp_path).find(original.id) is None
    assert not orphan.exists()


def test_out_of_order_archiving_keeps_history_chronological(tmp_path):
    history = History(tmp_path)
    history.add(RunEntry('newer', 2, str(tmp_path)))
    history.add(RunEntry('older', 1, str(tmp_path)))
    assert [e.id for e in History(tmp_path).entries()] == ['newer', 'older']


def test_slow_archive_unlocks_selection_and_does_not_delay_the_next_run(qtbot, tmp_path, monkeypatch):
    from runner.ui import end_run_feedback
    from runner.ui.main_window import MainWindow
    from runner.services.finalize_service import RunArchiveWorker
    for name in ('_on_run_started', '_on_outcome', '_on_progress', '_on_run_finished'):
        monkeypatch.setattr(MainWindow, name, getattr(MainWindow, name))
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    monkeypatch.setattr(MainWindow, '_notifier_fin_de_run', lambda *args: None)
    end_run_feedback.install()
    source = tmp_path / 'workspace'
    source.mkdir()
    (source / 'pytest.ini').write_text('[pytest]\n')
    (source / 'test_x.py').write_text('def test_a(): pass\ndef test_b(): pass\n')
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(source))
    nodes = ('test_x.py::test_a', 'test_x.py::test_b')
    window._on_collected(Collection(nodes))
    window._interpreter_override = sys.executable
    window.model.set_checked_nodeids([nodes[0]])
    ready, release = Event(), Event()
    real = RunArchiveWorker._persist
    def slow(worker):
        ready.set()
        if not release.wait(20):
            raise RuntimeError('Test did not release archive worker')
        real(worker)
    monkeypatch.setattr(RunArchiveWorker, '_persist', slow)
    try:
        window.run_selected()
        qtbot.waitUntil(lambda: ready.is_set() and not window.service.busy, timeout=15000)
        assert window._archive_worker is not None
        assert not window.run_tabs.is_locked(window)
        assert not window.model.selection_locked
        index = window.model.index_for_nodeid(nodes[1])
        assert window.model.flags(index) & Qt.ItemIsUserCheckable
        assert window.model.setData(index, Qt.Checked, Qt.CheckStateRole)
        assert window.model.setData(window.model.index_for_nodeid(nodes[0]), Qt.Unchecked, Qt.CheckStateRole)
        assert window.model.checked_nodeids() == [nodes[1]]
        # Le meme onglet peut repartir alors que son precedent run s'archive.
        window.run_selected()
        qtbot.waitUntil(lambda: len(getattr(window, '_archive_workers', ())) == 2, timeout=15000)
        assert not window.service.busy
        assert not window.run_tabs.busy
        release.set()
        qtbot.waitUntil(lambda: not window._archive_workers, timeout=15000)
        saved = History(window.history.racine).entries()
        assert {e.nodeids for e in saved} == {(nodes[0],), (nodes[1],)}
        assert len({e.build_number for e in saved}) == 2
        assert all(e.analysis_file and read_analysis(e)['occurrences'] for e in saved)
        assert window.model.checked_nodeids() == [nodes[1]]
    finally:
        release.set()
        for worker in tuple(getattr(window, '_archive_workers', ())):
            worker.wait(15000)
        window.close()
