"""Le classeur compare des verdicts connus, jamais des valeurs inventees."""
from dataclasses import replace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from runner.domain.history import RunEntry
from runner.domain.models import Reader, Status
from runner.domain.tree_results_export import (
    TreeExportRow, TreeResult, TreeSnapshot, difference, export_tree_results_xlsx,
)

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def sheet(path, index):
    with ZipFile(path) as book:
        root = ET.fromstring(book.read(f'xl/worksheets/sheet{index}.xml'))
    rows = []
    for row in root.findall('s:sheetData/s:row', NS):
        cells = []
        for cell in row:
            value = cell.find('s:v', NS)
            text = cell.find('s:is/s:t', NS)
            cells.append(value.text if value is not None else text.text or '' if text is not None else '')
        rows.append(cells)
    return root, rows


@pytest.fixture
def snapshot():
    def test(name, *results):
        return TreeExportRow(name, 'test', 2, f'suite / test_card.py / {name}',
                             f'suite/test_card.py::{name}', tuple(results))
    old = TreeResult(Status.PASSED, 'old', '2026-01-01T10:00:00+01:00', 'base.yml', True, 0)
    fresh = TreeResult(Status.PASSED, 'new', '2026-01-02T10:00:00+01:00', 'base.yml', False, 1.25)
    return TreeSnapshot('/workspace/tests', (Reader('A', 0), Reader('B', 1)), (
        TreeExportRow('suite', 'folder', 0, 'suite'),
        TreeExportRow('test_card.py', 'module', 1, 'suite / test_card.py'),
        test('test_equal', old, fresh),
        test('test_different', old, replace(fresh, status=Status.FAILED)),
        test('test_partial', fresh, TreeResult()),
        test('test_not_run', old, replace(fresh, status=Status.NOT_RUN, duration=None, reason='Reader crashed')),
        test('test_no_results', TreeResult(), TreeResult()),
    ), '2026-01-02T11:00:00+01:00')


@pytest.mark.parametrize('statuses,expected', [
    ([None, None], 'No results'),
    ([Status.PASSED], 'Single reader'),
    ([Status.PASSED, Status.PASSED], 'Identical'),
    ([Status.ERROR, Status.FAILED], 'Different statuses'),
    ([Status.NOT_RUN, None], 'Missing result'),
    ([Status.PASSED, Status.NOT_RUN, None], 'Different statuses + missing result'),
])
def test_difference_distinguishes_missing_from_not_run(statuses, expected):
    assert difference(tuple(TreeResult(status) for status in statuses)) == expected


def test_workbook_has_complete_tree_differences_and_measured_traceability(snapshot, tmp_path):
    path = tmp_path / 'tree.xlsx'
    assert export_tree_results_xlsx(path, snapshot) == (5, 3)
    with ZipFile(path) as book:
        for name in book.namelist():
            if name.endswith(('.xml', '.rels')):
                ET.fromstring(book.read(name))
        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        assert [node.attrib['name'] for node in workbook.find('s:sheets', NS)] == ['All results', 'Differences', 'Traceability']
    root, rows = sheet(path, 1)
    assert root.find('s:dimension', NS).attrib['ref'] == 'A1:F13'
    assert root.find('s:sheetViews/s:sheetView/s:pane', NS).attrib['topLeftCell'] == 'D7'
    assert rows[5] == ['Test tree', 'Reader differences', 'Result context', 'A', 'B', 'Test identifier']
    assert [row[0] for row in rows[6:8]] == ['suite', 'test_card.py']
    assert rows[8][1] == 'Identical' and 'Different runs' in rows[8][2]
    assert rows[11][4] == 'NOT RUN'
    assert rows[12][3:5] == ['No result', 'No result']
    _, changes = sheet(path, 2)
    changed_tests = [row for row in changes[6:] if row[-1]]
    assert len(changed_tests) == 3
    assert all('test_equal' not in row[-1] and 'test_no_results' not in row[-1] for row in changed_tests)
    assert [row[0] for row in changes[6:8]] == ['suite', 'test_card.py']
    _, trace = sheet(path, 3)
    assert len(trace[6:]) == 10
    assert trace[6][4] == '0'  # Un vrai zero ne disparait pas.
    assert trace[6][7] == 'Previous run'
    assert trace[7][4] == '1.25' and trace[7][7] == 'Latest run'
    assert trace[13][3] == 'NOT RUN' and trace[13][4] == 'Not applicable'
    assert trace[13][-1] == 'Reader crashed'
    assert trace[14][4] == 'Not recorded'


