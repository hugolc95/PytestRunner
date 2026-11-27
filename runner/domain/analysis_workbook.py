"""Classeur de travail editable : identites stables, suivi et sources separes."""
from collections import OrderedDict
from copy import copy
from hashlib import sha256
from html import escape
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import warnings
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image
from openpyxl.formatting.formatting import ConditionalFormatting
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from runner.domain.disabled_tests import workspace_key
from runner.domain.report_timing import valid_duration
from runner.domain.tree_results_export import difference, has_difference, _group_summaries
from runner.domain.xlsx_brand import BLUE, RED

META = '_PytestRunner'
HEADER = 6
FIRST = HEADER + 1
ALL = 'All readers'
FOLLOWUP = ('To analyze', 'To review', 'To retest', 'Expected', 'Done')
EDITABLE = ('Follow-up', 'Comment', 'Jira ticket', 'Owner', 'Action', 'Reader scope')
CORE = ('Group', 'Test', 'Needs review', 'Follow-up', 'Comment', 'Jira ticket',
        'Owner', 'Reader scope', 'Reader differences', 'Action', 'Collection', 'Test ID')
COLORS = {'PASSED': 'E2F2E8', 'FAILED': 'FBE4E5', 'ERROR': 'EDE6F7',
          'SKIPPED': 'FFF2D6', 'NOT RUN': 'E5EAF1', 'No result': 'F2F4F7'}
FONT = Font(name='Aptos', size=11, color='182333')
WRAP = Alignment(vertical='center', wrap_text=True)


def _text(cell, value):
    # Les noms de tests et commentaires ne sont jamais des formules executees.
    value = str(value)
    if len(value) > 32767:
        raise ValueError('A cell exceeds the Excel text limit (32767 characters).')
    cell.value = value
    cell.data_type = 's'


def _columns(ws):
    values = [c.value for c in ws[HEADER]]
    if any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
        raise ValueError('Analysis needs unique, non-empty column headers on row 6.')
    return {v: i for i, v in enumerate(values, 1)}


def _base(ws, title, headers, subtitle):
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 85
    ws.sheet_properties.tabColor = BLUE
    ws.freeze_panes = 'C7'
    for r, height in ((1, 40), (2, 25), (3, 25), (4, 3), (5, 10), (6, 30)):
        ws.row_dimensions[r].height = height
    last = max(3, len(headers))
    for r in (1, 2, 3, 4):
        ws.merge_cells(start_row=r, start_column=2 if r == 1 else 1, end_row=r, end_column=last)
    _text(ws['B1'], title)
    ws['B1'].font = Font(name='Aptos', size=18, bold=True, color=BLUE)
    _text(ws['A2'], subtitle)
    ws['A2'].font = Font(name='Aptos', size=10, color='667387')
    for cell in ws[4][:last]:
        cell.fill = PatternFill('solid', fgColor=RED)
    logo = Image(BytesIO(files('runner.report_assets').joinpath('in-groupe.png').read_bytes()))
    logo.width, logo.height = 70, 42
    ws.add_image(logo, 'A1')
    widths = {'Group': 24, 'Test': 40, 'Needs review': 22, 'Follow-up': 18,
              'Comment': 45, 'Jira ticket': 22, 'Owner': 20, 'Action': 36,
              'Reader scope': 24, 'Reader differences': 32, 'Collection': 19,
              'Test ID': 65, 'Reason / collection error': 60, 'Configuration': 45}
    for i, header in enumerate(headers, 1):
        cell = ws.cell(HEADER, i)
        _text(cell, header)
        cell.font = Font(name='Aptos', size=11, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor=BLUE)
        cell.alignment = WRAP
        ws.column_dimensions[letter(i)].width = widths.get(header, 24)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_title_rows = '1:6'
    ws.oddFooter.center.text = 'IN Groupe · Pytest Runner'
    ws.oddFooter.right.text = '&P / &N'


