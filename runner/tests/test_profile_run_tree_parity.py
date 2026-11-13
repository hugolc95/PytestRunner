"""Les profils gardent leurs occurrences avec les gestes de l'arbre classique."""
import copy
import sys
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile, ExecutionOptions
from runner.domain.models import Kind, Reader, ReaderReport, Status
from runner.domain.tree import build_tree, collapse_single_class
from runner.domain.workspace import Workspace
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.main_window import MainWindow
from runner.ui.tree_model import TestTreeModel
from runner.ui.widgets import SCOPE_FAILURES


NODES = ['Card/test_card.py::TestCard::test_connect',
         'Card/test_card.py::TestCard::test_select[T0]',
         'Card/test_card.py::TestCard::test_select[T1]',
         'Cleanup/test_cleanup.py::test_close']
READERS = (Reader('Reader A', 0), Reader('Reader B', 2))


def profile(nodes=None, repetitions=1, **options):
    return ExecutionProfile('Card qualification', list(nodes or NODES), '', '',
                            execution=ExecutionOptions(repetitions=repetitions), **options)


def shape(model):
    def visit(row):
        return row.node.name, row.node.kind, [visit(child) for child in row.children]
    return [visit(row) for row in model._roots]


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    w = MainWindow()
    qtbot.addWidget(w)
    for name in ('Card/test_card.py', 'Cleanup/test_cleanup.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('class TestCard:\n    def test_connect(self): pass\n')
    w.workspace = Workspace.load(str(tmp_path))
    w._on_collected(Collection(tuple(NODES)))
    w._open_collected_profile(profile())
    yield w
    w.close()


def test_same_hierarchy_labels_and_parameter_cases_as_classic():
    classic, live = TestTreeModel(), LiveProfileModel()
    classic.set_tree(collapse_single_class(build_tree(NODES)))
    live.prepare(profile(), READERS)
    assert shape(live) == shape(classic)
    assert all(row.node.kind is not Kind.CLASS for root in live._roots for row in [root, *root.descendants()])
    assert live.locations['1:0'][2] == NODES[1]
    assert live.index_for_nodeid('0:0').data() == 'test_connect'


def test_multiple_classes_remain_distinguishable_like_classic():
    nodes = ['a.py::TestA::test_same', 'a.py::TestB::test_same']
    classic, live = TestTreeModel(), LiveProfileModel()
    classic.set_tree(collapse_single_class(build_tree(nodes)))
    live.prepare(profile(nodes), ())
    assert shape(live) == shape(classic)
    assert [row.node.name for row in live._roots[0].children] == ['TestA', 'TestB']


def test_order_duplicates_groups_and_repetitions_are_preserved():
    nodes = [NODES[0], NODES[3], NODES[0], NODES[1]]
    group = dict(id='cards', name='Card group', color='#448aff', description='Qualification')
    live = LiveProfileModel()
    live.prepare(profile(nodes, repetitions=2, step_groups=[group] * 4), READERS)
    assert list(live.locations.values()) == [(i, 0, node) for i, node in enumerate(nodes * 2)]
    assert [row.node.name for row in live._roots] == ['Repetition 1 / 2', 'Repetition 2 / 2']
    assert live._roots[0].children[0].children[0].node.name == 'Card'
    assert 'Occurrence 5' in live.index_for_nodeid('4:0').data(Qt.ToolTipRole)


def test_duration_columns_and_modes_match_classic_with_sparse_reader_indices():
    live = LiveProfileModel()
    live.prepare(profile([NODES[0], NODES[0]]), READERS)
    assert live.columnCount() == 4 and live.duration_column == 3
    live.set_duration('0:0', 0, 1)
    live.set_duration('0:0', 2, 3)
    live.set_duration('1:0', 0, 2)
    for mode, expected in [('slowest', 3), ('fastest', 1), ('average', 2), ('spread', 2), ('reader:Reader B', 3)]:
        live.set_duration_mode(mode)
        assert live.duration_for_nodeid('0:0') == expected
    assert live.reader_durations(live._roots[0]) == {0: 3, 2: 3}
    live.apply_execution(0, 1, 0, NODES[0], Status.PASSED)
    live.set_duration('0:1', 0, 4)
    assert live.reader_durations(live._roots[0])[0] == 7


def test_checkboxes_are_per_occurrence_and_retry_rows_are_not_selections():
    live = LiveProfileModel()
    live.prepare(profile([NODES[0], NODES[0]]), READERS)
    assert live.counts() == (2, 2)
    live.setData(live.index_for_nodeid('0:0'), Qt.Unchecked, Qt.CheckStateRole)
    assert live.checked_nodeids() == ['1:0']
    assert live.index(0, 0).data(Qt.CheckStateRole) == Qt.PartiallyChecked
    live.apply_execution(0, 1, 0, NODES[0], Status.ERROR)
    assert not live.flags(live.index_for_nodeid('0:1')) & Qt.ItemIsUserCheckable
    assert live.counts() == (1, 2)
    live.set_checked_nodeids(['0:1'])
    assert live.checked_nodeids() == ['0:0']


def test_group_selection_shows_counts_source_and_exact_failure_link(window, qtbot):
    w = window
    w._on_profile_execution(1, 0, 0, NODES[1], Status.FAILED)
    w._on_profile_test_detail(1, 0, 0, dict(kind='test', nodeid=NODES[1], phase='call',
                                         message='live failure', body='live failure'))
    module = w.profile_model.index_for_nodeid('0:0').parent()
    w.profile_tree.setCurrentIndex(module)
    w._select_profile_execution(module)
    assert w.profile_results.detail.group_name.text() == 'test_card.py'
    assert '3 tests' in w.profile_results.detail.group_total.text()
    assert w.profile_results.detail.failures.item(0).data(Qt.UserRole) == '1:0'
    w.profile_results.test_chosen.emit('1:0')
    assert w._profile_selected_key == '1:0'
    assert 'live failure' in w.profile_results.detail.body.toPlainText()


def test_duration_preferences_and_header_menu_target_visible_tree(window):
    w = window
    menu = QMenu()
    w._ajouter_actions_colonnes(menu)
    assert menu.actions()[0].text() == 'Show Duration column'
    w.set_duration_column_visible(False)
    assert w.profile_tree.isColumnHidden(w.profile_model.duration_column)
    assert w.tree.isColumnHidden(w.model.duration_column)
    w.set_duration_mode('average')
    assert w.profile_model.duration_mode == w.model.duration_mode == 'average'
    w.set_duration_column_visible(True)
    assert not w.profile_tree.isColumnHidden(w.profile_model.duration_column)


def test_selection_controls_do_not_modify_classic_checkboxes(window):
    w = window
    before = w.model.checked_nodeids()
    w.select_none_button.click()
    assert w.profile_model.checked_nodeids() == []
    assert w.model.checked_nodeids() == before
    assert not w.run_button.isEnabled()
    w.select_all_button.click()
    assert w.profile_model.counts() == (4, 4)
    assert w.run_button.isEnabled()


def test_context_menu_launch_preserves_yaml_order_and_master_profile(window, monkeypatch):
    w = window
    group = dict(id='t1', name='T1', color='#448aff', description='', configuration_overrides={'protocol': 'T1'})
    original = profile([NODES[0], NODES[0]], step_groups=[group, group],
                       step_overrides=[{'timeout': 10}, {'timeout': 30}])
    w._open_collected_profile(original)
    before = copy.deepcopy(original)
    captured = []
    fake = SimpleNamespace(_open_collected_profile=captured.append, run_selected=lambda: captured.append('start'))
    monkeypatch.setattr(w.run_tabs, 'new_run', lambda source: fake)
    menu = w.profile_run_tree.menu(w.profile_model.index_for_nodeid('1:0'))
    menu.actions()[0].trigger()
    assert captured[0].sequence == [NODES[0]]
    assert captured[0].step_overrides == [{'timeout': 30}]
    assert captured[0].step_groups == [group]
    assert captured[1] == 'start'
    assert original == before
    assert w.profile_model.counts() == (2, 2)


def test_failure_search_includes_live_traces_and_uses_occurrence_keys(window):
    w = window
    w._on_profile_execution(1, 0, 0, NODES[1], Status.FAILED)
    w._on_profile_test_detail(1, 0, 0, dict(kind='test', nodeid=NODES[1], phase='call',
                                         message='APDU failure', body='APDU failure'))
    w.search._set_scope(SCOPE_FAILURES)
    w.search.field.setText('APDU')
    w._on_search('APDU')
    assert w._matches == ['1:0']
    assert w.failure_results.count() == 1
    assert w.failure_results.item(0).data(Qt.UserRole) == '1:0'
    assert w._profile_selected_key == '1:0'


def test_plain_names_still_keep_full_source_and_class_nodeids(window):
    w = window
    w._reveal_search_match('1:0')
    assert w.profile_results._nodeid == NODES[1]
    assert w.profile_model.activation_target(w.profile_model.index_for_nodeid('1:0')) == NODES[1]
    assert w.profile_model.activation_target(w.profile_model.index_for_nodeid('1:0').parent()) == NODES[1].split('[')[0]


def test_reader_feedback_uses_the_emitting_panel_and_sparse_reader_positions(window):
    w = window
    w.profile_results.set_readers(READERS)
    w.results.set_readers((Reader('Classic reader', 7),))
    w.profile_results.reader_selected.emit(1)
    assert w.status_label.text() == 'Showing Reader B'
    w.results.reader_selected.emit(0)
    assert w.status_label.text() == 'Showing Classic reader'


def test_detail_source_output_logs_shortcuts_follow_profile_view(window, qtbot):
    w = window
    w.show()
    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow)
    w._reveal_search_match('0:0')
    w.profile_tree.setFocus()
    for key, expected in ((Qt.Key_2, 1), (Qt.Key_3, 2), (Qt.Key_4, 3), (Qt.Key_1, 0)):
        qtbot.keyClick(w.profile_tree, key, Qt.ControlModifier)
        assert w.profile_results.tabs.currentIndex() == expected
    qtbot.keyRelease(w.profile_tree, Qt.Key_Control)
    assert w.results.tabs.currentIndex() == 0


