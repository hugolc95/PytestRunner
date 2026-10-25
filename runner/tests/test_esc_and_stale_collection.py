"""Esc pendant une saisie et arbre perime apres une collecte en echec."""
import sys

import pytest
from PySide6.QtCore import QSettings, Qt

from runner.domain import history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.services.run_service import RunService
from runner.ui.main_window import MainWindow
from runner.ui.widgets import ErrorDialog


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


@pytest.fixture
def busy_run(monkeypatch):
    """Un run en cours, sans lancer pytest : on compte les annulations."""
    cancelled = []
    monkeypatch.setattr(RunService, "busy", property(lambda self: True))
    monkeypatch.setattr(RunService, "cancel", lambda self: cancelled.append(True))
    return cancelled


def show(window, qtbot):
    from PySide6.QtWidgets import QApplication

    window.show()
    qtbot.waitExposed(window)
    QApplication.setActiveWindow(window)
    qtbot.waitUntil(window.isActiveWindow)
    # Sans vrai run, les onglets laissent Stop desactive : on l'active comme
    # le ferait un run en cours, pour que Esc atteigne bien son raccourci.
    window.act_stop.setEnabled(True)


def test_esc_in_test_search_clears_it_without_stopping_the_run(window, qtbot, busy_run):
    show(window, qtbot)
    context = window._selected_run_context()
    context.search.field.setFocus()
    qtbot.keyClicks(context.search.field, "step")
    qtbot.keyClick(context.search.field, Qt.Key_Escape)
    assert context.search.field.text() == ""
    assert not busy_run
    # Une seconde frappe dans le champ vide n'arrete pas davantage le run.
    qtbot.keyClick(context.search.field, Qt.Key_Escape)
    assert not busy_run


def test_esc_in_any_text_field_does_not_stop_the_run(window, qtbot, busy_run):
    show(window, qtbot)
    context = window._selected_run_context()
    editor = context.workspace_combo.lineEdit()
    editor.setFocus()
    qtbot.keyClick(editor, Qt.Key_Escape)
    assert not busy_run


def test_esc_outside_text_fields_still_stops_the_run(window, qtbot, busy_run):
    show(window, qtbot)
    context = window._selected_run_context()
    context.tree.setFocus()
    qtbot.keyClick(context.tree, Qt.Key_Escape)
    assert busy_run == [True]


def collect(window, qtbot, folder):
    window.workspace_combo.setCurrentText(str(folder))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None
                    and not window._collector.isRunning(), timeout=30000)
    qtbot.wait(50)


def test_failed_collection_of_another_workspace_forgets_the_previous_tests(
        window, qtbot, tmp_path, monkeypatch):
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics",
                        lambda *args, **kwargs: popups.append(args))
    good = tmp_path / "good"
    good.mkdir()
    (good / "test_good.py").write_text("def test_ok():\n    assert True\n")
    collect(window, qtbot, good)
    assert window.model.checked_nodeids() or window.model.rowCount() > 0

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "test_broken.py").write_text("def test_x(:\n    pass\n")
    collect(window, qtbot, broken)
    assert popups
    assert window.model.rowCount() == 0

    started = []
    monkeypatch.setattr(RunService, "start", lambda self, request, env: started.append(request))
    window.model.set_all_checked(True)
    window.run_selected()
    assert not started


def test_failed_recollection_of_the_same_workspace_keeps_its_tree(
        window, qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(ErrorDialog, "show_diagnostics", lambda *args, **kwargs: None)
    (tmp_path / "test_good.py").write_text("def test_ok():\n    assert True\n")
    collect(window, qtbot, tmp_path)
    rows = window.model.rowCount()
    assert rows > 0

    # Un conftest casse fait echouer toute la collecte ; un simple fichier de
    # tests casse ne donnerait qu'une collecte partielle.
    (tmp_path / "conftest.py").write_text("import missing_module_stale_xyz\n")
    collect(window, qtbot, tmp_path)
    assert window.status_label.text() == "Collection failed"
    assert window.model.rowCount() == rows
