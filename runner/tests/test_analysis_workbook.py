"""Le suivi reste associe au test apres tri, edition et nouveaux resultats."""
from copy import copy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
import pytest

from runner.domain.analysis_workbook import export_analysis_xlsx, META
from runner.domain.models import Reader, Status
from runner.domain.tree_results_export import TreeExportRow, TreeResult, TreeSnapshot


@pytest.fixture
def snapshot(tmp_path):
    return TreeSnapshot(str(tmp_path / 'project'), (Reader('A', 0), Reader('B', 1)), (
        TreeExportRow('crypto', 'folder', 0, 'crypto'),
        TreeExportRow('test_hmac[512]', 'test', 1, 'crypto / test_hmac[512]', 'crypto/test_crypto.py::test_hmac[512]',
                      (TreeResult(Status.PASSED, 'old', duration=0, previous=True),
                       TreeResult(Status.ERROR, 'new', duration=.125))),
        TreeExportRow('test_pin', 'test', 1, 'crypto / test_pin', 'crypto/test_crypto.py::test_pin',
                      (TreeResult(Status.NOT_RUN, 'new', reason='Native crash'), TreeResult())),
    ), '2026-11-27T12:00:00Z')


def columns(ws):
    return {cell.value: cell.column for cell in ws[6]}


def edit(path, callback):
    book = load_workbook(path)
    ws = book['Analysis']
    callback(book, ws, columns(ws))
    book.save(path)
    book.close()


def changed(snapshot):
    rows = list(snapshot.rows)
    rows[1] = replace(rows[1], results=(TreeResult(Status.PASSED), TreeResult(Status.FAILED)))
    return replace(snapshot, rows=tuple(rows))


