"""Guide d'utilisation : contenu, site hors ligne, bouton Help et F1."""
import json
import re

import pytest
from PySide6.QtCore import QUrl

from runner.ui import help_site
from runner.ui.help_content import APP_PAGES, CATEGORIES, CONTEXT_TOPICS, TOPICS, TOPICS_BY_ID
from runner.ui.main_window import MainWindow
from runner.version import __version__

LIEN = re.compile(r"href=['\"](topic|page):([\w-]+)['\"]")


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1440, 900)
    w.show()
    yield w
    w.close()


@pytest.fixture
def opened(monkeypatch):
    """Les URL que l'application demande d'ouvrir, sans lancer de navigateur."""
    urls = []
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl",
                        lambda url: urls.append(url) or True)
    return urls


def start_topic(path) -> str:
    texte = path.read_text(encoding="utf-8")
    return json.loads(re.search(r"var START_TOPIC = (\"[\w-]+\");", texte).group(1))


def test_every_topic_is_unique_categorized_and_links_resolve():
    ids = [topic.id for topic in TOPICS]
    assert len(ids) == len(set(ids))
    assert {topic.category for topic in TOPICS} == set(CATEGORIES)
    assert set(help_site.CATEGORY_BLURBS) == set(CATEGORIES)
    for topic in TOPICS:
        assert topic.title and topic.summary and topic.body.strip()
        for schema, cible in LIEN.findall(topic.body):
            if schema == "topic":
                assert cible in TOPICS_BY_ID, (topic.id, cible)
            else:
                assert cible in APP_PAGES, (topic.id, cible)
    assert set(CONTEXT_TOPICS.values()) <= set(TOPICS_BY_ID)


def test_every_navigation_page_has_a_contextual_topic(window):
    assert set(window.nav_buttons) <= set(CONTEXT_TOPICS)


def test_site_is_self_contained_and_contains_every_topic():
    site = help_site.build_site({"version": __version__}, start="history")
    assert site.startswith("<!doctype html>")
    # Hors ligne : aucune ressource chargee depuis le reseau.
    assert not re.search(r"(src|href)=['\"]https?://", site)
    assert "@import" not in site
    for topic in TOPICS:
        assert f'id="{topic.id}"' in site
        assert f'href="#{topic.id}"' in site
    # Plus aucun lien interne brut ni marqueur non remplace.
    assert not LIEN.search(site)
    assert not re.search(r"\{(version|history_dir|settings_file|interpreter)\}", site)
    assert 'var START_TOPIC = "history";' in site
    index = json.loads(re.search(
        r'<script type="application/json" id="search-index">(.*?)</script>', site, re.S).group(1))
    assert [entry["id"] for entry in index] == [topic.id for topic in TOPICS]
    assert all(entry["text"] and not entry["text"].startswith("#") for entry in index)


def test_unknown_start_topic_falls_back_to_welcome():
    assert 'var START_TOPIC = "welcome";' in help_site.build_site({}, start="nope")


def test_section_anchors_are_unique():
    site = help_site.build_site({})
    ancres = re.findall(r'<h2 id="([\w-]+)"', site)
    assert ancres and len(ancres) == len(set(ancres))


def test_support_topic_shows_the_real_values_and_a_copy_button(window):
    valeurs = help_site.support_values(window)
    assert valeurs["version"] == __version__
    assert valeurs["settings_file"].endswith(".ini")
    site = help_site.build_site(valeurs, start="support")
    support = re.search(r'<article class="topic" id="support".*?</article>', site, re.S).group(0)
    assert __version__ in support
    assert "data-copy=" in support and "Pytest Runner: " + __version__ in support


def test_help_sits_just_above_settings_and_opens_the_guide(window, opened):
    keys = list(window.nav_buttons)
    assert keys[-2:] == ["help", "settings"]
    layout = window.navigation.layout()
    help_index = layout.indexOf(window.nav_buttons["help"])
    assert layout.itemAt(help_index - 1).spacerItem() is not None
    assert layout.indexOf(window.nav_buttons["settings"]) == help_index + 1
    assert not window.nav_buttons["help"].isCheckable()
    page = window.pages.currentWidget()
    window.nav_buttons["help"].click()
    assert window.pages.currentWidget() is page
    assert len(opened) == 1 and opened[0].isLocalFile()
    chemin = help_site.guide_path()
    assert opened[0] == QUrl.fromLocalFile(str(chemin))
    assert start_topic(chemin) == "run-tests"