def test_real_partial_run_keeps_duplicate_yaml_occurrences_and_original_selection(window, qtbot, tmp_path):
    w = window
    path = tmp_path / 'Card/test_card.py'
    path.write_text('''import os, json, yaml
from pathlib import Path
class TestCard:
    def test_repeat(self):
        value = yaml.safe_load(Path(os.environ['PYTESTRUNNER_READER_CONFIG']).read_text())
        with Path('received.jsonl').open('a') as stream:
            stream.write(json.dumps(value) + '\\n')
''')
    node = 'Card/test_card.py::TestCard::test_repeat'
    w._on_collected(Collection((node,)))
    original = ExecutionProfile('Repeated YAML', [node] * 3, 'settings.yaml', 'timeout: 15\n',
                                step_overrides=[{'timeout': 10}, {'timeout': 20}, {'timeout': 30}])
    w._open_collected_profile(original)
    w._interpreter_override = sys.executable
    w.profile_model.set_checked_nodeids(['0:0', '2:0'])
    w.run_selected()
    context = w.run_tabs.current.context
    assert context is w
    try:
        qtbot.waitUntil(lambda: not context.service.busy, timeout=25000)
        qtbot.waitUntil(lambda: w.run_tabs.active is None, timeout=15000)
        received = [json.loads(line)['timeout'] for line in (tmp_path / 'received.jsonl').read_text().splitlines()]
        assert received == [10, 30]
        assert w.profile_model.checked_nodeids() == ['0:0', '2:0']
        assert w._active_execution_profile is original
        assert original.sequence == [node] * 3
        assert len(w.profile_model.locations) == 3
        assert w.profile_model.statuses_for_nodeid('2:0')[0] is Status.PASSED
        assert w.profile_model.statuses_for_nodeid('1:0').get(0, Status.PENDING) is Status.PENDING
    finally:
        context.service.cancel()
        context.service.wait()


