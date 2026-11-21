"""Centre d'aide : navigation, F1 contextuel, recherche, liens et export."""
import re

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from runner.ui import help_content
from runner.ui.help_content import APP_PAGES, CATEGORIES, CONTEXT_TOPICS, TOPICS, TOPICS_BY_ID
from runner.ui.help_page import HelpCenter, support_text
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


def test_every_topic_is_unique_categorized_and_links_resolve():
    ids = [topic.id for topic in TOPICS]
    assert len(ids) == len(set(ids))
    assert {topic.category for topic in TOPICS} == set(CATEGORIES)
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


def test_help_sits_just_above_settings_at_the_bottom(window):
    keys = list(window.nav_buttons)
    assert keys[-2:] == ["help", "settings"]
    layout = window.navigation.layout()
    help_index = layout.indexOf(window.nav_buttons["help"])
    assert layout.itemAt(help_index - 1).spacerItem() is not None
    assert layout.indexOf(window.nav_buttons["settings"]) == help_index + 1
    window.nav_buttons["help"].click()
    assert window.pages.currentWidget() is window.help_page
    assert window.nav_buttons["help"].isChecked()


def test_every_topic_renders_without_unreplaced_markers(window):
    centre = window.help_page.content
    for topic in TOPICS:
        assert centre.show_topic(topic.id)
        texte = centre.browser.toPlainText()
        assert topic.title in texte
        assert not re.search(r"\{[a-z_]+\}", texte), topic.id


def test_f1_opens_the_topic_of_the_current_page(window):
    window._show_page("history")
    window.act_help.trigger()
    assert window.pages.currentWidget() is window.help_page
    assert window.help_page.content.current_topic_id == "history"
    window._show_page("profiles")
    window.open_help()
    assert window.help_page.content.current_topic_id == "profiles"
    window.open_help("shortcuts")
    assert window.help_page.content.current_topic_id == "shortcuts"


def test_search_filters_topics_and_highlights_matches(window):
    centre = window.help_page.content
    centre.search.setText("queue")
    visibles = [topic_id for topic_id, item in centre._items.items() if not item.isHidden()]
    assert "run-tabs" in visibles and "glossary" in visibles
    assert "comparison" not in visibles
    centre._open_first_match()
    assert centre.current_topic_id in visibles
    assert centre.browser.extraSelections()
    centre.search.setText("zzzz-no-such-word")
    assert all(item.isHidden() for item in centre._items.values())
    assert "No topic matches" in centre.result_label.text()
    centre.search.clear()
    assert not any(item.isHidden() for item in centre._items.values())
    assert not centre.browser.extraSelections()


def test_links_navigate_topics_and_application_pages(window):
    centre = window.help_page.content
    centre.show_topic("welcome")
    centre._on_link(QUrl("topic:quick-start"))
    assert centre.current_topic_id == "quick-start"
    centre.back()
    assert centre.current_topic_id == "welcome"
    centre.forward()
    assert centre.current_topic_id == "quick-start"
    centre._on_link(QUrl("page:history"))
    assert window.pages.currentWidget() is window.history_page
    assert not centre.show_topic("does-not-exist")


def test_support_topic_and_clipboard_show_real_values(window):
    centre = window.help_page.content
    centre.show_topic("support")
    texte = centre.browser.toPlainText()
    assert __version__ in texte
    centre.copy_support_information()
    copie = QApplication.clipboard().text()
    assert copie == support_text(window)
    assert f"Pytest Runner: {__version__}" in copie
    assert "Settings:" in copie


def test_exported_guide_is_self_contained(window, tmp_path):
    centre = window.help_page.content
    cible = tmp_path / "guide.html"
    assert centre.export_guide(str(cible))
    contenu = cible.read_text(encoding="utf-8")
    for topic in TOPICS:
        assert f"name='{topic.id}'" in contenu
    assert "topic:" not in contenu and "page:" not in contenu
    assert not re.search(r"\{(version|history_dir|settings_file)\}", contenu)
    assert centre.export_guide(str(tmp_path / "missing" / "guide.html")) is False
    assert "Export failed" in centre.status_label.text()


def test_help_follows_theme_changes(window):
    centre = window.help_page.content
    centre.show_topic("results")
    window.apply_theme("light")
    assert centre.current_topic_id == "results"
    assert "Reading the results" in centre.browser.toPlainText()
    window.apply_theme("dark")


def test_help_center_works_without_a_window(qtbot):
    centre = HelpCenter()
    qtbot.addWidget(centre)
    assert centre.show_topic("support")
    centre._on_link(QUrl("page:history"))
    assert "Unknown" not in help_content.TOPICS_BY_ID["support"].title


def test_help_survives_sidebar_collapse(window):
    window._set_sidebar_collapsed(True)
    assert window.nav_buttons["help"].text() == ""
    assert window.nav_buttons["help"].toolTip() == "Help"
    window._set_sidebar_collapsed(False)
    assert window.nav_buttons["help"].text() == "Help"


def test_f1_from_help_keeps_the_topic_being_read(window):
    window.open_help("faq")
    window.open_help()
    assert window.help_page.content.current_topic_id == "faq"
