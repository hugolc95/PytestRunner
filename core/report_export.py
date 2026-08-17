"""
Generation d'un rapport HTML autonome (pas de dependance a pytest-html,
qui n'est pas dans les wheels embarquees). Le fichier produit est un
simple .html consultable dans n'importe quel navigateur, hors ligne.
"""

import html
import time


_STATUS = {
    "passed": ("Passed", "#22c55e", "#f0fdf4"),
    "failed": ("Failed", "#ef4444", "#fef2f2"),
    "skipped": ("Skipped", "#f59e0b", "#fffbeb"),
    "error": ("Error", "#a855f7", "#faf5ff"),
}


def _card(label: str, value: int, key: str) -> str:
    _, strong, base = _STATUS[key]
    return f"""
    <div class="card" style="border-top-color:{strong};background:{base};">
        <div class="card-value" style="color:{strong};">{value}</div>
        <div class="card-label">{label}</div>
    </div>
    """


def _nodeid_item(nodeid: str) -> str:
    """Une ligne de la liste : chemin en gris, nom du test en evidence.

    Le nodeid est coupe au dernier `::` : sur des suites profondement
    imbriquees, le chemin fait trois fois la longueur du nom du test et le
    noyait completement.
    """
    texte = str(nodeid)
    if "::" in texte:
        chemin, _, nom = texte.rpartition("::")
        return (
            f'<li><span class="np">{html.escape(chemin)}::</span>'
            f'<span class="nn">{html.escape(nom)}</span></li>'
        )
    return f'<li><span class="nn">{html.escape(texte)}</span></li>'


def _list_section(title: str, nodeids: list, empty_text: str, open_by_default: bool) -> str:
    items = "".join(_nodeid_item(n) for n in nodeids)
    body = f"<ul class='nodeids'>{items}</ul>" if nodeids else f"<p class='empty'>{empty_text}</p>"
    return f"""
    <details class="section" {"open" if open_by_default else ""}>
        <summary>{title} <span class="count">({len(nodeids)})</span></summary>
        {body}
    </details>
    """


# Cles de configuration sans interet dans un rapport : elles decrivent comment
# PytestRunner lance les tests, pas dans quelles conditions ils ont tourne.
_CONFIG_IGNOREES = {
    "readers", "reader_list", "lecteurs",
    "reader_mode", "readers_mode", "mode_lecteurs",
    "console_path_levels", "console_paths", "console_path",
    "show_test_class", "show_class", "show_classes",
}


def _config_badges(config: dict) -> str:
    """Parametres de la configuration, en pastilles a cote du lecteur.

    Les reglages d'un run se lisent d'un coup d'oeil avec lui, pas dans une
    section a deplier plus bas : ils font partie de son identite, au meme titre
    que le lecteur.

    Seules les valeurs simples sont reprises : une sous-section entiere
    remplirait le rapport de details qui ne disent rien du run.
    """
    if not isinstance(config, dict):
        return ""

    pastilles = []
    for cle, valeur in config.items():
        if str(cle).strip().lower().replace("-", "_") in _CONFIG_IGNOREES:
            continue
        if isinstance(valeur, (dict, list, tuple)):
            continue
        if valeur is None or valeur == "":
            continue
        pastilles.append(
            f'<span class="badge param"><b>{html.escape(str(cle))}</b>'
            f'{html.escape(str(valeur))}</span>'
        )

    return "".join(pastilles)