def test_profile_selection_is_saved_and_restored_with_session(window, qtbot):
    w = window
    w.profile_model.set_checked_nodeids(['1:0', '3:0'])
    w.run_tabs.save_sessions()
    saved = json.loads(w.settings.value('runs/session'))
    assert saved[0]['profile_checked'] == ['1:0', '3:0']
    restored = MainWindow()
    qtbot.addWidget(restored)
    try:
        restored.run_tabs.restore_sessions()
        assert restored.profile_model.checked_nodeids() == ['1:0', '3:0']
    finally:
        restored.close()


def test_rerun_failed_uses_latest_reader_attempt_and_profile_occurrence(window, monkeypatch):
    w = window
    w._on_profile_execution(0, 0, 0, NODES[0], Status.FAILED)
    w._on_profile_execution(0, 1, 0, NODES[0], Status.PASSED)
    w._on_profile_execution(1, 0, 0, NODES[1], Status.ERROR)
    called = []
    monkeypatch.setattr(w.profile_run_tree, 'launch', called.append)
    w.rerun_failed()
    assert called == [['1:0']]


def test_running_branch_repaints_name_and_preserves_other_reader(window):
    model = window.profile_model
    model.set_readers(READERS)
    changed = []
    model.dataChanged.connect(lambda first, last, *_: changed.append((first.column(), first.internalPointer())))
    model.apply_execution(0, 0, 0, NODES[0], Status.RUNNING)
    leaf = model.index_for_nodeid('0:0')
    assert (0, leaf.internalPointer()) in changed
    model.apply_execution(0, 0, 2, NODES[0], Status.RUNNING)
    model.apply_execution(0, 0, 0, NODES[0], Status.PASSED)
    assert leaf.data(Qt.ForegroundRole) is not None
    model.apply_execution(0, 0, 2, NODES[0], Status.PASSED)
    assert leaf.data(Qt.ForegroundRole) is None


def test_profile_context_signal_opens_one_complete_menu(window, qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    w = window
    w.show()
    w.profile_tree.expandAll()
    qtbot.waitUntil(lambda: w.profile_tree.visualRect(w.profile_model.index_for_nodeid('0:0')).isValid())
    seen = []
    timer = QTimer()
    def close_menu():
        menu = QApplication.activePopupWidget()
        if isinstance(menu, QMenu):
            seen.append([action.text() for action in menu.actions()])
            menu.close()
    timer.timeout.connect(close_menu)
    timer.start(10)
    try:
        point = w.profile_tree.visualRect(w.profile_model.index_for_nodeid('0:0')).center()
        w.profile_tree.customContextMenuRequested.emit(point)
    finally:
        timer.stop()
    assert len(seen) == 1
    assert 'Run only this test' in seen[0]
    assert 'Copy nodeid' in seen[0]
    assert 'Copy failure trace' in seen[0]
