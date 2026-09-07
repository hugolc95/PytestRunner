from PySide6.QtCore import Qt

from runner.domain.tree import group_hierarchically
from runner.domain.execution_profile import ProfileStore
from runner.ui.execution_profiles_page import AddTestsDialog, ExecutionProfilesPage


def test_picker_keeps_click_order_for_test_folder_test_folder(qtbot):
    ids = ['a/test_a.py::test_one', 'b/test_b.py::test_one',
           'b/test_b.py::test_two', 'c/test_c.py::test_one',
           'd/test_d.py::test_one', 'd/test_d.py::test_two']
    picker = AddTestsDialog(ids)
    qtbot.addWidget(picker)
    model = picker.model
    for index in [model.index_for_nodeid(ids[3]), model.index(1, 0),
                  model.index_for_nodeid(ids[0]), model.index(3, 0)]:
        model.setData(index, Qt.Checked)
    received = []
    picker.tests_added.connect(received.append)
    picker._add()
    assert received == [[ids[3], ids[1], ids[2], ids[0], ids[4], ids[5]]]
    assert picker._selection_order == []


def test_interleaved_folders_remain_ordered_after_rebuild(qtbot, tmp_path):
    ids = ['a/test_a.py::test_one', 'b/test_b.py::test_one',
           'b/nested/test_c.py::test_two', 'a/test_a.py::test_two',
           'd/test_d.py::test_one', 'd/nested/test_e.py::test_two']
    assert [n for group in group_hierarchically(ids) for n in group.nodeids] == ids
    page = ExecutionProfilesPage(ProfileStore(tmp_path))
    qtbot.addWidget(page)
    for batch in [ids[:1], ids[1:3], ids[3:4], ids[4:]]:
        page._append_tests(batch)
    assert page._flatten_sequence() == ids
    page._rebuild_sequence(ids)
    assert page._flatten_sequence() == ids
    assert any(item.childCount() for item, _, _ in page._sequence_ranges()[1]
               if item.parent() is not None)
