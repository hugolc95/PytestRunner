"""Une ligne d'historique par lecteur.

Avant, un run a plusieurs lecteurs ne laissait qu'UNE ligne dans l'historique,
avec les compteurs de tous les lecteurs additionnes : impossible d'y voir
lequel avait echoue. Chaque lecteur tournant dans son propre process, il a
maintenant sa propre ligne, taguee par son nom (`reader`), avec son propre
resume, sa propre sortie et son propre rapport JUnit.
"""

import textwrap

import pytest
from PyQt5.QtCore import QSettings

import core.run_history as run_history
from core.run_history import RunHistoryManager
from gui_qt.history_window import COLUMNS, HistoryWindow


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """Redirige l'historique vers un dossier jetable : les tests ne doivent
    ni lire ni ecraser l'historique reel de la machine qui les execute."""
    dossier = tmp_path / "history"
    monkeypatch.setattr(run_history, "history_dir", lambda: str(dossier))
    return dossier


def test_add_run_stores_the_reader(isolated_history):
    manager = RunHistoryManager()
    entry = manager.add_run(
        run_id="abc.0", workspace="/ws", duration_seconds=1.0, exit_code=0,
        counts={"PASSED": 1}, nodeids=["test_x.py::test_f"], failed_nodeids=[],
        output_text="ok", reader="Lecteur A",
    )
    assert entry["reader"] == "Lecteur A"
    assert manager.all_entries()[0]["reader"] == "Lecteur A"


def test_the_history_window_shows_a_reader_column(qtbot, isolated_history):
    manager = RunHistoryManager()
    manager.add_run(
        run_id="abc.0", workspace="/ws", duration_seconds=1.0, exit_code=0,
        counts={"PASSED": 1}, nodeids=["test_x.py::test_f"], failed_nodeids=[],
        output_text="ok", reader="Lecteur B",
    )

    fenetre = HistoryWindow(manager)
    qtbot.addWidget(fenetre)

    colonne = COLUMNS.index("Reader")
    assert fenetre.table.item(0, colonne).text() == "Lecteur B"


def test_add_run_defaults_to_no_reader(isolated_history):
    manager = RunHistoryManager()
    entry = manager.add_run(
        run_id="abc", workspace="/ws", duration_seconds=1.0, exit_code=0,
        counts={"PASSED": 1}, nodeids=[], failed_nodeids=[], output_text="",
    )
    assert entry["reader"] == ""


@pytest.fixture
def deux_lecteurs(qtbot, tmp_path, isolated_history):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "config.yml").write_text(
        "Reader: Lecteur A\nReaders:\n  - Lecteur B\n", encoding="utf-8")
    # test_maybe_fails echoue seulement pour Lecteur B : les deux lecteurs
    # doivent alors se retrouver avec des compteurs DIFFERENTS dans
    # l'historique, preuve que ce ne sont pas deux copies du meme total agrege.
    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import os

        def test_ok():
            assert True

        def test_maybe_fails():
            assert os.environ.get("PYTESTRUNNER_READER", "") != "Lecteur B"
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_one_history_entry_per_reader_with_its_own_counts(deux_lecteurs, qtbot):
    deux_lecteurs._launch_worker(
        ["test_x.py::test_ok", "test_x.py::test_maybe_fails"], "run\n")
    try:
        qtbot.waitUntil(lambda: deux_lecteurs._runs_left == 0, timeout=120000)
        for worker in deux_lecteurs.workers:
            worker.wait(10000)

        entries = {e["reader"]: e for e in deux_lecteurs.history_manager.all_entries()}
        assert set(entries) == {"Lecteur A", "Lecteur B"}
        assert entries["Lecteur A"]["id"] != entries["Lecteur B"]["id"]

        assert entries["Lecteur A"]["passed"] == 2
        assert entries["Lecteur A"]["failed"] == 0
        assert entries["Lecteur A"]["failed_nodeids"] == []

        assert entries["Lecteur B"]["passed"] == 1
        assert entries["Lecteur B"]["failed"] == 1
        assert entries["Lecteur B"]["failed_nodeids"] == ["test_x.py::test_maybe_fails"]
    finally:
        for worker in deux_lecteurs.workers:
            worker.stop()
            worker.wait(10000)


def test_a_single_reader_run_still_gets_one_entry_without_a_suffix(qtbot, tmp_path, isolated_history):
    """Sans plusieurs lecteurs, rien ne doit changer : une seule ligne, avec un
    identifiant de run qui ne porte pas de suffixe .0."""
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "test_x.py").write_text("def test_f():\n    pass\n", encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.refresh_readers()
    fenetre._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: fenetre._runs_left == 0, timeout=120000)
        for worker in fenetre.workers:
            worker.wait(10000)

        entries = fenetre.history_manager.all_entries()
        assert len(entries) == 1
        assert entries[0]["reader"] == ""
        assert not entries[0]["id"].endswith(".0")
    finally:
        for worker in fenetre.workers:
            worker.stop()
            worker.wait(10000)
