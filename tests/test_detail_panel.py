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
    assert "LOG_PATH" in message, "le message doit indiquer le reglage a ajuster"
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


# --------------------------------------------- modification du fichier source

SOURCE = "import pytest\n\n\ndef test_f():\n    assert True\n"


@pytest.fixture
def source(panel, tmp_path):
    """Un workspace d'un fichier, affiche dans l'onglet Source."""
    fichier = tmp_path / "test_x.py"
    fichier.write_text(SOURCE, encoding="utf-8")
    panel.set_workspace(str(tmp_path))
    panel.show_for("test_x.py", "test_x.py::test_f")
    return panel, fichier


def test_the_source_is_read_only_until_the_button_is_pressed(source):
    """On consulte un fichier de test bien plus souvent qu'on le corrige : il ne
    doit pas se modifier sous les doigts."""
    panel, _ = source
    assert panel.source_view.isReadOnly()
    assert not panel.edit_button.isChecked()
    assert panel.edit_button.isEnabled()


def test_pressing_the_button_allows_editing(source):
    panel, _ = source
    panel.edit_button.setChecked(True)
    assert not panel.source_view.isReadOnly()


def test_an_edit_is_saved_on_its_own(source, qtbot):
    """Le point demande : pas de bouton Enregistrer a penser."""
    panel, fichier = source
    panel.edit_button.setChecked(True)
    panel.source_view.setPlainText(SOURCE.replace("assert True", "assert 1 == 1"))

    qtbot.waitUntil(lambda: "assert 1 == 1" in fichier.read_text(encoding="utf-8"),
                    timeout=3000)


def test_leaving_edit_mode_saves_immediately(source):
    panel, fichier = source
    panel.edit_button.setChecked(True)
    panel.source_view.setPlainText("# corrige\n")
    panel.edit_button.setChecked(False)

    assert fichier.read_text(encoding="utf-8") == "# corrige\n"
    assert panel.source_view.isReadOnly()


def test_looking_at_a_file_never_rewrites_it(source):
    """Le seul echec inacceptable : abimer un fichier qu'on ne fait que lire."""
    panel, fichier = source
    avant = fichier.stat().st_mtime_ns

    panel.show_for("test_x.py", "test_x.py::test_f")
    panel.save_source()

    assert fichier.stat().st_mtime_ns == avant
    assert fichier.read_text(encoding="utf-8") == SOURCE


def test_switching_file_saves_the_pending_edit(panel, tmp_path):
    premier = tmp_path / "test_a.py"
    premier.write_text(SOURCE, encoding="utf-8")
    (tmp_path / "test_b.py").write_text(SOURCE, encoding="utf-8")
    panel.set_workspace(str(tmp_path))

    panel.show_for("test_a.py", "test_a.py::test_f")
    panel.edit_button.setChecked(True)
    panel.source_view.setPlainText("# a corrige\n")
    panel.show_for("test_b.py", "test_b.py::test_f")

    assert premier.read_text(encoding="utf-8") == "# a corrige\n"


def test_the_new_file_opens_read_only_again(panel, tmp_path):
    """Sinon on croirait consulter alors qu'on modifie encore."""
    for nom in ("test_a.py", "test_b.py"):
        (tmp_path / nom).write_text(SOURCE, encoding="utf-8")
    panel.set_workspace(str(tmp_path))

    panel.show_for("test_a.py", None)
    panel.edit_button.setChecked(True)
    panel.show_for("test_b.py", None)

    assert panel.source_view.isReadOnly()
    assert not panel.edit_button.isChecked()


def test_windows_line_endings_are_preserved(panel, tmp_path):
    """Sans cela, la premiere frappe reecrirait tout le fichier en LF et le diff
    porterait sur chaque ligne."""
    fichier = tmp_path / "test_crlf.py"
    fichier.write_bytes(b"import pytest\r\n\r\ndef test_f():\r\n    pass\r\n")
    panel.set_workspace(str(tmp_path))
    panel.show_for("test_crlf.py", None)

    panel.edit_button.setChecked(True)
    panel.source_view.setPlainText("import pytest\n\ndef test_f():\n    assert True\n")
    panel.edit_button.setChecked(False)

    assert fichier.read_bytes() == b"import pytest\r\n\r\ndef test_f():\r\n    assert True\r\n"


def test_an_undecodable_file_cannot_be_edited(panel, tmp_path):
    """Le reecrire depuis l'affichage remplacerait les octets bruts par des
    points d'interrogation."""
    fichier = tmp_path / "test_binaire.py"
    fichier.write_bytes(b"# \xff\xfe\ndef test_f(): pass\n")
    panel.set_workspace(str(tmp_path))
    panel.show_for("test_binaire.py", None)

    assert not panel.edit_button.isEnabled()
    panel.edit_button.setChecked(True)
    assert panel.source_view.isReadOnly()


def test_the_button_is_disabled_without_a_file(panel):
    assert not panel.edit_button.isEnabled()


def test_a_failed_save_is_reported_and_not_forgotten(source, monkeypatch):
    """Un fichier verrouille ne doit pas faire croire que c'est enregistre."""
    panel, _ = source
    panel.edit_button.setChecked(True)
    panel.source_view.setPlainText("# essai\n")

    monkeypatch.setattr("gui_qt.detail_panel.write_source_file",
                        lambda *a, **k: "Enregistrement impossible : verrouille")

    assert panel.save_source() is False
    assert "impossible" in panel.source_status.text().lower()
    assert panel._dirty, "la modification reste en attente, elle n'est pas perdue"


def test_the_saved_file_is_never_left_half_written(tmp_path):
    """L'ecriture passe par un temporaire : une erreur ne laisse pas un fichier
    de test tronque."""
    from gui_qt.detail_panel import write_source_file

    fichier = tmp_path / "test_x.py"
    fichier.write_text(SOURCE, encoding="utf-8")

    erreur = write_source_file(tmp_path, "peu importe", "\n")  # un dossier
    assert erreur is not None
    assert fichier.read_text(encoding="utf-8") == SOURCE
    assert list(tmp_path.glob("*.pytestrunner.tmp")) == []


def test_a_run_starts_from_the_edited_file(qtbot, tmp_path):
    """"pas besoin de reloader le workspace" : pytest relit le fichier, il faut
    seulement que la frappe en attente soit ecrite avant le lancement."""
    from gui_qt.main_window import MainWindow

    fichier = tmp_path / "test_x.py"
    fichier.write_text(SOURCE, encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.details.show_for("test_x.py", "test_x.py::test_f")
    fenetre.details.edit_button.setChecked(True)
    fenetre.details.source_view.setPlainText("# avant le run\n")

    fenetre._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        assert fichier.read_text(encoding="utf-8") == "# avant le run\n"
    finally:
        fenetre.worker.stop()
        fenetre.worker.wait(5000)
