"""Retours utilisateur sur la 1.4.0.

1. Un test supprime apres la collecte, puis lance : pytest refuse la commande
   (code 4, "ERROR: not found"), aucun verdict ne remonte, et le run finissait
   sur "All tests passed" sans le moindre message.
2. Passer a un autre test ramenait sur l'onglet Detail, meme quand on lisait
   les Logs du test precedent.
"""
import sys

import pytest
from PySide6.QtCore import QSettings

from runner.domain import diagnostics, execution, history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Reader, ReaderReport, RunRequest
from runner.ui import end_run_feedback
from runner.ui.main_window import MainWindow
from runner.ui.results_panel import ONGLET_LOGS, ONGLET_SOURCE
from runner.ui.widgets import ErrorDialog


# ------------------------------------------------------- test supprime : domaine

@pytest.mark.parametrize("nodeids", [
    ("test_a.py::test_removed",),
    ("test_gone.py::test_x",),
    ("test_a.py::test_keep", "test_a.py::test_removed"),
])
def test_running_a_deleted_test_reports_why_nothing_ran(tmp_path, nodeids):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_a.py").write_text("def test_keep():\n    pass\n")
    request = RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                         nodeids=nodeids, readers=(Reader("", 0),))
    report = execution.ReaderRun(request, Reader("", 0), {}).run(
        lambda line: None, lambda outcome: None)

    assert report.counts == {}
    [issue] = report.issues
    assert "not found" in issue
    assert "Click Collect" in issue


def test_other_pytest_errors_get_no_collect_hint():
    message = diagnostics.fallback_error("ERROR: usage: pytest [options]\n", 4)
    assert "Collect" not in message


# --------------------------------------------------------------- fenetre

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
    # Comme l'application (`runner/__main__.py`) : c'est ce gestionnaire de fin
    # de run qui tourne pour l'utilisateur, et c'est lui qui taisait l'erreur.
    for name in ("_on_run_started", "_on_outcome", "_on_progress", "_on_run_finished"):
        monkeypatch.setattr(MainWindow, name, getattr(MainWindow, name))
    end_run_feedback.install()
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()


def collect(window, qtbot, folder):
    window.workspace_combo.setCurrentText(str(folder))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None
                    and not window._collector.isRunning(), timeout=30000)
    qtbot.wait(50)


def test_running_a_test_deleted_since_collection_shows_an_error(
        window, qtbot, tmp_path, monkeypatch):
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics",
                        lambda *args, **kwargs: popups.append(args))
    folder = tmp_path / "ws"
    folder.mkdir()
    (folder / "pytest.ini").write_text("[pytest]\n")
    source = folder / "test_a.py"
    source.write_text("def test_keep():\n    pass\n\ndef test_removed():\n    pass\n")
    collect(window, qtbot, folder)
    assert "test_a.py::test_removed" in window.model.nodeids()

    source.write_text("def test_keep():\n    pass\n")
    window.model.set_checked_nodeids(["test_a.py::test_removed"])
    window.run_selected()
    qtbot.waitUntil(lambda: bool(popups), timeout=30000)

    [(_, title, errors, *_rest)] = popups
    assert title == "Execution error"
    assert "test_removed" in errors and "Click Collect" in errors
    assert window.status_label.text().startswith("Execution completed with errors")
    assert "All tests passed" not in window.status_label.text()


def test_a_run_ending_on_a_global_error_no_longer_reads_all_passed(window, qtbot, monkeypatch):
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics",
                        lambda *args, **kwargs: popups.append(args))
    rapport = ReaderReport(reader=Reader("Reader A", 0), exit_code=4,
                           issues=["ERROR: not found: test_a.py::test_x"])
    window._on_run_finished([rapport])
    qtbot.waitUntil(lambda: bool(popups), timeout=2000)
    assert "Reader A\nERROR: not found" in popups[0][2]
    assert window.status_label.text().startswith("Execution completed with errors")


def test_a_cancelled_run_shows_no_error(window, qtbot, monkeypatch):
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics",
                        lambda *args, **kwargs: popups.append(args))
    rapport = ReaderReport(reader=Reader("", 0), exit_code=-1, cancelled=True,
                           issues=["Process exited"])
    window._on_run_finished([rapport])
    qtbot.wait(20)
    assert popups == []
    assert window.status_label.text().startswith("Run stopped")


# ------------------------------------------------------------ onglet conserve

def test_selecting_another_test_keeps_the_logs_tab(window, qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(ErrorDialog, "show_diagnostics", lambda *args, **kwargs: None)
    folder = tmp_path / "ws"
    folder.mkdir()
    (folder / "test_a.py").write_text("def test_one():\n    pass\n\ndef test_two():\n    pass\n")
    collect(window, qtbot, folder)
    tree, model = window.tree, window.model

    tree.setCurrentIndex(model.index_for_nodeid("test_a.py::test_one"))
    window.results.show_tab(ONGLET_LOGS)
    tree.setCurrentIndex(model.index_for_nodeid("test_a.py::test_two"))
    qtbot.wait(20)
    assert window.results.tabs.currentIndex() == ONGLET_LOGS


def test_a_chosen_tab_still_wins_when_set_in_preferences(window, qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(ErrorDialog, "show_diagnostics", lambda *args, **kwargs: None)
    folder = tmp_path / "ws"
    folder.mkdir()
    (folder / "test_a.py").write_text("def test_one():\n    pass\n\ndef test_two():\n    pass\n")
    collect(window, qtbot, folder)
    window.preferences.values["selection_tab"] = "Source"

    window.results.show_tab(ONGLET_LOGS)
    window.tree.setCurrentIndex(window.model.index_for_nodeid("test_a.py::test_two"))
    assert window.results.tabs.currentIndex() == ONGLET_SOURCE


def test_the_old_detail_default_becomes_last_used(qtbot, tmp_path, monkeypatch):
    """`default_tab` valait Detail par defaut : l'avoir enregistre ne veut pas
    dire l'avoir choisi. Un autre onglet, lui, etait un choix et reste."""
    import json

    from runner.ui.preferences_pages import DEFAULTS

    for ancien, attendu in (("Detail", "Last used"), ("Logs", "Logs")):
        settings = QSettings(str(tmp_path / f"{ancien}.ini"), QSettings.IniFormat)
        settings.setValue("preferences/personal", json.dumps({"default_tab": ancien}))
        monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
        monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
        monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
        monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
        w = MainWindow()
        qtbot.addWidget(w)
        assert w.preferences.values["selection_tab"] == attendu
        w.close()
    assert DEFAULTS["selection_tab"] == "Last used"