def test_archived_yaml_context_is_scoped_to_workspace_and_does_not_require_archives(snapshot, tmp_path):
    a, b = tmp_path / 'a.yml', tmp_path / 'b.yml'
    a.write_text('PROTOCOL: T0\n')
    b.write_text('PROTOCOL: T1\n')
    entries = [RunEntry('old', 1, snapshot.workspace, reader='A', configuration_file=str(a)),
               RunEntry('new', 2, snapshot.workspace, reader='B', configuration_file=str(b)),
               RunEntry('old', 1, '/other', reader='A', configuration_file=str(b))]
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, snapshot, entries)
    _, rows = sheet(path, 1)
    assert 'Different base YAML' in rows[8][2]
    _, trace = sheet(path, 3)
    assert len(trace[6][9]) == 64 and trace[6][9] != trace[7][9]
    a.unlink()
    export_tree_results_xlsx(path, snapshot, entries)
    _, rows = sheet(path, 1)
    assert rows[8][3] == 'PASSED' and 'Base YAML not recorded' in rows[8][2]


def test_strings_are_literal_xml_safe_and_single_reader_has_no_differences(snapshot, tmp_path):
    dangerous = '=HYPERLINK("https://example.com")<&\x00'
    row = replace(snapshot.rows[2], name=dangerous, nodeid=dangerous, results=(TreeResult(Status.ERROR),))
    snapshot = replace(snapshot, readers=(Reader('No <reader>', 0),), rows=(row,))
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, snapshot)
    _, rows = sheet(path, 1)
    assert rows[6][0] == dangerous.replace('\x00', '')
    assert rows[6][1] == 'Single reader'
    _, changes = sheet(path, 2)
    assert len(changes) == 6
    with ZipFile(path) as book:
        root = ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
        assert not root.findall('.//s:f', NS)


def test_write_failure_keeps_existing_workbook(snapshot, tmp_path, monkeypatch):
    path = tmp_path / 'tree.xlsx'
    path.write_bytes(b'previous workbook')
    def fail(*_):
        raise OSError('Destination is open in Excel')
    monkeypatch.setattr('runner.domain.tree_results_export.os.replace', fail)
    with pytest.raises(OSError, match='open in Excel'):
        export_tree_results_xlsx(path, snapshot)
    assert path.read_bytes() == b'previous workbook'
    assert list(tmp_path.iterdir()) == [path]


def test_collection_errors_are_visible_and_no_empty_export_overwrites_file(snapshot, tmp_path):
    path = tmp_path / 'tree.xlsx'
    broken = TreeExportRow('broken.py', 'module', 0, 'broken.py', note='ImportError: missing dependency')
    export_tree_results_xlsx(path, replace(snapshot, rows=(*snapshot.rows, broken)))
    _, rows = sheet(path, 1)
    assert '1 collection errors (tree incomplete)' in rows[1][0]
    assert rows[-1][1:3] == ['Collection error', broken.note]
    previous = path.read_bytes()
    with pytest.raises(ValueError, match='Collect tests'):
        export_tree_results_xlsx(path, replace(snapshot, rows=()))
    assert path.read_bytes() == previous


