"""Colonne Duration avec plusieurs lecteurs : ce qu'elle montre se choisit.

Une seule colonne, et un mode : le plus lent (par defaut), le plus rapide, la
moyenne, l'ecart entre le plus lent et le plus rapide, ou un lecteur precis.
Un regroupement se calcule a partir du TOTAL de chaque lecteur ; son survol
donne ces totaux. En mode ecart, un ecart notable ressort en couleur.
"""
import sys

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor

from runner.domain import history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.ui import tokens as t
from runner.ui.tree_model import TestTreeModel

ONE, TWO = "pkg/test_a.py::test_one", "pkg/test_a.py::test_two"
A, B = Reader("Reader A", 0), Reader("Reader B", 1)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def model(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree([ONE, TWO]))
    m.set_readers((A, B))
    # one : A 1.0 s, B 2.5 s      two : A 2.0 s, B 2.1 s
    for nodeid, reader, seconds in ((ONE, 0, 1.0), (ONE, 1, 2.5), (TWO, 0, 2.0), (TWO, 1, 2.1)):
        m.set_duration(nodeid, reader, seconds)
    return m


def cell(m, nodeid=None, role=Qt.DisplayRole):
    """La case Duration d'un test, ou du module si `nodeid` est None."""
    colonne = m.duration_column
    if nodeid is None:
        module = m.index(0, 0, m.index(0, 0))
        return m.index(module.row(), colonne, module.parent()).data(role)
    return m.index_for_nodeid(nodeid).siblingAtColumn(colonne).data(role)


@pytest.mark.parametrize("mode, test, groupe, titre", [
    ("slowest", "2.50s", "4.60s", "Duration"),   # groupe : total de B (2.5 + 2.1)
    ("fastest", "1.00s", "3.00s", "Fastest"),    # groupe : total de A (1.0 + 2.0)
    ("average", "1.75s", "3.80s", "Average"),
    ("spread", "Δ 1.50s", "Δ 1.60s", "Spread"),
    ("reader:Reader A", "1.00s", "3.00s", "Duration · A"),
])
def test_each_mode(model, mode, test, groupe, titre):
    model.set_duration_mode(mode)
    assert cell(model, ONE) == test
    assert cell(model) == groupe
    assert model.headerData(model.duration_column, Qt.Horizontal) == titre


def test_slowest_is_the_default(model):
    assert model.duration_mode == "slowest"


def test_hovering_a_group_gives_each_readers_real_total(model):
    survol = cell(model, role=Qt.ToolTipRole)
    assert survol.splitlines() == ["Total per reader:", "Reader A: 3.00s",
                                   "Reader B: 4.60s", "Spread: 1.60s"]


def test_hovering_a_test_gives_each_reader_and_the_spread(model):
    assert cell(model, ONE, Qt.ToolTipRole).splitlines() == [
        "Reader A: 1.00s", "Reader B: 2.50s", "Spread: 1.50s"]


def test_spread_mode_colours_only_notable_spreads(model):
    model.set_duration_mode("spread")
    assert cell(model, ONE, Qt.ForegroundRole) == QColor(t.divergent_color())  # 1.5 s sur 2.5 s
    assert cell(model, TWO, Qt.ForegroundRole) == QColor(t.TEXT_MUTED)         # 0.1 s sur 2.1 s
    model.set_duration_mode("slowest")
    assert cell(model, ONE, Qt.ForegroundRole) == QColor(t.TEXT_MUTED)


def test_a_single_reader_shows_its_duration_whatever_the_mode(model):
    model.set_readers((A,))
    model.set_duration_mode("spread")
    assert cell(model, ONE) == "1.00s"
    assert model.headerData(model.duration_column, Qt.Horizontal) == "Duration"
    assert cell(model, ONE, Qt.ToolTipRole) is None


def test_a_reader_that_left_falls_back_to_slowest(model):
    model.set_duration_mode("reader:Reader B")
    model.set_readers((A, Reader("Reader C", 1)))
    assert model.headerData(model.duration_column, Qt.Horizontal) == "Duration"


def test_spread_needs_two_readers_with_a_duration(qapp):
    m = TestTreeModel()
    m.set_tree(build_tree([ONE]))
    m.set_readers((A, B))
    m.set_duration(ONE, 0, 1.0)
    m.set_duration_mode("spread")
    assert cell(m, ONE) is None


def test_group_totals_follow_live_durations(model):
    model.set_duration(TWO, 1, 5.0)
    assert cell(model) == "7.50s"


def test_an_unknown_mode_falls_back_to_slowest(model):
    model.set_duration_mode("nonsense")
    assert model.duration_mode == "slowest"


# ------------------------------------------------------------------- fenetre

@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from runner.ui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    made = []

    def make():
        w = MainWindow()
        qtbot.addWidget(w)
        w.model.set_tree(build_tree([ONE, TWO]))
        w.model.set_readers((A, B))
        made.append(w)
        return w

    yield make
    for w in made:
        w.close()


def modes_menu(w):
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    w._ajouter_actions_colonnes(menu)
    [sous_menu] = [a.menu() for a in menu.actions() if a.text() == "Duration shows"]
    return menu, sous_menu


def test_the_header_menu_lists_every_mode_and_each_reader(window):
    w = window()
    menu, sous_menu = modes_menu(w)  # garder le parent : il possede le sous-menu
    textes = [a.text() for a in sous_menu.actions() if not a.isSeparator()]
    assert textes == ["Slowest reader", "Fastest reader", "Average of the readers",
                      "Spread (slowest − fastest)", "Reader A only", "Reader B only"]
    assert sous_menu.isEnabled()
    assert [a.isChecked() for a in sous_menu.actions() if not a.isSeparator()][0]


def test_choosing_a_mode_applies_and_is_kept_after_a_restart(window):
    w = window()
    menu, sous_menu = modes_menu(w)  # garder le parent : il possede le sous-menu
    [spread] = [a for a in sous_menu.actions() if a.text().startswith("Spread")]
    spread.trigger()
    assert w.model.duration_mode == "spread"

    again = window()
    assert again.model.duration_mode == "spread"


def test_the_modes_are_disabled_with_a_single_reader(window):
    w = window()
    w.model.set_readers((A,))
    menu, sous_menu = modes_menu(w)  # garder le parent : il possede le sous-menu
    assert not sous_menu.isEnabled()
