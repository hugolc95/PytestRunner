"""Collecte partielle, colonne Duree et compteurs failed / error separes."""
import os
import sys

import pytest
from PySide6.QtCore import QSettings, Qt

from runner.domain import diagnostics, execution, history, interpreter, parsing
from runner.domain.interpreter import InterpreterInfo
from runner.domain.models import Kind, Reader, RunRequest, Status, failure_summary
from runner.domain.tree import add_broken_files, build_tree
from runner.ui.main_window import MainWindow
from runner.ui.tree_model import NODEID_ROLE, TestTreeModel
from runner.ui.widgets import ErrorDialog


def workspace(tmp_path, files):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


# ------------------------------------------------------------------ collecte


def test_broken_test_files_no_longer_hide_the_valid_tests(tmp_path):
    workspace(tmp_path, {
        "test_ok.py": "def test_ok():\n    assert True\n",
        "test_syntax.py": "def test_x(:\n    pass\n",
        "sub/test_import.py": "import missing_module_partial_xyz\n",
    })
    collection = execution.collect(str(tmp_path), sys.executable)
    assert collection.nodeids == ("test_ok.py::test_ok",)
    assert set(collection.broken_files) == {"test_syntax.py", "sub/test_import.py"}
    syntax = collection.broken_files["test_syntax.py"]
    assert syntax["location"].endswith("test_syntax.py:1")
    assert "SyntaxError" in syntax["message"]
    assert "def test_x(:" in syntax["body"]
    assert "missing_module_partial_xyz" in collection.broken_files["sub/test_import.py"]["message"]


def test_a_broken_conftest_still_fails_the_whole_collection(tmp_path):
    workspace(tmp_path, {"test_ok.py": "def test_ok(): pass\n",
                         "conftest.py": "import missing_module_partial_xyz\n"})
    with pytest.raises(diagnostics.CollectionError):
        execution.collect(str(tmp_path), sys.executable)


def test_a_workspace_where_every_file_is_broken_still_fails(tmp_path):
    workspace(tmp_path, {"test_syntax.py": "def test_x(:\n    pass\n"})
    with pytest.raises(diagnostics.CollectionError):
        execution.collect(str(tmp_path), sys.executable)


def test_broken_files_join_the_tree_beside_their_neighbours():
    roots = add_broken_files(build_tree(["sub/test_ok.py::test_ok"]),
                             {"sub/test_bad.py": "sub/test_bad.py:1\nSyntaxError",
                              "test_top.py": "boom"})
    sub = roots[0]
    assert [n.name for n in sub.children] == ["test_ok.py", "test_bad.py"]
    bad = sub.children[1]
    assert bad.kind is Kind.MODULE and bad.collection_error.endswith("SyntaxError")
    assert not list(bad.leaves())
    assert roots[1].name == "test_top.py" and roots[1].collection_error == "boom"


def test_broken_rows_are_visible_red_and_never_selectable(qapp):
    model = TestTreeModel()
    model.set_tree(add_broken_files(build_tree(["test_ok.py::test_ok"]),
                                    {"test_bad.py": "test_bad.py:1\nSyntaxError"}))
    model.set_all_checked(True)
    broken = model.index(1, 0)
    assert broken.data() == "test_bad.py"
    assert not model.flags(broken) & Qt.ItemIsUserCheckable
    assert broken.data(Qt.CheckStateRole) is None
    assert "SyntaxError" in broken.data(Qt.ToolTipRole)
    assert broken.data(NODEID_ROLE) == ""
    assert model.checked_nodeids() == ["test_ok.py::test_ok"]
    assert model.broken_file_count() == 1


# ------------------------------------------------------------------- durees


def test_duration_protocol_lines_are_parsed_and_hidden():
    line = "PYTESTRUNNER_DURATION\t0.250000\ttest_a.py::test_b[x y]\n"
    assert parsing.parse_duration_line(line) == ("test_a.py::test_b[x y]", 0.25)
    assert parsing.is_outcome_protocol_line(line)
    assert parsing.parse_status_line(line) is None
    assert parsing.parse_duration_line("PYTESTRUNNER_DURATION\tnope\tx::y") is None


