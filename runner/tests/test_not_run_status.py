"""Un test demande mais non execute est un resultat distinct et comparable."""
from zipfile import ZipFile
import sys

from PySide6.QtCore import Qt

from runner.domain.campaign_coverage import coverage
from runner.domain.history import History, RunEntry
from runner.domain.models import Reader, ReaderReport, RunRequest, Status, worst
from runner.domain.tree import build_tree
from runner.ui.comparison_page import ComparisonPage, records_by_reader, verdict
from runner.ui.comparison_export import export_comparison_xlsx
from runner.ui.history_dashboard import group_entries
from runner.ui.history_execution_tree import HistoryExecutionModel
from runner.ui.tree_model import TestTreeModel


NODE = 'test_card.py::test_after'


def test_missing_requested_result_is_final_but_not_an_execution():
    assert Status.NOT_RUN.is_final and not Status.NOT_RUN.is_executed
    assert not Status.NOT_RUN.is_bad
    assert worst([Status.PASSED, Status.NOT_RUN]) is Status.NOT_RUN
    assert not ReaderReport(Reader('A', 0), counts={Status.NOT_RUN: 1}).ok
    summary = coverage(dict(selected=[0], planned=1, unavailable=[]), {(0, 0, 0): Status.NOT_RUN}, 0)
    assert summary['executed'] == 0 and summary['not_completed'] == 1 and not summary['complete']


def test_not_run_diverges_counts_filters_and_is_replaced_by_a_real_result(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree([NODE, 'test_card.py::test_unselected']))
    model.set_readers((Reader('A', 0), Reader('B', 1)))
    checked = model.checked_nodeids()
    model.apply_outcome(NODE, Status.NOT_RUN, 0)
    model.apply_outcome(NODE, Status.PASSED, 1)
    row = model.index_for_nodeid(NODE).internalPointer()
    assert model.is_divergent(row) and model.divergent_nodeids() == [NODE]
    assert model.status_counts() == {Status.NOT_RUN: 1, Status.PASSED: 1}
    assert model.statuses_for_nodeid('test_card.py::test_unselected')[0] is Status.PENDING
    assert model.done() == 1 and model.failed_nodeids(include_not_run=True) == [NODE]
    assert row.parent.agg[0] is Status.NOT_RUN
    assert model.checked_nodeids() == checked
    model.apply_outcome(NODE, Status.PASSED, 0)
    assert not model.is_divergent(row) and model.status_counts() == {Status.PASSED: 2}


def test_status_survives_history_comparison_and_excel(qtbot, tmp_path):
    history = History(tmp_path / 'history')
    for run, status in (('old', 'PASSED'), ('new', 'NOT_RUN')):
        history.add(RunEntry(run, 1 if run == 'old' else 2, str(tmp_path),
            reader='A', nodeids=(NODE,), counts={status: 1}, test_statuses={NODE: status}, executions=((NODE, status),)))
    entries = History(history.racine).entries()
    newest = next(entry for entry in entries if entry.id == 'new')
    assert newest.count(Status.NOT_RUN) == 1 and not newest.ok and '1 not run' in newest.summary
    model = HistoryExecutionModel()
    model.set_entry(newest)
    leaf = model.ordered_leaves()[0]
    assert model.status_for(leaf, 0) is Status.NOT_RUN
    groups = group_entries(entries)
    page = ComparisonPage(history)
    qtbot.addWidget(page)
    page.set_groups(groups)
    assert len(page._records) == 2
    index = page._find_index(Qt.UserRole + 31, NODE)
    assert index.isValid()
    assert 'NOT RUN' in [index.siblingAtColumn(i).data() for i in (1, 2)]
    records = [records_by_reader(group) for group in groups]
    path = tmp_path / 'comparison.xlsx'
    export_comparison_xlsx(path, groups, records, verdict)
    with ZipFile(path) as archive:
        sheet = archive.read('xl/worksheets/sheet1.xml').decode()
    assert 'Not run' in sheet and 'Missing from a run' in sheet


