"""Rapport d'analyse HTML autonome ; export JUnit sans transformation."""
from __future__ import annotations

import base64
import json
import shutil
import time
from html import escape
from importlib.resources import files
from pathlib import Path

from runner.domain.duration import format_duration
from runner.domain.history import RunEntry
from runner.domain.report_data import report_payload


def _resource(name):
    return files('runner.report_assets').joinpath(name).read_text(encoding='utf-8')


def _json(data):
    # Un nodeid parametre peut contenir </script>. JSON ne protege pas le
    # parseur HTML : neutraliser les delimiteurs avant de l'inserer.
    return json.dumps(data, ensure_ascii=False, allow_nan=False, default=str).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def _static_tree(data):
    nodes, rows = data['nodes'], data['rows']
    def show(identifier):
        node = nodes[identifier]
        if node['kind'] != 'test':
            return '<details open><summary>' + escape(node['name']) + '</summary><div class="static-children">' + ''.join(show(child) for child in node['children']) + '</div></details>'
        row = rows[node['index']]
        parts = []
        for name, result in zip(data['readers'], row['readers']):
            body = '<p>' + escape(name) + ' · ' + escape(result['status'].upper()) + '</p>'
            for attempt in result['attempts']:
                body += '<p>Recorded attempt ' + str(attempt.get('attempt', 0) + 1) + ' · ' + escape(attempt['status']) + '</p>'
                if attempt.get('trace'):
                    body += '<pre class="tr-code">' + escape(attempt['trace']) + '</pre>'
            parts.append(body)
        return '<details><summary>' + escape(row['nodeid']) + ' · Occurrence ' + str(row['index']+1) + '</summary>' + ''.join(parts) + '</details>'
    return show('profile')


def html_report(entry, output=None):
    """Accepte un lecteur, ou toutes les entrees d'un meme lancement."""
    entries = (entry,) if isinstance(entry, RunEntry) else tuple(entry)
    outputs = [output] if isinstance(entry, RunEntry) and output is not None else None
    data = report_payload(entries, outputs)
    logo = 'data:image/png;base64,' + base64.b64encode(files('runner.report_assets').joinpath('in-groupe.png').read_bytes()).decode('ascii')
    when = time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(data['timestamp']))
    statuses = ('passed', 'failed', 'error', 'skipped', 'notrun', 'unknown')
    counts = dict(data['counts'])
    # Les compteurs historiques ne permettent pas d'inventer des verdicts
    # individuels. Les afficher a part lorsque seuls ces totaux subsistent.
    if not any(e.analysis_file or e.analysis_data for e in entries):
        counts.update({status:sum(int(e.counts.get(status.upper(), 0)) for e in entries) for status in statuses[:4]})
    summary = ''.join('<span data-status="' + status + '" class="tr-' + status + '"><strong>' + str(counts.get(status, 0)) + '</strong> ' + {'notrun':'Not run', 'unknown':'Unknown'}.get(status, status.title()) + '</span>' for status in statuses)
    label = 'Completed' if data['complete'] else 'Incomplete or older archive'
    if any(e.exit_code for e in entries):
        label += ' · Execution errors recorded'
    console = ''.join('<details><summary>' + escape(name) + '</summary><pre class="tr-code">' + escape(text or 'No console output was archived.') + '</pre></details>' for name, text in zip(data['readers'], data['console']))
    css = _resource('report.css')
    js = _resource('report.js')
    icons = _resource('icons.json')
    fallback = _static_tree(data)
    configurations, known = {}, {}
    for row in data['rows']:
        for result in row['readers']:
            yaml = result.pop('yaml')
            key = known.setdefault(id(yaml), 'c' + str(len(known)))
            configurations[key] = yaml
            result['configuration'] = key
    data['configurations'] = configurations
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test report — {escape(data['title'])} — {escape(when)}</title>
<style>{css}</style></head><body>
<article id="pytest-tree-report-in" aria-label="IN Groupe test analysis report">
<header><div class="tr-logo-plate"><img src="{logo}" alt="IN Groupe" width="420" height="253"></div><div class="tr-heading-brand"><div class="tr-brand">PYTEST RUNNER / ANALYSIS REPORT</div><h2>{escape(data['title'])}</h2><div class="tr-meta">{escape(when)} · Build #{data['build'] if data['build'] is not None else 'not recorded'} · {format_duration(data['duration'])}</div><div class="tr-meta">{escape(label)} · {len(data['rows'])} planned occurrences · {len(entries)} reader(s)</div></div></header>
<div class="tr-summary">{summary}</div><p class="tr-note">Latest verdicts per occurrence and reader. Unknown means the archive cannot establish the result. Archived totals: {escape('; '.join(e.summary for e in entries))}</p>
<div class="tr-ui" hidden>
<details class="tr-context"><summary>Run context, environment &amp; recorded commands</summary><div class="tr-context-body"></div></details>
<div class="tr-toolbar"><input class="tr-search" type="search" aria-label="Search the execution tree" placeholder="Search a group, test, parameter or path…"><select class="tr-reader-filter" aria-label="Filter by reader"></select><select class="tr-status-filter" aria-label="Filter by result"><option value="all">All results</option><option value="issues">Failures / errors</option><option value="notrun">Not run</option><option value="unknown">Unknown</option></select></div>
<div class="tr-note tr-filter-count" aria-live="polite"></div><div class="tr-cols"><section class="tr-tree-area" aria-label="Execution hierarchy"><div class="tr-tools"><button type="button" class="tr-button" data-action="expand">Expand all</button><button type="button" class="tr-button" data-action="collapse">Collapse all</button></div><div class="tr-tree-head"></div><ul class="tr-tree" aria-label="Profile tree"></ul><div class="tr-legend"></div><div class="tr-caption">Profile order and group colours preserved. Σ time sums recorded latest-attempt durations across displayed readers.</div></section><section class="tr-inspector" aria-label="Selected result details" aria-live="polite"></section></div>
<details class="tr-context"><summary>Console output — all recorded readers</summary><div class="tr-console"></div></details></div>
<section class="tr-static"><h3>Execution hierarchy and recorded details</h3><p class="tr-meta">{escape(data['workspace'])}</p>{fallback}<h3>Console output</h3>{console}</section>
<footer class="tr-footer"><span>IN Groupe · Pytest Runner · Self-contained report</span><span>Missing historical data is marked explicitly.</span></footer></article>
<script type="application/json" id="report-data">{_json(data)}</script>
<script type="application/json" id="report-icons">{icons}</script>
<script>{js}</script></body></html>"""


def write_html(entry, destination, output=None):
    """Ecriture atomique ; une erreur ne laisse jamais un demi-rapport."""
    path = Path(destination)
    temporary = path.with_name(path.name + '.tmp')
    try:
        temporary.write_text(html_report(entry, output), encoding='utf-8')
        temporary.replace(path)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False, str(exc)
    return True, ''


def write_junit(entry: RunEntry, destination: Path) -> tuple[bool, str]:
    """Recopie le JUnit XML produit par pytest pendant ce run.

    Rien n'est regenere : le fichier ecrit par pytest est la reference, et le
    reconstruire a partir des compteurs donnerait un XML approximatif la ou on
    attend celui du run.
    """
    source = Path(entry.junit_path) if entry.junit_path else None
    if source is None or not source.is_file():
        return False, ("This run has no JUnit file. It is written by pytest "
                       "during the run; older entries may predate it.")
    try:
        shutil.copyfile(source, destination)
    except OSError as exc:
        return False, str(exc)
    return True, ""