def _row(ws, values):
    # max_row parcourt toutes les cellules ; le recalculer a chaque ajout
    # rendait un export de 30000 tests quadratique.
    r = ws._current_row + 1
    ws.append([None] * len(values))
    for c, value in enumerate(values, 1):
        cell = ws.cell(r, c)
        if isinstance(value, str):
            _text(cell, value)
        else:
            cell.value = value
        cell.font, cell.alignment = FONT, WRAP
    return r


def _source(snapshot, entries):
    tests = [row for row in snapshot.rows if row.nodeid]
    readers = [r.name or 'No reader' for r in snapshot.readers]
    if not tests or not readers:
        raise ValueError('Collect tests before exporting results.')
    if len(set(readers)) != len(readers) or ALL in readers:
        raise ValueError('Reader names must be unique and different from "All readers".')
    if len({row.nodeid for row in tests}) != len(tests):
        raise ValueError('Duplicate test identifiers in the collected tree.')
    if len(tests) * len(readers) + HEADER > 1048576:
        raise ValueError('The reference exceeds the Excel worksheet row limit.')
    archives = {(e.id, e.reader): e for e in entries
                if workspace_key(e.workspace) == workspace_key(snapshot.workspace)}
    hashes, source = {}, {}
    for row in tests:
        if len(row.results) != len(readers):
            raise ValueError('Reader columns do not match the results.')
        signatures = {}
        for reader, original, result in zip(readers, snapshot.readers, row.results):
            if result.status is not None and not result.status.is_final:
                raise ValueError('Wait for execution to finish before exporting results.')
            key = (result.run_id, original.name)
            if key not in hashes:
                entry = archives.get(key)
                try:
                    config = entry.configuration_text() if entry else None
                except (OSError, UnicodeError, ValueError, TypeError):
                    config = None
                hashes[key] = sha256(config.encode('utf-8')).hexdigest() if config is not None else ''
            signatures[reader] = [result.status.label if result.status else 'No result',
                                  sha256(result.reason.encode('utf-8')).hexdigest(), hashes[key]]
        source[row.nodeid] = signatures
    return tests, readers, source, hashes


def _load(path, snapshot):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        book = load_workbook(path)
    if caught:
        raise ValueError('This workbook uses unsupported Excel features. Save a simpler copy before updating: '
                         + '; '.join(str(w.message) for w in caught))
    if META not in book or book[META]['A1'].value != 'Pytest Runner analysis 1':
        raise ValueError('Choose an analysis workbook created by this version of Pytest Runner. '
                         'Export to a new file to keep your existing workbook.')
    meta = book[META]
    if meta['B1'].value != workspace_key(snapshot.workspace):
        raise ValueError('This analysis belongs to a different project. Export a new workbook instead.')
    previous = {}
    scope_col = meta['C1'].value
    if not isinstance(scope_col, int) or scope_col < 4:
        raise ValueError('The workbook source metadata is incomplete.')
    for row in meta.iter_rows(min_row=3, max_col=scope_col - 1, values_only=True):
        if row[0]:
            if row[0] in previous:
                raise ValueError('Duplicate source identifiers. The workbook was not updated.')
            previous[row[0]] = json.loads(''.join(v or '' for v in row[1:]))
    ws = book['Analysis']
    cols = _columns(ws)
    if not set(CORE).issubset(cols) or 'TestAnalysis' not in ws.tables:
        raise ValueError('Keep the Analysis table and its original column headers to update this workbook.')
    identities = {}
    # Les colonnes et les lignes peuvent etre deplacees : jamais de jointure par position.
    for r in range(FIRST, ws.max_row + 1):
        nodeid = ws.cell(r, cols['Test ID']).value
        if not nodeid:
            if any(ws.cell(r, c).value is not None for c in cols.values()):
                raise ValueError(f'Analysis row {r} has no Test ID. Copy a complete test row instead.')
            continue
        scope = ws.cell(r, cols['Reader scope']).value
        if not isinstance(nodeid, str) or nodeid not in previous or not scope or not isinstance(scope, str):
            raise ValueError(f'Invalid test identity or reader scope on Analysis row {r}.')
        key = nodeid, scope
        if key in identities:
            raise ValueError(f'Duplicate test and reader scope on rows {identities[key]} and {r}. '
                             'Choose another reader scope for a copied row.')
        identities[key] = r
    return book, cols, identities, previous


