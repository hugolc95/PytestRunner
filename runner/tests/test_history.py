"""L'historique des runs : ce qui est garde, ce qui est compare, ce qui derive.

Un verdict seul ne dit pas grand-chose. Devant un rouge on veut savoir s'il
est nouveau, devant un vert s'il tient. C'est tout l'objet de ce qui suit.
"""

from __future__ import annotations

import json
import time

import pytest

from runner.domain.history import (
    History,
    RunEntry,
    compare,
    nouvel_identifiant,
)
from runner.domain.models import Status
from runner.domain.report import html_report, write_html, write_junit


def entree(identifiant="a", decalage=0.0, reader="", passed=8, failed=2,
           nodeids=("t1", "t2", "t3"), echecs=("t1", "t2"), **extra) -> RunEntry:
    return RunEntry(
        id=identifiant, timestamp=time.time() + decalage,
        workspace="/w", reader=reader, duration=1.5, exit_code=1 if failed else 0,
        counts={"PASSED": passed, "FAILED": failed},
        nodeids=tuple(nodeids), failed_nodeids=tuple(echecs), **extra)


@pytest.fixture
def historique(tmp_path):
    return History(tmp_path)


# ------------------------------------------------------------- enregistrement

def test_a_run_is_kept_with_its_output(historique):
    """La sortie va dans un fichier a part : gardee dans le JSON, elle le
    ferait grossir de plusieurs mega-octets pour rien."""
    garde = historique.add(entree(), output="FAILED t1\nFAILED t2\n")

    assert garde.output_file
    assert garde.output() == "FAILED t1\nFAILED t2\n"
    assert json.loads(historique.fichier.read_text(encoding="utf-8"))


def test_the_newest_run_comes_first(historique):
    historique.add(entree("vieux", decalage=-60))
    historique.add(entree("recent"))

    assert [e.id for e in historique.entries()] == ["recent", "vieux"]


def test_the_history_survives_a_restart(historique, tmp_path):
    historique.add(entree("a"), output="trace")

    relu = History(tmp_path)
    assert [e.id for e in relu.entries()] == ["a"]
    assert relu.entries()[0].output() == "trace"


def test_each_reader_gets_its_own_entry(historique):
    """Un total agrege masquerait lequel a echoue -- justement la question
    quand on teste la meme suite sur deux lecteurs."""
    historique.add(entree("run", reader="A", failed=0, echecs=()))
    historique.add(entree("run", reader="B", failed=2, echecs=("t1", "t2")))

    par_lecteur = {e.reader: e for e in historique.entries()}
    assert par_lecteur["A"].ok and not par_lecteur["B"].ok
    assert par_lecteur["A"].failed_nodeids == ()


def test_the_output_files_of_two_readers_do_not_collide(historique):
    """Meme identifiant de run, deux lecteurs : un seul nom de fichier et le
    second ecraserait la sortie du premier."""
    a = historique.add(entree("run", reader="A"), output="vu par A")
    b = historique.add(entree("run", reader="B"), output="vu par B")

    assert a.output_file != b.output_file
    assert a.output() == "vu par A" and b.output() == "vu par B"


def test_two_identifiers_in_a_row_differ():
    assert nouvel_identifiant() != nouvel_identifiant()


# ------------------------------------------------------------------- limites

def test_the_history_stops_growing(tmp_path):
    petite = History(tmp_path, max_entrees=3)
    for i in range(6):
        petite.add(entree(f"r{i}"))

    assert [e.id for e in petite.entries()] == ["r5", "r4", "r3"]


def test_a_run_that_falls_out_takes_its_files_with_it(tmp_path):
    """Sinon le dossier grossit indefiniment avec des .log que plus aucune
    entree ne designe -- invisibles, et jamais nettoyes."""
    petite = History(tmp_path, max_entrees=1)
    premier = petite.add(entree("r0"), output="a jeter")
    petite.add(entree("r1"), output="a garder")

    assert not (tmp_path / premier.output_file.split("/")[-1]).exists()


def test_clearing_removes_the_saved_output_too(historique, tmp_path):
    garde = historique.add(entree("a"), output="trace")
    historique.clear()

    assert historique.entries() == []
    assert not (tmp_path / garde.output_file.split("/")[-1]).exists()


# --------------------------------------------------------------- robustesse

@pytest.mark.parametrize("contenu", ["{ pas du json", '{"a": 1}', "null"])
def test_a_broken_history_file_does_not_stop_the_application(tmp_path, contenu):
    (tmp_path / "run_history.json").write_text(contenu, encoding="utf-8")
    assert History(tmp_path).entries() == []


