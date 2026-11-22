"""Guide d'utilisation : site HTML hors ligne d'un seul fichier.

Le bouton Help et F1 l'ouvrent dans le navigateur, sur la rubrique de la page
affichee. Un navigateur offre ce qu'un QTextBrowser ne sait pas rendre :
mise en page moderne, recherche instantanee, theme clair ou sombre,
impression propre. Le fichier ne charge rien depuis le reseau : il marche
sur un poste sans Internet et se partage par mail.

Le contenu vient de `help_content` ; ce module ne fait que la mise en page.
"""
from __future__ import annotations

import html
import json
import platform
import re
import sys
from pathlib import Path
from urllib.parse import quote

from runner.ui.help_content import CATEGORIES, CONTEXT_TOPICS, TOPICS, TOPICS_BY_ID

GUIDE_FILE = "pytest-runner-guide.html"
SUPPORT_KEYS = ("version", "python", "qt", "os", "interpreter",
                "history_dir", "data_dir", "settings_file", "guide_file")

# Une phrase par categorie, pour les cartes de la page d'accueil.
CATEGORY_BLURBS = {
    "Getting started": "Install, first run, the tour of the application and what's new.",
    "Running tests": "Workspaces, selection, readers, runs, tabs and the queue.",
    "Results and diagnosis": "Verdicts, durations, tracebacks, logs and crashes.",
    "Execution profiles": "Reusable test sequences with groups and YAML parameters.",
    "Configuration": "The YAML configuration, the test interpreter and writing tests.",
    "History and reports": "Recorded runs, comparisons and shareable HTML reports.",
    "Application": "Settings, console, themes and keyboard shortcuts.",
    "Troubleshooting": "Common problems, FAQ, glossary and support.",
}

_BALISE = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")


def plain_text(fragment: str) -> str:
    texte = html.unescape(_BALISE.sub(" ", fragment))
    return _ESPACES.sub(" ", texte).strip()


# ---------------------------------------------------------------------------
# Valeurs du poste (rubrique Support)
# ---------------------------------------------------------------------------

def support_values(window=None) -> dict[str, str]:
    """Valeurs reelles du poste, affichees dans la rubrique Support.

    Chaque valeur est protegee : une information indisponible ne doit jamais
    empecher d'ouvrir l'aide -- c'est justement quand quelque chose ne marche
    pas qu'on vient la lire.
    """
    from runner.version import __version__

    def sur(fonction, defaut="Unknown"):
        try:
            valeur = fonction()
        except Exception:
            return defaut
        return str(valeur) if valeur not in (None, "") else defaut

    def qt_version():
        import PySide6
        from PySide6.QtCore import qVersion
        return f"Qt {qVersion()} · PySide6 {PySide6.__version__}"

    def history_dir():
        from runner.domain import history
        return history.dossier()

    def data_dir():
        from PySide6.QtCore import QStandardPaths
        return QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)

    def interpreter():
        if window is None:
            return ""
        context = (window._selected_run_context()
                   if hasattr(window, "_selected_run_context") else window)
        return context._effective_interpreter()

    return {
        "version": __version__,
        "python": sur(lambda: f"{platform.python_version()} "
                              f"({platform.architecture()[0]}) · {sys.executable}"),
        "qt": sur(qt_version),
        "os": sur(platform.platform),
        "interpreter": sur(interpreter, "Not configured (default Python)"),
        "history_dir": sur(history_dir),
        "data_dir": sur(data_dir),
        "settings_file": sur(lambda: window.settings.fileName() if window is not None else ""),
        "guide_file": sur(guide_path),
    }


def support_text(values: dict[str, str]) -> str:
    """Bloc texte a coller dans un signalement."""
    lignes = (
        ("Pytest Runner", "version"), ("Application Python", "python"),
        ("Qt", "qt"), ("Operating system", "os"),
        ("Test interpreter", "interpreter"), ("History folder", "history_dir"),
        ("Application data", "data_dir"), ("Settings", "settings_file"),
        ("User guide", "guide_file"),
    )
    return "\n".join(f"{libelle}: {values.get(cle, 'Unknown')}" for libelle, cle in lignes)


# ---------------------------------------------------------------------------
# Transformation du contenu
# ---------------------------------------------------------------------------

