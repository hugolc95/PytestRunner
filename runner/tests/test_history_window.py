"""La fenetre d'historique : ce qu'elle montre, et ce qu'elle laisse faire.

Le point sensible n'est pas l'affichage mais les GARDES : un export propose
sur un run qui n'a pas de fichier, une comparaison lancee sur une seule ligne,
un effacement sans confirmation. Chacun se termine par une erreur ou par une
perte, et chacun se previent en eteignant un bouton.
"""

from __future__ import annotations

import time

import pytest
from PyQt5.QtCore import QItemSelectionModel

from runner.domain.history import History, RunEntry
from runner.ui.history_window import ComparisonDialog, FlakyDialog, HistoryWindow


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def entree(identifiant, decalage=0.0, reader="", echecs=("t1",), **extra):
    return RunEntry(
        id=identifiant, timestamp=time.time() + decalage, workspace="/w",
        reader=reader, duration=1.0, exit_code=1 if echecs else 0,
        counts={"PASSED": 2, "FAILED": len(echecs)},
        nodeids=("t1", "t2", "t3"), failed_nodeids=tuple(echecs), **extra)


@pytest.fixture
def historique(tmp_path):
    h = History(tmp_path)
    h.add(entree("vieux", decalage=-60, reader="A", echecs=("t1", "t2")),
          output="sortie du vieux run")
    h.add(entree("recent", reader="A", echecs=("t2",)))
    return h


@pytest.fixture
def fenetre(qapp, historique):
    return HistoryWindow(historique)