@pytest.mark.parametrize("abimee", [
    {"pas": "d'identifiant"},                       # clef manquante
    {"id": "x", "timestamp": "pas un nombre"},      # valeur inconvertible
    {"id": "x", "counts": "pas un dictionnaire"},   # type inattendu
    {"id": "x", "duration": None},
])
def test_one_bad_entry_does_not_take_the_others_with_it(tmp_path, abimee):
    """Une seule ligne abimee ne doit pas priver de tout l'historique.

    Les formes testees echouent chacune d'une facon differente -- clef
    absente, conversion impossible, type inattendu. N'en essayer qu'une
    laissait passer un rattrapage trop etroit.
    """
    (tmp_path / "run_history.json").write_text(json.dumps([
        {"id": "bon", "timestamp": 1.0, "counts": {"PASSED": 1}},
        abimee,
        {"id": "aussi bon", "timestamp": 2.0},
    ]), encoding="utf-8")

    assert [e.id for e in History(tmp_path).entries()] == ["bon", "aussi bon"]


def test_writing_the_history_is_atomic(tmp_path, monkeypatch):
    """Un JSON tronque par une coupure rend TOUT l'historique illisible."""
    import pathlib

    historique = History(tmp_path)
    historique.add(entree("a"))
    avant = historique.fichier.read_bytes()

    monkeypatch.setattr(pathlib.Path, "replace",
                        lambda self, cible: (_ for _ in ()).throw(OSError("plein")))
    historique.add(entree("b"))

    assert historique.fichier.read_bytes() == avant
    assert not list(tmp_path.glob("*.tmp"))


def test_a_missing_output_file_reads_as_empty(historique):
    """Le fichier peut avoir ete efface a la main entre deux ouvertures."""
    garde = historique.add(entree("a"), output="trace")
    import os

    os.remove(garde.output_file)
    assert garde.output() == ""


# ------------------------------------------------------------- comparaison

def test_comparing_says_what_broke_and_what_was_fixed(historique):
    ancien = entree("vieux", decalage=-60, echecs=("t1", "t2"))
    recent = entree("recent", echecs=("t2", "t3"))

    resultat = compare(ancien, recent)
    assert resultat.newly_failed == ("t3",)
    assert resultat.newly_fixed == ("t1",)
    assert resultat.still_failing == ("t2",)


def test_the_older_run_is_always_the_reference(historique):
    """« Ce test s'est mis a echouer » et « ce test est repare » sont deux
    phrases inversees : se tromper de sens rend le resultat trompeur."""
    ancien = entree("vieux", decalage=-60, echecs=("t1",))
    recent = entree("recent", echecs=("t3",))

    dans_un_sens = compare(ancien, recent)
    dans_l_autre = compare(recent, ancien)

    assert dans_un_sens.newly_failed == dans_l_autre.newly_failed == ("t3",)
    assert dans_un_sens.newly_fixed == dans_l_autre.newly_fixed == ("t1",)


def test_two_identical_runs_compare_to_nothing(historique):
    a = entree("a", decalage=-60, echecs=("t1",))
    b = entree("b", echecs=("t1",))

    resultat = compare(a, b)
    assert resultat.unchanged
    assert resultat.still_failing == ("t1",)


# -------------------------------------------------------------------- flaky

def test_a_test_that_sometimes_fails_is_flagged(historique):
    historique.add(entree("r1", echecs=("t1",)))
    historique.add(entree("r2", echecs=()))
    historique.add(entree("r3", echecs=("t1",)))

    instables = {f.nodeid: f for f in historique.flaky()}
    assert "t1" in instables
    assert instables["t1"].seen == 3 and instables["t1"].failed == 2


def test_a_test_that_always_fails_is_not_flaky(historique):
    """Il est casse, ce qui est une autre conversation."""
    for i in range(3):
        historique.add(entree(f"r{i}", echecs=("t1",)))

    assert [f.nodeid for f in historique.flaky()] == []


def test_a_test_that_never_fails_is_not_flaky(historique):
    for i in range(3):
        historique.add(entree(f"r{i}", echecs=()))

    assert historique.flaky() == []


def test_the_most_unstable_comes_first(historique):
    """`t2` rate deux fois sur trois, `t1` une seule.

    Il apparait pourtant APRES `t1` dans les nodeids : sans tri, c'est cet
    ordre-la qui ressortait, et le test passait sans rien exiger.
    """
    historique.add(entree("r1", nodeids=("t1", "t2"), echecs=("t1", "t2")))
    historique.add(entree("r2", nodeids=("t1", "t2"), echecs=("t2",)))
    historique.add(entree("r3", nodeids=("t1", "t2"), echecs=()))

    instables = historique.flaky()
    assert [f.nodeid for f in instables] == ["t2", "t1"]
    assert instables[0].ratio > instables[1].ratio


