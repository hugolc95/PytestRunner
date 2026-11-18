"""Comparer a part sans perdre le contexte ni modifier les logs principaux."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPlainTextEdit

from runner.domain.models import Reader
from runner.ui.results_panel import ResultsPanel, ONGLET_LOGS


@pytest.fixture
def source(qtbot, tmp_path):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(500, 650)
    panel.set_readers((Reader('Reader A', 0), Reader('Reader B', 4)))
    panel.set_log_root(tmp_path)
    panel.show_tab(ONGLET_LOGS)
    panel.show()
    yield panel
    panel.close_comparison()


def select(source, tmp_path, test):
    files = {}
    for reader in source._readers:
        file = tmp_path / f'{test}-{reader.index}.log'
        file.write_text(f'INFO - {test}\nINFO - APDU 9000\n' +
                        ('ERROR - timeout\n' if reader.index == 4 else 'INFO - ready\n'))
        files[reader.index] = file
    source.set_log_files(files)
    source.show_test(f'test_card.py::{test}', {}, workspace=str(tmp_path))
    return files


def test_comparison_follows_selection_and_keeps_searches_independent(source, tmp_path, qtbot):
    select(source, tmp_path, 'test_a')
    source.logs.views[0].search.field.setText('ready')
    source.logs.compare.click()
    window = source._comparison_window
    assert window.isWindow() and window.isVisible()
    assert window.readers._readers == source._readers
    window.readers.views[0].search.field.setText('APDU')
    window.readers.views[0].search.refresh()
    assert window.readers.views[0].search.counter.text() == '1/1'
    assert source.logs.views[0].search.field.text() == 'ready'
    select(source, tmp_path, 'test_b')
    qtbot.waitUntil(lambda: window._snapshot[0].endswith('test_b'))
    assert 'test_b' in window.readers.views[1].text()
    assert window.readers.views[0].search.field.text() == 'APDU'
    assert not source.logs.compare.isChecked()
    assert not source.logs.tabs.isHidden()
    assert sum(not view.parentWidget().isHidden() for view in source.logs.views) == 1


def test_pin_keeps_logs_and_files_until_explicitly_loading_another_test(source, tmp_path, qtbot, monkeypatch):
    first_files = select(source, tmp_path, 'test_a')
    source.open_log_comparison()
    window = source._comparison_window
    window.follow.setChecked(False)
    select(source, tmp_path, 'test_b')
    qtbot.waitUntil(lambda: not source._comparison_timer.isActive())
    assert window._snapshot[0].endswith('test_a')
    assert 'test_a' in window.readers.views[1].text()
    opened = []
    monkeypatch.setattr('runner.ui.log_comparison.open_in_notepad_plus_plus',
                        lambda parent, path: opened.append(path))
    window.readers.open_buttons[1].click()
    assert opened == [first_files[4]]
    source.open_log_comparison()
    assert source._comparison_window is window and window._snapshot[0].endswith('test_a')
    window.load_selected.click()
    assert window._snapshot[0].endswith('test_b')
    assert not window.follow.isChecked()
    select(source, tmp_path, 'test_c')
    window.follow.setChecked(True)
    assert window._snapshot[0].endswith('test_c')


def test_shortcut_reuses_window_and_close_restores_launcher(source, tmp_path, qtbot):
    select(source, tmp_path, 'test_a')
    source.logs.toggle_compare()
    first = source._comparison_window
    source.logs.toggle_compare()
    assert source._comparison_window is first
    first.close()
    assert source._comparison_window is None
    assert source.logs.compare.text() == 'Compare…'
    qtbot.waitUntil(lambda: not source._comparison_timer.isActive())
    source.logs.compare.click()
    assert source._comparison_window is not first
    assert source._comparison_window.readers.views[0].text() == source.logs.views[0].text()


def test_window_controls_apply_to_all_compared_logs_without_changing_main(source, tmp_path):
    select(source, tmp_path, 'test_a')
    source.open_log_comparison()
    views = source._comparison_window.readers
    views.wrap_all.click()
    assert all(view.view.lineWrapMode() == QPlainTextEdit.WidgetWidth for view in views.views)
    assert all(view.view.lineWrapMode() == QPlainTextEdit.NoWrap for view in source.logs.views)
    views.set_compare_layout(Qt.Horizontal)
    assert views.split.orientation() == Qt.Horizontal
    assert not views.difference_navigation.isHidden()
    assert views._difference_groups


def test_same_test_in_another_campaign_step_updates_comparison_context(source, tmp_path, qtbot):
    select(source, tmp_path, 'test_a')
    source._comparison_context = 'Repetition 1/2 · Step 1/3'
    source.open_log_comparison()
    window = source._comparison_window
    assert 'Step 1/3' in window.test_label.text()
    source._comparison_context = 'Repetition 2/2 · Step 3/3'
    select(source, tmp_path, 'test_a')
    qtbot.waitUntil(lambda: 'Step 3/3' in window.test_label.text())


def test_immediate_close_of_window_with_hidden_owner_is_safe(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_readers((Reader('A', 0), Reader('B', 1)))
    panel.logs.set_text(0, 'INFO - ready')
    panel.logs.set_text(1, 'ERROR - failed')
    for _ in range(5):
        panel.open_log_comparison()
        window = panel._comparison_window
        destroyed = []
        window.destroyed.connect(lambda: destroyed.append(True))
        window.close()
        qtbot.waitUntil(lambda: bool(destroyed))
        assert panel._comparison_window is None
    panel.show()
    panel.open_log_comparison()
    assert panel._comparison_window.readers.views[1].text() == 'ERROR - failed'
    panel.close_comparison()


def test_destroying_the_source_closes_its_comparison(qtbot):
    from shiboken6 import isValid
    panel = ResultsPanel()
    panel.set_readers((Reader('A', 0), Reader('B', 1)))
    panel.open_log_comparison()
    window = panel._comparison_window
    panel.deleteLater()
    qtbot.waitUntil(lambda: not isValid(window))


def test_recollecting_other_readers_does_not_relabel_previous_logs(source, tmp_path, qtbot):
    select(source, tmp_path, 'test_a')
    source.open_log_comparison()
    window = source._comparison_window
    source.set_readers((Reader('Other A', 0), Reader('Other B', 1)))
    qtbot.waitUntil(lambda: window.readers._readers == source._readers)
    assert window.test_label.text() == 'No test selected'
    assert all(not view.text() for view in window.readers.views[:2])