def _decision(statuses, scope, diff, state, follow):
    if follow in ('Done', 'Expected'):
        return '—'
    if follow == 'To review':
        return 'Updated results'
    if state == 'Removed':
        return 'Removed test'
    if scope != ALL and scope not in statuses:
        return 'Reader unavailable'
    if follow == 'To retest':
        return 'Retest'
    values = list(statuses.values()) if scope == ALL else [statuses[scope]]
    for status, label in (('ERROR', 'Error'), ('FAILED', 'Failure'), ('NOT RUN', 'Not run')):
        if status in values:
            return label
    if scope == ALL and diff not in ('Identical', 'Single reader', 'No results'):
        return diff
    return '—'


def _formula(r, cols, readers):
    cell = lambda name: f'{letter(cols[name])}{r}'
    quoted = lambda value: '"' + value.replace('"', '""') + '"'
    scope, follow, state = (cell(v) for v in ('Reader scope', 'Follow-up', 'Collection'))
    expr = f'IF({scope}={quoted(ALL)},IF(OR({cell("Reader differences")}="Identical",' \
           f'{cell("Reader differences")}="Single reader",{cell("Reader differences")}="No results"),' \
           f'"—",{cell("Reader differences")}),"—")'
    for status, label in reversed((('ERROR', 'Error'), ('FAILED', 'Failure'), ('NOT RUN', 'Not run'))):
        all_check = 'OR(' + ','.join(f'{cell("Result: " + name)}="{status}"' for name in readers) + ')'
        scoped = 'FALSE'
        for name in reversed(readers):
            scoped = f'IF({scope}={quoted(name)},{cell("Result: " + name)}="{status}",{scoped})'
        expr = f'IF(IF({scope}={quoted(ALL)},{all_check},{scoped}),"{label}",{expr})'
    available = 'OR(' + ','.join(f'{scope}={quoted(n)}' for n in [ALL] + readers) + ')'
    return (f'=IF(OR({follow}="Done",{follow}="Expected"),"—",'
            f'IF({follow}="To review","Updated results",IF({state}="Removed","Removed test",'
            f'IF(NOT({available}),"Reader unavailable",IF({follow}="To retest","Retest",{expr})))))')


def _resize(ws, cols, old_end):
    end = max(FIRST, ws.max_row)
    ref = f'A6:{letter(max(cols.values()))}{end}'
    old = ws.tables.get('TestAnalysis')
    saved = {c.name: c for c in old.tableColumns} if old else {}
    table = Table(displayName='TestAnalysis', ref=ref)
    table._initialise_columns()
    for i, name in enumerate(cols):
        column = copy(saved[name]) if name in saved else table.tableColumns[i]
        column.id, column.name = i + 1, name
        table.tableColumns[i] = column
    table.tableStyleInfo = copy(old.tableStyleInfo) if old else TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    if old:
        table.autoFilter = copy(old.autoFilter)
        if table.autoFilter:
            table.autoFilter.ref = ref
        del ws.tables['TestAnalysis']
    ws.add_table(table)
    if ws.auto_filter.ref:
        ws.auto_filter.ref = ref
    # Etendre les validations utilisateur portant sur toute la table, sans
    # appliquer des regles a un million de cellules vides.
    def resized(ranges):
        spans = []
        for span in ranges:
            clone = copy(span)
            if clone.min_row == FIRST and clone.max_row == old_end:
                clone.max_row = end
            spans.append(str(clone))
        return ' '.join(spans)
    rules = OrderedDict()
    for key, values in ws.conditional_formatting._cf_rules.items():
        rules[ConditionalFormatting(sqref=resized(key.sqref.ranges))] = values
    ws.conditional_formatting._cf_rules = rules
    for validation in ws.data_validations.dataValidation:
        validation.sqref = resized(validation.sqref.ranges)
    if not old:
        validation = DataValidation(type='list', formula1='"' + ','.join(FOLLOWUP) + '"', allow_blank=False)
        validation.showErrorMessage = True
        validation.error = 'Choose a follow-up state from the list.'
        ws.add_data_validation(validation)
        validation.add(f'{letter(cols["Follow-up"])}7:{letter(cols["Follow-up"])}{end}')
        _status_colors(ws, [c for h, c in cols.items() if h.startswith('Result: ')], end)
        c = letter(cols['Needs review'])
        ws.conditional_formatting.add(f'{c}7:{c}{end}', CellIsRule(operator='notEqual', formula=['"—"'],
            fill=PatternFill('solid', fgColor='FFF2D6')))


