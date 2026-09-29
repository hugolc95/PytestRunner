import sys

from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem
from runner.ui.config_dialog import ConfigDialog, ReaderList


def editor(qtbot, tmp_path, **kwargs):
    path = tmp_path / 'config.yml'
    path.write_text('Reader: Offline\nReaders:\n  - Saved\n', encoding='utf-8')
    dialog = ConfigDialog(str(path), **kwargs)
    qtbot.addWidget(dialog)
    return dialog


def test_discovery_preserves_configuration_and_offers_dropdowns(qtbot, tmp_path):
    dialog = editor(qtbot, tmp_path)
    dialog._apply_discovered_readers(['Device A', 'Device B', 'Device A', ''])
    primary = next(f for f in dialog._champs if f.chemin == ('Reader',))
    assert primary.widget.currentText() == 'Offline'
    assert [primary.widget.itemText(i) for i in range(primary.widget.count())] == ['Offline', 'Device A', 'Device B']
    extra = next(f.widget for f in dialog._champs if isinstance(f.widget, ReaderList))
    index = extra.list.model().index(0, 0)
    delegate = extra.list.itemDelegate()
    combo = delegate.createEditor(extra.list, QStyleOptionViewItem(), index)
    delegate.setEditorData(combo, index)
    assert isinstance(combo, QComboBox) and combo.currentText() == 'Saved'
    combo.setCurrentText('Device B')
    delegate.setModelData(combo, extra.list.model(), index)
    assert extra.valeurs() == ['Device B']
    assert primary.valeur() == 'Offline'
    assert 'Offline' in dialog.path.read_text()


def test_async_discovery_success_and_dependency_error(qtbot, tmp_path, monkeypatch):
    from runner.domain import reader_discovery
    monkeypatch.setattr(reader_discovery, 'PROBE', "print('HUBREADERS_JSON:[\"Reader A\"]')")
    dialog = editor(qtbot, tmp_path, interpreter=sys.executable)
    qtbot.waitUntil(lambda: '1 available' in dialog.reader_discovery_status.text(), timeout=5000)
    assert dialog._readers_connus == ('Reader A',)
    monkeypatch.setattr(reader_discovery, 'PROBE', "raise ModuleNotFoundError(\"No module named 'six'\")")
    dialog.discover_readers()
    qtbot.waitUntil(lambda: 'six' in dialog.reader_discovery_status.text(), timeout=5000)
    assert dialog._readers_connus == ('Reader A',)
    assert dialog.discover_readers_button.isEnabled()
