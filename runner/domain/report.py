"""Rapport HTML autonome pour un run, et recuperation du JUnit XML.

Un rapport sert a etre transmis : joint a un ticket, depose sur un partage,
ouvert par quelqu'un qui n'a pas l'outil. Il doit donc tenir dans UN fichier,
sans feuille de style ni police a aller chercher -- une page qui se decompose
parce que le reseau interne bloque un CDN ne vaut rien comme piece jointe.

Le XML, lui, n'est pas produit ici : pytest l'ecrit nativement avec
`--junitxml`. L'exporter, c'est le recopier -- aucune dependance, et un
fichier que les serveurs d'integration savent deja lire.
"""

from __future__ import annotations

import shutil
import time
from html import escape
from pathlib import Path

from runner.domain.ansi import strip_ansi
from runner.domain.history import RunEntry
from runner.domain.models import Status

# Le rapport est lu ailleurs que dans l'outil, souvent imprime ou colle dans
# un ticket : il garde ses propres couleurs, claires et sobres, plutot que
# celles du theme en cours.
_CSS = """
:root {
  --bg:#f6f7f9; --surface:#fff; --border:#e3e7ec; --text:#1b2230;
  --muted:#5b6675; --passed:#2e7d32; --failed:#c62828; --skipped:#a1651a;
  --error:#7b3fa0;
}
* { box-sizing:border-box; }
body { margin:0; padding:32px; background:var(--bg); color:var(--text);
       font:14px/1.5 "Segoe UI", system-ui, sans-serif; }
.wrap { max-width:960px; margin:0 auto; }
.card { background:var(--surface); border:1px solid var(--border);
        border-radius:10px; padding:20px 24px; margin-bottom:16px; }
h1 { font-size:19px; margin:0 0 6px; }
h2 { font-size:15px; margin:0 0 12px; }
.meta { color:var(--muted); font-size:13px; }
.counts { display:flex; gap:12px; flex-wrap:wrap; margin-top:16px; }
.count { flex:1 1 120px; border:1px solid var(--border); border-radius:8px;
         padding:12px 14px; }
.count .n { font-size:24px; font-weight:700; }
.count .l { color:var(--muted); font-size:12px; text-transform:uppercase;
            letter-spacing:.04em; }
.passed .n { color:var(--passed); } .failed .n { color:var(--failed); }
.skipped .n { color:var(--skipped); } .error .n { color:var(--error); }
ul { margin:0; padding-left:18px; }
li { font-family:"Cascadia Mono", Consolas, monospace; font-size:12.5px;
     padding:2px 0; word-break:break-all; }
pre { background:#0d0f13; color:#e4e7ec; border-radius:8px; padding:16px;
      overflow-x:auto; font-family:"Cascadia Mono", Consolas, monospace;
      font-size:12.5px; line-height:1.45; }
.badge { display:inline-block; border-radius:999px; padding:3px 10px;
         font-size:12px; font-weight:600; }
.ok { background:#e6f4ea; color:var(--passed); }
.ko { background:#fdecea; color:var(--failed); }
.rd { background:#e8effc; color:#1f6feb; }
.empty { color:var(--muted); font-style:italic; }
"""


def _compteurs(entry: RunEntry) -> str:
    cases = []
    for statut in (Status.PASSED, Status.FAILED, Status.SKIPPED, Status.ERROR):
        cases.append(
            f'<div class="count {statut.name.lower()}">'
            f'<div class="n">{entry.count(statut)}</div>'
            f'<div class="l">{statut.name.lower()}</div></div>')
    return f'<div class="counts">{"".join(cases)}</div>'


def _liste(titre: str, nodeids, vide: str) -> str:
    if not nodeids:
        corps = f'<p class="empty">{escape(vide)}</p>'
    else:
        corps = "<ul>" + "".join(
            f"<li>{escape(str(n))}</li>" for n in nodeids) + "</ul>"
    return f'<div class="card"><h2>{escape(titre)} ({len(nodeids)})</h2>{corps}</div>'


def html_report(entry: RunEntry, output: str = "") -> str:
    """Le rapport, en un seul fichier HTML."""
    quand = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
    reussi = entry.ok

    etiquettes = [f'<span class="badge {"ok" if reussi else "ko"}">'
                  f'exit code {entry.exit_code}</span>']
    if entry.reader:
        etiquettes.append(f'<span class="badge rd">{escape(entry.reader)}</span>')

    # La sortie est nettoyee de ses sequences ANSI : dans un fichier HTML
    # elles s'afficheraient telles quelles, en plein milieu du texte.
    console = escape(strip_ansi(output)) if output else ""
    bloc_console = (f'<div class="card"><h2>Console output</h2><pre>{console}</pre>'
                    "</div>") if console else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test report — {escape(quand)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<div class="card">
  <h1>Test report</h1>
  <p class="meta">{escape(quand)} · {entry.duration:.1f}s ·
     {escape(entry.workspace)}</p>
  <p style="margin-top:12px">{"".join(etiquettes)}</p>
  {_compteurs(entry)}
</div>
{_liste("Failed tests", entry.failed_nodeids, "Nothing failed in this run.")}
{_liste("Tests in this run", entry.nodeids, "No test was collected.")}
{bloc_console}
</div></body></html>
"""


def write_html(entry: RunEntry, destination: Path, output: str = "") -> tuple[bool, str]:
    """Ecrit le rapport. Rend (succes, message)."""
    try:
        Path(destination).write_text(html_report(entry, output), encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, ""


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
