"""Instantane complet et generation asynchrone dans la vraie fenetre Qt."""
from threading import Event

from PySide6.QtCore import QModelIndex, QTimer

from runner.domain.models import Reader, Status
from runner.domain.tree_results import TreeResultsStore
from runner.tests.test_tree_result_history import window, NODES
from runner.ui.tree_results_export import snapshot_tree


def test_snapshot_ignores_selection_search_and_collapsing_and_preserves_provenance(window):
    model = window.model
    model.set_readers((Reader('A', 0), Reader('B', 1)))
    model.set_retained_results({NODES[0]: {0: dict(status='PASSED', duration=0,
        meta=dict(run_id='old', at='2026-01-01T10:00:00+01:00', config='old.yml'))}})
    model._run_meta = dict(run_id='new', at='2026-01-02T10:00:00+01:00', config='new.yml')
    model.apply_outcome(NODES[0], Status.FAILED, 1)
    model.set_duration(NODES[0], 1, 2.5)
    model.apply_outcome(NODES[1], Status.NOT_RUN, 1)
    model.set_not_run(1, {NODES[1]: 'Reader process crashed'})
    model.set_checked_nodeids([NODES[2]])
    window.search.field.setText('does not exist')
    window.tree.collapseAll()
    snapshot = snapshot_tree(window)
    tests = {row.nodeid: row for row in snapshot.rows if row.nodeid}
    assert list(tests) == NODES
    first = tests[NODES[0]].results
    assert first[0].previous and first[0].run_id == 'old' and first[0].duration == 0
    assert not first[1].previous and first[1].run_id == 'new' and first[1].duration == 2.5
    assert tests[NODES[1]].results[0].status is None
    assert tests[NODES[1]].results[1].status is Status.NOT_RUN
    assert tests[NODES[1]].results[1].reason == 'Reader process crashed'
    assert model.checked_nodeids() == [NODES[2]]
    model.apply_outcome(NODES[0], Status.PASSED, 1)
    assert first[1].status is Status.FAILED  # Instantane independant du modele.


def test_retention_keeps_duration_and_not_run_reason_across_sessions(window, tmp_path):
    model = window.model
    model.apply_outcome(NODES[0], Status.PASSED, 0)
    model.set_duration(NODES[0], 0, .125)
    model.apply_outcome(NODES[1], Status.NOT_RUN, 0)
    model.set_not_run(0, {NODES[1]: 'Execution stopped'})
    window.tree_results.completed()
    stored = TreeResultsStore(window.tree_results.store.root).read(window.workspace.path)
    assert stored[NODES[0]]['']['duration'] == .125
    assert stored[NODES[1]]['']['reason'] == 'Execution stopped'
    model.begin_run(retain=True, meta={'run_id': 'next'})
    snapshot = snapshot_tree(window)
    rows = {row.nodeid: row for row in snapshot.rows if row.nodeid}
    assert rows[NODES[0]].results[0].duration == .125
    assert rows[NODES[1]].results[0].reason == 'Execution stopped'
    model.apply_outcome(NODES[0], Status.ERROR, 0)
    rows = {row.nodeid: row for row in snapshot_tree(window).rows if row.nodeid}
    assert rows[NODES[0]].results[0].duration is None  # Pas la mesure de l'ancien run.


def test_export_is_available_in_both_menus_without_a_toolbar_button(window):
    action = window.tree_results.export_action
    window.tree_tools.populate_menu()
    assert action in window.tree_tools.menu.actions()
    assert action in window._tree_context_menu(QModelIndex()).actions()
    assert action.isEnabled()
    update = window.tree_results.update_export_action
    assert update in window.tree_tools.menu.actions()
    assert update in window._tree_context_menu(QModelIndex()).actions()
    assert update.isEnabled()
    window.profile_tree_button.setChecked(True)
    assert not action.isEnabled()
    assert not update.isEnabled()


def test_update_uses_existing_workbook_and_background_worker(window, qtbot, tmp_path, monkeypatch):
    path = tmp_path / 'analysis.xlsx'
    path.write_bytes(b'annotations')
    calls = []
    def update(destination, snapshot, entries):
        calls.append((destination, destination.read_bytes()))
        return 3, 0
    monkeypatch.setattr('runner.services.tree_results_service.export_tree_results_xlsx', update)
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getOpenFileName', lambda *_: (str(path), ''))
    exporter = window.tree_results.exporter
    monkeypatch.setattr(exporter, 'offer_open', lambda *_: None)
    window.tree_results.update_export_action.trigger()
    qtbot.waitUntil(lambda: exporter.worker is None)
    assert calls == [(path, b'annotations')]