def export_html_report(entry: dict, output_text: str, dest_path: str) -> None:
    """Ecrit un rapport HTML pour l'entree d'historique donnee vers dest_path."""

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("timestamp", time.time())))
    workspace = html.escape(entry.get("workspace", ""))
    reader = html.escape(entry.get("reader", "") or "")
    duration = entry.get("duration_seconds", 0)
    exit_code = entry.get("exit_code", "")
    nodeids = entry.get("nodeids", [])
    failed_nodeids = entry.get("failed_nodeids", [])
    passed = entry.get("passed", 0)
    total = max(entry.get("total", 0), 1)
    pass_rate = round(100 * passed / total)
    success = exit_code == 0

    reader_badge = f'<span class="badge reader">{reader}</span>' if reader else ""
    exit_badge = (
        f'<span class="badge {"ok" if success else "ko"}">exit code {exit_code}</span>'
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Test report - {ts}</title>
<style>
    :root {{
        --bg: #f6f7f9; --surface: #ffffff; --border: #e5e7eb;
        --text: #111827; --muted: #6b7280; --primary: #4f46e5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
        margin: 0; padding: 32px; background: var(--bg); color: var(--text);
        line-height: 1.5;
    }}
    .wrap {{ max-width: 960px; margin: 0 auto; }}
    .header {{
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;
    }}
    h1 {{ font-size: 19px; margin: 0 0 6px; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .meta code {{ color: var(--text); }}
    .badges {{ margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .badge {{
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 600;
    }}
    .badge.reader {{ background: #eef2ff; color: var(--primary); }}
    /* Memes pastilles que le lecteur : les reglages d'un run se lisent avec
       lui, ils font partie de son identite. La cle en gras, la valeur a cote. */
    .badge.param {{ background: #eef2ff; color: var(--primary); font-weight: 500; }}
    .badge.param b {{ font-weight: 700; margin-right: 6px; }}
    .badge.ok {{ background: #f0fdf4; color: #16a34a; }}
    .badge.ko {{ background: #fef2f2; color: #dc2626; }}

    .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
    .card {{
        background: var(--surface); border: 1px solid var(--border); border-top: 3px solid;
        border-radius: 10px; padding: 16px; text-align: center;
    }}
    .card-value {{ font-size: 26px; font-weight: 700; }}
    .card-label {{ font-size: 12px; color: var(--muted); margin-top: 2px; text-transform: uppercase; letter-spacing: .04em; }}

    .bar-track {{ height: 8px; border-radius: 999px; background: #fee2e2; overflow: hidden; margin-bottom: 24px; }}
    .bar-fill {{ height: 100%; background: #22c55e; width: {pass_rate}%; }}

    details.section {{
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 10px; margin-bottom: 12px; overflow: hidden;
    }}
    details.section summary {{
        cursor: pointer; padding: 12px 16px; font-weight: 600; font-size: 14px;
        list-style: none; display: flex; align-items: center; gap: 8px;
    }}
    details.section summary::-webkit-details-marker {{ display: none; }}
    details.section summary::before {{ content: "▸"; color: var(--muted); font-size: 11px; }}
    details.section[open] summary::before {{ content: "▾"; }}
    .count {{ color: var(--muted); font-weight: 400; }}
    .nodeids, pre {{ margin: 0; padding: 12px 16px 16px; }}
    /* Une seule colonne, et une coupure autorisee n'importe ou : en deux
       colonnes, un nodeid plus large que sa colonne debordait sur la voisine
       et les chemins s'ecrivaient les uns par-dessus les autres. */
    .nodeids {{ list-style: none; }}
    .nodeids li {{
        padding: 3px 0; font-size: 12.5px; line-height: 1.45;
        font-family: ui-monospace, Consolas, monospace;
        overflow-wrap: anywhere; word-break: break-word;
        border-bottom: 1px solid var(--border);
    }}
    .nodeids li:last-child {{ border-bottom: none; }}
    .np {{ color: var(--muted); }}
    .nn {{ color: #dc2626; font-weight: 600; }}

    .empty {{ margin: 0; padding: 0 16px 16px; color: var(--muted); font-size: 13px; }}
    pre {{
        background: #0f172a; color: #e2e8f0; overflow-x: auto;
        white-space: pre-wrap; word-break: break-word; font-size: 12px;
        border-radius: 0 0 10px 10px;
    }}
</style>
</head>
<body>
<div class="wrap">
    <div class="header">
        <h1>Pytest run report</h1>
        <div class="meta">
            <code>{workspace}</code><br>
            {ts} &middot; {duration}s
        </div>
        <div class="badges">
            {reader_badge}
            {exit_badge}
            {_config_badges(entry.get("config") or {})}
        </div>
    </div>

    <div class="cards">
        {_card("Passed", entry.get("passed", 0), "passed")}
        {_card("Failed", entry.get("failed", 0), "failed")}
        {_card("Skipped", entry.get("skipped", 0), "skipped")}
        {_card("Error", entry.get("error", 0), "error")}
    </div>

    <div class="bar-track"><div class="bar-fill"></div></div>

    {_list_section("Failed tests", failed_nodeids, "No failure.", bool(failed_nodeids))}
    {_list_section("Tests run", nodeids, "No test ran.", False)}

    <details class="section">
        <summary>Console output</summary>
        <pre>{html.escape(output_text or "")}</pre>
    </details>
</div>
</body>
</html>
"""

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(doc)
