"""Non-regressions des defauts trouves lors de la passe de stabilite 1.8.0.

Ctrl+Z ambigu dans l'editeur de profils : couvert par
`test_profile_sequence_view` et `test_profile_editor_polish`, qui echouaient
avant la correction.
"""
import pytest
from runner.domain.execution import _couvert


@pytest.mark.parametrize("nodeid, verdicts, attendu", [
    ("t.py::test_a", {"t.py::test_a": 1}, True),
    # Fonction devenue parametree depuis la collecte : ses cas la couvrent.
    ("t.py::test_a", {"t.py::test_a[1]": 1, "t.py::test_a[2]": 1}, True),
    ("t.py", {"t.py::test_a": 1}, True),
    ("suite/", {"suite/t.py::test_a": 1}, True),
    ("suite", {"suite/t.py::test_a": 1}, True),
    ("t.py::TestA", {"t.py::TestA::test_x": 1}, True),
    # Un simple prefixe de nom n'est pas un parent.
    ("t.py::test_a", {"t.py::test_ab": 1}, False),
    ("t.py::test_a", {}, False),
])
def test_requested_parent_nodeids_are_covered_by_their_children(nodeid, verdicts, attendu):
    assert _couvert(nodeid, verdicts) is attendu



def test_profile_picker_refresh_leaves_no_stale_item_wrappers(qtbot, monkeypatch, tmp_path):
    """`model().item(row)` laissait une enveloppe Python survivre a `clear()`.

    Un QEvent alloue ensuite a la meme adresse etait pris pour ce
    QStandardItem : segfault natif en basculant Tests / Profiles.
    """
    import gc

    import shiboken6
    from PySide6.QtGui import QStandardItem

    from runner.domain.execution_profile import ExecutionProfile, ProfileStore
    from runner.domain.tree import build_tree
    from runner.domain.workspace import Workspace
    from runner.ui.main_window import MainWindow

    def item_wrappers():
        gc.collect()
        return sum(isinstance(w, QStandardItem) for w in shiboken6.getAllValidWrappers())

    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.workspace = Workspace.load(str(tmp_path))
    window._tree_workspace = window.workspace.path
    window.profiles_page.store = ProfileStore(tmp_path)
    nodeid = 'test_a.py::test_a'
    window.model.set_tree(build_tree([nodeid]))
    for name, sequence in (('Ready', [nodeid]), ('Broken', ['gone.py::test_x'])):
        window.profiles_page.store.save(ExecutionProfile(
            name=name, sequence=sequence, configuration_name='', configuration_text=''))
    before = item_wrappers()
    for _ in range(5):
        window._refresh_profile_picker()
    assert item_wrappers() == before
    assert window.profile_picker.count() == 2
    assert all(window._profile_picker_enabled(i) for i in range(2))


def test_handlers_ignore_only_objects_destroyed_during_teardown():
    from runner.ui.qt_safety import tolerate_destruction

    @tolerate_destruction(False)
    def detruit():
        raise RuntimeError("Internal C++ object (QTimer) already deleted.")

    @tolerate_destruction(False)
    def autre():
        raise RuntimeError("something else")

    assert detruit() is False
    with pytest.raises(RuntimeError, match="something else"):
        autre()