def test_invalid_archived_yaml_encoding_does_not_block_verdict_export(snapshot, tmp_path):
    config = tmp_path / 'broken.yml'
    config.write_bytes(b'bad: \xff\xfe')
    entry = RunEntry('old', 1, snapshot.workspace, reader='A', configuration_file=str(config))
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, snapshot, [entry])
    _, rows = sheet(path, 1)
    assert rows[8][3] == 'PASSED' and 'Base YAML not recorded' in rows[8][2]


def test_outline_controls_keep_parent_summaries_and_brand_on_all_sheets(snapshot, tmp_path):
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, snapshot)
    with ZipFile(path) as book:
        assert book.read('xl/media/in-groupe.png').startswith(b'\x89PNG')
        theme = ET.fromstring(book.read('xl/theme/theme1.xml'))
        assert theme.attrib['name'] == 'IN Groupe'
        ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
        assert theme.find('.//a:accent1/a:srgbClr', ns).attrib['val'] == '002F87'
        assert theme.find('.//a:accent2/a:srgbClr', ns).attrib['val'] == 'EA0029'
        for index in (1, 2, 3):
            root = ET.fromstring(book.read(f'xl/worksheets/sheet{index}.xml'))
            assert root.find('s:drawing', NS) is not None
            assert f'xl/worksheets/_rels/sheet{index}.xml.rels' in book.namelist()
            assert f'xl/drawings/drawing{index}.xml' in book.namelist()
            assert root.find('s:sheetViews/s:sheetView', NS).attrib['showOutlineSymbols'] == '1'
            assert root.find('s:sheetPr/s:outlinePr', NS).attrib['summaryBelow'] == '0'
    for index, expected_count, expected_results in (
            (1, '3 differences / 5 tests', '4 PASSED · 1 No result'),
            (2, '3 differences / 3 tests', '3 PASSED')):
        root, rows = sheet(path, index)
        assert rows[6][1] == expected_count
        assert rows[6][3] == expected_results
        assert root.find('s:sheetFormatPr', NS).attrib['outlineLevelRow'] == '2'
        data = root.findall('s:sheetData/s:row', NS)
        assert [row.attrib['outlineLevel'] for row in data[6:9]] == ['0', '1', '2']
        assert data[6].attrib['collapsed'] == '0'
        assert all(row.attrib.get('hidden', '0') == '0' for row in data)
    root, _ = sheet(path, 3)
    assert root.find('s:sheetFormatPr', NS).attrib['outlineLevelRow'] == '0'


def test_differences_keep_only_relevant_ancestors_and_never_mix_sibling_groups(snapshot, tmp_path):
    rows = (
        TreeExportRow('root', 'folder', 0, 'root'),
        TreeExportRow('stable', 'folder', 1, 'root/stable'),
        replace(snapshot.rows[2], depth=2),
        TreeExportRow('changed', 'folder', 1, 'root/changed'),
        replace(snapshot.rows[3], depth=2),
        TreeExportRow('empty', 'folder', 1, 'root/empty'),
        replace(snapshot.rows[-1], depth=2),
    )
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, replace(snapshot, rows=rows))
    _, changes = sheet(path, 2)
    assert [row[0] for row in changes[6:]] == ['root', 'changed', 'test_different']
    _, all_results = sheet(path, 1)
    assert all_results[6][1] == '1 difference / 3 tests'
    assert all_results[7][1] == '0 differences / 1 test'
    assert all_results[9][1] == '1 difference / 1 test'


def test_folded_parent_warns_about_descendant_collection_error(snapshot, tmp_path):
    broken = TreeExportRow('broken.py', 'module', 1, 'suite/broken.py', note='ImportError: missing dependency')
    path = tmp_path / 'tree.xlsx'
    export_tree_results_xlsx(path, replace(snapshot, rows=(*snapshot.rows, broken)))
    _, rows = sheet(path, 1)
    assert rows[6][2] == '1 collection error'
    assert rows[-1][2] == broken.note
