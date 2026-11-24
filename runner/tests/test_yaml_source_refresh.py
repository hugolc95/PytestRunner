"""Le vrai editeur recharge la source et conserve les choix de chaque onglet."""
from pathlib import Path
import sys

import pytest
from PySide6.QtCore import Qt

from runner.domain.execution import Collection
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow


@pytest.fixture
def editor(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    source = tmp_path / 'config.yml'
    source.write_text('PROTOCOL: T0\n')
    window = MainWindow()
    qtbot.addWidget(window)
    window._interpreter_override = sys.executable
    window.workspace = Workspace.load(str(tmp_path), str(source))
    window._on_collected(Collection(('test_card.py::test_card',)))
    monkeypatch.setattr(window, 'load_workspace', lambda: None)
    window._refresh_yaml_page(force=True)
    yield window, window.yaml_editor, source
    window.close()


def test_reload_updates_source_values_used_by_the_run(editor, qtbot):
    window, dialog, source = editor
    source.write_text('PROTOCOL: T1\n')
    qtbot.mouseClick(dialog.reload_button, Qt.LeftButton)
    assert 'T1' in dialog.raw.toPlainText()
    assert window.workspace.settings['PROTOCOL'] == 'T1'
    assert not dialog.source_notice.isVisible()
    assert Path(window.workspace.config_path) != source


def test_reload_saved_local_edits_offers_keep_or_replace(editor, monkeypatch):
    window, dialog, source = editor
    dialog.path.write_text('PROTOCOL: local\n')
    dialog.reload(sync_source=False)
    source.write_text('PROTOCOL: T1\n')
    monkeypatch.setattr(dialog, '_confirm_source_reload', lambda: False)
    dialog.reload_requested()
    assert 'local' in dialog.raw.toPlainText()
    assert not dialog.source_notice.isHidden()
    monkeypatch.setattr(dialog, '_confirm_source_reload', lambda: True)
    dialog.update_from_source()
    assert window.workspace.settings['PROTOCOL'] == 'T1'
    assert dialog.path.read_bytes() == source.read_bytes()


def test_page_refresh_does_not_discard_unsaved_settings(editor, monkeypatch):
    window, dialog, source = editor
    dialog.raw.setPlainText('PROTOCOL: unsaved\n')
    source.write_text('PROTOCOL: T1\n')
    window._refresh_yaml_page(force=True)
    assert window.yaml_editor is dialog
    assert 'unsaved' in dialog.raw.toPlainText()
    assert 'T0' in dialog.path.read_text()
    monkeypatch.setattr(dialog, '_confirm_source_reload', lambda: False)
    dialog.reload_requested()
    assert 'unsaved' in dialog.raw.toPlainText()
    monkeypatch.setattr(dialog, '_confirm_source_reload', lambda: True)
    dialog.update_from_source()
    assert 'T1' in dialog.raw.toPlainText() and not dialog.has_changes()


def test_other_customized_runs_are_not_changed(editor):
    window, dialog, source = editor
    other = window.run_tabs.new_run()
    other_path = Path(other.workspace.config_path)
    other_path.write_text('PROTOCOL: other\n')
    source.write_text('PROTOCOL: T1\n')
    dialog.reload_requested()
    assert 'T1' in dialog.raw.toPlainText()
    assert 'other' in other_path.read_text()
    assert source.read_text() == 'PROTOCOL: T1\n'


def test_queued_configuration_is_kept_even_if_the_ide_saves(editor):
    window, dialog, source = editor
    entry = window.run_tabs.entry_for(window)
    previous = dialog.path.read_bytes()
    entry.state = 'waiting'
    try:
        source.write_text('PROTOCOL: T1\n')
        assert window.run_tabs.ensure_configuration(window)
        assert dialog.path.read_bytes() == previous
        state = window._sync_run_configuration(str(dialog.path), force=False)
        assert state.changed and not state.updated
        with pytest.raises(OSError, match='locked'):
            window._sync_run_configuration(str(dialog.path), force=True)
    finally:
        entry.state = 'draft'