def _choisir(fenetre, *lignes) -> None:
    fenetre.table.clearSelection()
    modele = fenetre.table.model()
    for ligne in lignes:
        fenetre.table.selectionModel().select(
            modele.index(ligne, 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows)


# -------------------------------------------------------------- l'affichage

def test_the_runs_are_listed_newest_first(fenetre):
    assert fenetre.table.rowCount() == 2
    assert fenetre.table.item(0, 1).text() == "A"
    assert fenetre.table.item(0, 3).text() == "1", "le run recent a un echec"
    assert fenetre.table.item(1, 3).text() == "2"


def test_a_run_without_reader_shows_a_dash(qapp, tmp_path):
    """Une cellule vide se lit comme une donnee manquante ; le tiret dit que
    ce run n'avait pas de lecteur du tout."""
    h = History(tmp_path)
    h.add(entree("seul"))
    fenetre = HistoryWindow(h)

    assert fenetre.table.item(0, 1).text() == "—"


def test_an_empty_history_says_so_instead_of_showing_a_blank_table(qapp,
                                                                   tmp_path):
    fenetre = HistoryWindow(History(tmp_path))

    assert fenetre.table.isHidden()
    assert not fenetre.empty.isHidden()


# ----------------------------------------------------------------- les gardes

def test_nothing_is_offered_without_a_selection(fenetre):
    fenetre.table.clearSelection()

    assert not fenetre.view_button.isEnabled()
    assert not fenetre.html_button.isEnabled()
    assert not fenetre.compare_button.isEnabled()


def test_comparing_needs_exactly_two_runs(fenetre):
    _choisir(fenetre, 0)
    assert not fenetre.compare_button.isEnabled()

    _choisir(fenetre, 0, 1)
    assert fenetre.compare_button.isEnabled()


def test_exporting_a_report_needs_exactly_one_run(fenetre):
    _choisir(fenetre, 0, 1)
    assert not fenetre.html_button.isEnabled()

    _choisir(fenetre, 0)
    assert fenetre.html_button.isEnabled()


def test_the_junit_export_is_off_when_the_run_has_no_xml(fenetre):
    """Le proposer quand meme donnerait une erreur au moment du clic, apres
    avoir fait choisir un nom de fichier pour rien."""
    _choisir(fenetre, 0)
    assert not fenetre.junit_button.isEnabled()


def test_the_junit_export_is_on_when_the_run_has_one(qapp, tmp_path):
    xml = tmp_path / "junit.xml"
    xml.write_text("<testsuites/>", encoding="utf-8")
    h = History(tmp_path)
    h.add(entree("avec", junit_path=str(xml)))
    fenetre = HistoryWindow(h)
    _choisir(fenetre, 0)

    assert fenetre.junit_button.isEnabled()


def test_clearing_is_off_on_an_empty_history(qapp, tmp_path):
    fenetre = HistoryWindow(History(tmp_path))
    assert not fenetre.clear_button.isEnabled()
    assert not fenetre.flaky_button.isEnabled()


# ------------------------------------------------------------------ actions

def test_exporting_writes_the_report(fenetre, tmp_path, monkeypatch):
    cible = tmp_path / "rapport.html"
    monkeypatch.setattr(
        "runner.ui.history_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(cible), ""))

    _choisir(fenetre, 0)
    fenetre.export_html()

    assert cible.is_file()
    assert "<!DOCTYPE html>" in cible.read_text(encoding="utf-8")
    assert "Report written" in fenetre.status.text()


def test_cancelling_the_save_dialog_is_a_no_op(fenetre, tmp_path, monkeypatch):
    """Renoncer n'est pas une panne.

    Sans garde, on part ecrire dans un chemin vide, cela echoue, et on
    reproche a l'utilisateur une erreur qu'il n'a pas commise -- il vient
    justement de dire non.
    """
    monkeypatch.setattr(
        "runner.ui.history_window.QFileDialog.getSaveFileName",
        lambda *a, **k: ("", ""))

    _choisir(fenetre, 0)
    fenetre.export_html()

    assert not list(tmp_path.glob("*.html"))
    assert fenetre.status.text() == "", (
        f"une erreur est signalee apres une annulation : {fenetre.status.text()!r}")


def test_a_failed_export_is_reported_not_swallowed(fenetre, monkeypatch):
    monkeypatch.setattr(
        "runner.ui.history_window.QFileDialog.getSaveFileName",
        lambda *a, **k: ("/nulle/part/rapport.html", ""))

    _choisir(fenetre, 0)
    fenetre.export_html()

    assert "Could not write" in fenetre.status.text()


def test_clearing_asks_first(fenetre, monkeypatch):
    """Effacer supprime aussi les sorties conservees : c'est irreversible."""
    from PyQt5.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    fenetre.clear_history()

    assert fenetre.table.rowCount() == 2, "l'historique a ete efface sans accord"


def test_clearing_after_confirmation_empties_the_window(fenetre, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    fenetre.clear_history()

    assert fenetre.table.rowCount() == 0
    assert not fenetre.empty.isHidden()


def test_the_output_window_shows_what_was_kept(fenetre, qapp, monkeypatch):
    ouvertes = []
    monkeypatch.setattr("PyQt5.QtWidgets.QDialog.exec_",
                        lambda self: ouvertes.append(self) or 0)

    _choisir(fenetre, 1)          # le vieux run, celui qui a une sortie
    fenetre.view_output()

    assert ouvertes, "aucune fenetre de sortie n'a ete ouverte"
    from runner.ui.console_view import ConsoleView

    vues = ouvertes[0].findChildren(ConsoleView)
    assert vues and "sortie du vieux run" in vues[0].text()


def test_a_run_without_output_says_so(fenetre, qapp, monkeypatch):
    """Une console vide se lit comme un bug de l'outil."""
    from runner.ui.console_view import ConsoleView

    ouvertes = []
    monkeypatch.setattr("PyQt5.QtWidgets.QDialog.exec_",
                        lambda self: ouvertes.append(self) or 0)

    _choisir(fenetre, 0)          # le run recent, enregistre sans sortie
    fenetre.view_output()

    vues = ouvertes[0].findChildren(ConsoleView)
    assert "kept no output" in vues[0].text()


# -------------------------------------------------------------- comparaison

def test_the_comparison_dialog_lists_what_changed(qapp, historique):
    from runner.domain.history import compare

    from PyQt5.QtWidgets import QLabel

    entrees = historique.entries()
    boite = ComparisonDialog(compare(entrees[0], entrees[1]))
    titres = [w.text() for w in boite.findChildren(QLabel)]
    assert any("Fixed (1)" in x for x in titres), titres
    assert any("New failures (0)" in x for x in titres)


def test_two_identical_runs_say_nothing_changed(qapp, tmp_path):
    """Deux listes vides laisseraient croire que la comparaison n'a pas
    tourne."""
    from PyQt5.QtWidgets import QLabel

    from runner.domain.history import compare

    h = History(tmp_path)
    h.add(entree("a", decalage=-60, echecs=("t1",)))
    h.add(entree("b", echecs=("t1",)))
    entrees = h.entries()

    boite = ComparisonDialog(compare(entrees[0], entrees[1]))
    titres = [w.text() for w in boite.findChildren(QLabel)]
    assert any("Nothing changed" in x for x in titres)


# -------------------------------------------------------------------- flaky

def test_the_flaky_dialog_lists_the_unstable_tests(qapp, historique):
    from PyQt5.QtWidgets import QTableWidget

    boite = FlakyDialog(historique.flaky())
    table = boite.findChild(QTableWidget)

    lignes = [table.item(i, 0).text() for i in range(table.rowCount())]
    assert "t1" in lignes, "t1 a echoue une fois sur deux"
    assert "t3" not in lignes, "t3 n'a jamais echoue"


def test_the_flaky_dialog_says_when_there_is_nothing(qapp):
    from PyQt5.QtWidgets import QLabel

    boite = FlakyDialog([])
    titres = [w.text() for w in boite.findChildren(QLabel)]
    assert any("No unstable test" in x for x in titres)
