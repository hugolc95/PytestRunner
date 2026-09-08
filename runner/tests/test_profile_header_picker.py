from types import SimpleNamespace

from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.domain.tree import build_tree
from runner.ui.main_window import MainWindow


def make_window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.profiles_page.store = ProfileStore(tmp_path)
    return window


def test_open_from_execution_profiles_clears_old_result_filter(qtbot, monkeypatch, tmp_path):
    from runner.domain.models import Status

    window = make_window(qtbot, monkeypatch, tmp_path)
    nodeid = 'test_a.py::test_a'
    window.model.set_tree(build_tree([nodeid]))
    first = ExecutionProfile(name='First', sequence=[nodeid], configuration_name='', configuration_text='')
    second = ExecutionProfile(name='Second', sequence=[nodeid, nodeid], configuration_name='', configuration_text='')
    window._load_execution_profile(first)
    window.filter_by_status(Status.FAILED)
    assert window.profile_tree.isRowHidden(0, window.profile_model.index(0, 0).parent())
    monkeypatch.setattr(window.profiles_page, '_profile_from_editor', lambda: second)
    window.profiles_page.open_in_run_tests()
    assert window._status_filter is None
    assert len(window.profile_model.locations) == 2
    assert window.left_stack.currentWidget() is window.profile_tree
    index = window.profile_model.index_for_nodeid('0:0')
    while index.isValid():
        assert not window.profile_tree.isRowHidden(index.row(), index.parent())
        index = index.parent()
    window.filter_by_status(Status.ERROR)
    window.profiles_page.open_in_run_tests()  # Reopening the same profile also works.
    assert window._status_filter is None
    assert not window.profile_tree.isRowHidden(0, window.profile_model.index(0, 0).parent())


def test_header_profiles_preview_compatibility_and_run_target(qtbot, monkeypatch, tmp_path):
    window = make_window(qtbot, monkeypatch, tmp_path)
    good = ExecutionProfile(name='Smoke', sequence=['test_a.py::test_a'], configuration_name='', configuration_text='')
    bad = ExecutionProfile(name='Other workspace', sequence=['test_other.py::test_missing'], configuration_name='', configuration_text='')
    window.profiles_page.store.save(good)
    window.profiles_page.store.save(bad)
    window.model.set_tree(build_tree(['test_a.py::test_a']))
    window._set_profile_tree_visible(False)
    assert not window.tree_view_switch.isHidden()
    assert window.tree_view_switch.parentWidget() is window.tree.header().viewport()
    window._refresh_profile_picker()
    unavailable = [window.profile_picker.model().item(i) for i in range(window.profile_picker.count())
                   if 'Incompatible' in window.profile_picker.itemText(i)]
    assert len(unavailable) == 1 and not unavailable[0].isEnabled()
    window._open_profile_view()
    assert window._active_execution_profile.name == 'Smoke'
    assert window.profile_model.locations['0:0'][2] == 'test_a.py::test_a'
    assert window.tree_view_switch.parentWidget() is window.profile_tree.header().viewport()
    assert window.profile_chip.isHidden()
    launches = []
    monkeypatch.setattr(window, '_start_profile', lambda value: launches.append(value.name))
    monkeypatch.setattr(window, '_start', lambda nodes: launches.append(nodes))
    window.run_selected()
    window._set_profile_tree_visible(False)
    window.run_selected()
    assert launches == ['Smoke', ['test_a.py::test_a']]


def test_profiles_cannot_replace_the_active_run(qtbot, monkeypatch, tmp_path):
    window = make_window(qtbot, monkeypatch, tmp_path)
    window.model.set_tree(build_tree(['test_a']))
    first = ExecutionProfile(name='First', sequence=['test_a'], configuration_name='', configuration_text='')
    second = ExecutionProfile(name='Second', sequence=['test_a'], configuration_name='', configuration_text='')
    window._load_execution_profile(first)
    window._stress_worker = SimpleNamespace()
    window._load_execution_profile(second)
    assert window._active_execution_profile.name == 'First'
    window._stress_worker = None


def test_no_saved_profiles_has_an_explicit_empty_state(qtbot, monkeypatch, tmp_path):
    window = make_window(qtbot, monkeypatch, tmp_path)
    window.model.set_tree(build_tree(['test_a']))
    window._open_profile_view()
    assert 'No compatible profile' in window.profile_selection_label.text()
    assert not window.run_button.isEnabled()


def test_switching_modes_keeps_tree_controls_and_detail_tabs_in_place(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QPoint

    window = make_window(qtbot, monkeypatch, tmp_path)
    window.model.set_tree(build_tree(['test_a.py::test_a']))
    profile = ExecutionProfile(name='A long profile name that should not resize the layout',
                               sequence=['test_a.py::test_a'],
                               configuration_name='', configuration_text='')
    window._load_execution_profile(profile)
    window.resize(1400, 900)
    window.show()

    def position(widget):
        return widget.mapTo(window, QPoint(0, 0))

    window._set_profile_tree_visible(False)
    qtbot.wait(50)
    classic = (window.left_stack.geometry(), position(window.classic_tree_button),
               window.classic_tree_button.size(), position(window.profile_tree_button),
               window.profile_tree_button.size(), position(window.results.tabs),
               window.run_button.geometry())
    window._set_profile_tree_visible(True)
    qtbot.wait(50)
    profiled = (window.left_stack.geometry(), position(window.classic_tree_button),
                window.classic_tree_button.size(), position(window.profile_tree_button),
                window.profile_tree_button.size(), position(window.profile_results.tabs),
                window.run_button.geometry())
    assert profiled == classic
    window._set_profile_tree_visible(False)
    qtbot.wait(50)
    assert window.left_stack.geometry() == classic[0]


def test_profile_search_and_repeated_switches_keep_the_correct_tree(qtbot, monkeypatch, tmp_path):
    window = make_window(qtbot, monkeypatch, tmp_path)
    nodeid = 'test_a.py::test_a'
    window.model.set_tree(build_tree([nodeid]))
    profile = ExecutionProfile(name='Smoke', sequence=[nodeid, nodeid],
                               configuration_name='', configuration_text='')
    window._load_execution_profile(profile)
    window.show()
    window.search.field.setText('test_a')
    window._on_search('test_a')
    assert window._matches == ['0:0', '1:0']
    window._goto_match(1)
    assert window._profile_selected_key == '1:0'
    window._edit_run_name()
    window.run_name_edit.setText('Validation build')
    window._save_run_name()
    assert profile.name == 'Smoke'
    for _ in range(30):
        window._set_profile_tree_visible(False)
        assert window._matches == [nodeid]
        window._goto_match(1)
        window._open_profile_view()
        qtbot.wait(1)
        assert window._matches == ['0:0', '1:0']
        assert window.tree_view_switch.isVisible()
        assert window.tree_toolbar.isVisible()
        assert window.run_name_stack.isVisible()
        assert window.run_name_button.isEnabled()
        assert window.run_name_button.text() == 'Validation build'
        assert window._profile_selected_key == '1:0'
    window.collapse_button.click()
    assert not window.profile_tree.isExpanded(window.profile_model.index(0, 0))
    window.expand_button.click()
    assert window.profile_tree.isExpanded(window.profile_model.index(0, 0))
    assert not window.select_all_button.isEnabled()
