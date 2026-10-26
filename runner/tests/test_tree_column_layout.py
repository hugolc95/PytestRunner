"""Colonnes de l'arbre : Duration affichable ou non, largeurs reglables et retenues.

Les largeurs etaient recalculees a chaque collecte qui changeait de lecteurs
et a chaque demarrage : un reglage fait a la souris ne tenait pas. Elles sont
retenues par colonne (Test, nom du lecteur, Duration), et seuls les gestes de
l'utilisateur comptent.
"""
import json
import sys

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest

from runner.domain import history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.ui.main_window import MainWindow
from runner.ui.tree_columns import TreeColumnLayout

NODEIDS = ["suite/test_a.py::test_one", "suite/test_a.py::test_two"]
DEUX = (Reader("Reader A", 0), Reader("Reader B", 1))


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)


@pytest.fixture
def make_window(qtbot, tmp_path, monkeypatch, settings):
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    windows = []

    def make(readers=DEUX):
        w = MainWindow()
        qtbot.addWidget(w)
        w.resize(1400, 800)
        w.model.set_tree(build_tree(NODEIDS))
        w.model.set_readers(readers)
        w._size_reader_columns()
        w._set_profile_tree_visible(False)
        windows.append(w)
        return w

    yield make
    for w in windows:
        w.close()


def duration(w):
    return w.model.duration_column


def hidden(w, section):
    return w.tree.header().isSectionHidden(section)


def as_user(w, monkeypatch):
    monkeypatch.setattr(w.tree_columns, "_user_gesture", lambda: True)


# ------------------------------------------------------------------- Duration

def test_duration_is_shown_by_default_and_can_be_hidden(make_window, settings):
    w = make_window()
    assert not hidden(w, duration(w))

    w.set_duration_column_visible(False)
    assert hidden(w, duration(w))
    assert not any(hidden(w, c) for c in range(1, duration(w)))
    saved = json.loads(settings.value("preferences/personal", "{}"))
    assert saved["show_duration"] is False
    assert not w.preferences.settings_panel.controls["show_duration"].isChecked()

    w.set_duration_column_visible(True)
    assert not hidden(w, duration(w))


def test_hidden_duration_follows_the_column_when_readers_change(make_window):
    w = make_window()
    w.set_duration_column_visible(False)
    w.model.set_readers(DEUX + (Reader("Reader C", 2),))
    w._size_reader_columns()
    assert duration(w) == 4
    assert hidden(w, 4) and not hidden(w, 3)

    w.model.set_readers(DEUX[:1])
    assert duration(w) == 2
    assert hidden(w, 2) and not hidden(w, 1)


def test_hidden_duration_survives_a_new_collection(make_window):
    w = make_window()
    w.set_duration_column_visible(False)
    w.model.set_tree(build_tree(NODEIDS + ["suite/test_b.py::test_three"]))
    assert hidden(w, duration(w))


def test_the_settings_checkbox_drives_the_column(make_window):
    w = make_window()
    w.preferences.settings_panel.controls["show_duration"].setChecked(False)
    w.preferences.save()
    assert hidden(w, duration(w))


def test_the_choice_is_kept_after_a_restart(make_window):
    make_window().set_duration_column_visible(False)
    w = make_window()
    assert hidden(w, duration(w))


def test_both_menus_offer_the_column_actions(make_window):
    w = make_window()
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    w._ajouter_actions_colonnes(menu)
    textes = [a.text() for a in menu.actions()]
    assert textes == ["Show Duration column", "Duration shows", "Reset column widths"]
    assert menu.actions()[0].isChecked()

    # Le menu « … » de la barre de l'arbre, et le clic droit sur l'en-tete.
    w.tree_tools.populate_menu()
    assert {"Show Duration column", "Reset column widths"} <= {
        a.text() for a in w.tree_tools.menu.actions()}
    assert w.tree.header().contextMenuPolicy() == Qt.CustomContextMenu


def test_unchecking_the_menu_action_hides_the_column(make_window):
    w = make_window()
    from PySide6.QtWidgets import QMenu

    menu = QMenu()
    w._ajouter_actions_colonnes(menu)
    menu.actions()[0].trigger()
    assert hidden(w, duration(w))


