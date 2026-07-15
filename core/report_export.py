"""
Generation d'un rapport HTML autonome (pas de dependance a pytest-html,
qui n'est pas dans les wheels embarquees). Le fichier produit est un
simple .html consultable dans n'importe quel navigateur, hors ligne.
"""

import html
import time


_STATUS_COLORS = {
    "passed": ("#c8e6c9", "#2e7d32"),
    "failed": ("#ffcdd2", "#c62828"),
    "skipped": ("#ffe0b2", "#ef6c00"),
    "error": ("#e1bee7", "#6a1b9a"),
}


def _card(label: str, value: int, key: str) -> str:
    base, strong = _STATUS_COLORS[key]
    return f"""
    <div style="background:{base};border-left:6px solid {strong};
                border-radius:8px;padding:12px 18px;min-width:100px;text-align:center;">
        <div style="font-size:24px;font-weight:bold;color:#222;">{value}</div>
        <div style="font-size:12px;color:#444;">{label}</div>
    </div>
    """


def export_html_report(entry: dict, output_text: str, dest_path: str) -> None:
    """Ecrit un rapport HTML pour l'entree d'historique donnee vers dest_path."""

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("timestamp", time.time())))
    workspace = html.escape(entry.get("workspace", ""))
    duration = entry.get("duration_seconds", 0)
    exit_code = entry.get("exit_code", "")
    nodeids = entry.get("nodeids", [])
    failed_nodeids = entry.get("failed_nodeids", [])

    nodeids_html = "".join(f"<li><code>{html.escape(n)}</code></li>" for n in nodeids) or "<li>(aucun)</li>"
    failed_html = (
        "".join(f"<li><code>{html.escape(n)}</code></li>" for n in failed_nodeids)
        or "<li>(aucun echec)</li>"
    )

    doc = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Rapport de tests - {ts}</title>
<style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background:#fafafa; color:#222; }}
    h1 {{ font-size: 20px; }}
    .meta {{ color:#555; margin-bottom: 16px; }}
    .cards {{ display:flex; gap:12px; margin-bottom: 24px; flex-wrap: wrap; }}
    .section {{ margin-bottom: 24px; }}
    .section h2 {{ font-size: 15px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
    ul {{ columns: 2; -webkit-columns: 2; }}
    pre {{ background:#1e1e1e; color:#dcdcdc; padding:14px; border-radius:8px;
           overflow-x:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; }}
</style>
</head>
<body>
    <h1>Rapport d'execution pytest</h1>
    <div class="meta">
        Workspace : <code>{workspace}</code><br>
        Date : {ts} &mdash; Duree : {duration}s &mdash; Code de sortie : {exit_code}
    </div>

    <div class="cards">
        {_card("PASSED", entry.get("passed", 0), "passed")}
        {_card("FAILED", entry.get("failed", 0), "failed")}
        {_card("SKIPPED", entry.get("skipped", 0), "skipped")}
        {_card("ERROR", entry.get("error", 0), "error")}
    </div>

    <div class="section">
        <h2>Tests en echec ({len(failed_nodeids)})</h2>
        <ul>{failed_html}</ul>
    </div>

    <div class="section">
        <h2>Tests executes ({len(nodeids)})</h2>
        <ul>{nodeids_html}</ul>
    </div>

    <div class="section">
        <h2>Sortie console complete</h2>
        <pre>{html.escape(output_text or "")}</pre>
    </div>
</body>
</html>
"""

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(doc)
