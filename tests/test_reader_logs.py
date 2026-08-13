"""Un log par lecteur, empiles, pour comparer le meme test d'un lecteur a l'autre.

Le conftest du workspace range ses logs par lecteur
(`<LOG_PATH>/<date>/<lecteur>/.../test.log`). Avec une seule vue, comparer ce
que le meme test a fait sur deux lecteurs obligeait a rouvrir le fichier a la
main. Les deux logs sont desormais charges cote a cote.
"""

import json

import pytest
from PyQt5.QtCore import QSettings

from gui_qt.config.config_loader import find_test_log

NODEID = "module/test_exemple.py::test_cible"


def build_workspace(tmp_path):
    (tmp_path / "module").mkdir(exist_ok=True)
    (tmp_path / "module" / "test_exemple.py").write_text(
        "def test_cible():\n    pass\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("log_directory: logs\n", encoding="utf-8")


def write_reader_logs(tmp_path, contenus: dict):
    """Ecrit un log par lecteur, dans l'arborescence du conftest reel."""
    for lecteur, contenu in contenus.items():
        dossier = tmp_path / "logs" / "20260813" / lecteur / "module"
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "test_cible.log").write_text(contenu, encoding="utf-8")


@pytest.fixture
def panel(qtbot):
    from gui_qt.detail_panel import DetailPanel

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    widget = DetailPanel()
    qtbot.addWidget(widget)
    return widget


# ------------------------------------------------------- resolution du fichier

def test_the_log_of_a_given_reader_is_found(tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})

    trouve = find_test_log(str(tmp_path), NODEID, reader="Cosmo11Secured Reader")
    assert trouve is not None
    assert trouve.read_text(encoding="utf-8") == "A"


def test_each_reader_gets_its_own_log_not_the_neighbours(tmp_path):
    """Le point critique : deux lecteurs ne doivent pas rendre le meme fichier."""
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})

    a = find_test_log(str(tmp_path), NODEID, reader="Cosmo11Secured Reader")
    b = find_test_log(str(tmp_path), NODEID, reader="Reader")

    assert a != b
    assert (a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")) == ("A", "B")


def test_an_unknown_reader_finds_nothing_rather_than_the_wrong_log(tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})

    assert find_test_log(str(tmp_path), NODEID, reader="Lecteur absent") is None


def test_without_a_reader_the_search_is_unchanged(tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})

    assert find_test_log(str(tmp_path), NODEID) is not None


def test_the_manifest_is_ignored_when_it_points_at_another_reader(tmp_path):
    """Le manifeste ne connait qu'un log par test : s'il donne celui d'un autre
    lecteur, le rendre sous le nom du lecteur demande serait un mensonge."""
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})
    manifeste = tmp_path / "logs" / "last_run_index.json"
    vise = tmp_path / "logs" / "20260813" / "Reader" / "module" / "test_cible.log"
    manifeste.write_text(json.dumps({NODEID: str(vise)}), encoding="utf-8")

    trouve = find_test_log(str(tmp_path), NODEID, reader="Cosmo11Secured Reader")
    assert trouve is not None
    assert trouve.read_text(encoding="utf-8") == "A"


# --------------------------------------------------------------- panneau Log

def test_a_single_reader_keeps_one_log_view(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})
    panel.set_workspace(str(tmp_path))

    panel.show_for(NODEID, NODEID)

    assert panel.log_view.toPlainText().strip() == "A"


def test_two_readers_show_their_two_logs_side_by_side(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "vu par A",
                                 "Reader": "vu par B"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    panel.show_for(NODEID, NODEID)

    assert len(panel.log_views) >= 2
    assert panel.log_views[0].toPlainText().strip() == "vu par A"
    assert panel.log_views[1].toPlainText().strip() == "vu par B"


def test_each_log_header_names_its_reader(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    panel.show_for(NODEID, NODEID)

    assert "Cosmo11Secured Reader" in panel.log_headers[0].text()
    assert panel.log_headers[1].text().startswith("Reader")


def test_a_reader_without_a_log_says_so_without_borrowing_the_other(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    panel.show_for(NODEID, NODEID)

    assert panel.log_views[0].toPlainText().strip() == "A"
    assert panel.log_views[1].toPlainText() == ""
    assert "LOG_PATH" in panel.log_headers[1].text()


def test_going_back_to_one_reader_hides_the_extra_view(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    panel.set_readers([])

    assert not panel.log_views[1].parentWidget().isVisible()