def test_a_test_that_always_fails_on_one_reader_only_is_not_flaky(historique):
    """C'est une difference entre LECTEURS, pas un alea.

    Tous lecteurs confondus, ce test ressortait a 50 % d'echec au milieu des
    vrais instables -- et envoyait chercher un hasard qui n'existe pas. Le
    verdict est parfaitement reproductible sur chaque lecteur.
    """
    for i in range(3):
        historique.add(entree(f"a{i}", reader="A", echecs=()))
        historique.add(entree(f"b{i}", reader="B", echecs=("t1",)))

    assert historique.flaky() == []


def test_the_reader_it_is_unstable_on_is_reported(historique):
    """Savoir lequel est la moitie de l'enquete."""
    historique.add(entree("r1", reader="B", echecs=("t1",)))
    historique.add(entree("r2", reader="B", echecs=()))
    historique.add(entree("r3", reader="A", echecs=()))

    instables = historique.flaky()
    assert [(f.nodeid, f.reader) for f in instables] == [("t1", "B")]


def test_only_the_recent_runs_are_looked_at(historique):
    """Un test repare il y a trois mois ne doit pas rester marque instable."""
    historique.add(entree("vieux", decalage=-9999, echecs=("t1",)))
    for i in range(4):
        historique.add(entree(f"r{i}", echecs=()))

    assert historique.flaky(fenetre=3) == []
    assert [f.nodeid for f in historique.flaky(fenetre=10)] == ["t1"]


# ------------------------------------------------------------------ rapport

def test_the_report_holds_together_on_its_own(historique):
    """Une page qui se decompose parce que le reseau interne bloque un CDN ne
    vaut rien comme piece jointe."""
    page = html_report(entree("a", reader="R1"), "FAILED t1\n")

    assert "<style>" in page
    for interdit in ("http://", "https://", "<script"):
        assert interdit not in page, f"le rapport va chercher {interdit}"


def test_the_report_says_what_failed(historique):
    page = html_report(entree("a", reader="Cosmo11"), "")

    assert "Cosmo11" in page
    assert "t1" in page and "t2" in page
    assert ">8<" in page and ">2<" in page


def test_the_report_strips_the_terminal_colours(historique):
    """Dans un fichier HTML, les sequences ANSI s'afficheraient telles quelles,
    en plein milieu du texte."""
    page = html_report(entree("a"), "\x1b[31mFAILED\x1b[0m t1\n")

    assert "\x1b[" not in page
    assert "FAILED t1" in page


def test_a_report_with_a_hostile_test_name_stays_safe(historique):
    """Un nom de test parametre peut contenir n'importe quoi."""
    page = html_report(entree("a", nodeids=("t<script>x</script>",),
                              echecs=("t<script>x</script>",)), "")

    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_the_report_is_written_where_asked(historique, tmp_path):
    cible = tmp_path / "rapport.html"
    ok, message = write_html(entree("a"), cible, "sortie")

    assert ok, message
    assert "<!DOCTYPE html>" in cible.read_text(encoding="utf-8")


def test_the_junit_export_copies_what_pytest_wrote(historique, tmp_path):
    """Reconstruire le XML a partir des compteurs donnerait un fichier
    approximatif la ou on attend celui du run."""
    source = tmp_path / "junit.xml"
    source.write_text('<testsuites><testsuite name="x"/></testsuites>',
                      encoding="utf-8")
    cible = tmp_path / "export.xml"

    ok, message = write_junit(entree("a", junit_path=str(source)), cible)
    assert ok, message
    assert cible.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_a_run_without_junit_says_so_instead_of_writing_nothing(historique,
                                                                tmp_path):
    ok, message = write_junit(entree("a"), tmp_path / "export.xml")

    assert not ok and "JUnit" in message
    assert not (tmp_path / "export.xml").exists()


def test_a_junit_file_deleted_since_the_run_is_reported(historique, tmp_path):
    ok, message = write_junit(entree("a", junit_path=str(tmp_path / "parti.xml")),
                              tmp_path / "export.xml")
    assert not ok and message


# ------------------------------------------------------------------ compteurs

def test_an_entry_knows_if_the_run_went_well():
    assert entree("a", failed=0, echecs=()).ok
    assert not entree("a", failed=1).ok
    assert not RunEntry(id="a", timestamp=0, workspace="/w",
                        counts={"ERROR": 1}).ok


def test_the_total_adds_every_status():
    e = RunEntry(id="a", timestamp=0, workspace="/w",
                 counts={"PASSED": 3, "FAILED": 1, "SKIPPED": 2})
    assert e.total == 6
    assert e.count(Status.SKIPPED) == 2
    assert e.count(Status.ERROR) == 0