def _slug(texte: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", plain_text(texte).casefold()).strip("-")


def _topic_body(topic, values: dict[str, str]) -> str:
    corps = topic.body
    # Valeurs du poste. `replace` et non `format` : les autres rubriques
    # peuvent contenir des accolades sans qu'elles soient interpretees.
    for cle in SUPPORT_KEYS:
        valeur = values.get(cle) or "Open Help from Pytest Runner to see this value"
        corps = corps.replace("{" + cle + "}", html.escape(valeur))
    corps = re.sub(r"href=(['\"])topic:([\w-]+)\1", r'href="#\2"', corps)
    # Une page de l'application n'est pas une URL : un repere d'interface.
    corps = re.sub(r"<a href=(['\"])page:[\w-]+\1>(.*?)</a>",
                   r'<span class="ui-ref">\2</span>', corps, flags=re.S)
    corps = corps.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>")

    vus: set[str] = set()

    def ancre(correspondance):
        titre = correspondance.group(1)
        base = f"{topic.id}--{_slug(titre)}"
        ident, n = base, 2
        while ident in vus:
            ident, n = f"{base}-{n}", n + 1
        vus.add(ident)
        return (f'<h2 id="{ident}"><a class="anchor" href="#{ident}" '
                f'aria-label="Link to this section">#</a>{titre}</h2>')

    corps = re.sub(r"<h2>(.*?)</h2>", ancre, corps, flags=re.S)
    if topic.id == "support":
        corps = (
            '<div class="actions"><button type="button" class="button primary" '
            f'data-copy="{html.escape(support_text(values), quote=True)}">'
            f'{_ICONES["copy"]}<span>Copy support information</span></button></div>' + corps)
    return corps


def _category_cards() -> str:
    cartes = []
    for categorie in CATEGORIES:
        premier = next(topic for topic in TOPICS if topic.category == categorie)
        nombre = sum(topic.category == categorie for topic in TOPICS)
        cartes.append(
            f'<a class="card" href="#{premier.id}">'
            f'<span class="card-title">{html.escape(categorie)}</span>'
            f'<span class="card-text">{html.escape(CATEGORY_BLURBS.get(categorie, ""))}</span>'
            f'<span class="card-meta">{nombre} topic{"s" if nombre > 1 else ""} →</span></a>')
    return '<div class="cards">' + "".join(cartes) + "</div>"


def _pager(position: int) -> str:
    liens = []
    if position > 0:
        precedent = TOPICS[position - 1]
        liens.append(f'<a class="pager-link prev" href="#{precedent.id}">'
                     f'<span class="pager-label">Previous</span>'
                     f'<span class="pager-title">← {html.escape(precedent.title)}</span></a>')
    else:
        liens.append('<span></span>')
    if position < len(TOPICS) - 1:
        suivant = TOPICS[position + 1]
        liens.append(f'<a class="pager-link next" href="#{suivant.id}">'
                     f'<span class="pager-label">Next</span>'
                     f'<span class="pager-title">{html.escape(suivant.title)} →</span></a>')
    return '<nav class="pager" aria-label="Previous and next topics">' + "".join(liens) + "</nav>"


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------

def build_site(values: dict[str, str] | None = None, start: str = "welcome",
               theme: str = "") -> str:
    """Le guide complet, en un seul document HTML autonome.

    `theme` ("light" ou "dark") : celui de l'application, applique tant que le
    lecteur n'a pas choisi le sien dans le guide.
    """
    from runner.version import AUTHOR, AUTHOR_COPYRIGHT, __version__

    values = values or {}
    if start not in TOPICS_BY_ID:
        start = "welcome"

    navigation = []
    for categorie in CATEGORIES:
        liens = "".join(
            f'<a class="nav-link" href="#{topic.id}" data-topic="{topic.id}">'
            f'{html.escape(topic.title)}</a>'
            for topic in TOPICS if topic.category == categorie)
        navigation.append(f'<div class="nav-group"><div class="nav-title">'
                          f'{html.escape(categorie)}</div>{liens}</div>')

    articles, index = [], []
    for position, topic in enumerate(TOPICS):
        corps = _topic_body(topic, values)
        if topic.id == "welcome":
            corps = _category_cards() + corps
        articles.append(
            f'<article class="topic" id="{topic.id}" data-topic="{topic.id}">'
            f'<div class="eyebrow">{html.escape(topic.category)}</div>'
            f'<h1>{html.escape(topic.title)}</h1>'
            f'<p class="lead">{html.escape(topic.summary)}</p>'
            f'<div class="prose">{corps}</div>{_pager(position)}</article>')
        # Le texte de la rubrique seul : ni ancres "#", ni cartes de l'accueil
        # dans les extraits de recherche.
        index.append(dict(id=topic.id, title=topic.title, category=topic.category,
                          summary=topic.summary, keywords=topic.keywords,
                          text=plain_text(re.sub(r"\{\w+\}", "", topic.body))))

    donnees = json.dumps(index, ensure_ascii=False).replace("</", "<\\/")
    titre = f"Pytest Runner {__version__} — User Guide"
    return (_GABARIT
            .replace("@@TITLE@@", html.escape(titre))
            .replace("@@VERSION@@", html.escape(__version__))
            .replace("@@AUTHOR@@", html.escape(AUTHOR))
            .replace("@@COPYRIGHT@@", html.escape(AUTHOR_COPYRIGHT))
            .replace("@@CSS@@", _CSS)
            .replace("@@NAV@@", "".join(navigation))
            .replace("@@ARTICLES@@", "".join(articles))
            .replace("@@INDEX@@", donnees)
            .replace("@@START@@", json.dumps(start))
            .replace("@@APP_THEME@@", json.dumps(theme if theme in ("light", "dark") else ""))
            .replace("@@ICON_DOWNLOAD@@", _ICONES["download"])
            .replace("@@ICON_SEARCH@@", _ICONES["search"])
            .replace("@@ICON_MENU@@", _ICONES["menu"])
            .replace("@@ICON_THEME@@", _ICONES["theme"])
            .replace("@@ICON_PRINT@@", _ICONES["print"])
            .replace("@@LOGO@@", _ICONES["logo"])
            .replace("@@FAVICON@@", html.escape(_FAVICON, quote=True))
            .replace("@@JS@@", _JS))


def guide_path() -> Path:
    from PySide6.QtCore import QStandardPaths
    racine = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return racine / "help" / GUIDE_FILE


def write_guide(window=None, topic: str = "welcome", path: Path | None = None) -> Path:
    """Ecrit le guide, ouvert sur `topic`, et rend son chemin.

    Reecrit a chaque ouverture : la rubrique de depart est dans le fichier.
    Un fragment `#rubrique` serait plus simple, mais Windows le perd en
    ouvrant un fichier local dans le navigateur par defaut.
    """
    path = path or guide_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from runner.ui import tokens as t
        theme = "dark" if t.is_dark() else "light"
    except Exception:
        theme = ""
    contenu = build_site(support_values(window), start=topic, theme=theme)
    temporaire = path.with_suffix(".tmp")
    temporaire.write_text(contenu, encoding="utf-8")
    temporaire.replace(path)
    return path


def topic_for_page(page: str) -> str:
    return CONTEXT_TOPICS.get(page, "welcome")


# ---------------------------------------------------------------------------
# Ressources du site (aucune requete reseau)
# ---------------------------------------------------------------------------

def _svg(chemin: str, taille: int = 18) -> str:
    return (f'<svg width="{taille}" height="{taille}" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{chemin}</svg>')


# Le logo de l'application (assets/pytest_runner.svg), recopie ici : le
# guide doit rester autonome, et l'executable n'embarque que le .ico.
# `test_help_page` verifie qu'il suit le fichier d'origine.
_LOGO_FORMES = (
    '<rect x="28" y="28" width="456" height="456" rx="104" fill="#082F49"/>'
    '<rect x="34" y="34" width="444" height="444" rx="98" fill="none" stroke="#15506F" stroke-width="12"/>'
    '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M132 171V341" stroke="#53657B" stroke-width="14"/>'
    '<path d="M132 174H247M132 256H270M132 338H229" stroke="#E7EEF7" stroke-width="22"/>'
    '</g>'
    '<circle cx="132" cy="174" r="22" fill="#22C55E"/>'
    '<path d="M122 174l7 7 14-16" fill="none" stroke="#F8FAFC" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="132" cy="256" r="22" fill="#EF4444"/>'
    '<path d="M123 247l18 18M141 247l-18 18" fill="none" stroke="#F8FAFC" stroke-width="8" stroke-linecap="round"/>'
    '<circle cx="132" cy="338" r="22" fill="#F59E0B"/>'
    '<path d="M121 338h22" fill="none" stroke="#F8FAFC" stroke-width="8" stroke-linecap="round"/>'
    '<path d="M292 151C292 139 305 132 315 139L401 242C408 250 408 262 401 270L315 373C305 380 292 373 292 361V151Z" fill="#38BDF8"/>'
)

_ICONES = {
    "search": _svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', 16),
    "menu": _svg('<path d="M4 6h16M4 12h16M4 18h16"/>'),
    "theme": _svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
    "download": _svg('<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>'),
    "print": _svg('<path d="M6 9V2h12v7"/><rect x="6" y="14" width="12" height="8" rx="1"/>'
                  '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'),
    "copy": _svg('<rect x="9" y="9" width="13" height="13" rx="2"/>'
                 '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>', 16),
    "logo": ('<svg class="logo" width="30" height="30" viewBox="0 0 512 512" aria-hidden="true">'
             + _LOGO_FORMES + '</svg>'),
}

# Icone d'onglet du navigateur : le meme logo, en URL de donnees.
_FAVICON = ("data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">' + _LOGO_FORMES + '</svg>'))


_GABARIT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>@@TITLE@@</title>
<link rel="icon" href="@@FAVICON@@">
<script>
(function () {
  var theme = null;
  try { theme = localStorage.getItem("pr-guide-theme"); } catch (e) {}
  if (!theme) theme = @@APP_THEME@@;
  if (!theme) theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.className = "js";
})();
</script>
<style>@@CSS@@</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <button type="button" class="icon-button menu-button" aria-label="Open the topic list">@@ICON_MENU@@</button>
  <a class="brand" href="#welcome">@@LOGO@@<span class="brand-name">Pytest Runner</span><span class="brand-sep">/</span><span class="brand-sub">User Guide</span><span class="version">v@@VERSION@@</span></a>
  <button type="button" class="search-trigger" aria-label="Search the guide">@@ICON_SEARCH@@<span>Search the guide…</span><span class="keys"><kbd>Ctrl</kbd><kbd>K</kbd></span></button>
  <div class="top-actions">
    <button type="button" class="icon-button theme-button" aria-label="Switch between light and dark theme" title="Light / dark theme">@@ICON_THEME@@</button>
    <button type="button" class="icon-button download-button" aria-label="Download this guide as one HTML file, to share it" title="Download this guide (one HTML file, to share)">@@ICON_DOWNLOAD@@</button>
    <button type="button" class="icon-button print-button" aria-label="Print or save the whole guide as PDF" title="Print or save as PDF">@@ICON_PRINT@@</button>
  </div>
</header>
<div class="layout">
  <nav class="sidebar" aria-label="Topics">@@NAV@@</nav>
  <main id="main" class="content" tabindex="-1">@@ARTICLES@@
    <footer class="footer"><span>Pytest Runner v@@VERSION@@ · Created by <b>@@AUTHOR@@</b></span><span>@@COPYRIGHT@@</span><span>This guide works offline and can be shared as a single file.</span></footer>
  </main>
  <aside class="toc" aria-label="On this page"><div class="toc-title">On this page</div><ul class="toc-list"></ul></aside>
</div>
<div class="scrim" hidden></div>
<div class="search-dialog" role="dialog" aria-modal="true" aria-label="Search the guide" hidden>
  <div class="search-panel">
    <div class="search-field">@@ICON_SEARCH@@<input type="search" placeholder="Search topics, buttons, shortcuts…" autocomplete="off" spellcheck="false" aria-label="Search the guide"><kbd>Esc</kbd></div>
    <ul class="search-results" role="listbox"></ul>
    <div class="search-footer"><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><kbd>Enter</kbd> to open</span><span><kbd>Esc</kbd> to close</span></div>
  </div>
</div>
<div class="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="search-index">@@INDEX@@</script>
<script>var START_TOPIC = @@START@@;</script>
<script>@@JS@@</script>
</body>
</html>
"""


_CSS = r"""
:root {
  --bg: #ffffff; --bg-subtle: #f6f8fa; --bg-raised: #ffffff; --bg-hover: #eef1f5;
  --border: #e3e6ea; --border-strong: #cfd5dc;
  --text: #1b2230; --text-muted: #5b6675; --text-faint: #8a94a3;
  --accent: #1f6feb; --accent-hover: #1859c4; --accent-soft: #e8f1fe; --accent-text: #1859c4;
  --note: #9a6700; --note-soft: #fff8e6; --note-border: #f2d48a;
  --tip-border: #b7d3fb;
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.08);
  --radius: 10px; --topbar: 60px; --sidebar: 272px; --toc: 220px;
  --font: "Segoe UI Variable Text", "Segoe UI", Inter, system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: "Cascadia Mono", "JetBrains Mono", Consolas, "SFMono-Regular", Menlo, monospace;
  color-scheme: light;
}
[data-theme="dark"] {
  --bg: #0f1218; --bg-subtle: #161b23; --bg-raised: #1b212b; --bg-hover: #222a35;
  --border: #29313d; --border-strong: #3a4452;
  --text: #e6eaf0; --text-muted: #9aa4b2; --text-faint: #6b7584;
  --accent: #5b9bff; --accent-hover: #7aaeff; --accent-soft: #17253d; --accent-text: #8cb8ff;
  --note: #e3b341; --note-soft: #2a2312; --note-border: #5c4813;
  --tip-border: #22406b;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.45);
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { scroll-padding-top: calc(var(--topbar) + 16px); -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15.5px/1.65 var(--font);
  -webkit-font-smoothing: antialiased; }
a { color: var(--accent-text); text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 3px; }
button { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 6px; }
.skip { position: absolute; left: -999px; top: 8px; background: var(--accent); color: #fff; padding: 8px 12px; border-radius: 8px; z-index: 100; }
.skip:focus { left: 8px; }

/* Barre superieure */
.topbar { position: sticky; top: 0; z-index: 30; height: var(--topbar); display: flex; align-items: center; gap: 16px;
  padding: 0 20px; background: var(--bg); background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: saturate(180%) blur(10px);
  border-bottom: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 10px; color: var(--text); font-weight: 650; white-space: nowrap; }
.brand .logo { flex: none; border-radius: 7px; }
.brand:hover { text-decoration: none; }
.brand-name { font-size: 16px; letter-spacing: -.01em; }
.brand-sep { color: var(--text-faint); font-weight: 400; }
.brand-sub { color: var(--text-muted); font-weight: 500; }
.version { font-size: 12px; font-weight: 600; color: var(--accent-text); background: var(--accent-soft);
  padding: 2px 8px; border-radius: 999px; }
.search-trigger { margin-left: auto; display: flex; align-items: center; gap: 10px; width: min(380px, 40vw); height: 38px;
  padding: 0 10px 0 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg-subtle);
  color: var(--text-muted); cursor: pointer; transition: border-color .15s, background .15s; }
.search-trigger:hover { border-color: var(--border-strong); background: var(--bg-hover); }
.search-trigger > span:first-of-type { flex: 1; text-align: left; }
.top-actions { display: flex; gap: 4px; }
.icon-button { display: inline-grid; place-items: center; width: 38px; height: 38px; border: 0; border-radius: 9px;
  background: transparent; color: var(--text-muted); cursor: pointer; }
.icon-button:hover { background: var(--bg-hover); color: var(--text); }
.menu-button { display: none; }
kbd { display: inline-block; min-width: 1.7em; padding: 1px 6px; font: 600 .76em/1.5 var(--mono); text-align: center;
  color: var(--text); background: var(--bg-raised); border: 1px solid var(--border-strong); border-bottom-width: 2px;
  border-radius: 6px; }
.keys { display: inline-flex; gap: 3px; vertical-align: baseline; white-space: nowrap; }

/* Mise en page */
.layout { display: grid; grid-template-columns: var(--sidebar) minmax(0, 1fr) var(--toc); max-width: 1440px; margin: 0 auto; }
.sidebar { position: sticky; top: var(--topbar); height: calc(100vh - var(--topbar)); overflow-y: auto;
  padding: 24px 12px 40px 20px; border-right: 1px solid var(--border); }
.nav-group + .nav-group { margin-top: 20px; }
.nav-title { font-size: 11.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--text-faint);
  padding: 0 10px 6px; }
.nav-link { display: block; padding: 6px 10px; border-radius: 7px; color: var(--text-muted); font-size: 14.5px; line-height: 1.4; }
.nav-link:hover { background: var(--bg-hover); color: var(--text); text-decoration: none; }
.nav-link.active { background: var(--accent-soft); color: var(--accent-text); font-weight: 600; }
.content { min-width: 0; padding: 40px 56px 64px; outline: none; }
.topic { max-width: 780px; margin: 0 auto; }
.js .topic { display: none; }
.js .topic.active { display: block; animation: fade .18s ease-out; }
@keyframes fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.topic + .topic { margin-top: 64px; }
.js .topic + .topic { margin-top: 0; }
.toc { position: sticky; top: var(--topbar); height: calc(100vh - var(--topbar)); overflow-y: auto; padding: 40px 20px 40px 8px; }
.toc-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--text-faint); margin-bottom: 10px; }
.toc-list { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--border); }
.toc-list a { display: block; padding: 4px 0 4px 14px; margin-left: -1px; border-left: 2px solid transparent; color: var(--text-muted); font-size: 13.5px; line-height: 1.4; }
.toc-list a:hover { color: var(--text); text-decoration: none; }
.toc-list a.active { color: var(--accent-text); border-left-color: var(--accent); font-weight: 600; }
.toc.empty { visibility: hidden; }