def test_background_export_keeps_ui_responsive_and_captures_before_changes(window, qtbot, tmp_path, monkeypatch):
    started, finish = Event(), Event()
    saved = []
    def export(destination, snapshot, entries):
        saved.append(snapshot)
        started.set()
        assert finish.wait(10)
        destination.write_bytes(b'completed')
        return 3, 1
    monkeypatch.setattr('runner.services.tree_results_service.export_tree_results_xlsx', export)
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getSaveFileName',
                        lambda *_: (str(tmp_path / 'report'), ''))
    exporter = window.tree_results.exporter
    completed = []
    monkeypatch.setattr(exporter, 'offer_open', lambda *args: completed.append(args))
    try:
        exporter.export(window)
        qtbot.waitUntil(started.is_set)
        assert not window.tree_results.export_action.isEnabled()
        timer = []
        QTimer.singleShot(0, lambda: timer.append(True))
        qtbot.waitUntil(lambda: bool(timer))
        window.model.set_checked_nodeids(NODES[:1])
        window.model.apply_outcome(NODES[0], Status.FAILED, 0)
        assert window.model.checked_nodeids() == NODES[:1]
        assert next(row for row in saved[0].rows if row.nodeid == NODES[0]).results[0].status is None
        # Les autres onglets partagent l'exporteur, pas son modele Qt.
        other = window.run_tabs.new_run()
        assert other.tree_results.exporter is exporter
        assert not other.tree_results.export_action.isEnabled()
    finally:
        finish.set()
        qtbot.waitUntil(lambda: exporter.worker is None)
    assert (tmp_path / 'report.xlsx').read_bytes() == b'completed'
    assert completed[0][1] == (3, 1)
    assert window.tree_results.export_action.isEnabled()
    assert window.status_label.text() == 'Tree results exported to Excel'


def test_export_failure_restores_action_and_cancel_does_nothing(window, qtbot, tmp_path, monkeypatch):
    exporter = window.tree_results.exporter
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getSaveFileName', lambda *_: ('', ''))
    exporter.export(window)
    assert exporter.worker is None
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getSaveFileName',
                        lambda *_: (str(tmp_path / 'report.xlsx'), ''))
    def fail(*_):
        raise PermissionError('File is open')
    monkeypatch.setattr('runner.services.tree_results_service.export_tree_results_xlsx', fail)
    errors = []
    monkeypatch.setattr('runner.ui.tree_results_export.QMessageBox.critical', lambda *args: errors.append(args))
    exporter.export(window)
    qtbot.waitUntil(lambda: exporter.worker is None)
    assert 'File is open' in errors[0][-1]
    assert window.tree_results.export_action.isEnabled()


def test_closing_host_waits_for_export_without_destroying_thread_or_showing_popup(window, qtbot, tmp_path, monkeypatch):
    started, finish = Event(), Event()
    def export(*_):
        started.set()
        assert finish.wait(10)
        return 3, 0
    monkeypatch.setattr('runner.services.tree_results_service.export_tree_results_xlsx', export)
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getSaveFileName',
                        lambda *_: (str(tmp_path / 'report.xlsx'), ''))
    exporter = window.tree_results.exporter
    opened = []
    monkeypatch.setattr(exporter, 'offer_open', lambda *_: opened.append(True))
    try:
        exporter.export(window)
        qtbot.waitUntil(started.is_set)
        assert not window.close()
        assert window.isVisible() and exporter.worker.isRunning()
    finally:
        finish.set()
        qtbot.waitUntil(lambda: exporter.worker is None)
    qtbot.waitUntil(lambda: not window.isVisible())
    assert not opened


def test_adding_extension_does_not_silently_overwrite_an_existing_workbook(window, tmp_path, monkeypatch):
    path = tmp_path / 'report.xlsx'
    path.write_bytes(b'existing')
    monkeypatch.setattr('runner.ui.tree_results_export.QFileDialog.getSaveFileName',
                        lambda *_: (str(path.with_suffix('')), ''))
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr('runner.ui.tree_results_export.QMessageBox.question', lambda *_: QMessageBox.No)
    window.tree_results.exporter.export(window)
    assert window.tree_results.exporter.worker is None
    assert path.read_bytes() == b'existing'
