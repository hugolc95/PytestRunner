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


def test_the_complete_log_can_be_opened_in_notepad_plus_plus(
    panel, tmp_path, monkeypatch
):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})
    panel.set_workspace(str(tmp_path))
    panel.show_for(NODEID, NODEID)

    opened = []
    monkeypatch.setattr(
        "gui_qt.detail_panel.open_in_notepad_plus_plus",
        lambda parent, path: opened.append(path) or True,
    )
    panel.open_full_log_button.click()

    assert opened == [
        tmp_path / "logs" / "20260813" / "Cosmo11Secured Reader"
        / "module" / "test_cible.log"
    ]


def test_right_click_is_enabled_on_each_log_view(panel):
    from PyQt5.QtCore import Qt

    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    assert all(
        view.contextMenuPolicy() == Qt.CustomContextMenu
        for view in panel.log_views[:2]
    )


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

    assert panel.log_views[1].parentWidget().isHidden()


# ------------------------ onglets et comparaison, comme pour la console

def test_the_log_panel_has_the_same_tabs_as_the_console(panel, tmp_path):
    """Le geste doit etre le meme des deux cotes : une barre d'onglets pour
    choisir le lecteur, un bouton pour les voir tous."""
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    # isHidden() et non isVisible() : rien n'est "visible" tant que la fenetre
    # n'est pas affichee, et l'assertion passerait alors pour de mauvaises
    # raisons quel que soit le comportement teste.
    assert not panel.log_tabs.isHidden()
    assert not panel.log_compare_button.isHidden()
    assert panel.log_tabs.count() == 2


def test_a_single_reader_shows_no_log_tabs(panel, tmp_path):
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))
    panel.set_readers([])

    assert panel.log_tabs.isHidden()
    assert panel.log_compare_button.isHidden()


def test_logs_are_compared_horizontally(panel):
    """Cote a cote, et non l'un sous l'autre : on compare la meme ligne d'un
    lecteur a l'autre, ce qu'un empilement vertical ne permet pas."""
    from PyQt5.QtCore import Qt

    assert panel.log_split.orientation() == Qt.Horizontal
    # Les consoles, elles, restent l'une sous l'autre : leurs lignes defilent.
    assert panel.console_split.orientation() == Qt.Vertical


def test_switching_the_log_tab_shows_only_that_reader(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    panel.show_for(NODEID, NODEID)

    panel.log_tabs.setCurrentIndex(1)
    assert panel.log_views[0].parentWidget().isHidden()
    assert not panel.log_views[1].parentWidget().isHidden()


def test_comparing_shows_every_log_at_once(panel, tmp_path):
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    panel.show_for(NODEID, NODEID)

    panel.log_compare_button.setChecked(True)
    assert not panel.log_views[0].parentWidget().isHidden()
    assert not panel.log_views[1].parentWidget().isHidden()


def test_console_and_log_stay_on_the_same_reader(panel, tmp_path):
    """Changer de lecteur cote Log doit y amener aussi la console, sinon on lit
    le log d'un lecteur en regardant la sortie d'un autre."""
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    panel.log_tabs.setCurrentIndex(1)
    assert panel.console_tabs.currentIndex() == 1

    panel.console_tabs.setCurrentIndex(0)
    assert panel.log_tabs.currentIndex() == 0


def test_choosing_a_reader_is_announced_once(panel, tmp_path):
    """Les deux barres se suivent : sans garde, chacune renverrait son choix a
    l'autre et le signal partirait en boucle."""
    build_workspace(tmp_path)
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])

    recus = []
    panel.reader_selected.connect(recus.append)
    panel.log_tabs.setCurrentIndex(1)

    assert recus == [1]


def test_scrolling_one_log_scrolls_the_others(panel, tmp_path):
    """Cote a cote, chaque log ne montre que la moitie de la largeur. Sans
    defilement synchronise, amener la valeur d'un lecteur sous les yeux
    laissait celle de l'autre hors champ -- il n'y avait plus rien a comparer."""
    build_workspace(tmp_path)
    longue = "\n".join(f"ligne {i} " + "x" * 200 for i in range(80))
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": longue, "Reader": longue})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    panel.show_for(NODEID, NODEID)

    panel.log_views[0].verticalScrollBar().setValue(17)
    assert panel.log_views[1].verticalScrollBar().value() == 17

    panel.log_views[1].horizontalScrollBar().setValue(40)
    assert panel.log_views[0].horizontalScrollBar().value() == 40


def test_consoles_scroll_independently(panel):
    """Deux lecteurs n'avancent pas au meme rythme : lier leurs consoles
    ramenerait sans cesse l'une la ou l'autre en est."""
    panel.set_readers(["Lecteur A", "Lecteur B"])
    for i, vue in enumerate(panel.consoles[:2]):
        vue.setPlainText("\n".join(f"ligne {n}" for n in range(200)))

    panel.consoles[0].verticalScrollBar().setValue(30)
    assert panel.consoles[1].verticalScrollBar().value() != 30


def test_a_compared_log_header_is_just_the_reader_name(panel, tmp_path):
    """Cote a cote la colonne est etroite : le chemin y tenait sur trois lignes
    alors qu'il ne differe d'un lecteur a l'autre que par le dossier du lecteur,
    justement ce que l'en-tete dit deja. Chemin complet en infobulle."""
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A", "Reader": "B"})
    panel.set_workspace(str(tmp_path))
    panel.set_readers(["Cosmo11Secured Reader", "Reader"])
    panel.show_for(NODEID, NODEID)

    assert panel.log_headers[0].text() == "Cosmo11Secured Reader"
    assert "test_cible.log" in panel.log_headers[0].toolTip()


def test_a_single_log_header_still_shows_the_path(panel, tmp_path):
    """Sans lecteur a nommer, c'est le chemin qui renseigne."""
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})
    panel.set_workspace(str(tmp_path))

    panel.show_for(NODEID, NODEID)

    assert "test_cible.log" in panel.log_header.text()


def test_a_single_log_header_shows_only_the_file_name(panel, tmp_path):
    """Un chemin de log reel fait plusieurs lignes de gros texte au-dessus du
    log, pour une information qu'on ne lit pas. Il passe en infobulle."""
    build_workspace(tmp_path)
    write_reader_logs(tmp_path, {"Cosmo11Secured Reader": "A"})
    panel.set_workspace(str(tmp_path))

    panel.show_for(NODEID, NODEID)

    entete = panel.log_header.text()
    assert "test_cible.log" in entete
    assert "Cosmo11Secured Reader" not in entete, "le dossier du lecteur n'a rien a faire la"
    assert "20260813" not in entete, "ni le dossier de run"
    # Le chemin complet reste atteignable.
    assert "20260813" in panel.log_header.toolTip()
