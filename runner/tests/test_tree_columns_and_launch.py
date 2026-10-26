"""Colonnes de resultat toujours visibles et bouton Run/Pause immobile."""
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QTreeView

from runner.domain import history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader
from runner.domain.tree import build_tree
from runner.ui.main_window import MainWindow
from runner.ui.tree_columns import NameColumnFitter
from runner.ui.tree_model import TestTreeModel


def test_name_column_yields_space_and_fills_the_rest(qtbot):
    model = TestTreeModel()
    model.set_tree(build_tree(["pkg/test_a.py::test_one"]))
    model.set_readers((Reader("Reader A", 0), Reader("Reader B", 1)))
    tree = QTreeView()
    qtbot.addWidget(tree)
    tree.setModel(model)
    header = tree.header()
    header.setStretchLastSection(False)
    for column in range(1, model.columnCount()):
        header.resizeSection(column, 80)
    header.resizeSection(0, 420)
    NameColumnFitter(tree)
    tree.resize(760, 300)
    tree.show()
    qtbot.waitExposed(tree)

    def last_edge():
        return max(header.sectionViewportPosition(i) + header.sectionSize(i)
                   for i in range(header.count()))

    tree.resize(400, 300)
    qtbot.waitUntil(lambda: last_edge() <= tree.viewport().width())
    assert header.sectionSize(0) < 420

    # Avec de la place, les colonnes de resultat restent collees au bord
    # droit : la colonne des noms prend tout le reste, pas une largeur fixe.
    tree.resize(900, 300)
    qtbot.waitUntil(lambda: last_edge() == tree.viewport().width())
    assert header.sectionSize(0) > 420

    # Masquer une colonne (Duration) ne laisse pas de vide a droite.
    header.setSectionHidden(model.duration_column, True)
    qtbot.waitUntil(lambda: last_edge() == tree.viewport().width())


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()


def test_pause_takes_exactly_the_place_of_run(window, qtbot):
    window.resize(1400, 900)
    window.show()
    qtbot.waitExposed(window)
    context = window._selected_run_context()
    for label in MainWindow.LAUNCH_LABELS:
        context.run_button.setText(label)
        context.pause_button.setText(label)
        assert context.run_button.minimumWidth() >= context.run_button.sizeHint().width()
        assert context.pause_button.minimumWidth() >= context.pause_button.sizeHint().width()
    assert context.run_button.minimumWidth() == context.pause_button.minimumWidth()
