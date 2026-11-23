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


def test_a_new_yaml_editor_reuses_the_readers_found_this_session(qtbot, tmp_path, monkeypatch):
    """Chaque editeur YAML (un par run) relancait Python et le framework avant
    de proposer un lecteur : la liste restait vide plusieurs secondes. Les
    lecteurs trouves sont repris aussitot ; « Refresh » les reinterroge."""
    from runner.domain import reader_discovery
    from runner.ui import config_dialog
    monkeypatch.setattr(reader_discovery, 'PROBE', "print('HUBREADERS_JSON:[\"Reader A\", \"Reader B\"]')")
    premier = editor(qtbot, tmp_path, interpreter=sys.executable)
    qtbot.waitUntil(lambda: '2 available' in premier.reader_discovery_status.text(), timeout=5000)

    lances = []
    monkeypatch.setattr(config_dialog.ConfigDialog, 'discover_readers', lambda self: lances.append(self))
    second = editor(qtbot, tmp_path, interpreter=sys.executable)
    qtbot.wait(20)
    assert lances == []
    assert second._readers_connus == ('Reader A', 'Reader B')
    assert '2 available' in second.reader_discovery_status.text()

    # Un autre interpreteur n'a rien trouve encore : il cherche.
    autre = editor(qtbot, tmp_path, interpreter=sys.executable + '-other')
    qtbot.waitUntil(lambda: lances == [autre], timeout=2000)