/* Rubrique */
.eyebrow { font-size: 13px; font-weight: 650; color: var(--accent-text); margin-bottom: 6px; }
h1 { font-size: 2.15rem; line-height: 1.2; letter-spacing: -.025em; font-weight: 750; margin: 0 0 10px; }
.lead { font-size: 1.12rem; color: var(--text-muted); margin: 0 0 32px; }
.prose h2 { position: relative; font-size: 1.35rem; letter-spacing: -.015em; font-weight: 700; margin: 44px 0 12px;
  padding-top: 8px; }
.prose h3 { font-size: 1.08rem; font-weight: 650; margin: 28px 0 8px; }
.prose p, .prose li { color: var(--text); }
.prose ul, .prose ol { padding-left: 1.4em; }
.prose li + li { margin-top: 6px; }
.prose b, .prose strong { font-weight: 650; }
.anchor { position: absolute; left: -1.1em; color: var(--text-faint); opacity: 0; font-weight: 500; }
.prose h2:hover .anchor { opacity: 1; text-decoration: none; }
code { font: .86em var(--mono); padding: .15em .4em; border-radius: 6px; background: var(--bg-subtle); border: 1px solid var(--border); }
pre { position: relative; font: 13.5px/1.6 var(--mono); padding: 16px 18px; border-radius: var(--radius); background: var(--bg-subtle);
  border: 1px solid var(--border); overflow-x: auto; }
