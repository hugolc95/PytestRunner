"""Instantane du tree et rapport Excel autonome, sans dependance bureautique."""
from dataclasses import dataclass
from collections import Counter
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from runner.domain.disabled_tests import workspace_key
from runner.domain.models import Reader, Status, worst
from runner.domain.report_timing import valid_duration
from runner.domain.xlsx_brand import BLUE, RED, brand_content_types, write_brand


@dataclass(frozen=True)
class TreeResult:
    status: Status | None = None
    run_id: str = ''
    at: str = ''
    configuration: str = ''
    previous: bool = False
    duration: float | None = None
    reason: str = ''


@dataclass(frozen=True)
class TreeExportRow:
    name: str
    kind: str
    depth: int
    path: str
    nodeid: str = ''
    results: tuple[TreeResult, ...] = ()
    note: str = ''


@dataclass(frozen=True)
class TreeSnapshot:
    workspace: str
    readers: tuple[Reader, ...]
    rows: tuple[TreeExportRow, ...]
    at: str


def difference(results):
    statuses = [result.status for result in results]
    known = {status for status in statuses if status is not None}
    if not known:
        return 'No results'
    if len(statuses) < 2:
        return 'Single reader'
    missing = any(status is None for status in statuses)
    if len(known) > 1:
        return 'Different statuses + missing result' if missing else 'Different statuses'
    return 'Missing result' if missing else 'Identical'


def has_difference(row):
    return difference(row.results) not in ('Identical', 'Single reader', 'No results')


