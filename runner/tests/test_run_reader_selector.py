import sys

from PySide6.QtCore import QSettings

from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.reader_selector import ReaderSelector


def test_discovery_keeps_primary_and_manual_input(qtbot, tmp_path, monkeypatch):
    from runner.domain import reader_discovery
    monkeypatch.setattr(reader_discovery, "PROBE", 'print(\'HUBREADERS_JSON:["Device A", "Device B"]\')')
    selector = ReaderSelector()
    qtbot.addWidget(selector)
    selector.set_context(str(tmp_path), sys.executable, "Saved")
    qtbot.waitUntil(lambda: "2 available" in selector.toolTip(), timeout=5000)
    assert selector.currentText() == "Saved"
    assert "Device B" in [selector.itemText(i) for i in range(selector.count())]
    with qtbot.waitSignal(selector.committed) as signal:
        selector.setCurrentText("Manual reader")
        selector.lineEdit().editingFinished.emit()
    assert signal.args == ["Manual reader"]
    selector.stop_discovery()


def test_primary_reader_save_preserves_other_settings_and_opens_config(qtbot, tmp_path, monkeypatch):
    QSettings(ORG, APP).clear()
    path = tmp_path / "config.yml"
    path.write_text("hardware:\n  Reader: Old # keep\nReaders: [Extra]\nComponent: PQC\n", encoding="utf-8")
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    monkeypatch.setattr(window, "_effective_interpreter", lambda: "")
    reloaded = []
    monkeypatch.setattr(window, "load_workspace", lambda: reloaded.append(True))
    window._update_actions()
    assert window.reader_selector.currentText() == "Old"
    window.reader_selector.setCurrentText("New")
    window.reader_selector.activated.emit(0)
    assert path.read_text() == "hardware:\n  Reader: New # keep\nReaders: [Extra]\nComponent: PQC\n"
    assert window.workspace.readers[0].name == "New"
    assert reloaded == [True]
    window.reader_config_button.click()
    assert window.pages.currentWidget() is window.yaml_page
    assert next(f for f in window.yaml_editor._champs if f.chemin == ("hardware", "Reader")).valeur() == "New"
    window.close()


def test_reader_is_locked_during_run(qtbot, tmp_path, monkeypatch):
    QSettings(ORG, APP).clear()
    (tmp_path / "config.yml").write_text("Reader: Old\n", encoding="utf-8")
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    monkeypatch.setattr(window, "_effective_interpreter", lambda: "")
    window._refresh_primary_reader(busy=True)
    assert not window.reader_selector.isEnabled()
    window._refresh_primary_reader(busy=False)
    assert window.reader_selector.isEnabled()
    window.close()