def test_f1_opens_the_topic_of_the_current_page(window, opened):
    window._show_page("history")
    window.act_help.trigger()
    assert start_topic(help_site.guide_path()) == "history"
    window._show_page("profiles")
    window.open_help()
    assert start_topic(help_site.guide_path()) == "profiles"
    window.open_help("shortcuts")
    assert start_topic(help_site.guide_path()) == "shortcuts"
    assert len(opened) == 3


def test_a_missing_browser_is_reported_with_the_file_path(window, monkeypatch):
    erreurs = []
    monkeypatch.setattr("runner.ui.main_window.QDesktopServices.openUrl", lambda url: False)
    monkeypatch.setattr("runner.ui.main_window.ErrorDialog.show_error",
                        lambda *args, **kwargs: erreurs.append(args))
    assert window.open_help() is False
    assert erreurs and str(help_site.guide_path()) in erreurs[0]


def test_help_survives_sidebar_collapse(window):
    window._set_sidebar_collapsed(True)
    assert window.nav_buttons["help"].text() == ""
    assert window.nav_buttons["help"].toolTip()
    window._set_sidebar_collapsed(False)
    assert window.nav_buttons["help"].text() == "Help"


# Mises en valeur du texte qui ne sont pas des libelles de l'interface. Un
# nouveau mot en gras qui n'est pas un libelle s'ajoute ici ; un libelle
# absent du code veut dire que l'interface a change et que le guide est faux.
EMPHASE = {
    "A conftest.py fails, or no file is valid", "A file cannot be imported",
    "Check the test interpreter", "Choose the readers", "Select the tests",
    "Every tab works on its own copy", "Slow Python", "Stability", "Display",
    "User guide", "Not run", "History", "X / Y", "amber dot", "warning triangle",
    "collects, selects, runs and analyzes pytest test suites", "colour-blind-friendly",
    "ordered sequence of tests", "profile → parent groups → subgroup → test",
    "protects", "single file", "two independent Python installations", "whole folder",
    # Libelles construits avec des nombres (domain/collection_state, campaign_coverage)
    "2 files not collected", "files not collected",
    "Campaign incomplete · 3/5 tests executed",
}


def test_every_bold_ui_label_still_exists_in_the_interface():
    import glob
    import html as html_mod
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    sources = [p for p in glob.glob(str(racine / "ui" / "*.py")) if not p.endswith("help_content.py")]
    code = " ".join(Path(p).read_text(encoding="utf-8") for p in sources)
    code = re.sub(r"\s+", " ", code).casefold().replace("...", "…")
    absents = {}
    for topic in TOPICS:
        for brut in re.findall(r"<b>(.*?)</b>", topic.body, re.S):
            texte = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", "", brut)))
            texte = texte.strip().rstrip(".").strip()
            if len(texte) < 3 or texte in EMPHASE or texte.casefold() in code:
                continue
            absents.setdefault(texte, topic.id)
    assert not absents, f"Libelles du guide introuvables dans l'interface : {absents}"


def test_guide_follows_the_application_theme_and_can_be_downloaded(window, opened):
    from runner.ui import tokens as t

    window.apply_theme("light")
    chemin = help_site.write_guide(window, "welcome")
    texte = chemin.read_text(encoding="utf-8")
    assert 'if (!theme) theme = "light";' in texte
    assert 'class="icon-button download-button"' in texte
    window.apply_theme("dark")
    assert 'if (!theme) theme = "dark";' in help_site.write_guide(window).read_text(encoding="utf-8")
    assert t.is_dark()


def test_support_lists_the_guide_file_and_old_browsers_keep_an_opaque_top_bar(window):
    valeurs = help_site.support_values(window)
    assert valeurs["guide_file"] == str(help_site.guide_path())
    assert "User guide: " in help_site.support_text(valeurs)
    site = help_site.build_site(valeurs, start="support")
    assert valeurs["guide_file"] in site
    # Sans color-mix() (Chrome/Edge < 111), la barre du haut garde un fond.
    assert "background: var(--bg); background: color-mix(" in site


def test_guide_shows_the_application_logo():
    """Le logo du guide suit assets/pytest_runner.svg, forme par forme."""
    from pathlib import Path

    svg = (Path(__file__).resolve().parents[2] / "assets" / "pytest_runner.svg").read_text(encoding="utf-8")
    formes = re.findall(r"<(?:rect|path|circle)\b[^>]*/>", svg)
    assert formes
    site = help_site.build_site({})
    marque = re.search(r'<a class="brand".*?</a>', site, re.S).group(0)
    for forme in formes:
        assert forme in marque, forme
    assert '<link rel="icon" href="data:image/svg+xml,' in site