def _column(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _text(value):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', str(value))
    if len(text) > 32767:
        text = text[:32740] + ' [text truncated]'
    return escape(text, quote=False)


def _cell(column, row, value, style=0):
    ref = f'{_column(column)}{row}'
    if type(value) in (int, float) and valid_duration(value):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{_text(value)}</t></is></c>'


NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
STATUS_STYLE = {Status.PASSED: 3, Status.FAILED: 4, Status.ERROR: 5,
                Status.SKIPPED: 6, Status.NOT_RUN: 7, None: 8}


def _styles():
    ET.register_namespace('', NS)
    root = ET.Element('styleSheet', xmlns=NS)
    fonts = ET.SubElement(root, 'fonts', count='4')
    for size, bold, color in ((11, False, '1B2230'), (18, True, BLUE),
                              (11, True, 'FFFFFF'), (11, True, BLUE)):
        font = ET.SubElement(fonts, 'font')
        ET.SubElement(font, 'sz', val=str(size))
        ET.SubElement(font, 'name', val='Aptos')
        ET.SubElement(font, 'color', rgb='FF' + color)
        if bold:
            ET.SubElement(font, 'b')
    fills = ET.SubElement(root, 'fills', count='14')
    for pattern, color in [('none', ''), ('gray125', ''), ('solid', '172033'),
                           ('solid', BLUE), ('solid', 'DCFCE7'), ('solid', 'FEE2E2'),
                           ('solid', 'EDE9FE'), ('solid', 'FEF3C7'), ('solid', 'E2E8F0'),
                           ('solid', 'F1F5F9'), ('solid', 'FFF2CC'), ('solid', 'EAF0FA'),
                           ('solid', RED), ('solid', 'FFFFFF')]:
        node = ET.SubElement(ET.SubElement(fills, 'fill'), 'patternFill', patternType=pattern)
        if color:
            ET.SubElement(node, 'fgColor', rgb='FF' + color)
    border = ET.SubElement(ET.SubElement(root, 'borders', count='1'), 'border')
    for name in ('left', 'right', 'top', 'bottom', 'diagonal'):
        ET.SubElement(border, name)
    formats = ET.SubElement(root, 'numFmts', count='1')
    ET.SubElement(formats, 'numFmt', numFmtId='164', formatCode='0.000')
    # L'ordre des elements est impose par OOXML (numFmts avant fonts).
    root.remove(formats)
    root.insert(0, formats)
    base = ET.SubElement(root, 'cellStyleXfs', count='1')
    ET.SubElement(base, 'xf', numFmtId='0', fontId='0', fillId='0', borderId='0')
    xfs = ET.SubElement(root, 'cellXfs')
    def style(font=0, fill=0, horizontal='left', indent=0, numeric=False):
        xf = ET.SubElement(xfs, 'xf', numFmtId='164' if numeric else '0', fontId=str(font),
                           fillId=str(fill), borderId='0', xfId='0', applyAlignment='1')
        if numeric:
            xf.set('applyNumberFormat', '1')
        attrs = dict(horizontal=horizontal, vertical='center', wrapText='1')
        if indent:
            attrs['indent'] = str(indent)
        ET.SubElement(xf, 'alignment', **attrs)
    style()                       # 0 texte
    style(1, 13, indent=8)        # 1 titre, place reservee au logo
    style(2, 3, 'center')          # 2 entetes
    for fill in (4, 5, 6, 7, 8, 9):
        style(0, fill, 'center')   # 3..8 statuts / absence
    style(3, 10)                  # 9 ecart
    style(0, 11)                  # 10 contexte
    style(numeric=True)           # 11 secondes mesurables
    for bold in (False, True):
        for indent in range(16):
            style(3 if bold else 0, 11 if bold else 0, indent=indent)
    style(fill=12)                # 44 accent rouge IN Groupe
    xfs.set('count', str(len(xfs)))
    named = ET.SubElement(root, 'cellStyles', count='1')
    ET.SubElement(named, 'cellStyle', name='Normal', xfId='0', builtinId='0')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _sheet(book, identifier, title, summary, note, headers, widths, rows, count, frozen=1, outline=0):
    last_column = _column(len(headers))
    last_row = 6 + count
    with book.open(f'xl/worksheets/sheet{identifier}.xml', 'w') as stream:
        def write(text):
            stream.write(text.encode('utf-8'))
        write(f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}" xmlns:r="{REL}">'
              f'<sheetPr><tabColor rgb="FF{BLUE}"/><outlinePr summaryBelow="0" showOutlineSymbols="1"/></sheetPr>'
              f'<dimension ref="A1:{last_column}{last_row}"/>'
              '<sheetViews><sheetView workbookViewId="0" showGridLines="0" showOutlineSymbols="1">'
              f'<pane ySplit="6" xSplit="{frozen}" topLeftCell="{_column(frozen+1)}7" activePane="bottomRight" state="frozen"/>'
              f'</sheetView></sheetViews><sheetFormatPr defaultRowHeight="22" outlineLevelRow="{min(outline,7)}"/><cols>')
        for index, width in enumerate(widths, 1):
            write(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')
        write('</cols><sheetData>')
        instruction = ('Use + / − on the left to expand or collapse parents; numbered levels change the detail shown.'
                       if outline else 'Filter by test, reader or run to inspect recorded results.')
        if outline > 7:
            instruction += ' Excel supports 7 outline levels; deeper paths remain visible in the cells.'
        for row, (value, height, style) in enumerate(((f'IN GROUPE / PYTEST RUNNER · {title}', 64, 1), (summary, 30, 0),
                                                   (note, 42, 0), ('', 3, 44), (instruction, 24, 0)), 1):
            write(f'<row r="{row}" ht="{height}" customHeight="1">{_cell(1, row, value, style)}</row>')
        write('<row r="6" ht="36" customHeight="1">' + ''.join(
            _cell(column, 6, value, 2) for column, value in enumerate(headers, 1)) + '</row>')
        for number, (values, styles, depth, group) in enumerate(rows, 7):
            lines = max((len(str(value)) // width + 1 for value, width in zip(values, widths)), default=1)
            height = max(28 if group else 42, min(126, 14 * lines))
            collapsed = ' collapsed="0"' if group else ''
            write(f'<row r="{number}" ht="{height}" customHeight="1" outlineLevel="{min(depth,7)}"{collapsed}>')
            write(''.join(_cell(column, number, value, styles[column-1])
                          for column, value in enumerate(values, 1)))
            write('</row>')
        write(f'</sheetData><autoFilter ref="A6:{last_column}{last_row}"/>'
              '<mergeCells count="5">' + ''.join(f'<mergeCell ref="A{r}:{last_column}{r}"/>' for r in (1, 2, 3, 4, 5)) +
              '</mergeCells><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
              '<pageSetup orientation="landscape" paperSize="9"/><drawing r:id="rId1"/></worksheet>')


def _difference_tree(rows):
    """Conserve uniquement les tests en ecart et leurs parents, sans arbre plat."""
    keep, parents = set(), []
    for index, row in enumerate(rows):
        while parents and rows[parents[-1]].depth >= row.depth:
            parents.pop()
        if not row.nodeid:
            parents.append(index)
        elif has_difference(row):
            keep.add(index)
            keep.update(parents)
    return tuple(row for index, row in enumerate(rows) if index in keep)


def _group_summaries(rows, reader_count):
    summaries, parents = {}, []
    for index, row in enumerate(rows):
        while parents and rows[parents[-1]].depth >= row.depth:
            parents.pop()
        if row.note:
            for parent in parents:
                summaries[parent][3] += 1
        if not row.nodeid:
            summaries[index] = [0, 0, [Counter() for _ in range(reader_count)], int(bool(row.note))]
            parents.append(index)
        else:
            for parent in parents:
                summary = summaries[parent]
                summary[0] += 1
                summary[1] += has_difference(row)
                for counts, result in zip(summary[2], row.results):
                    counts[result.status] += 1
    return summaries


def export_tree_results_xlsx(destination, snapshot, entries=()):
    """Ecrit atomiquement trois feuilles a partir d'un instantane sans Qt."""
    tests = [row for row in snapshot.rows if row.nodeid]
    if not tests or not snapshot.readers:
        raise ValueError('Collect tests before exporting tree results.')
    if any(len(row.results) != len(snapshot.readers) for row in tests):
        raise ValueError('The reader columns do not match the results.')
    if any(result.status is not None and not result.status.is_final for row in tests for result in row.results):
        raise ValueError('Wait for the run to finish before exporting tree results.')
    if len(snapshot.readers) + 4 > 16384 or max(len(snapshot.rows), len(tests)*len(snapshot.readers)) + 6 > 1048576:
        raise ValueError('This tree exceeds the Excel worksheet size limit.')
    # On ne lit que les YAML de runs effectivement references, jamais leurs
    # traces ou logs volumineux. Une archive absente laisse le verdict intact.
    archives = {(entry.id, entry.reader): entry for entry in entries
                if workspace_key(entry.workspace) == workspace_key(snapshot.workspace)}
    configurations = {}
    def configuration(result, reader):
        key = (result.run_id, reader.name)
        if key not in configurations:
            entry = archives.get(key)
            try:
                text = entry.configuration_text() if entry else None
            except (OSError, UnicodeError, ValueError, TypeError):
                text = None
            configurations[key] = sha256(text.encode('utf-8')).hexdigest() if text is not None else ''
        return configurations[key]
    def context(row):
        known = [result for result in row.results if result.status is not None]
        notes = []
        if len({result.run_id for result in known if result.run_id}) > 1:
            notes.append('Different runs')
        hashes = [configuration(result, reader) for reader, result in zip(snapshot.readers, row.results)
                  if result.status is not None]
        if len(set(hashes) - {''}) > 1:
            notes.append('Different base YAML')
        if known and any(not value for value in hashes):
            notes.append('Base YAML not recorded')
        return ' · '.join(notes)
    differences = [row for row in tests if has_difference(row)]
    difference_rows = _difference_tree(snapshot.rows)
    status_differences = sum(len({result.status for result in row.results if result.status is not None}) > 1 for row in tests)
    missing = sum(difference(row.results).endswith('missing result') or difference(row.results) == 'Missing result' for row in tests)
    summary = (f'{len(tests)} tests · {len(snapshot.readers)} readers · {status_differences} status differences · '
               f'{missing} coverage gaps · Exported {snapshot.at}')
    collection_errors = sum(bool(row.note) for row in snapshot.rows)
    if collection_errors:
        summary += f' · {collection_errors} collection errors (tree incomplete)'
    note = ('All collected tests and current tree readers; search, checkboxes and collapsed branches do not limit this export. '
            'NOT RUN = requested but not executed. No result = no recorded verdict. '
            'Results may come from different runs; see Traceability. Base YAML excludes per-test overrides.')
    headers = ['Test tree', 'Reader differences', 'Result context'] + [reader.name or 'No reader' for reader in snapshot.readers] + ['Test identifier']
    widths = [58, 30, 34] + [24] * len(snapshot.readers) + [80]
    def matrix(rows):
        summaries = _group_summaries(rows, len(snapshot.readers))
        for index, row in enumerate(rows):
            group = not row.nodeid
            values = [row.name, ('Collection error' if row.note else '') if group else difference(row.results),
                      row.note if group else context(row)]
            result_styles = []
            if group:
                total, changed, counts, errors = summaries[index]
                if total and not row.note:
                    values[1] = f'{changed} difference{"s" if changed != 1 else ""} / {total} test{"s" if total != 1 else ""}'
                if errors and not row.note:
                    values[2] = f'{errors} collection error{"s" if errors != 1 else ""}'
                for reader_counts in counts:
                    order = (Status.ERROR, Status.FAILED, Status.NOT_RUN, Status.SKIPPED, Status.PASSED, None)
                    values.append(' · '.join(f'{reader_counts[status]} {status.label if status else "No result"}'
                                             for status in order if reader_counts[status]))
                    statuses = [status for status in reader_counts if status is not None]
                    status = worst(statuses) if statuses else None
                    result_styles.append(9 if None in reader_counts and statuses and not status.is_bad else STATUS_STYLE[status])
            else:
                values += [result.status.label if result.status is not None else 'No result' for result in row.results]
                result_styles = [STATUS_STYLE[result.status] for result in row.results]
            values.append(row.nodeid)
            changed = summaries[index][1] if group else has_difference(row)
            styles = [12 + min(15, row.depth) + (16 if group else 0),
                      9 if row.note or changed else 0, 9 if group and summaries[index][3] else 10 if values[2] else 0]
            styles += result_styles
            styles.append(0)
            yield values, styles, row.depth, group
    def traceability():
        for row in tests:
            for reader, result in zip(snapshot.readers, row.results):
                status = result.status
                duration = result.duration if status is not Status.NOT_RUN and valid_duration(result.duration) else 'Not applicable' if status is Status.NOT_RUN else 'Not recorded'
                values = [row.path, row.nodeid, reader.name or 'No reader', status.label if status is not None else 'No result',
                          duration, result.run_id or 'Not recorded', result.at or 'Not recorded',
                          ('Previous run' if result.previous else 'Latest run') if status is not None else 'No result',
                          result.configuration or 'Not recorded', configuration(result, reader) if status is not None else '', result.reason]
                yield values, [0, 0, 0, STATUS_STYLE[status], 11 if valid_duration(duration) else 0, 0, 0, 0, 0, 0, 0], 0, False
    names = ['All results', 'Differences', 'Traceability']
    destination = Path(destination)
    with NamedTemporaryFile(dir=destination.parent, suffix='.xlsx', delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, 'w', ZIP_DEFLATED) as book:
            types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            types += brand_content_types(3)
            types += '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            types += ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,4)) + '</Types>'
            book.writestr('[Content_Types].xml', types)
            book.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            book.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>' + ''.join(
                f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1)) + '</sheets></workbook>')
            book.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(
                f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,4)) + f'<Relationship Id="rId4" Type="{REL}/styles" Target="styles.xml"/><Relationship Id="rId5" Type="{REL}/theme" Target="theme/theme1.xml"/></Relationships>')
            book.writestr('xl/styles.xml', _styles())
            write_brand(book, 3)
            _sheet(book, 1, 'Tree results', summary, f'{snapshot.workspace}\n{note}', headers, widths, matrix(snapshot.rows), len(snapshot.rows), 3,
                   max(row.depth for row in snapshot.rows))
            _sheet(book, 2, 'Reader differences', summary, 'Different verdicts or partial coverage only. Tests with no result on any reader are listed in All results.', headers, widths, matrix(difference_rows), len(difference_rows), 3,
                   max((row.depth for row in difference_rows), default=0))
            _sheet(book, 3, 'Result traceability', summary, 'One row per test and reader. Durations are seconds; missing measurements are never replaced by zero. Base YAML SHA-256 identifies the archived run configuration, excluding per-test overrides.',
                   ['Tree path', 'Test identifier', 'Reader', 'Status', 'Duration (s)', 'Run ID', 'Recorded at', 'Result source', 'Run YAML file', 'Base YAML SHA-256', 'Note'],
                   [62, 80, 28, 20, 18, 30, 30, 20, 28, 38, 65], traceability(), len(tests)*len(snapshot.readers), 3)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return len(tests), len(differences)