pre .copy-code { position: absolute; top: 8px; right: 8px; }
.ui-ref { display: inline-flex; align-items: center; padding: 0 8px; font-size: .9em; font-weight: 600; color: var(--text);
  background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 6px; white-space: nowrap; line-height: 1.7; }

/* Etapes */
ol.steps { list-style: none; counter-reset: step; padding: 0; margin: 20px 0; }
ol.steps > li { counter-increment: step; position: relative; padding: 0 0 22px 52px; margin: 0; }
ol.steps > li::before { content: counter(step); position: absolute; left: 0; top: -1px; width: 32px; height: 32px;
  display: grid; place-items: center; border-radius: 50%; font-weight: 700; font-size: 14px; color: var(--accent-text);
  background: var(--accent-soft); border: 1px solid var(--tip-border); }
ol.steps > li::after { content: ""; position: absolute; left: 15.5px; top: 36px; bottom: 4px; width: 1px; background: var(--border); }
ol.steps > li:last-child::after { display: none; }

/* Encadres */
.callout { margin: 24px 0; padding: 14px 18px 14px 18px; border-radius: var(--radius); border: 1px solid var(--tip-border);
  background: var(--accent-soft); }
.callout p { margin: 0; }
.callout-title { font-size: 12.5px; font-weight: 750; letter-spacing: .05em; text-transform: uppercase; color: var(--accent-text); margin-bottom: 4px; }
.callout.note { border-color: var(--note-border); background: var(--note-soft); }
.callout.note .callout-title { color: var(--note); }