def test_cancel_also_reports_a_requested_reader_that_never_started(qtbot, tmp_path):
    from runner.services.run_service import RunService
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_card.py').write_text('import time\ndef test_after(): time.sleep(30)\n')
    service = RunService()
    reports, starts = [], []
    service.finished.connect(reports.extend)
    service.line.connect(lambda reader, text: starts.append(text) if text.startswith('PYTESTRUNNER_START\t') else None)
    request = RunRequest(str(tmp_path), sys.executable, (NODE,), (Reader('A', 0), Reader('B', 1)), sequential=True)
    try:
        assert service.start(request, {})
        qtbot.waitUntil(lambda: bool(starts), timeout=15000)
        service.cancel()
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        assert len(reports) == 2
        assert all(report.cancelled and report.counts == {Status.NOT_RUN: 1} for report in reports)
        assert 'before this reader started' in reports[1].not_run[NODE]
    finally:
        service.cancel()
        service.wait()


def test_profile_stop_marks_every_remaining_occurrence_including_repetitions(qtbot, tmp_path):
    from runner.services.run_service import RunService
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'test_card.py').write_text('def test_failure(): assert False\ndef test_after(): assert False, "must not run"\n')
    failure = 'test_card.py::test_failure'
    service = RunService()
    reports, executions = [], []
    service.finished.connect(reports.extend)
    service.profile_execution.connect(lambda p, a, r, n, s: executions.append((p, s)) if s.is_final else None)
    request = RunRequest(str(tmp_path), sys.executable, (failure, NODE), ())
    try:
        assert service.start_profile(request, {}, [failure, NODE, NODE], repetitions=2, stop_after_failure=True)
        qtbot.waitUntil(lambda: bool(reports), timeout=15000)
        assert reports[0].counts == {Status.FAILED: 1, Status.NOT_RUN: 5}
        assert executions == [(0, Status.FAILED)] + [(p, Status.NOT_RUN) for p in range(1, 6)]
    finally:
        service.cancel()
        service.wait()


def test_runner_preparation_error_also_finishes_with_not_run(qtbot, tmp_path, monkeypatch):
    from runner.domain.execution import ReaderRun
    from runner.services.run_service import RunService
    def preparation_failed(*args, **kwargs):
        raise OSError('configuration could not be written')
    monkeypatch.setattr(ReaderRun, 'run', preparation_failed)
    service = RunService()
    reports, outcomes = [], []
    service.finished.connect(reports.extend)
    service.outcome.connect(outcomes.append)
    try:
        assert service.start(RunRequest(str(tmp_path), sys.executable, (NODE,), ()), {})
        qtbot.waitUntil(lambda: bool(reports), timeout=5000)
        assert reports[0].counts == {Status.NOT_RUN: 1}
        assert outcomes[0].status is Status.NOT_RUN
        assert 'configuration could not be written' in reports[0].not_run[NODE]
    finally:
        service.wait()


def test_not_run_is_neither_a_fix_nor_a_success_for_flakiness(tmp_path):
    from runner.domain.history import compare
    history = History(tmp_path)
    failed = RunEntry('old', 1, str(tmp_path), nodeids=(NODE,), counts={'FAILED': 1},
                      failed_nodeids=(NODE,), test_statuses={NODE: 'FAILED'})
    missing = RunEntry('new', 2, str(tmp_path), nodeids=(NODE,), counts={'NOT_RUN': 1},
                       test_statuses={NODE: 'NOT_RUN'})
    history.add(failed)
    history.add(missing)
    assert not compare(failed, missing).newly_fixed
    assert not history.flaky()
    assert history.recent_runs(NODE) == [False]


def test_not_run_never_archives_an_old_log_or_duration(tmp_path):
    from runner.domain.report_capture import persist_analysis, read_analysis
    old_log = tmp_path / 'old.log'
    old_log.write_text('stale log')
    entry = RunEntry('missing', 1, str(tmp_path), analysis_data=dict(schema=1, occurrences=[dict(
        nodeid=NODE, not_run=True, attempts=[dict(status='NOT_RUN', duration=2, log_path=str(old_log))])]))
    saved = persist_analysis(entry, tmp_path)
    attempt = read_analysis(saved)['occurrences'][0]['attempts'][0]
    assert not attempt['log'] and not attempt['log_path'] and attempt['duration'] is None