def test_export_sources_and_live_followup_are_separate(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    assert export_analysis_xlsx(path, snapshot) == (2, 2)
    book = load_workbook(path, data_only=True)
    assert book.sheetnames == ['Summary', 'Analysis', META, 'Reference', 'Groups']
    ws = book['Analysis']; cols = columns(ws)
    assert ws.cell(7, cols['Needs review']).value == 'Error'
    assert ws.cell(8, cols['Needs review']).value == 'Not run'
    assert ws.cell(7, cols['Result: A']).value == 'PASSED'
    reference = list(book['Reference'].values)[6:]
    assert [row[3] for row in reference] == ['PASSED', 'ERROR', 'NOT RUN', 'No result']
    assert reference[0][4] == 0 and reference[0][7] == 'Previous run'
    assert reference[2][10] == 'Native crash'
    assert book['Summary']['B9'].value == 2
    assert book['Groups'].row_dimensions[8].outlineLevel == 1
    assert 'NOT RUN' in book['Groups']['E7'].value
    assert 'No result' in book['Groups']['F7'].value
    assert book['Groups']['E8'].value == 'PASSED'
    assert book[META].sheet_state == 'veryHidden'
    assert not ws.protection.sheet and book['Reference'].protection.sheet
    assert all(len(book[name]._images) == 1 for name in ('Summary', 'Analysis', 'Reference', 'Groups'))
    formulas = load_workbook(path)
    assert formulas['Analysis'].cell(7, cols['Needs review']).data_type == 'f'
    assert all(span.max_row == 8 for rule in formulas['Analysis'].conditional_formatting for span in rule.sqref.ranges)


def test_preserves_notes_ticket_custom_columns_sorted_rows_and_user_sheet(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    url = 'https://jira.example.test/browse/CRYPTO-142?view=full#comment-12'
    def annotate(book, ws, cols):
        ws.cell(7, cols['Comment'], 'Reproduire avec une autre carte.\nDeuxieme essai.')
        ws.cell(7, cols['Comment']).comment = Comment('Native note', 'Tester')
        ws.cell(7, cols['Jira ticket'], url)
        ws.cell(7, cols['Follow-up'], 'Done')
        ws.cell(6, ws.max_column + 1, 'Severity')
        ws.cell(7, ws.max_column, 'Critical').fill = PatternFill('solid', fgColor='FF00FF')
        val = DataValidation(type='list', formula1='"Critical,Low"')
        ws.add_data_validation(val); val.add(ws.cell(7, ws.max_column))
        # Simule un tri complet, y compris notes, styles et commentaires.
        for c in range(1, ws.max_column + 1):
            a, b = ws.cell(7, c), ws.cell(8, c)
            av, ast, ac = a.value, copy(a._style), copy(a.comment)
            a.value, a._style, a.comment = b.value, copy(b._style), copy(b.comment)
            b.value, b._style, b.comment = av, ast, ac
        book.create_sheet('My notes')['A1'] = 'Keep this'
    edit(path, annotate)
    export_analysis_xlsx(path, changed(snapshot))
    book = load_workbook(path)
    ws = book['Analysis']; cols = columns(ws)
    assert ws.cell(8, cols['Test ID']).value == snapshot.rows[1].nodeid
    assert ws.cell(8, cols['Comment']).value.startswith('Reproduire')
    assert ws.cell(8, cols['Comment']).comment.text == 'Native note'
    assert ws.cell(8, cols['Jira ticket']).hyperlink.target == url
    assert ws.cell(8, cols['Jira ticket']).value == 'CRYPTO-142'
    assert ws.cell(8, cols['Severity']).value == 'Critical'
    assert ws.cell(8, cols['Severity']).fill.fgColor.rgb.endswith('FF00FF')
    assert ws.cell(8, cols['Follow-up']).value == 'To review'
    assert 'Previous follow-up: Done' in ws.cell(8, cols['Follow-up']).comment.text
    assert book['My notes']['A1'].value == 'Keep this'
    assert any(v.formula1 == '"Critical,Low"' for v in ws.data_validations.dataValidation)


def test_done_clears_review_and_unchanged_refresh_does_not_reopen(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    export_analysis_xlsx(path, changed(snapshot))
    edit(path, lambda book, ws, c: ws.cell(7, c['Follow-up'], 'Done'))
    export_analysis_xlsx(path, changed(snapshot))
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Follow-up']).value == 'Done'
    assert ws.cell(7, c['Needs review']).value == '—'
    assert ws.cell(7, c['Result: B']).value == 'FAILED'
    assert book['Summary']['B9'].value == 1


def test_reader_scopes_have_independent_tickets_and_reopen_only_changed_reader(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    def annotate(book, ws, c):
        ws.cell(7, c['Reader scope'], 'A'); ws.cell(7, c['Follow-up'], 'Done')
        values = [cell.value for cell in ws[7]]
        ws.append(values)
        ws.cell(9, c['Reader scope'], 'B'); ws.cell(9, c['Follow-up'], 'Done')
        ws.cell(7, c['Jira ticket'], 'TEAM-1'); ws.cell(9, c['Jira ticket'], 'TEAM-2')
    edit(path, annotate)
    export_analysis_xlsx(path, changed(snapshot))
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Follow-up']).value == 'Done'
    assert ws.cell(7, c['Needs review']).value == '—'
    assert ws.cell(9, c['Follow-up']).value == 'To review'
    assert ws.cell(9, c['Needs review']).value == 'Updated results'
    assert [ws.cell(r, c['Jira ticket']).value for r in (7, 9)] == ['TEAM-1', 'TEAM-2']


def test_reordered_columns_new_removed_restored_and_new_reader(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    def move(book, ws, c):
        a, b = c['Comment'], c['Owner']
        for r in range(6, ws.max_row + 1):
            left, right = ws.cell(r, a), ws.cell(r, b)
            left.value, right.value = right.value, left.value
        ws.cell(8, c['Owner'], 'Keep removed note')
    edit(path, move)
    new = replace(snapshot.rows[1], name='new', nodeid='test_new.py::test_new')
    fewer = replace(snapshot, rows=(snapshot.rows[0], snapshot.rows[1], new))
    export_analysis_xlsx(path, fewer)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(8, c['Collection']).value == 'Removed'
    assert ws.cell(8, c['Comment']).value == 'Keep removed note'
    assert ws.cell(9, c['Collection']).value == 'New'
    edit(path, lambda book, ws, c: ws.cell(8, c['Follow-up'], 'Done'))
    export_analysis_xlsx(path, fewer)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(8, c['Follow-up']).value == 'Done'
    export_analysis_xlsx(path, snapshot)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(8, c['Collection']).value == 'Restored'
    assert ws.cell(8, c['Follow-up']).value == 'To review'
    more_readers = replace(snapshot, readers=snapshot.readers + (Reader('C', 2),), rows=tuple(
        replace(row, results=row.results + (TreeResult(Status.PASSED),)) if row.nodeid else row for row in snapshot.rows))
    export_analysis_xlsx(path, more_readers)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Result: C']).value == 'PASSED'


@pytest.mark.parametrize('bad', ['duplicate', 'project', 'unknown', 'missing_id'])
def test_invalid_update_does_not_overwrite_original(snapshot, tmp_path, bad):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    if bad == 'duplicate':
        edit(path, lambda book, ws, c: ws.append([cell.value for cell in ws[7]]))
    elif bad == 'missing_id':
        edit(path, lambda book, ws, c: setattr(ws.cell(7, c['Test ID']), 'value', None))
    elif bad == 'unknown':
        path.write_bytes(b'old incompatible file')
    else:
        snapshot = replace(snapshot, workspace=str(tmp_path / 'other'))
    before = path.read_bytes()
    with pytest.raises(Exception):
        export_analysis_xlsx(path, snapshot)
    assert path.read_bytes() == before


def test_atomic_replace_failure_and_source_formula_injection(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    snapshot = replace(snapshot, rows=(replace(snapshot.rows[1], nodeid='=HYPERLINK("bad")'),))
    export_analysis_xlsx(path, snapshot)
    book = load_workbook(path); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Test ID']).data_type == 's'
    before = path.read_bytes()
    from runner.domain import analysis_workbook
    real_replace = analysis_workbook.os.replace
    def fail(source, dest):
        if Path(dest) == path:
            raise PermissionError('File is open')
        return real_replace(source, dest)
    with patch.object(analysis_workbook.os, 'replace', fail), pytest.raises(PermissionError):
        export_analysis_xlsx(path, snapshot)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['analysis.xlsx']


def test_dates_and_durations_do_not_reopen_but_configuration_changes_do(snapshot, tmp_path):
    from types import SimpleNamespace
    path = tmp_path / 'analysis.xlsx'
    texts = ['PROTOCOL: T0']
    calls = []
    def config():
        calls.append(True)
        return texts[0]
    entry = SimpleNamespace(id='new', reader='B', workspace=snapshot.workspace, configuration_text=config)
    export_analysis_xlsx(path, snapshot, [entry])
    edit(path, lambda book, ws, c: ws.cell(7, c['Follow-up'], 'Done'))
    rows = list(snapshot.rows)
    rows[1] = replace(rows[1], results=tuple(replace(r, at='later', duration=42) for r in rows[1].results))
    refreshed = replace(snapshot, rows=tuple(rows))
    export_analysis_xlsx(path, refreshed, [entry])
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Follow-up']).value == 'Done'
    texts[0] = 'PROTOCOL: T1'
    export_analysis_xlsx(path, refreshed, [entry])
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Follow-up']).value == 'To review'
    assert len(calls) == 3


def test_lost_reader_is_explicit_and_can_be_acknowledged(snapshot, tmp_path):
    path = tmp_path / 'analysis.xlsx'
    export_analysis_xlsx(path, snapshot)
    edit(path, lambda book, ws, c: ws.cell(7, c['Reader scope'], 'B'))
    reduced = replace(snapshot, readers=snapshot.readers[:1], rows=tuple(
        replace(row, results=row.results[:1]) if row.nodeid else row for row in snapshot.rows))
    export_analysis_xlsx(path, reduced)
    export_analysis_xlsx(path, reduced)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Needs review']).value == 'Updated results'
    edit(path, lambda book, ws, c: ws.cell(7, c['Follow-up'], 'To analyze'))
    export_analysis_xlsx(path, reduced)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Needs review']).value == 'Reader unavailable'
    edit(path, lambda book, ws, c: ws.cell(7, c['Follow-up'], 'Done'))
    export_analysis_xlsx(path, reduced)
    book = load_workbook(path, data_only=True); ws = book['Analysis']; c = columns(ws)
    assert ws.cell(7, c['Needs review']).value == '—'