def test_each_test_reports_its_duration_as_soon_as_it_ends(tmp_path):
    workspace(tmp_path, {"test_timing.py": (
        "import time\n"
        "def test_fast():\n    pass\n"
        "def test_slow():\n    time.sleep(0.2)\n"
        "def test_fails():\n    assert False\n")})
    collection = execution.collect(str(tmp_path), sys.executable)
    request = RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                         nodeids=collection.nodeids, readers=())
    events = []
    report = execution.ReaderRun(request, Reader("", 0), dict(os.environ)).run(
        on_line=lambda line: None,
        on_outcome=lambda outcome: events.append(("outcome", outcome.nodeid)),
        on_duration=lambda nodeid, seconds: events.append(("duration", nodeid, seconds)))
    durations = {event[1]: event[2] for event in events if event[0] == "duration"}
    assert set(durations) == set(collection.nodeids)
    assert durations["test_timing.py::test_slow"] >= 0.2
    # pytest masque les tests de moins de 5 ms dans son releve : le direct
    # les garde, le rapport de fin aussi.
    assert set(report.durations) == set(collection.nodeids)
    # Une duree arrive avant la fin du lecteur, test par test.
    assert sum(1 for event in events if event[0] == "outcome") == 3


def test_duration_column_shows_longest_reader_and_group_sums(qapp):
    model = TestTreeModel()
    model.set_tree(build_tree(["pkg/test_a.py::test_one", "pkg/test_a.py::test_two"]))
    model.set_readers((Reader("Reader A", 0), Reader("Reader B", 1)))
    column = model.duration_column
    assert column == 3 and model.columnCount() == 4
    assert model.headerData(column, Qt.Horizontal) == "Duration"

    model.set_duration("pkg/test_a.py::test_one", 0, 1.0)
    model.set_duration("pkg/test_a.py::test_one", 1, 2.5)
    model.set_duration("pkg/test_a.py::test_two", 0, 0.5)
    folder = model.index(0, column)
    module = model.index(0, column, model.index(0, 0))
    one = model.index(0, column, model.index(0, 0, model.index(0, 0)))
    assert one.data() == "2.50s"
    assert "Reader A: 1.00s" in one.data(Qt.ToolTipRole)
    # Un groupe montre le total du lecteur le plus lent (B : 2.5 s), pas la
    # somme des pires cas de chaque test (3 s), qui n'etait celle de personne.
    assert module.data() == "2.50s" and folder.data() == "2.50s"
    assert "Reader A: 1.50s" in module.data(Qt.ToolTipRole)

    # Le releve de fin complete, sans ecraser la mesure en direct.
    model.merge_durations(0, {"pkg/test_a.py::test_one": 9.0,
                              "pkg/test_a.py::test_two": 0.5})
    assert one.data() == "2.50s"

    model.clear_statuses()
    assert one.data() is None and folder.data() is None


# --------------------------------------------------------------- compteurs


def test_failure_summary_keeps_failed_and_errors_apart():
    assert failure_summary({Status.FAILED: 8, Status.ERROR: 1}) == "8 failed · 1 error"
    assert failure_summary({Status.ERROR: 2}) == "2 errors"
    assert failure_summary({Status.FAILED: 3, Status.PASSED: 10}) == "3 failed"
    assert failure_summary({Status.PASSED: 3}) == ""


# ------------------------------------------------------------------ fenetre


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr(history, "dossier", lambda: tmp_path / "history")
    monkeypatch.setattr(MainWindow, "_restore", lambda self: None)
    monkeypatch.setattr(MainWindow, "_require_interpreter", lambda self: sys.executable)
    monkeypatch.setattr(MainWindow, "_refresh_primary_reader", lambda self, *args: None)
    monkeypatch.setattr(interpreter, "cached_probe", lambda path: InterpreterInfo(
        path=path, version="3", bits=64, pytest_version="test"))
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()


def test_window_keeps_valid_tests_and_explains_the_broken_file(
        window, qtbot, tmp_path, monkeypatch):
    popups = []
    monkeypatch.setattr(ErrorDialog, "show_diagnostics",
                        lambda *args, **kwargs: popups.append(args))
    folder = workspace(tmp_path / "ws", {
        "test_ok.py": "def test_ok():\n    assert True\n",
        "test_bad.py": "def test_x(:\n    pass\n",
    })
    window.workspace_combo.setCurrentText(str(folder))
    window.load_workspace()
    qtbot.waitUntil(lambda: window._collector is not None
                    and not window._collector.isRunning(), timeout=30000)
    qtbot.wait(50)

    assert not popups
    assert "1 file could not be collected" in window.status_label.text()
    names = [window.model.index(row, 0).data() for row in range(window.model.rowCount())]
    assert "test_bad.py" in names and "test_ok.py" in names
    broken = window.model.index(names.index("test_bad.py"), 0)
    window._select_test(broken)
    assert window.results.detail.group_total.text() == "Collection error · not runnable"
    assert "SyntaxError" in window.results.detail.failures.item(0).text()
    window.preferences.console.refresh()
    assert "could not be collected" in window.preferences.console.text.toPlainText()
