"""Dependency-free XLSX export for the multi-run comparison report."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import os
import re
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET


def _xml(value):
    # Parametrized IDs can contain control characters forbidden by XML 1.0.
    return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', str(value)), quote=False)


def _col(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def export_comparison_xlsx(path, groups, records, status_for_values):
    """Write a polished comparison workbook without requiring openpyxl."""
    path = Path(path)
    if len(groups) < 2 or len(groups) != len(records):
        raise ValueError('Select at least two runs with matching comparison data.')
    tests = list(dict.fromkeys(
        nodeid for record in records for tests in record.values() for nodeid in tests
    ))
    if not tests:
        raise ValueError('No recorded tests are available in the selected runs. No Excel file was written.')
    rows = []
    for nodeid in tests:
        row = [nodeid]
        for record in records:
            values = [status for tests_by_reader in record.values()
                      for status in tests_by_reader.get(nodeid, ())]
            status = status_for_values(values)
            result = 'Not run' if status is None else ('Unknown' if status.name == 'PENDING' else status.label)
            row.extend((result, 'Not recorded'))
        rows.append(row)

    headers = ['Test']
    for group in groups:
        headers.extend(('Status', 'Duration'))

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="18"/><name val="Aptos Display"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts>
<fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF172033"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF334155"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF3CD"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellXfs count="8"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="4" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="5" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="6" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="7" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>
</styleSheet>'''

    # Run headers use a restrained, repeating palette. All body cells wrap.
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', ns)
    style_root = ET.fromstring(styles)
    fills = style_root.find(f'{{{ns}}}fills')
    xfs = style_root.find(f'{{{ns}}}cellXfs')
    for index in (3, 4, 5, 6):
        xfs[index].set('applyAlignment', '1')
        ET.SubElement(xfs[index], f'{{{ns}}}alignment', horizontal='center', vertical='center', wrapText='1')
    for color in ('FF2563EB', 'FF0F766E', 'FF7C3AED', 'FFB45309'):
        fill = ET.SubElement(fills, f'{{{ns}}}fill')
        pattern = ET.SubElement(fill, f'{{{ns}}}patternFill', patternType='solid')
        ET.SubElement(pattern, f'{{{ns}}}fgColor', rgb=color)
        xf = ET.SubElement(xfs, f'{{{ns}}}xf', numFmtId='0', fontId='2', fillId=str(len(fills)-1), borderId='0', xfId='0', applyAlignment='1')
        ET.SubElement(xf, f'{{{ns}}}alignment', horizontal='center', vertical='center', wrapText='1')
    fills.set('count', str(len(fills)))
    xfs.set('count', str(len(xfs)))
    base_styles = ET.Element(f'{{{ns}}}cellStyleXfs', count='1')
    ET.SubElement(base_styles, f'{{{ns}}}xf', numFmtId='0', fontId='0', fillId='0', borderId='0')
    style_root.insert(list(style_root).index(xfs), base_styles)
    named_styles = ET.SubElement(style_root, f'{{{ns}}}cellStyles', count='1')
    ET.SubElement(named_styles, f'{{{ns}}}cellStyle', name='Normal', xfId='0', builtinId='0')
    styles = ET.tostring(style_root, encoding='utf-8', xml_declaration=True)

    def cell(ref, value, style=0):
        return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{_xml(value)}</t></is></c>'

    last_col = _col(len(headers))
    sheet_rows = [f'<row r="1" ht="30">{cell("A1", "Pytest Runner · Comparison Report", 1)}</row>']
    meta = f'{len(groups)} runs · {len(tests)} tests · Exported {datetime.now():%Y-%m-%d %H:%M}'
    sheet_rows.append(f'<row r="2">{cell("A2", meta, 7)}</row>')
    merges = [f'A1:{last_col}1', f'A2:{last_col}2', f'A3:{last_col}3']
    sheet_rows.append(f'<row r="3" ht="28" customHeight="1">{cell("A3", "All selected runs and readers. Global status = worst recorded result. Test durations: Not recorded.", 7)}</row>')
    metadata = {4: [cell('A4', 'RUN INFORMATION', 2)], 5: [cell('A5', 'Run ID', 6)],
                6: [cell('A6', 'Date', 6)], 7: [cell('A7', 'Workspace', 6)],
                8: [cell('A8', 'Readers', 6)]}
    for i, group in enumerate(groups):
        left, right = _col(2 + 2*i), _col(3 + 2*i)
        details = [group.display_name, group.id,
                   datetime.fromtimestamp(group.timestamp).strftime('%Y-%m-%d %H:%M'),
                   group.workspace, ', '.join(group.reader_names) or 'No reader']
        for r, value in enumerate(details, 4):
            metadata[r].append(cell(f'{left}{r}', value, 8+i%4 if r == 4 else 7))
            merges.append(f'{left}{r}:{right}{r}')
    for r, cells in metadata.items():
        sheet_rows.append(f'<row r="{r}" ht="{42 if r in (4, 7, 8) else 28}" customHeight="1">{"".join(cells)}</row>')
    header_row = 10
    header_cells = ''.join(cell(f'{_col(i)}{header_row}', value, 2 if i == 1 else 8+((i-2)//2)%4) for i, value in enumerate(headers, 1))
    sheet_rows.append(f'<row r="{header_row}" ht="28" customHeight="1">{header_cells}</row>')
    for r, values in enumerate(rows, header_row + 1):
        cells = []
        for c, value in enumerate(values, 1):
            style = 7
            if c > 1 and c % 2 == 0:
                low = str(value).casefold()
                style = 3 if low == 'passed' else 4 if low in ('failed', 'error') else 5 if low == 'skipped' else 6
            elif c > 1:
                style = 6
            cells.append(cell(f'{_col(c)}{r}', value, style))
        height = min(150, max(32, 16 * (1 + len(str(values[0])) // 65)))
        sheet_rows.append(f'<row r="{r}" ht="{height}" customHeight="1">{"".join(cells)}</row>')

    widths = ['<col min="1" max="1" width="72" customWidth="1"/>']
    for c in range(2, len(headers) + 1):
        widths.append(f'<col min="{c}" max="{c}" width="22" customWidth="1"/>')
    last_row = header_row + len(rows)
    merged_cells = ''.join(f'<mergeCell ref="{ref}"/>' for ref in merges)
    # dimension is required by some preview/streaming readers. OOXML requires
    # autoFilter before mergeCells (Excel may repair an out-of-order sheet).
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{last_col}{last_row}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="10" xSplit="1" topLeftCell="B11" activePane="bottomRight" state="frozen"/><selection pane="bottomRight" activeCell="B11" sqref="B11"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>{''.join(widths)}</cols><sheetData>{''.join(sheet_rows)}</sheetData><autoFilter ref="A10:{last_col}{last_row}"/><mergeCells count="{len(merges)}">{merged_cells}</mergeCells><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/><pageSetup orientation="landscape" paperSize="9"/></worksheet>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Comparison" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    # Do not replace an existing report with a partial archive on write failure.
    with NamedTemporaryFile(dir=path.parent, suffix='.xlsx', delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, 'w', ZIP_DEFLATED) as book:
            book.writestr('[Content_Types].xml', content_types)
            book.writestr('_rels/.rels', rels)
            book.writestr('xl/workbook.xml', workbook)
            book.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
            book.writestr('xl/worksheets/sheet1.xml', sheet)
            book.writestr('xl/styles.xml', styles)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
