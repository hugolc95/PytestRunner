from time import perf_counter

from PySide6.QtCore import Qt

from runner.domain.tree import build_tree
from runner.domain.models import Status
from runner.ui.tree_model import TestTreeModel


def test_50000_results_and_cached_group_paint(qtbot):
    model = TestTreeModel()
    start = perf_counter()
    ids = [f'test_big.py::test_case[{i}]' for i in range(50000)]
    model.set_tree(build_tree(ids))
    root = model.index(0, 0)
    assert model.data(root, Qt.CheckStateRole) == Qt.Checked
    # Once cached, repeated paints must not descend into the 50,000 cases.
    cached = model._roots[0].check_cache
    assert cached == Qt.Checked
    signals = []
    model.dataChanged.connect(lambda *args: signals.append(1))
    for nodeid in ids:
        model.apply_outcome(nodeid, Status.PASSED, 0)
        assert model.data(root, Qt.CheckStateRole) == Qt.Checked
    assert model.done() == 50000
    assert len(signals) < 50010
    print(f'50000 collection + outcomes + cached paints: {perf_counter() - start:.2f}s')
    model.set_all_checked(False)
    assert model.data(root, Qt.CheckStateRole) == Qt.Unchecked
    model.set_checked_nodeids(ids[:1])
    assert model.data(root, Qt.CheckStateRole) == Qt.PartiallyChecked
    model.set_tree(build_tree(ids[:1]))
    assert model.done() == 0


def test_large_run_start_and_live_window(qtbot, monkeypatch):
    from runner.ui.main_window import MainWindow
    from runner.domain.models import RunRequest, Outcome
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    ids = tuple(f'test_big.py::test_case[{i}]' for i in range(50000))
    window.model.set_tree(build_tree(ids))
    window.show()
    qtbot.wait(20)
    start = perf_counter()
    window._on_run_started(RunRequest(workspace='', interpreter='python', nodeids=ids, readers=()))
    print(f'50000 UI run start: {perf_counter() - start:.2f}s')
    start = perf_counter()
    for i, nodeid in enumerate(ids):
        window._on_outcome(Outcome(nodeid=nodeid, status=Status.PASSED, reader_index=0))
        window._on_progress(i + 1, len(ids))
        if i % 500 == 0:
            qtbot.wait(1)
    window._show_failure_actions([])
    window._elapsed.stop()
    assert window.progress.value() == 50000
    print(f'50000 UI live results with event processing: {perf_counter() - start:.2f}s')