/* Tableaux */
.table-wrap { margin: 18px 0; overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }
table { width: 100%; border-collapse: collapse; font-size: 14.5px; }
th { text-align: left; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--text-muted);
  background: var(--bg-subtle); }
th, td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
tbody tr:hover td, tr:hover td { background: var(--bg-subtle); background: color-mix(in srgb, var(--bg-hover) 50%, transparent); }

/* Cartes de l'accueil */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin: 8px 0 36px; }
.card { display: flex; flex-direction: column; gap: 6px; padding: 18px; border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg-raised); color: var(--text); transition: border-color .15s, box-shadow .15s, transform .15s; }
.card:hover { border-color: var(--accent); box-shadow: var(--shadow); transform: translateY(-1px); text-decoration: none; }
.card-title { font-weight: 650; }
.card-text { font-size: 14px; color: var(--text-muted); line-height: 1.5; flex: 1; }
.card-meta { font-size: 13px; font-weight: 600; color: var(--accent-text); }

/* Boutons */
.actions { margin: -12px 0 24px; }
.button { display: inline-flex; align-items: center; gap: 8px; height: 38px; padding: 0 14px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--border-strong); background: var(--bg-raised); font-weight: 600; font-size: 14px; }
.button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.button.primary:hover { background: var(--accent-hover); }
.button.small { height: 28px; padding: 0 8px; font-size: 12px; }