def _status_colors(ws, columns, end):
    if columns:
        spans = ' '.join(f'{letter(c)}7:{letter(c)}{end}' for c in columns)
        for status, color in COLORS.items():
            ws.conditional_formatting.add(spans, CellIsRule(operator='equal', formula=['"' + status + '"'],
                                                          fill=PatternFill('solid', fgColor=color)))


def _cache_formulas(path, caches):
    # Fournir aussi un affichage initial aux visionneuses sans moteur de calcul.
    # Les formules restent actives ; Excel recalcule apres les editions.
    temporary = path.with_suffix('.cached.xlsx')
    pattern = re.compile(rb'<c\b([^>]*\br="([^"]+)"[^>]*)>(.*?)</c>', re.S)
    try:
        with ZipFile(path) as src, ZipFile(temporary, 'w', ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                values = caches.get(info.filename)
                if values:
                    def replace(match):
                        value = values.get(match[2].decode())
                        if value is None or b'<f' not in match[3]:
                            return match[0]
                        attrs = re.sub(rb'\s+t="[^"]*"', b'', match[1])
                        content = re.sub(rb'<v(?:\s[^>]*)?>.*?</v>|<v\s*/>', b'', match[3], flags=re.S)
                        numeric = type(value) in (int, float)
                        return b'<c' + attrs + (b'' if numeric else b' t="str"') + b'>' + content + \
                            ('<v>' + escape(str(value)) + '</v></c>').encode('utf-8')
                    data = pattern.sub(replace, data)
                dst.writestr(copy(info), data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_analysis_xlsx(destination, snapshot, entries=()):
    """Cree ou actualise le classeur sans perdre le suivi des tests existants."""
    destination = Path(destination)
    tests, readers, source, hashes = _source(snapshot, entries)
    if destination.exists():
        book, cols, identities, previous = _load(destination, snapshot)
        ws = book['Analysis']
    else:
        book = Workbook()
        book.active.title = 'Summary'
        ws = book.create_sheet('Analysis')
        headers = list(CORE[:9]) + ['Result: ' + n for n in readers] + list(CORE[9:])
        _base(ws, 'Test results · Analysis', headers, 'Edit the blue columns · Filter Needs review to focus on issues')
        cols, identities, previous = _columns(ws), {}, {}
    old_end = max(FIRST, ws.max_row)
    added_columns = []
    for name in readers:
        header = 'Result: ' + name
        if header not in cols:
            cols[header] = ws.max_column + 1
            _text(ws.cell(HEADER, cols[header]), header)
            ws.cell(HEADER, cols[header])._style = copy(ws.cell(HEADER, 1)._style)
            ws.column_dimensions[letter(cols[header])].width = 24
            added_columns.append(cols[header])
    # Une occurrence par cas au depart ; copier une ligne et changer Reader
    # scope permet deux tickets independants sur deux lecteurs.
    represented = {key[0] for key in identities}
    rows_by_id = {row.nodeid: row for row in tests}
    next_row = ws.max_row + 1
    for row in tests:
        if row.nodeid not in represented:
            r = next_row
            next_row += 1
            for c in cols.values():
                cell = ws.cell(r, c)
                cell.font, cell.alignment = FONT, WRAP
                if r > FIRST:
                    cell._style = copy(ws.cell(FIRST, c)._style)
            for name, value in (('Test ID', row.nodeid), ('Reader scope', ALL), ('Follow-up', 'To analyze')):
                _text(ws.cell(r, cols[name]), value)
            identities[row.nodeid, ALL] = r
    caches = {}
    for (nodeid, scope), r in identities.items():
        row = rows_by_id.get(nodeid)
        current, before = source.get(nodeid), previous.get(nodeid)
        state = 'Removed' if row is None else 'New' if before is None else 'Current'
        old_scope = before if scope == ALL else (before or {}).get(scope)
        new_scope = current if scope == ALL else (current or {}).get(scope)
        changed = bool(before is not None and old_scope != new_scope)
        if row is None:
            changed = ws.cell(r, cols['Collection']).value != 'Removed'
        if row and before is not None and ws.cell(r, cols['Collection']).value == 'Removed':
            changed, state = True, 'Restored'
        elif changed and row:
            state = 'Results changed'
        follow_cell = ws.cell(r, cols['Follow-up'])
        if changed and follow_cell.value != 'To review':
            note = f'Previous follow-up: {follow_cell.value or "To analyze"}. Results changed on {snapshot.at}.'
            existing = follow_cell.comment.text + '\n' if follow_cell.comment else ''
            follow_cell.comment = Comment(existing + note, 'Pytest Runner')
            _text(follow_cell, 'To review')
        if row:
            _text(ws.cell(r, cols['Group']), row.path.rsplit(' / ', 1)[0] if ' / ' in row.path else '')
            _text(ws.cell(r, cols['Test']), (nodeid.partition('::')[2] or row.name) + '\n' + nodeid.partition('::')[0])
        _text(ws.cell(r, cols['Collection']), state)
        statuses = {name: values[0] for name, values in (current or {}).items()}
        for header, c in cols.items():
            if header.startswith('Result: '):
                _text(ws.cell(r, c), statuses.get(header[8:], 'No result'))
        diff = difference(row.results) if row else 'No results'
        _text(ws.cell(r, cols['Reader differences']), diff)
        c = ws.cell(r, cols['Needs review'])
        c.value = _formula(r, cols, readers)
        if len(c.value) > 8192:
            raise ValueError('Too many or too long reader names for the Excel formula limit.')
        caches[c.coordinate] = _decision(statuses, scope, diff, state, follow_cell.value)
        for name in EDITABLE:
            ws.cell(r, cols[name]).fill = PatternFill('solid', fgColor='F1F7FD')
        ticket = ws.cell(r, cols['Jira ticket'])
        value = ticket.value
        if isinstance(value, str) and value.startswith(('https://', 'http://')):
            ticket.hyperlink = value
            match = re.search(r'/browse/([A-Za-z][A-Za-z0-9_]*-\d+)(?:[/?#]|$)', value)
            if match:
                _text(ticket, match[1])
            ticket.font = Font(name='Aptos', size=11, color=BLUE, underline='single')
        elif ticket.hyperlink and value != (re.search(r'/browse/([^/?#]+)', ticket.hyperlink.target or '') or [None, None])[1]:
            # Un ticket remplace ou efface ne doit pas ouvrir son ancienne URL.
            ticket.hyperlink = None
    if ws.max_row > 1048576 or ws.max_column > 16384:
        raise ValueError('The analysis exceeds the Excel worksheet size limit.')
    _resize(ws, cols, old_end)
    _status_colors(ws, added_columns, ws.max_row)
    ws.column_dimensions[letter(cols['Test ID'])].hidden = True
    _text(ws['A3'], f'{len(tests)} collected tests · {len(readers)} readers · Updated {snapshot.at}')
    # La validation par plage ne depend pas de la longueur des noms (limite
    # Excel de 255 caracteres pour une liste ecrite directement dans la formule).
    old_meta = book[META] if META in book else None
    if old_meta:
        book.remove(old_meta)
    meta = book.create_sheet(META)
    meta.sheet_state = 'veryHidden'
    meta.append(['Pytest Runner analysis 1', workspace_key(snapshot.workspace)])
    meta.append(['Test ID', 'Source signatures'])
    retained = dict(previous)
    retained.update(source)
    for nodeid, signatures in retained.items():
        payload = json.dumps(signatures, ensure_ascii=False, separators=(',', ':'))
        _row(meta, [nodeid] + [payload[i:i + 30000] for i in range(0, len(payload), 30000)])
    scope_col = max(4, meta.max_column + 1)
    meta['C1'] = scope_col
    for i, name in enumerate([ALL] + readers, 1):
        _text(meta.cell(i, scope_col), name)
    for validation in list(ws.data_validations.dataValidation):
        if validation.errorTitle == 'Pytest Runner reader scope':
            ws.data_validations.dataValidation.remove(validation)
    book.defined_names.add(DefinedName('RunnerReaderScopes',
        attr_text=f"'{META}'!${letter(scope_col)}$1:${letter(scope_col)}${len(readers) + 1}"))
    validation = DataValidation(type='list', formula1='RunnerReaderScopes')
    validation.errorTitle, validation.error = 'Pytest Runner reader scope', 'Choose All readers or a reader from the list.'
    validation.showErrorMessage = True
    ws.add_data_validation(validation)
    validation.add(f'{letter(cols["Reader scope"])}7:{letter(cols["Reader scope"])}{ws.max_row}')
    # Ces feuilles sont des instantanes geres par le runner ; les feuilles
    # personnelles et la table Analysis restent dans le classeur existant.
    for name in ('Summary', 'Reference', 'Groups'):
        if name in book:
            index = book.index(book[name])
            book.remove(book[name])
            book.create_sheet(name, index)
        else:
            book.create_sheet(name)
    reference = book['Reference']
    headers = ['Group', 'Test', 'Reader', 'Status', 'Duration (s)', 'Run', 'Date', 'Result source',
               'Configuration', 'Base YAML SHA256', 'Reason / collection error', 'Test ID']
    _base(reference, 'Result provenance', headers, 'Source values · NOT RUN = requested but not executed · No result = no recorded verdict')
    for row in tests:
        for reader, result in zip(snapshot.readers, row.results):
            r = _row(reference, [row.path.rsplit(' / ', 1)[0] if ' / ' in row.path else '', row.name, reader.name or 'No reader',
                result.status.label if result.status else 'No result', result.duration if valid_duration(result.duration) else None,
                result.run_id, result.at, 'Previous run' if result.previous else 'Latest run' if result.status else '',
                result.configuration, hashes[result.run_id, reader.name], result.reason or row.note, row.nodeid])
            reference.cell(r, 5).number_format = '0.000'
    reference.auto_filter.ref = f'A6:L{reference.max_row}'
    _status_colors(reference, [4], reference.max_row)
    reference.protection.sheet = True
    reference.protection.autoFilter = False
    _groups(book['Groups'], snapshot)
    summary_cache = _summary(book['Summary'], snapshot, tests, identities, cols, ws, caches)
    book.calculation.fullCalcOnLoad = True
    book.calculation.forceFullCalc = True
    book.active = book.index(book['Summary'])
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, suffix='.xlsx', delete=False) as stream:
            temporary = Path(stream.name)
        book.save(temporary)
        cache_map = {f'xl/worksheets/sheet{book.index(ws) + 1}.xml': caches,
                     f'xl/worksheets/sheet{book.index(book["Summary"]) + 1}.xml': summary_cache}
        _cache_formulas(temporary, cache_map)
        os.replace(temporary, destination)
    finally:
        book.close()
        if temporary:
            temporary.unlink(missing_ok=True)
    return len(tests), sum(has_difference(row) for row in tests)


def _groups(ws, snapshot):
    _base(ws, 'Test tree', ['Group / test', 'Tests', 'Reader differences', 'Collection error']
          + ['Result: ' + (reader.name or 'No reader') for reader in snapshot.readers],
          'Use + / − to expand folders · Analysis contains the editable follow-up')
    ws.column_dimensions['A'].width = 65
    ws.sheet_properties.outlinePr.summaryBelow = False
    summaries = _group_summaries(snapshot.rows, len(snapshot.readers))
    for i, row in enumerate(snapshot.rows):
        counts = summaries.get(i)
        if counts:
            statuses = [' · '.join(f'{value} {status.label if status else "No result"}'
                                   for status, value in counter.items()) for counter in counts[2]]
        else:
            statuses = [result.status.label if result.status else 'No result' for result in row.results]
        r = _row(ws, [row.name, counts[0] if counts else 1,
                      counts[1] if counts else int(has_difference(row)),
                      row.note or (f'{counts[3]} collection errors' if counts and counts[3] else '')] + statuses)
        ws.row_dimensions[r].outlineLevel = min(row.depth, 7)
        ws.cell(r, 1).alignment = Alignment(indent=min(row.depth, 15), vertical='center')
        if counts:
            for cell in ws[r]:
                cell.font = Font(name='Aptos', size=11, bold=True, color=BLUE)
                cell.fill = PatternFill('solid', fgColor='EAF0FA')
    ws.sheet_format.outlineLevelRow = min(max(row.depth for row in snapshot.rows), 7)
    _status_colors(ws, list(range(5, 5 + len(snapshot.readers))), ws.max_row)


def _summary(ws, snapshot, tests, identities, cols, analysis, caches):
    _base(ws, 'Test results · Summary', ['Overview', 'Count', 'Next step'],
          f'IN Groupe · {snapshot.at}')
    ws.freeze_panes = None
    for col, width in (('A', 28), ('B', 18), ('C', 80)):
        ws.column_dimensions[col].width = width
    span = lambda name: f"'Analysis'!{letter(cols[name])}7:{letter(cols[name])}{analysis.max_row}"
    issues = sum(value != '—' for value in caches.values())
    tickets = sum(bool(analysis.cell(r, cols['Jira ticket']).value) for r in identities.values())
    metrics = [
        ('Collected tests', len(tests), 'All collected tests, including unchecked or hidden tests.'),
        ('Reader differences', sum(has_difference(row) for row in tests), 'Source differences, regardless of follow-up.'),
        ('Needs review', f'=COUNTIFS({span("Needs review")},"<>—",{span("Needs review")},"<>")', 'Open Analysis, then filter Needs review to exclude —.'),
        ('With a ticket', f'=COUNTIF({span("Jira ticket")},"?*")', 'Edit Comment, Jira ticket, Owner and Action on the test row.'),
        ('Collection errors', sum(bool(row.note) for row in snapshot.rows), 'See Groups: collection errors can make this export incomplete.'),
    ]
    for values in metrics:
        _row(ws, values)
    ws['B9'] = metrics[2][1]
    ws['B10'] = metrics[3][1]
    for r, name in ((13, 'Analysis'), (14, 'Groups'), (15, 'Reference')):
        _text(ws.cell(r, 1), 'Open ' + name)
        ws.cell(r, 1).hyperlink = f"#'{name}'!A6"
        ws.cell(r, 1).style = 'Hyperlink'
    instructions = [
        'Find a test: Ctrl+F. Filter by group, status, reader differences or follow-up.',
        'Close an analysis: choose Done or Expected. Changed results reopen it as To review.',
        'Different tickets per reader: copy the complete row, then change Reader scope.',
        'Refresh: save and close this file, then choose Update Excel analysis… in Pytest Runner.',
        'Personal columns and sheets stay editable. Keep Test ID and original Analysis headers.',
        'Summary, Groups and Reference are regenerated. Results can come from different runs.',
        'Base YAML fingerprints identify archived run settings; per-test overrides are not compared.',
    ]
    for r, text in enumerate(instructions, 17):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        _text(ws.cell(r, 1), text)
        ws.cell(r, 1).font, ws.cell(r, 1).alignment = FONT, WRAP
        ws.row_dimensions[r].height = 30
    return {'B9': issues, 'B10': tickets}
