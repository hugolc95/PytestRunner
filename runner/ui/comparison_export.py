"""Dependency-free XLSX export for the multi-run comparison report."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def _xml(value):
    return escape(str(value), quote=False)


def _col(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def export_comparison_xlsx(path, groups, records, status_for_values):
    """Write a polished comparison workbook without requiring openpyxl."""
    path = Path(path)
    tests = list(dict.fromkeys(
        nodeid for record in records for tests in record.values() for nodeid in tests
    ))
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
        headers.extend((f'{group.display_name} · Result', f'{group.display_name} · Duration'))

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="18"/><name val="Aptos Display"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts>
<fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF172033"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF334155"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF3CD"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellXfs count="8"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="4" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="5" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="6" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="7" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>
</styleSheet>'''

    def cell(ref, value, style=0):
        return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{_xml(value)}</t></is></c>'

    last_col = _col(len(headers))
    sheet_rows = [f'<row r="1" ht="30">{cell("A1", "Pytest Runner · Comparison Report", 1)}</row>']
    meta = f'{len(groups)} runs · {len(tests)} tests · Exported {datetime.now():%Y-%m-%d %H:%M}'
    sheet_rows.append(f'<row r="2">{cell("A2", meta, 7)}</row>')
    header_cells = ''.join(cell(f'{_col(i)}4', value, 2) for i, value in enumerate(headers, 1))
    sheet_rows.append(f'<row r="4" ht="34">{header_cells}</row>')
    for r, values in enumerate(rows, 5):
        cells = []
        for c, value in enumerate(values, 1):
            style = 7
            if c > 1 and c % 2 == 0:
                low = str(value).casefold()
                style = 3 if low == 'passed' else 4 if low in ('failed', 'error') else 5 if low == 'skipped' else 6
            elif c > 1:
                style = 6
            cells.append(cell(f'{_col(c)}{r}', value, style))
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')

    widths = ['<col min="1" max="1" width="52" customWidth="1"/>']
    for c in range(2, len(headers) + 1):
        widths.append(f'<col min="{c}" max="{c}" width="22" customWidth="1"/>')
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="4" xSplit="1" topLeftCell="B5" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><cols>{''.join(widths)}</cols><sheetData>{''.join(sheet_rows)}</sheetData><mergeCells count="2"><mergeCell ref="A1:{last_col}1"/><mergeCell ref="A2:{last_col}2"/></mergeCells><autoFilter ref="A4:{last_col}{max(4, len(rows)+4)}"/></worksheet>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Comparison" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    with ZipFile(path, 'w', ZIP_DEFLATED) as book:
        book.writestr('[Content_Types].xml', content_types)
        book.writestr('_rels/.rels', rels)
        book.writestr('xl/workbook.xml', workbook)
        book.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        book.writestr('xl/worksheets/sheet1.xml', sheet)
        book.writestr('xl/styles.xml', styles)
