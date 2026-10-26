"""La liste des lecteurs de Run tests voit les memes lecteurs que la config YAML.

La decouverte HubReader partait juste apres le debut de la collecte, alors
que la liste est desactivee pendant une collecte : elle abandonnait sans
reessayer, et la liste ne montrait que les lecteurs deja ecrits dans le
fichier de configuration.
"""
import sys
import textwrap

import pytest
from PySide6.QtCore import QSettings

from runner.domain import history, interpreter
from runner.domain.interpreter import InterpreterInfo
from runner.ui.main_window import MainWindow

BRANCHES = ["OMNIKEY CardMan 3x21 0", "Cosmo11SecuredSLC27G",
            "OTR V4 ISO_SPI Reader", "OTReader ISO_SWP Reader"]


def workspace(tmp_path, readers=BRANCHES):
    ws = tmp_path / "ws"
    paquet = ws / "Reader"
    paquet.mkdir(parents=True)
    (paquet / "__init__.py").write_text("")
    (paquet / "PyHubreader.py").write_text(textwrap.dedent(f'''
        class pyHubReader:
            def __init__(self, readerName="", logger=None):
                self.readerName = readerName
            def GetAllReaders(self):
                return {list(readers)!r}
    '''))
    (ws / "config.yml").write_text("Reader: OMNIKEY CardMan 3x21 0\n", encoding="utf-8")
    (ws / "test_a.py").write_text("def test_one():\n    pass\n")
    return ws


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_effective_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.reader_selector.stop_discovery()
    w.reader_atr.release()
    w.close()


def items(selector):
    return [selector.itemText(i) for i in range(selector.count())]


def test_the_run_list_shows_every_reader_found_after_collecting(window, qtbot, tmp_path):
    ws = workspace(tmp_path)
    window.workspace_combo.setCurrentText(str(ws))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None
                    and not window._collector.isRunning(), timeout=30000)
    selector = window.reader_selector
    qtbot.waitUntil(lambda: set(BRANCHES) <= set(items(selector)), timeout=15000)
    assert selector.currentText() == "OMNIKEY CardMan 3x21 0"
    assert "4 available HubReader devices" in selector.toolTip()


def test_opening_the_list_looks_again_when_discovery_did_not_succeed(window, qtbot, tmp_path):
    ws = workspace(tmp_path)
    selector = window.reader_selector
    selector.setEnabled(False)
    selector.set_context(str(ws), sys.executable, "OMNIKEY CardMan 3x21 0")
    qtbot.wait(50)                         # desactivee : rien n'a ete cherche
    assert items(selector) == ["OMNIKEY CardMan 3x21 0"]

    selector.setEnabled(True)
    qtbot.waitUntil(lambda: set(BRANCHES) <= set(items(selector)), timeout=15000)


def test_a_reader_plugged_later_appears_when_the_list_is_opened(window, qtbot, tmp_path):
    ws = workspace(tmp_path, BRANCHES[:2])
    selector = window.reader_selector
    selector.setEnabled(True)
    selector.set_context(str(ws), sys.executable, BRANCHES[0])
    qtbot.waitUntil(lambda: set(BRANCHES[:2]) <= set(items(selector)), timeout=15000)

    workspace(tmp_path / "later", BRANCHES)  # nouvel etat du poste...
    (ws / "Reader" / "PyHubreader.py").write_text(
        (tmp_path / "later" / "ws" / "Reader" / "PyHubreader.py").read_text())
    selector.showPopup()
    qtbot.waitUntil(lambda: set(BRANCHES) <= set(items(selector)), timeout=15000)
    selector.hidePopup()
