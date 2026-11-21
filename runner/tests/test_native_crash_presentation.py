"""Les erreurs natives et les tests non executes restent analysables et archives."""
from types import SimpleNamespace
import json

from PySide6.QtCore import Qt

from runner.domain import diagnostics
from runner.domain.console import apply_lens, Lens
from runner.domain.models import Reader, ReaderReport, Status
from runner.domain.tree import build_tree
from runner.domain.history import RunEntry
from runner.domain.report import html_report
from runner.domain.report_data import report_payload
from runner.ui.results_panel import ResultsPanel
from runner.ui.tree_model import TestTreeModel
from runner.ui.report_capture import capture_report


NODES = ('test_card.py::test_before', 'test_card.py::test_crash', 'test_card.py::test_after')
REASON = 'Not executed after Windows fatal exception: access violation (0xC0000005)'


def report():
    detail = dict(kind='test', nodeid=NODES[1], phase='call', message='Windows fatal exception: access violation',
        body='Windows fatal exception: access violation (0xC0000005)\n  File "C:\\project\\test_card.py", line 12 in test_crash')
    return ReaderReport(Reader('Card reader', 0), exit_code=-1073741819,
        counts={Status.PASSED: 1, Status.ERROR: 1, Status.NOT_RUN: 1}, not_run={NODES[2]: REASON},
        output=diagnostics.PREFIX + json.dumps(detail) + '\n', issues=[detail['body']])


def test_not_executed_details_replace_previous_success_without_inventing_a_skip(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    result = report()
    panel.set_readers((result.reader,))
    panel.show_test(NODES[2], {0: Status.PASSED})
    panel.set_report(result)
    assert 'Not run' in panel.detail.body.toPlainText()
    assert '0xC0000005' in panel.detail.body.toPlainText()
    assert 'not run yet' not in panel.detail.body.toPlainText()
    panel.show_test(NODES[1], {0: Status.ERROR})
    assert 'Windows fatal exception' in panel.detail.body.toPlainText()
    assert 'line 12' in panel.detail.body.toPlainText()


def test_not_executed_marker_does_not_change_checkboxes_or_count_as_error(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree(NODES))
    model.set_readers((Reader('A', 0),))
    model.apply_outcome(NODES[2], Status.PASSED, 0)
    model.begin_run(retain=True)
    selection = model.checked_nodeids()
    model.set_not_run(0, {NODES[2]: REASON})
    index = model.index_for_nodeid(NODES[2]).siblingAtColumn(1)
    assert 'Not run' in model.data(index, Qt.ToolTipRole)
    assert model.status_counts() == {}
    assert model.checked_nodeids() == selection
    model.apply_outcome(NODES[2], Status.PASSED, 0)
    assert 'Not run' not in (model.data(index, Qt.ToolTipRole) or '')


def test_problem_lens_keeps_the_fatal_header_and_all_native_frames():
    lines = ['ordinary output', 'test_card.py::test_crash Windows fatal exception: access violation',
             'Thread 0x1234 (most recent call first):', '  File "driver.py", line 31 in send_apdu',
             '  File "test_card.py", line 12 in test_crash']
    filtered = apply_lens(lines, Lens.PROBLEMS)
    assert filtered == lines[1:]


def test_html_and_history_payload_keep_crash_and_unexecuted_reason(tmp_path):
    result = report()
    window = SimpleNamespace(_archive_run_nodeids=NODES, _running_execution_profile=None,
        _archive_statuses_by_reader={0: {NODES[0]: 'PASSED', NODES[1]: 'ERROR'}})
    analysis = capture_report(window, result)
    entry = RunEntry('crash-run', 1, str(tmp_path), reader='A', nodeids=NODES,
        counts={'PASSED': 1, 'ERROR': 1, 'NOT_RUN': 1}, exit_code=result.exit_code,
        analysis_data=analysis, campaign_coverage=analysis['coverage'])
    payload = report_payload((entry,), (result.output,))
    assert payload['rows'][1]['readers'][0]['status'] == 'error'
    assert '0xC0000005' in payload['rows'][1]['readers'][0]['attempts'][0]['trace']
    assert payload['rows'][2]['readers'][0]['status'] == 'notrun'
    assert payload['rows'][2]['readers'][0]['notice'] == REASON
    assert analysis['coverage']['executed'] == 2 and not analysis['coverage']['complete']
    assert 'Run incomplete' in entry.summary
    rendered = html_report(entry, result.output)
    assert 'Windows fatal exception' in rendered and '0xC0000005' in rendered
    assert 'Not executed after' in rendered