/* Precedent / suivant */
.pager { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 56px; padding-top: 28px; border-top: 1px solid var(--border); }
.pager-link { display: flex; flex-direction: column; gap: 2px; padding: 14px 18px; border: 1px solid var(--border); border-radius: 12px; color: var(--text); }
.pager-link:hover { border-color: var(--accent); text-decoration: none; }
.pager-link.next { text-align: right; grid-column: 2; }
.pager-label { font-size: 12.5px; color: var(--text-muted); }
.pager-title { font-weight: 650; color: var(--accent-text); }
.footer { max-width: 780px; margin: 48px auto 0; display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; color: var(--text-faint); }
.footer b { color: var(--text-muted); font-weight: 600; }

/* Recherche */
.scrim { position: fixed; inset: 0; z-index: 40; background: rgba(10,14,20,.45); backdrop-filter: blur(2px); }
.search-dialog { position: fixed; inset: 0; z-index: 50; display: flex; justify-content: center; align-items: flex-start; padding: 12vh 16px 16px; }
.search-dialog[hidden], .scrim[hidden] { display: none; }
.search-panel { width: min(640px, 100%); max-height: 70vh; display: flex; flex-direction: column; background: var(--bg-raised);
  border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); overflow: hidden; }
.search-field { display: flex; align-items: center; gap: 10px; padding: 0 16px; height: 56px; border-bottom: 1px solid var(--border); color: var(--text-muted); }
.search-field input { flex: 1; height: 100%; border: 0; outline: 0; background: transparent; color: var(--text); font: inherit; font-size: 16px; }
.search-results { list-style: none; margin: 0; padding: 8px; overflow-y: auto; }
.search-results li a { display: block; padding: 10px 12px; border-radius: 9px; color: var(--text); }
.search-results li a:hover { text-decoration: none; }
.search-results li.selected a, .search-results li a:hover { background: var(--accent-soft); }
.result-category { font-size: 12px; font-weight: 600; color: var(--text-faint); }
.result-title { display: block; font-weight: 650; }
.result-snippet { display: block; font-size: 13.5px; color: var(--text-muted); line-height: 1.5; margin-top: 2px; }
mark { background: #ffe58f; background: color-mix(in srgb, #ffd33d 55%, transparent); color: inherit; border-radius: 3px; padding: 0 1px; }
.search-note { padding: 6px 12px 8px; font-size: 13px; color: var(--text-muted); }
.search-empty { padding: 28px 16px; text-align: center; color: var(--text-muted); }
.search-footer { display: flex; gap: 18px; padding: 10px 16px; border-top: 1px solid var(--border); font-size: 12.5px; color: var(--text-faint); }
.toast { position: fixed; bottom: 24px; left: 50%; transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
  background: var(--text); color: var(--bg); padding: 10px 16px; border-radius: 10px; font-size: 14px; font-weight: 600;
  transition: opacity .2s, transform .2s; z-index: 60; }
.toast.show { opacity: 1; transform: translate(-50%, 0); }

/* Ecrans plus petits */
@media (max-width: 1180px) {
  .layout { grid-template-columns: var(--sidebar) minmax(0, 1fr); }
  .toc { display: none; }
}
@media (max-width: 860px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .menu-button { display: inline-grid; }
  .sidebar { position: fixed; z-index: 45; left: 0; top: var(--topbar); width: min(300px, 86vw); background: var(--bg);
    transform: translateX(-100%); transition: transform .2s ease; box-shadow: var(--shadow); }
  body.nav-open .sidebar { transform: none; }
  .content { padding: 28px 18px 48px; }
  .brand-sep, .brand-sub, .search-trigger > span, .search-trigger .keys, .print-button, .download-button { display: none; }
  .search-trigger { width: 38px; padding: 0; justify-content: center; }
  h1 { font-size: 1.75rem; }
  .pager { grid-template-columns: 1fr; }
  .pager-link.next { grid-column: 1; }
}

/* Impression : tout le guide, sans l'interface du site */
@media print {
  :root, [data-theme="dark"] { --bg: #fff; --bg-subtle: #f6f8fa; --text: #000; --text-muted: #333; --border: #ccc; --accent-soft: #eef4ff; --note-soft: #fff8e6; }
  .topbar, .sidebar, .toc, .pager, .search-dialog, .scrim, .toast, .actions, .anchor, .skip { display: none !important; }
  .layout { display: block; }
  .content { padding: 0; }
  .js .topic { display: block !important; animation: none; }
  .topic { max-width: none; page-break-before: always; }
  .topic:first-child { page-break-before: auto; }
  a { color: #000; }
  .card { break-inside: avoid; }
  body { font-size: 11pt; }
}
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""


_JS = r"""
(function () {
  "use strict";
  var root = document.documentElement;
  // Copie du document AVANT que le script ne le modifie (rubrique active,
  // sommaire, boutons de copie) : c'est elle qui est telechargee.
  var ORIGINAL = "<!doctype html>\n" + root.outerHTML
    .replace(/^<html([^>]*?) data-theme="[^"]*"/, "<html$1")
    .replace(/^<html([^>]*?) class="js"/, "<html$1");
  var topics = Array.prototype.slice.call(document.querySelectorAll(".topic"));
  var navLinks = Array.prototype.slice.call(document.querySelectorAll(".nav-link"));
  var index = JSON.parse(document.getElementById("search-index").textContent);
  var tocList = document.querySelector(".toc-list");
  var toc = document.querySelector(".toc");
  var current = null;
  var observer = null;

  function byId(id) { return document.getElementById(id); }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }

  /* Theme ------------------------------------------------------------ */
  document.querySelector(".theme-button").addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    store("pr-guide-theme", next);
  });
  document.querySelector(".print-button").addEventListener("click", function () { window.print(); });
  document.querySelector(".download-button").addEventListener("click", function () {
    var blob = new Blob([ORIGINAL], { type: "text/html;charset=utf-8" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "Pytest Runner User Guide.html";
    document.body.appendChild(link);
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
  });

  /* Navigation entre rubriques ----------------------------------------- */
  function topicOf(hash) {
    var id = decodeURIComponent((hash || "").replace(/^#/, ""));
    if (!id) return null;
    var topicId = id.split("--")[0];
    return byId(topicId) && byId(topicId).classList.contains("topic") ? { topic: topicId, anchor: id } : null;
  }

  function buildToc(article) {
    if (observer) observer.disconnect();
    tocList.innerHTML = "";
    var headings = article.querySelectorAll(".prose h2");
    toc.classList.toggle("empty", headings.length < 2);
    var links = {};
    Array.prototype.forEach.call(headings, function (h) {
      var a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent.replace(/^#/, "");
      var li = document.createElement("li");
      li.appendChild(a);
      tocList.appendChild(li);
      links[h.id] = a;
    });
    if (!("IntersectionObserver" in window) || !headings.length) return;
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          Object.keys(links).forEach(function (k) { links[k].classList.remove("active"); });
          links[entry.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    Array.prototype.forEach.call(headings, function (h) { observer.observe(h); });
  }

  function show(target, scroll) {
    var article = byId(target.topic);
    if (current !== article) {
      topics.forEach(function (t) { t.classList.toggle("active", t === article); });
      navLinks.forEach(function (link) {
        var active = link.getAttribute("data-topic") === target.topic;
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
      });
      current = article;
      buildToc(article);
      var title = article.querySelector("h1").textContent;
      document.title = title + " · Pytest Runner User Guide";
      var activeLink = document.querySelector(".nav-link.active");
      if (activeLink && activeLink.scrollIntoView) activeLink.scrollIntoView({ block: "nearest" });
    }
    document.body.classList.remove("nav-open");
    if (scroll === false) return;
    if (target.anchor !== target.topic && byId(target.anchor)) byId(target.anchor).scrollIntoView();
    else window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", function () {
    var target = topicOf(location.hash);
    if (target) show(target);
  });
  var initial = topicOf(location.hash) || { topic: START_TOPIC, anchor: START_TOPIC };
  show(initial);
  if (!location.hash && history.replaceState) history.replaceState(null, "", "#" + initial.topic);

  /* Menu mobile -------------------------------------------------------- */
  document.querySelector(".menu-button").addEventListener("click", function () {
    document.body.classList.toggle("nav-open");
  });

  /* Copie --------------------------------------------------------------- */
  var toast = document.querySelector(".toast");
  function notify(text) {
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(notify.timer);
    notify.timer = setTimeout(function () { toast.classList.remove("show"); }, 1800);
  }
  function copy(text) {
    function fallback() {
      var area = document.createElement("textarea");
      area.value = text; document.body.appendChild(area); area.select();
      try { document.execCommand("copy"); notify("Copied to the clipboard"); } catch (e) { notify("Copy failed"); }
      document.body.removeChild(area);
    }
    if (navigator.clipboard && window.isSecureContext !== false) {
      navigator.clipboard.writeText(text).then(function () { notify("Copied to the clipboard"); }, fallback);
    } else { fallback(); }
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (button) copy(button.getAttribute("data-copy"));
  });
  Array.prototype.forEach.call(document.querySelectorAll(".prose pre"), function (pre) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "button small copy-code";
    button.textContent = "Copy";
    button.setAttribute("data-copy", pre.textContent);
    pre.appendChild(button);
  });

  /* Recherche ----------------------------------------------------------- */
  var dialog = document.querySelector(".search-dialog");
  var scrim = document.querySelector(".scrim");
  var input = dialog.querySelector("input");
  var results = dialog.querySelector(".search-results");
  var selected = 0;
  var lastFocus = null;

  function escapeHtml(text) {
    return text.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function highlight(text, words) {
    var html = escapeHtml(text);
    words.forEach(function (w) {
      if (!w) return;
      var pattern = new RegExp("(" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      html = html.replace(pattern, "<mark>$1</mark>");
    });
    return html;
  }
  function snippet(text, word) {
    var at = text.toLowerCase().indexOf(word);
    if (at < 0) return text.slice(0, 140) + (text.length > 140 ? "…" : "");
    var start = Math.max(0, at - 60);
    return (start ? "…" : "") + text.slice(start, at + 100) + (at + 100 < text.length ? "…" : "");
  }
  /* Fautes de frappe : un mot absent du guide est remplace par le mot le
     plus proche du vocabulaire (distance d'edition 1, ou 2 au-dela de six
     lettres). "redaer" trouve "reader". */
  var vocabulary = null;
  function distance(a, b, limit) {
    // Deux lettres inversees ("redaer") ne comptent que pour une faute.
    if (Math.abs(a.length - b.length) > limit) return limit + 1;
    var before = null, previous = [], current, i, j;
    for (j = 0; j <= b.length; j++) previous[j] = j;
    for (i = 1; i <= a.length; i++) {
      current = [i];
      var best = i;
      for (j = 1; j <= b.length; j++) {
        current[j] = Math.min(previous[j] + 1, current[j - 1] + 1,
          previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (before && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
          current[j] = Math.min(current[j], before[j - 2] + 1);
        if (current[j] < best) best = current[j];
      }
      if (best > limit) return limit + 1;
      before = previous;
      previous = current;
    }
    return previous[b.length];
  }
  function correct(word) {
    if (!vocabulary) {
      var seen = {};
      index.forEach(function (entry) {
        (entry.title + " " + entry.keywords + " " + entry.text).toLowerCase()
          .split(/[^a-z0-9_+.-]+/).forEach(function (w) { if (w.length > 2) seen[w] = true; });
      });
      vocabulary = Object.keys(seen);
    }
    var limit = word.length > 6 ? 2 : 1, best = null, bestDistance = limit + 1;
    vocabulary.forEach(function (candidate) {
      var d = distance(word, candidate, limit);
      if (d < bestDistance) { best = candidate; bestDistance = d; }
    });
    return best;
  }
  function matching(words) {
    return index.map(function (entry) {
      var title = entry.title.toLowerCase();
      var hay = (entry.title + " " + entry.summary + " " + entry.keywords + " " + entry.text).toLowerCase();
      if (!words.every(function (w) { return hay.indexOf(w) >= 0; })) return null;
      var score = words.every(function (w) { return title.indexOf(w) >= 0; }) ? 0 :
                  words.every(function (w) { return entry.keywords.toLowerCase().indexOf(w) >= 0; }) ? 1 : 2;
      return { entry: entry, score: score };
    }).filter(Boolean).sort(function (a, b) { return a.score - b.score; })
      .map(function (item) { return item.entry; });
  }
  function search(query) {
    var words = query.toLowerCase().split(/\s+/).filter(Boolean);
    var found = index;
    var corrected = "";
    if (words.length) {
      found = matching(words);
      if (!found.length) {
        var fixed = words.map(function (w) { return correct(w) || w; });
        if (fixed.join(" ") !== words.join(" ")) {
          found = matching(fixed);
          if (found.length) { words = fixed; corrected = fixed.join(" "); }
        }
      }
    }
    selected = 0;
    if (!found.length) {
      results.innerHTML = '<li class="search-empty">No topic matches “' + escapeHtml(query) +
        '”. Try another word, or open <a href="#troubleshooting">Troubleshooting</a>.</li>';
      return;
    }
    var note = corrected ? '<li class="search-note">Showing results for <b>' + escapeHtml(corrected) + '</b></li>' : "";
    results.innerHTML = note + found.slice(0, 12).map(function (entry, i) {
      var text = words.length ? snippet(entry.text, words[0]) : entry.summary;
      return '<li role="option"' + (i === 0 ? ' class="selected"' : "") + '><a href="#' + entry.id + '">' +
        '<span class="result-category">' + escapeHtml(entry.category) + '</span>' +
        '<span class="result-title">' + highlight(entry.title, words) + '</span>' +
        '<span class="result-snippet">' + highlight(text, words) + '</span></a></li>';
    }).join("");
  }
  function openSearch() {
    lastFocus = document.activeElement;
    dialog.hidden = false; scrim.hidden = false;
    input.value = ""; search("");
    input.focus();
  }
  function closeSearch() {
    dialog.hidden = true; scrim.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function move(step) {
    var items = results.querySelectorAll("li[role=option]");
    if (!items.length) return;
    items[selected].classList.remove("selected");
    selected = (selected + step + items.length) % items.length;
    items[selected].classList.add("selected");
    items[selected].scrollIntoView({ block: "nearest" });
  }
  document.querySelector(".search-trigger").addEventListener("click", openSearch);
  scrim.addEventListener("click", function () { closeSearch(); document.body.classList.remove("nav-open"); });
  input.addEventListener("input", function () { search(input.value); });
  results.addEventListener("click", function (event) { if (event.target.closest("a")) closeSearch(); });
  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
    else if (event.key === "Enter") {
      var link = results.querySelector("li.selected a");
      if (link) { location.hash = link.getAttribute("href"); closeSearch(); }
    }
  });
  document.addEventListener("keydown", function (event) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openSearch(); }
    else if (event.key === "/" && !typing && dialog.hidden) { event.preventDefault(); openSearch(); }
    else if (event.key === "Escape") {
      if (!dialog.hidden) closeSearch();
      document.body.classList.remove("nav-open");
    }
  });
})();
"""
