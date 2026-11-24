"""Sauvegardes IDE et copies privees : ne jamais perdre les reglages locaux."""
import os
from pathlib import Path

import pytest

from runner.domain.configuration_sync import remember_source, sync_source


@pytest.fixture
def files(tmp_path):
    source, copy = tmp_path / 'source.yml', tmp_path / 'run.yml'
    source.write_bytes(b'# original\r\nPROTOCOL: T0\r\n')
    copy.write_bytes(source.read_bytes())
    remember_source(copy, source)
    return source, copy


def test_atomic_ide_save_with_unchanged_size_and_timestamp_is_detected(files):
    source, copy = files
    stat = source.stat()
    replacement = source.with_suffix('.save')
    replacement.write_bytes(b'# original\r\nPROTOCOL: T1\r\n')
    os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    replacement.replace(source)
    state = sync_source(copy, source)
    assert state.updated and copy.read_bytes() == source.read_bytes()
    assert b'\r\n' in copy.read_bytes()
    assert not sync_source(copy, source).changed


def test_saved_local_changes_require_explicit_replacement(files):
    source, copy = files
    copy.write_text('PROTOCOL: local\n', encoding='utf-8')
    source.write_text('PROTOCOL: source\n', encoding='utf-8')
    state = sync_source(copy, source)
    assert state.changed and state.local_changed and not state.updated
    assert 'local' in copy.read_text()
    assert sync_source(copy, source, force=True).updated
    assert copy.read_bytes() == source.read_bytes()


def test_unsaved_ui_changes_prevent_automatic_replacement(files):
    source, copy = files
    previous = copy.read_bytes()
    source.write_text('PROTOCOL: T1\n')
    state = sync_source(copy, source, local_edits=True)
    assert state.changed and state.local_changed and copy.read_bytes() == previous


@pytest.mark.parametrize('source_content', [b'broken: [', b'- not a mapping\n', b'bad: \xff'])
def test_invalid_source_never_replaces_working_copy(files, source_content):
    source, copy = files
    previous = copy.read_bytes()
    source.write_bytes(source_content)
    state = sync_source(copy, source)
    assert state.problem and not state.updated and copy.read_bytes() == previous


def test_missing_source_keeps_run_usable_and_can_be_restored(files):
    source, copy = files
    previous = copy.read_bytes()
    source.unlink()
    assert sync_source(copy, source).problem
    assert copy.read_bytes() == previous
    source.write_text('PROTOCOL: T1\n')
    assert sync_source(copy, source).updated


def test_locked_runs_do_not_change_their_copy(files):
    source, copy = files
    previous = copy.read_bytes()
    source.write_text('PROTOCOL: T1\n')
    state = sync_source(copy, source, allow_update=False)
    assert state.changed and not state.updated and copy.read_bytes() == previous


def test_legacy_or_corrupt_metadata_does_not_erase_unknown_customizations(files):
    source, copy = files
    copy.with_name(copy.name + '.source.json').write_text('{broken')
    source.write_text('PROTOCOL: T1\n')
    state = sync_source(copy, source)
    assert state.changed and state.local_changed and not state.updated
    assert 'T0' in copy.read_text()


def test_duplicate_preserves_customization_when_source_changes(files, tmp_path):
    source, copy = files
    copy.write_text('PROTOCOL: local\n')
    duplicate = tmp_path / 'duplicate.yml'
    duplicate.write_bytes(copy.read_bytes())
    remember_source(duplicate, source, ancestor=copy)
    source.write_text('PROTOCOL: T1\n')
    assert sync_source(duplicate, source).local_changed
    assert 'local' in duplicate.read_text()
    assert 'local' in copy.read_text()


def test_converged_files_reestablish_the_baseline(files):
    source, copy = files
    source.write_text('PROTOCOL: T1\n')
    copy.write_bytes(source.read_bytes())
    assert not sync_source(copy, source).changed
    source.write_text('PROTOCOL: T2\n')
    assert sync_source(copy, source).updated and 'T2' in copy.read_text()


def test_standalone_source_does_not_create_a_copy(files):
    source, _ = files
    assert not sync_source(source, source).source


def test_keep_acknowledges_only_the_current_source_version(files):
    source, copy = files
    copy.write_text('PROTOCOL: custom\n')
    source.write_text('PROTOCOL: T1\n')
    assert sync_source(copy, source).changed
    state = sync_source(copy, source, keep=True)
    assert not state.changed and state.local_changed
    assert not sync_source(copy, source).changed
    assert 'custom' in copy.read_text()
    source.write_text('PROTOCOL: T2\n')
    assert sync_source(copy, source).changed


def test_import_baseline_tracks_copied_bytes_if_ide_saves_during_import(files):
    source, copy = files
    source.write_text('PROTOCOL: T1\n')
    remember_source(copy, source, ancestor=source)
    assert sync_source(copy, source).updated
    assert copy.read_bytes() == source.read_bytes()
