"""Onglets Console / Source / Log affiches a droite de l'arbre.

Cliquer un test doit montrer son code source, positionne sur la definition du
test, et son fichier de log. Les cas degrades (dossier, fichier absent, log
jamais produit) doivent afficher une explication plutot que rester vides.
"""

import json

import pytest

from gui_qt.detail_panel import DetailPanel, function_name_from_nodeid, read_text_file


@pytest.fixture
def panel(qtbot):
    widget = DetailPanel()
    qtbot.addWidget(widget)
    return widget


# ---------------------------------------------------------------- utilitaires

def test_function_name_is_extracted_without_the_parameter():
    assert function_name_from_nodeid("a/test_x.py::test_f[cas-1]") == "test_f"


def test_function_name_is_extracted_through_a_class():
    assert function_name_from_nodeid("a/test_x.py::TestC::test_f") == "test_f"


def test_function_name_is_none_without_a_node_separator():
    assert function_name_from_nodeid("a/test_x.py") is None


def test_reading_a_missing_file_reports_the_error(tmp_path):
    contenu, avertissement = read_text_file(tmp_path / "absent.txt")
    assert contenu == ""
    assert "impossible" in avertissement.lower()


def test_reading_undecodable_bytes_does_not_crash(tmp_path):
    """Les logs APDU peuvent contenir des octets bruts."""
    fichier = tmp_path / "trace.log"
    fichier.write_bytes(b"APDU \xff\xfe brut\n")
    contenu, avertissement = read_text_file(fichier)
    assert "APDU" in contenu
    assert avertissement is None


def test_a_huge_file_is_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr("gui_qt.detail_panel.MAX_DISPLAY_BYTES", 100)
    fichier = tmp_path / "gros.log"
    fichier.write_text("x" * 5000, encoding="utf-8")

    contenu, avertissement = read_text_file(fichier)
    assert len(contenu) == 100
    assert "tronque" in avertissement.lower()


# ---------------------------------------------------------------------- source

def build_workspace(tmp_path):
    (tmp_path / "module").mkdir()
    (tmp_path / "module" / "test_exemple.py").write_text(
        "import pytest\n"
        "\n"
        "\n"
        "def test_premier():\n"
        "    assert True\n"
        "\n"
        "\n"
        "def test_cible(valeur):\n"
        "    assert valeur\n",
        encoding="utf-8",
    )
    return tmp_path


def test_clicking_a_test_shows_its_source(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py::test_cible", "module/test_exemple.py::test_cible")

    assert "def test_cible" in panel.source_view.toPlainText()
    assert "test_exemple.py" in panel.source_header.text()


def test_the_cursor_lands_on_the_test_definition(panel, tmp_path):
    """Sur un fichier de plusieurs milliers de lignes, arriver en haut serait inutile."""
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py::test_cible", "module/test_exemple.py::test_cible")

    ligne = panel.source_view.textCursor().blockNumber()
    assert panel.source_view.toPlainText().splitlines()[ligne].startswith("def test_cible")


def test_a_parametrized_case_finds_its_function(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py::test_cible[x]", "module/test_exemple.py::test_cible[x]")

    ligne = panel.source_view.textCursor().blockNumber()
    assert panel.source_view.toPlainText().splitlines()[ligne].startswith("def test_cible")


def test_clicking_a_folder_explains_instead_of_showing_nothing(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module", "")

    assert panel.source_view.toPlainText() == ""
    assert "dossier" in panel.source_header.text()


def test_a_missing_source_file_is_reported(panel, tmp_path):
    panel.set_workspace(str(tmp_path))
    panel.show_for("module/disparu.py::test_x", "module/disparu.py::test_x")

    assert "introuvable" in panel.source_header.text()


def test_without_a_workspace_nothing_explodes(panel):
    panel.show_for("module/test_exemple.py::test_x", "module/test_exemple.py::test_x")
    assert "workspace" in panel.source_header.text().lower()


# ------------------------------------------------------------------------- log

def write_log(tmp_path, nodeid: str, contenu: str):
    """Reproduit ce que le conftest du workspace ecrit : un fichier par test,
    plus un manifeste qui fait le lien avec le nodeid."""
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    fichier = logs / "test_cible.log"
    fichier.write_text(contenu, encoding="utf-8")
    (logs / "last_run_index.json").write_text(
        json.dumps({nodeid: str(fichier)}), encoding="utf-8"
    )
    return fichier


def test_clicking_a_test_shows_its_log(panel, tmp_path):
    build_workspace(tmp_path)
    nodeid = "module/test_exemple.py::test_cible"
    write_log(tmp_path, nodeid, "APDU >> 00A4 << 9000\n")
    panel.set_workspace(str(tmp_path))

    panel.show_for(nodeid, nodeid)

    assert "APDU" in panel.log_view.toPlainText()
    assert "test_cible.log" in panel.log_header.text()


def test_a_test_without_log_says_where_it_looked(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py::test_cible", "module/test_exemple.py::test_cible")

    assert panel.log_view.toPlainText() == ""
    message = panel.log_header.text()
    assert "log_directory" in message, "le message doit indiquer le reglage a ajuster"
    assert "logs" in message, "le message doit indiquer ou le log est cherche"


def test_a_custom_log_directory_is_honoured(panel, tmp_path):
    """Le chemin des logs se regle par la cle log_directory du config.yml."""
    build_workspace(tmp_path)
    (tmp_path / "config.yaml").write_text("log_directory: traces\n", encoding="utf-8")
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py::test_cible", "module/test_exemple.py::test_cible")

    assert "traces" in panel.log_header.text()


def test_a_node_without_nodeid_asks_for_a_precise_test(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))

    panel.show_for("module/test_exemple.py", "")

    assert "test precis" in panel.log_header.text()


# ----------------------------------------------------------------------- onglets

def test_the_console_is_the_default_tab(panel):
    assert panel.tabs.currentIndex() == 0
    assert panel.tabs.tabText(0) == "Console"
    assert [panel.tabs.tabText(i) for i in range(3)] == ["Console", "Source", "Log"]


def test_the_console_widget_is_still_a_plain_text_edit(panel):
    """Tout le code d'affichage existant ecrit dans panel.console."""
    panel.console.append("ligne de run")
    assert "ligne de run" in panel.console.toPlainText()


def test_switching_tabs(panel):
    panel.show_source()
    assert panel.tabs.currentIndex() == 1
    panel.show_log()
    assert panel.tabs.currentIndex() == 2
    panel.show_console()
    assert panel.tabs.currentIndex() == 0
