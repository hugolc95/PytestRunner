"""Run cards and progress labels must not jump while outcomes arrive."""
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from runner.domain.execution import Collection
from runner.domain.models import Outcome, Reader, RunRequest, Status
from runner.domain.workspace import Workspace
from runner.ui.main_window import MainWindow
from runner.ui.run_tabs_strip import RunTabBar


def test_run_tab_width_does_not_depend_on_name_count_or_state(qtbot):
    tabs = RunTabBar()
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    tabs.setFont(QFont('Segoe UI', 10))
    qtbot.addWidget(tabs)
    tabs.setExpanding(False)
    tabs.addTab('New run · Draft · 2 selected')
    tabs.resize(500, 48)
    tabs.show()
    widths = set()
    for text in ('New run · Draft · 2 selected', 'New run · Running 9/10',
                 'New run · Running 10000/10000', 'New run · Completed · 10000 passed',
                 'Long qualification campaign name · Running 1/10000'):
        tabs.setTabText(0, text)
        widths.add(tabs.tabSizeHint(0).width())
        widths.add(tabs.tabRect(0).width())
    assert len(widths) == 1, widths


def test_narrow_tab_bar_keeps_card_width_instead_of_compressing_cards(qtbot):
    tabs = RunTabBar()
    qtbot.addWidget(tabs)
    tabs.setExpanding(False)
    tabs.setUsesScrollButtons(True)
    for number in range(4):
        tabs.addTab(f'New run {number} · Running 10/100')
    tabs.resize(330, 48)
    tabs.show()
    assert {tabs.tabRect(i).width() for i in range(4)} == {RunTabBar.TAB_WIDTH}


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    monkeypatch.setattr(MainWindow, '_refresh_primary_reader', lambda *_, **__: None)
    widget = MainWindow()
    qtbot.addWidget(widget)
    widget.workspace = Workspace(str(tmp_path), settings={'Reader': 'A', 'Readers': ['B']})
    widget._on_collected(Collection(('test_card.py::test_a', 'test_card.py::test_b')))
    widget.show()
    yield widget
    widget.close()


def test_every_progress_write_uses_fraction_including_delayed_refresh(window, qtbot, monkeypatch):
    writes = []
    original = window.compass_pct.setText
    def record(text):
        writes.append(text)
        original(text)
    monkeypatch.setattr(window.compass_pct, 'setText', record)
    nodes = tuple(window.model._by_nodeid)
    request = RunRequest(window.workspace.path, sys.executable, nodes,
                         (Reader('A', 0), Reader('B', 1)))
    window._on_run_started(request)
    for outcome in (Outcome(nodes[0], Status.PASSED, 0), Outcome(nodes[1], Status.FAILED, 0),
                    Outcome(nodes[0], Status.SKIPPED, 1)):
        window._on_outcome(outcome)
    window._profile_counts_timer.start()
    qtbot.waitUntil(lambda: not window._profile_counts_timer.isActive())
    assert window.compass_pct.text() == '3 / 4'
    assert not any('%' in text for text in writes), writes
    window._on_outcome(Outcome(nodes[1], Status.NOT_RUN, 1))
    window._rafraichir_compteurs()
    assert window.compass_pct.text() == '3 / 4'


def test_run_and_configuration_tabs_stay_same_width_during_progress(window):
    controller = window.run_tabs
    entry = controller.entry_for(window)
    entry.state = 'running'
    widths = []
    for done, total in ((0, 2), (9, 10), (99, 100), (1000, 10000)):
        entry.progress = done, total
        controller.refresh_labels()
        widths.append((controller.tabs.tabRect(0).width(),
                       window.configuration_tabs.tabSizeHint(0).width()))
    entry.state = 'draft'
    assert len(set(widths)) == 1, widths


def test_profile_fraction_excludes_not_run_and_tracks_its_own_total(window):
    window._main_run_total = 100
    window._profile_count_statuses = {}
    window._profile_execution_total = 12
    window._profile_verdict_counts = {Status.PASSED: 2, Status.FAILED: 1, Status.NOT_RUN: 1}
    window._rafraichir_compteurs()
    assert window.compass_pct.text() == '3 / 12'


def test_repeat_run_keeps_previous_results_fraction(window):
    window._main_run_total = 4
    window._stress_previous_counts = {Status.PASSED: 2, Status.FAILED: 1}
    window._stress_previous_completed = 3
    window._stress_counts = {Status.PASSED: 7}
    window._rafraichir_compteurs()
    assert window.compass_pct.text() == '3 / 4'
