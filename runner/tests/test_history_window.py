"""Le tableau de bord d'historique, ses filtres et ses actions groupees."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QTabWidget, QTableWidget

from runner.domain.history import History, RunEntry
from runner.domain.models import Reader, Status
from runner.ui.history_dashboard import (
    GroupComparisonDialog,
    HistoryWindow,
    group_entries,
)
from runner.ui.history_window import FlakyDialog


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def entree(identifiant, decalage=0.0, reader="A", workspace="/w",
           echecs=("t1",), erreurs=0, passed=2, output="", **extra):
    entry = RunEntry(
        id=identifiant, timestamp=time.time() + decalage,
        workspace=workspace, reader=reader, duration=1.5,
        exit_code=1 if echecs or erreurs else 0,
        counts={"PASSED": passed, "FAILED": len(echecs), "ERROR": erreurs},
        nodeids=("t1", "t2", "suite/test_visible.py::test_ok"),
        failed_nodeids=tuple(echecs), **extra)
    return entry, output


def ajoute(history, *args, **kwargs):
    entry, output = entree(*args, **kwargs)
    return history.add(entry, output=output)


@pytest.fixture
def historique(tmp_path):
    history = History(tmp_path)
    ajoute(history, "old", decalage=-60, reader="Reader A",
           echecs=("t1", "t2"), output="old A output")
    ajoute(history, "old", decalage=-60, reader="Reader B",
           echecs=(), output="old B output")
    ajoute(history, "recent", reader="Reader A", echecs=("t2",),
           output="recent A output")
    ajoute(history, "recent", reader="Reader B", echecs=(),
           output="recent B output")
    return history


@pytest.fixture
def fenetre(qapp, historique):
    return HistoryWindow(historique)


def run_items(window):
    return [window.run_list.item(row) for row in range(window.run_list.count())
            if window.run_list.item(row).data(Qt.UserRole) is not None]


def select_run(window, index=0):
    item = run_items(window)[index]
    window.run_list.setCurrentItem(item)
    item.setSelected(True)
    return item.data(Qt.UserRole)


# --------------------------------------------------------------- regroupement

def test_reader_entries_from_one_launch_are_grouped(historique):
    groups = group_entries(historique.entries())

    assert len(groups) == 2
    assert groups[0].id == "recent"
    assert groups[0].reader_names == ("Reader A", "Reader B")
    assert groups[0].count(Status.PASSED) == 4
    assert groups[0].failed_nodeids == ("t2",)


def test_a_group_exposes_the_shared_build_number(tmp_path):
    history = History(tmp_path)
    ajoute(history, "run", reader="A", build_number=42, log_root="/logs")
    ajoute(history, "run", reader="B", build_number=42, log_root="/logs")

    group = group_entries(history.entries())[0]
    assert group.build_number == 42
    assert group.log_root == "/logs"


def test_history_shows_the_build_and_opens_its_log_folder(
        qapp, tmp_path, monkeypatch):
    import runner.ui.history_dashboard as dashboard

    log_file = tmp_path / "logs" / "20260819" / "Run_0042" / "test.log"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("ok", encoding="utf-8")
    history = History(tmp_path / "history")
    ajoute(history, "run", build_number=42, log_root=str(tmp_path / "logs"))
    window = HistoryWindow(history)
    select_run(window)

    assert "Build #0042" in window.detail_meta.text()
    opened = []
    monkeypatch.setattr(dashboard.QDesktopServices, "openUrl",
                        lambda url: opened.append(url) or True)
    window.open_logs()

    assert Path(opened[0].toLocalFile()) == log_file.parent


def test_runs_are_listed_newest_first(fenetre):
    groups = [item.data(Qt.UserRole) for item in run_items(fenetre)]
    assert [group.id for group in groups] == ["recent", "old"]


def test_empty_history_has_an_explicit_state(qapp, tmp_path):
    window = HistoryWindow(History(tmp_path))

    assert window.left_stack.currentWidget() is window.empty
    assert window.detail_stack.currentWidget() is window.detail_empty
    assert not window.clear_button.isEnabled()


# ------------------------------------------------------------------- filtres

@pytest.mark.parametrize("query", [
    "test_visible", "Reader B", "/w", "recent",
])
def test_search_matches_tests_readers_workspaces_and_ids(fenetre, query):
    fenetre.search.setText(query)
    assert run_items(fenetre)


def test_search_that_matches_nothing_clears_the_detail(fenetre):
    fenetre.search.setText("there-is-no-such-run")

    assert run_items(fenetre) == []
    assert fenetre.left_stack.currentWidget() is fenetre.filtered_empty
    assert fenetre.detail_stack.currentWidget() is fenetre.detail_empty


def test_active_filters_are_visible_and_can_be_cleared(fenetre):
    fenetre.search.setText("there-is-no-such-run")

    assert not fenetre.clear_filters_button.isHidden()
    assert fenetre.list_count.text() == "0/2 runs"

    fenetre._clear_filters()

    assert fenetre.search.text() == ""
    assert fenetre.list_all.isChecked()
    assert fenetre.list_count.text() == "2 runs"
    assert len(run_items(fenetre)) == 2


def test_history_list_resizes_with_the_embedded_page(fenetre):
    assert fenetre.history_list_panel.minimumWidth() == 360
    assert fenetre.history_list_panel.maximumWidth() == 520


def test_issue_filter_keeps_only_runs_with_problems(qapp, tmp_path):
    history = History(tmp_path)
    ajoute(history, "green", echecs=())
    ajoute(history, "red", echecs=("t1",))
    window = HistoryWindow(history)

    window._set_issue_filter(True)

    assert [item.data(Qt.UserRole).id for item in run_items(window)] == ["red"]


def test_workspace_filter_is_functional(qapp, tmp_path):
    history = History(tmp_path)
    ajoute(history, "one", workspace="/projects/one")
    ajoute(history, "two", workspace="/projects/two")
    window = HistoryWindow(history)

    window.workspace_filter.setCurrentIndex(
        window.workspace_filter.findData("/projects/one"))

    assert [item.data(Qt.UserRole).id for item in run_items(window)] == ["one"]


def test_reader_filter_is_functional(fenetre):
    fenetre._set_reader_filter("Reader B")
    assert len(run_items(fenetre)) == 2

    fenetre._set_reader_filter("Reader absent")
    assert run_items(fenetre) == []


# --------------------------------------------------------------- panneau droit

def test_selected_run_combines_reader_results(fenetre):
    select_run(fenetre, 0)

    assert fenetre.passed_value.text() == "4"
    assert fenetre.failed_value.text() == "1 failed"
    assert fenetre.tabs.tabText(1) == "Issues (1)"
    assert fenetre.details_table.rowCount() == 2
    assert fenetre.issue_preview.item(0, 0).text() == "t2"


def test_saved_outputs_are_integrated_in_the_output_tab(fenetre):
    select_run(fenetre, 0)
    fenetre.view_output()

    assert fenetre.tabs.currentWidget() is fenetre.output
    assert "recent A output" in fenetre.output.views[0].text()
    assert "recent B output" in fenetre.output.views[1].text()


def test_history_tabs_have_equal_professional_proportions(fenetre, qtbot):
    qtbot.addWidget(fenetre)
    fenetre.show()
    qtbot.wait(20)

    widths = [fenetre.tabs.tabBar().tabRect(index).width()
              for index in range(fenetre.tabs.count())]
    heights = [fenetre.tabs.tabBar().tabRect(index).height()
               for index in range(fenetre.tabs.count())]
    assert len(set(widths)) == 1
    assert min(widths) >= 92
    assert len(set(heights)) == 1 and min(heights) >= 32


def test_junit_action_is_disabled_when_reader_has_no_xml(fenetre):
    select_run(fenetre)
    submenus = [action.menu() for action in fenetre.export_menu.actions()
                if action.menu() is not None]
    assert submenus
    junit_actions = [menu.actions()[1] for menu in submenus]
    assert all(not action.isEnabled() for action in junit_actions)


def test_html_export_uses_the_chosen_reader(fenetre, tmp_path, monkeypatch):
    target = tmp_path / "report.html"
    monkeypatch.setattr(
        "runner.ui.history_dashboard.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), ""))
    select_run(fenetre)
    chosen = fenetre._current_group().entry_for_reader("Reader B")

    fenetre.export_html(chosen)

    page = target.read_text(encoding="utf-8")
    assert "Reader B" in page and "recent B output" in page
    assert "Report written" in fenetre.status.text()


# ------------------------------------------------------------------ actions

def test_rerun_emits_the_whole_group(fenetre, qtbot):
    group = select_run(fenetre)

    with qtbot.waitSignal(fenetre.rerun_requested) as signal:
        fenetre.rerun()

    assert signal.args == [group]


def test_main_window_rerun_restores_tests_and_readers(historique):
    from runner.ui.main_window import MainWindow

    group = group_entries(historique.entries())[0]
    selected = []
    started = []
    fake = SimpleNamespace(
        _pending_history_run=group,
        workspace=SimpleNamespace(
            path=group.workspace,
            readers=(Reader("Reader A", 0), Reader("Reader B", 1),
                     Reader("Reader C", 2))),
        model=SimpleNamespace(nodeids=lambda: list(group.nodeids) + ["new"]),
        readers_bar=SimpleNamespace(
            select_names=lambda readers, names: selected.append(
                (readers, set(names)))),
        _start=lambda nodeids: started.append(list(nodeids)),
    )

    MainWindow._launch_pending_history_run(fake)

    assert started == [list(group.nodeids)]
    assert selected[0][1] == {"Reader A", "Reader B"}
    assert fake._pending_history_run is None


def test_delete_removes_every_reader_entry_for_the_run(
        fenetre, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Yes))
    select_run(fenetre, 0)

    fenetre.delete_run()

    assert {entry.id for entry in fenetre.history.entries()} == {"old"}
    assert len(fenetre.history.entries()) == 2


def test_delete_and_clear_both_ask_for_confirmation(fenetre, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.No))
    select_run(fenetre)

    fenetre.delete_run()
    fenetre.clear_history()

    assert len(fenetre.history.entries()) == 4


def test_clear_after_confirmation_empties_the_dashboard(fenetre, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Yes))

    fenetre.clear_history()

    assert fenetre.history.entries() == []
    assert fenetre.left_stack.currentWidget() is fenetre.empty


# -------------------------------------------------------------- comparaison

def test_compare_mode_allows_two_clicks_without_ctrl(fenetre):
    fenetre._enter_compare_mode()
    items = run_items(fenetre)
    items[0].setSelected(True)
    items[1].setSelected(True)

    assert len(fenetre._selected_groups()) == 2
    assert fenetre.compare_button.isEnabled()
    assert fenetre.compare_button.text() == "Compare selected"
    assert fenetre.cancel_compare.isVisible() is False  # parent not shown
    assert not fenetre.cancel_compare.isHidden()


def test_incompatible_runs_are_explained(qapp, tmp_path):
    history = History(tmp_path)
    ajoute(history, "one", workspace="/one", reader="A")
    ajoute(history, "two", workspace="/two", reader="A")
    window = HistoryWindow(history)
    window._enter_compare_mode()
    for item in run_items(window):
        item.setSelected(True)

    window._compare_clicked()

    assert "same workspace" in window.status.text()


def test_group_comparison_has_one_tab_per_common_reader(qapp, historique):
    recent, old = group_entries(historique.entries())
    dialog = GroupComparisonDialog(old, recent)
    tabs = dialog.findChild(QTabWidget)

    assert tabs.count() == 2
    assert {tabs.tabText(index) for index in range(tabs.count())} == {
        "Reader A", "Reader B"}


def test_identical_reader_results_say_nothing_changed(qapp, tmp_path):
    history = History(tmp_path)
    ajoute(history, "old", decalage=-60, reader="A", echecs=("t1",))
    ajoute(history, "new", reader="A", echecs=("t1",))
    newer, older = group_entries(history.entries())

    dialog = GroupComparisonDialog(older, newer)
    labels = [label.text() for label in dialog.findChildren(QLabel)]

    assert "No verdict changed between these runs." in labels


# ------------------------------------------------------------------- instables

def test_flaky_dialog_still_lists_unstable_tests(qapp, historique):
    dialog = FlakyDialog(historique.flaky())
    table = dialog.findChild(QTableWidget)
    tests = [table.item(row, 0).text() for row in range(table.rowCount())]
    assert "t1" in tests


def test_flaky_dialog_has_an_explicit_empty_state(qapp):
    dialog = FlakyDialog([])
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("No unstable test" in text for text in labels)