# ------------------------------------------------------------------- largeurs

def test_the_duration_column_fits_a_duration_of_several_minutes(make_window):
    w = make_window()
    texte = w.tree.fontMetrics().horizontalAdvance(TreeColumnLayout.DURATION_SAMPLE)
    assert w.tree.columnWidth(duration(w)) >= texte + 12


def test_a_width_set_by_the_user_survives_a_reader_change(make_window, monkeypatch):
    w = make_window()
    as_user(w, monkeypatch)
    w.tree.header().resizeSection(2, 150)       # Reader B
    w.tree.header().resizeSection(duration(w), 130)

    # Reader B passe en troisieme position : sa largeur le suit.
    w.model.set_readers((Reader("Reader A", 0), Reader("Reader C", 1), Reader("Reader B", 2)))
    w._size_reader_columns()
    assert w.tree.columnWidth(3) == 150
    assert w.tree.columnWidth(2) != 150
    assert w.tree.columnWidth(duration(w)) == 130


def test_automatic_resizes_are_not_remembered(make_window):
    w = make_window()
    w.tree.header().resizeSection(1, 177)        # pas de geste : rien a retenir
    w.model.set_readers(DEUX)
    w._size_reader_columns()
    assert w.tree.columnWidth(1) != 177


def test_widths_are_kept_after_a_restart(make_window, monkeypatch):
    w = make_window()
    as_user(w, monkeypatch)
    w.tree.header().resizeSection(1, 140)
    w.tree_columns._save()
    w.close()

    again = make_window()
    assert again.tree.columnWidth(1) == 140


def test_reset_restores_the_computed_widths(make_window, monkeypatch):
    w = make_window()
    defaut = w.tree.columnWidth(1)
    as_user(w, monkeypatch)
    w.tree.header().resizeSection(1, 200)

    w.tree_columns.reset()
    assert w.tree.columnWidth(1) == defaut
    w.model.set_readers(DEUX)
    w._size_reader_columns()
    assert w.tree.columnWidth(1) == defaut


def _bord_droit(tree):
    header = tree.header()
    return max(header.sectionViewportPosition(i) + header.sectionSize(i)
               for i in range(header.count()) if not header.isSectionHidden(i))


@pytest.mark.parametrize("arbre", ["tree", "profile_tree"])
def test_result_columns_stay_flush_right_without_duration(make_window, qtbot, arbre):
    """Sans Duration, les colonnes des lecteurs restent collees au bord droit :
    la colonne Test prend la place liberee au lieu de laisser un vide."""
    w = make_window()
    w.resize(1400, 800)
    w.show()
    qtbot.waitExposed(w)
    if arbre == "profile_tree":
        w.profile_model.set_readers(DEUX)
        w._size_reader_columns(w.profile_tree, w.profile_model)
        w._set_profile_tree_visible(True)
    tree = getattr(w, arbre)
    qtbot.waitUntil(lambda: _bord_droit(tree) == tree.viewport().width())

    if arbre == "tree":
        w.set_duration_column_visible(False)
        qtbot.waitUntil(lambda: _bord_droit(tree) == tree.viewport().width())
        w.set_duration_column_visible(True)
        qtbot.waitUntil(lambda: _bord_droit(tree) == tree.viewport().width())


def test_dragging_a_column_edge_with_the_mouse_is_remembered(make_window, qtbot):
    """Le vrai geste, sans raccourci : glisser le bord droit de la colonne."""
    w = make_window()
    w.show()
    qtbot.waitExposed(w)
    header = w.tree.header()
    viewport = header.viewport()
    bord = header.sectionViewportPosition(1) + header.sectionSize(1) - 1
    y = header.height() // 2
    avant = header.sectionSize(1)

    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(bord, y))
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    for dx in (10, 25, 40):
        local = QPointF(bord + dx, y)
        QApplication.sendEvent(viewport, QMouseEvent(
            QMouseEvent.MouseMove, local, viewport.mapToGlobal(local),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(bord + 40, y))

    assert header.sectionSize(1) > avant
    assert w.tree_columns.remembered(1) == header.sectionSize(1)
