"""Regression checks for the actual dependency-free Excel exporter."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from runner.domain.models import Status, worst
from runner.ui.comparison_export import export_comparison_xlsx

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def verdict(values):
    if not values:
        return None
    result = worst(values)
    return Status.PENDING if Status.PENDING in values and not result.is_bad else result


class ComparisonExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'comparison.xlsx'
        self.groups = [SimpleNamespace(display_name=f'Run {i}', id=str(i), timestamp=i,
                                       workspace='C:/Tests', reader_names=('DE620', 'OMNIKEY'))
                       for i in range(3)]
        self.records = [
            {'DE620': {'test_auth': [Status.PASSED], 'test_dg': [Status.SKIPPED]},
             'OMNIKEY': {'test_auth': [Status.FAILED]}},
            {'DE620': {'test_auth': [Status.PASSED], 'test_unknown': [Status.PENDING]}},
            {'DE620': {'test_auth': [Status.ERROR], 'test_dg': [Status.PASSED]}},
        ]

    def export(self):
        export_comparison_xlsx(self.path, self.groups, self.records, verdict)
        with ZipFile(self.path) as book:
            self.assertIsNone(book.testzip())
            for name in book.namelist():
                ET.fromstring(book.read(name))
            root = ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
        cells = {cell.attrib['r']: ''.join(cell.itertext()) for cell in root.findall('.//s:c', NS)}
        return root, cells

    def test_three_runs_have_real_results_and_template(self):
        root, cells = self.export()
        self.assertEqual([cells[f'{c}11'] for c in 'ABCDEFG'],
                         ['test_auth', 'FAILED', 'Not recorded', 'PASSED', 'Not recorded', 'ERROR', 'Not recorded'])
        self.assertEqual(cells['D12'], 'Not run')
        self.assertEqual(cells['D13'], 'Unknown')
        self.assertEqual(cells['B12'], 'SKIPPED')
        self.assertEqual(root.find('s:dimension', NS).attrib['ref'], 'A1:G13')
        self.assertEqual(root.find('s:autoFilter', NS).attrib['ref'], 'A10:G13')
        self.assertEqual(root.find('.//s:pane', NS).attrib['topLeftCell'], 'B11')
        tags = [element.tag.split('}')[1] for element in root]
        self.assertLess(tags.index('autoFilter'), tags.index('mergeCells'))
        self.assertEqual(cells['B7'], 'C:/Tests')
        self.assertEqual(cells['B8'], 'DE620, OMNIKEY')

    def test_empty_export_does_not_overwrite_existing_file(self):
        self.path.write_bytes(b'existing report')
        with self.assertRaisesRegex(ValueError, 'No recorded tests'):
            export_comparison_xlsx(self.path, self.groups, [{}, {}, {}], verdict)
        self.assertEqual(self.path.read_bytes(), b'existing report')

    def test_mismatched_runs_are_rejected(self):
        with self.assertRaises(ValueError):
            export_comparison_xlsx(self.path, self.groups, [{}], verdict)
        self.assertFalse(self.path.exists())

    def test_xml_controls_and_formula_like_ids_are_text(self):
        node = '=test[<xml>&\x00\x1b]'
        self.records[0]['DE620'][node] = [Status.PASSED]
        root, cells = self.export()
        self.assertIn('=test[<xml>&]', cells.values())
        self.assertFalse(root.findall('.//s:f', NS))

    def test_write_failure_preserves_existing_report_and_cleans_temporary(self):
        self.path.write_bytes(b'existing report')
        with patch('runner.ui.comparison_export.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                self.export()
        self.assertEqual(self.path.read_bytes(), b'existing report')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == '__main__':
    unittest.main()
