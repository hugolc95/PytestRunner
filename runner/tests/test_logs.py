"""Retrouver le .log qu'un test vient de produire.

C'est souvent la seule trace de ce que la carte a reellement repondu : la
sortie pytest ne montre que le verdict. La refonte s'etait contentee d'un
rapprochement sur le nom de la fonction, ce qui suffisait sur l'exemple et
echouait sur un vrai workspace -- arborescence recreee sous un dossier
horodate, parametres dans le nom du fichier, un dossier par lecteur.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from runner.domain.logs import (
    find_test_log,
    nodeid_tokens,
    places_searched,
    run_directories,
)

NODEID = ("NIST/TestSuiteCDS/test_PSO_CDS_RSA.py::TestSuite"
          "::test_pso[nom-RSA-mod2048-tg1-tc11]")


def ecrire(dossier, nom: str, contenu: str = "trace", age: float = 0.0):
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / f"{nom}.log"
    fichier.write_text(contenu, encoding="utf-8")
    if age:
        quand = time.time() - age
        os.utime(fichier, (quand, quand))
    return fichier


def dater(dossier, age: float) -> None:
    quand = time.time() - age
    os.utime(dossier, (quand, quand))


# ---------------------------------------------------------------- decoupage

def test_a_nodeid_is_split_into_its_parts():
    assert nodeid_tokens(NODEID) == [
        "test_PSO_CDS_RSA", "TestSuite", "test_pso", "nom-RSA-mod2048-tg1-tc11",
    ]


def test_a_nodeid_without_a_class_is_handled():
    assert nodeid_tokens("a/test_x.py::test_f") == ["test_x", "test_f"]


def test_a_parametrised_nodeid_without_a_class_is_handled():
    assert nodeid_tokens("test_x.py::test_f[cas]") == ["test_x", "test_f", "cas"]


def test_backslashes_do_not_change_the_split():
    """Les nodeids viennent d'un pytest lance sous Windows."""
    assert nodeid_tokens(r"a\b\test_x.py::test_f") == ["test_x", "test_f"]


# ------------------------------------------------------- recherche sans manifeste

def test_the_log_is_found_with_no_manifest_at_all(tmp_path):
    """Le cas d'un vrai workspace : des .log, pas de manifeste."""
    attendu = ecrire(tmp_path / "20260810_112653" / "NIST" / "TestSuiteCDS",
                     "test_pso[nom-RSA-mod2048-tg1-tc11]")
    assert find_test_log(tmp_path, NODEID) == attendu


def test_the_test_identity_may_be_carried_by_the_folders(tmp_path):
    """Le conftest recree l'arborescence : le nom du fichier ne porte alors
    que le parametre, le reste est dans le chemin."""
    attendu = ecrire(
        tmp_path / "20260810_112653" / "TestSuiteCDS" / "test_PSO_CDS_RSA",
        "nom-RSA-mod2048-tg1-tc11")
    assert find_test_log(tmp_path, NODEID) == attendu


def test_the_run_of_today_wins_over_the_one_of_yesterday(tmp_path):
    """Repondre avec le log d'un run precedent est pire que ne rien rendre :
    on lit une trace qui n'a rien a voir avec le verdict affiche."""
    vieux = tmp_path / "20260809_090000" / "NIST"
    recent = tmp_path / "20260810_112653" / "NIST"
    ecrire(vieux, "test_pso[nom-RSA-mod2048-tg1-tc11]", "hier", age=90000)
    attendu = ecrire(recent, "test_pso[nom-RSA-mod2048-tg1-tc11]", "aujourdhui")
    dater(vieux.parent, 90000)

    trouve = find_test_log(tmp_path, NODEID)
    assert trouve == attendu
    assert trouve.read_text(encoding="utf-8") == "aujourdhui"


def test_a_run_folder_nested_under_a_project_folder_is_still_found(tmp_path):
    """L'horodate n'est pas toujours un enfant direct de la racine."""
    attendu = ecrire(
        tmp_path / "CryptoWrapper" / "20260810_112653" / "NIST",
        "test_pso[nom-RSA-mod2048-tg1-tc11]")
    assert find_test_log(tmp_path, NODEID) == attendu


def test_nested_run_folders_are_still_ordered_by_run(tmp_path):
    """Les horodates comptent MEME sous un dossier de projet.

    Sans descendre jusqu'a eux, on retombe sur les dossiers de projet, dont la
    date de modification ne dit rien de la date du run : celui d'hier peut tres
    bien avoir ete touche apres, et son log serait alors rendu pour celui
    d'aujourd'hui.
    """
    hier = ecrire(tmp_path / "ProjetA" / "20260809_090000" / "NIST",
                  "test_pso[nom-RSA-mod2048-tg1-tc11]", "hier", age=90000)
    aujourdhui = ecrire(tmp_path / "ProjetB" / "20260810_112653" / "NIST",
                        "test_pso[nom-RSA-mod2048-tg1-tc11]", "aujourdhui")
    dater(hier.parent.parent, 90000)
    dater(aujourdhui.parent.parent, 90000)
    # Le dossier de PROJET du vieux run parait le plus recent des deux.
    dater(tmp_path / "ProjetB", 90000)

    trouve = find_test_log(tmp_path, NODEID)
    assert trouve is not None
    assert trouve.read_text(encoding="utf-8") == "aujourdhui"


def test_todays_run_wins_even_when_an_older_log_matches_better(tmp_path):
    """On s'arrete au premier dossier de run qui contient le test.

    Chercher depuis la racine mettrait tous les runs en concurrence sur le
    score : un vieux log range plus profond, donc portant plus de morceaux du
    nodeid dans son chemin, battrait celui que le run qui vient de finir a
    ecrit a plat. On lirait une trace sans rapport avec le verdict affiche.
    """
    vieux = ecrire(tmp_path / "20260809_090000" / "NIST" / "TestSuiteCDS",
                   "test_pso[nom-RSA-mod2048-tg1-tc11]", "hier", age=90000)
    recent = ecrire(tmp_path / "20260810_112653",
                    "test_pso[nom-RSA-mod2048-tg1-tc11]", "aujourdhui")
    dater(vieux.parent.parent.parent, 90000)

    trouve = find_test_log(tmp_path, NODEID)
    assert trouve == recent, (
        f"le log d'hier a gagne sur celui d'aujourd'hui : {trouve}")


def test_a_conftest_that_does_not_date_its_folders_still_works(tmp_path):
    attendu = ecrire(tmp_path, "test_pso[nom-RSA-mod2048-tg1-tc11]")
    assert find_test_log(tmp_path, NODEID) == attendu


@pytest.mark.parametrize("nom", [
    "test_pso[nom-RSA-mod2048-tg1-tc11]",
    "test_pso_nom-RSA-mod2048-tg1-tc11",
    "test_pso.nom_RSA_mod2048_tg1_tc11",
])
def test_the_conftest_may_sanitise_the_nodeid_as_it_likes(tmp_path, nom):
    """`cas-1`, `cas_1` et `cas.1` doivent tous se reconnaitre : chaque
    conftest assainit le nodeid a sa facon."""
    attendu = ecrire(tmp_path / "20260810_112653", nom)
    assert find_test_log(tmp_path, NODEID) == attendu


def test_a_parameter_that_prefixes_another_is_not_confused(tmp_path):
    """`[...HashAlg==SHA512]` et `[...HashAlg==SHA512_256]` : normalises, le
    premier est contenu dans le second, donc les deux fichiers passent le
    filtre et comptent le meme nombre de morceaux. Seule la prime au nom qui
    se TERMINE par le parametre les departage.

    Le mauvais fichier est ecrit EN DERNIER : a egalite de score, c'est la
    date qui tranche, et il gagnerait. Ecrit en premier, il perdait sur la
    date -- le test passait alors sans que la prime serve a rien.
    """
    nodeid = "t/test_h.py::test_sign[HashAlg==SHA512]"
    dossier = tmp_path / "20260810_112653"
    attendu = ecrire(dossier, "test_sign[HashAlg==SHA512]", "le bon", age=60)
    ecrire(dossier, "test_sign[HashAlg==SHA512_256]", "le mauvais")

    assert find_test_log(tmp_path, nodeid) == attendu


def test_the_function_name_alone_does_not_pick_up_a_neighbour(tmp_path):
    """Normalise, `test_pso` se retrouve dans `test_PSO_CDS_RSA` : exiger aussi
    le parametre est ce qui empeche n'importe quel log du fichier de passer."""
    dossier = tmp_path / "20260810_112653" / "NIST"
    ecrire(dossier, "test_pso[un-autre-cas]")
    assert find_test_log(tmp_path, NODEID) is None


def test_a_txt_log_counts_too(tmp_path):
    """Les conftest ne sont pas d'accord sur l'extension."""
    dossier = tmp_path / "20260810_112653"
    dossier.mkdir(parents=True)
    attendu = dossier / "test_f.txt"
    attendu.write_text("trace", encoding="utf-8")

    assert find_test_log(tmp_path, "t/test_x.py::test_f") == attendu


def test_a_file_that_is_not_a_log_is_left_alone(tmp_path):
    """Le dossier de run contient aussi des rapports, des captures, du XML."""
    dossier = tmp_path / "20260810_112653"
    dossier.mkdir(parents=True)
    (dossier / "test_f.xml").write_text("<x/>", encoding="utf-8")

    assert find_test_log(tmp_path, "t/test_x.py::test_f") is None


def test_nothing_is_returned_when_there_is_nothing(tmp_path):
    assert find_test_log(tmp_path, NODEID) is None
    assert find_test_log(tmp_path / "absent", NODEID) is None
    assert find_test_log(tmp_path, "") is None


# ------------------------------------------------------------- avec un manifeste

def test_the_manifest_is_used_when_there_is_one(tmp_path):
    """Il est exact et immediat : inutile de fouiller l'arborescence."""
    vise = ecrire(tmp_path / "ailleurs", "peu-importe-le-nom")
    # Un fichier que la recherche prefererait, pour prouver que le manifeste
    # l'emporte.
    ecrire(tmp_path / "20260810_112653", "test_pso[nom-RSA-mod2048-tg1-tc11]")
    (tmp_path / "last_run_index.json").write_text(
        json.dumps({NODEID: str(vise)}), encoding="utf-8")

    assert find_test_log(tmp_path, NODEID) == vise


def test_the_manifest_key_may_carry_a_different_prefix(tmp_path):
    """Selon le rootdir de pytest, la clef du manifeste n'a pas forcement le
    meme prefixe de dossier que le nodeid de l'arbre."""
    vise = ecrire(tmp_path / "ailleurs", "trace")
    (tmp_path / "last_run_index.json").write_text(
        json.dumps({"prefixe/" + NODEID: str(vise)}), encoding="utf-8")

    assert find_test_log(tmp_path, NODEID) == vise


def test_a_manifest_that_ignores_this_test_falls_back_to_searching(tmp_path):
    attendu = ecrire(tmp_path / "20260810_112653",
                     "test_pso[nom-RSA-mod2048-tg1-tc11]")
    (tmp_path / "last_run_index.json").write_text(
        json.dumps({"autre/test_y.py::test_z": "/nulle/part"}), encoding="utf-8")

    assert find_test_log(tmp_path, NODEID) == attendu


@pytest.mark.parametrize("contenu", ["{ pas du json", "[]", '{"a": 1}'])
def test_a_broken_manifest_falls_back_to_searching(tmp_path, contenu):
    """Un manifeste tronque par un run interrompu ne doit pas priver du log."""
    attendu = ecrire(tmp_path / "20260810_112653",
                     "test_pso[nom-RSA-mod2048-tg1-tc11]")
    (tmp_path / "last_run_index.json").write_text(contenu, encoding="utf-8")

    assert find_test_log(tmp_path, NODEID) == attendu


def test_a_manifest_pointing_at_a_deleted_file_falls_back_to_searching(tmp_path):
    attendu = ecrire(tmp_path / "20260810_112653",
                     "test_pso[nom-RSA-mod2048-tg1-tc11]")
    (tmp_path / "last_run_index.json").write_text(
        json.dumps({NODEID: str(tmp_path / "efface.log")}), encoding="utf-8")

    assert find_test_log(tmp_path, NODEID) == attendu


# -------------------------------------------------------------- par lecteur

NODEID_SIMPLE = "module/test_exemple.py::test_cible"


def _logs_par_lecteur(racine, contenus: dict) -> dict:
    """Un log par lecteur, dans l'arborescence d'un vrai conftest."""
    ecrits = {}
    for lecteur, contenu in contenus.items():
        dossier = racine / "20260813" / lecteur / "module"
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / "test_cible.log"
        fichier.write_text(contenu, encoding="utf-8")
        ecrits[lecteur] = fichier
    return ecrits


def test_each_reader_gets_its_own_log(tmp_path):
    ecrits = _logs_par_lecteur(tmp_path, {"LecteurA": "vu par A",
                                          "LecteurB": "vu par B"})
    for lecteur, attendu in ecrits.items():
        assert find_test_log(tmp_path, NODEID_SIMPLE, lecteur) == attendu


def test_a_reader_whose_name_is_inside_another_does_not_borrow_its_log(tmp_path):
    """`Reader` se retrouve dans `Cosmo11Secured Reader` : comparer par
    sous-chaine ferait rendre le log du voisin."""
    ecrits = _logs_par_lecteur(tmp_path, {"Reader": "le court",
                                          "Cosmo11Secured Reader": "le long"})
    assert find_test_log(tmp_path, NODEID_SIMPLE, "Reader") == ecrits["Reader"]
    assert (find_test_log(tmp_path, NODEID_SIMPLE, "Cosmo11Secured Reader")
            == ecrits["Cosmo11Secured Reader"])


def test_a_reader_with_no_log_of_its_own_gets_nothing(tmp_path):
    """Plutot rien que le log d'un autre lecteur affiche sous son nom."""
    _logs_par_lecteur(tmp_path, {"LecteurA": "vu par A"})
    assert find_test_log(tmp_path, NODEID_SIMPLE, "LecteurB") is None


def test_a_manifest_pointing_at_another_reader_is_set_aside(tmp_path):
    """Le manifeste ne connait qu'un log par test. Quand il donne celui d'un
    autre lecteur, on repasse par la recherche."""
    ecrits = _logs_par_lecteur(tmp_path, {"LecteurA": "vu par A",
                                          "LecteurB": "vu par B"})
    (tmp_path / "last_run_index.json").write_text(
        json.dumps({NODEID_SIMPLE: str(ecrits["LecteurA"])}), encoding="utf-8")

    assert find_test_log(tmp_path, NODEID_SIMPLE, "LecteurB") == ecrits["LecteurB"]
    assert find_test_log(tmp_path, NODEID_SIMPLE, "LecteurA") == ecrits["LecteurA"]


# ------------------------------------------------------- ou l'on a regarde

def test_the_places_searched_are_the_ones_actually_visited(tmp_path):
    """Le message d'absence les montre : il doit dire vrai."""
    ecrire(tmp_path / "20260810_112653", "un")
    ecrire(tmp_path / "20260809_090000", "deux")

    ou = places_searched(tmp_path)
    assert ou[-1] == tmp_path, "la racine est examinee en dernier"
    assert set(ou) == set(run_directories(tmp_path)) | {tmp_path}


def test_the_most_recent_run_is_named_first(tmp_path):
    vieux = tmp_path / "20260809_090000"
    recent = tmp_path / "20260810_112653"
    ecrire(vieux, "x", age=90000)
    ecrire(recent, "y")
    dater(vieux, 90000)

    assert places_searched(tmp_path)[0] == recent


def test_a_missing_log_folder_is_reported_as_such(tmp_path):
    """Pas de dossier a citer : le message doit alors parler du dossier absent
    plutot que d'aligner une liste vide."""
    assert places_searched(tmp_path / "jamais-cree") == []


# ------------------------------------------------- ce que la fenetre affiche

@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def panneau(qapp):
    from runner.domain.models import Reader
    from runner.ui.results_panel import ResultsPanel

    p = ResultsPanel()
    p.set_readers((Reader("LecteurA", 0), Reader("LecteurB", 1)))
    return p


def test_the_panel_loads_one_log_per_reader(panneau, tmp_path):
    from runner.domain.models import Reader

    _logs_par_lecteur(tmp_path, {"LecteurA": "vu par A", "LecteurB": "vu par B"})
    panneau.set_log_root(tmp_path)
    panneau.show_logs_for(NODEID_SIMPLE,
                          (Reader("LecteurA", 0), Reader("LecteurB", 1)))

    assert "vu par A" in panneau.logs.views[0].text()
    assert "vu par B" in panneau.logs.views[1].text()


def test_the_panel_says_where_it_looked(panneau, tmp_path):
    """« No log found » tout seul se lit comme une panne de l'outil."""
    from runner.domain.models import Reader

    ecrire(tmp_path / "20260810_112653", "un-autre-test")
    panneau.set_log_root(tmp_path)
    panneau.show_logs_for(NODEID_SIMPLE, (Reader("LecteurA", 0),))

    texte = panneau.logs.views[0].text()
    assert "No log found" in texte
    assert "20260810_112653" in texte, "les dossiers examines ne sont pas cites"


def test_the_panel_points_at_the_missing_folder(panneau, tmp_path):
    from runner.domain.models import Reader

    absent = tmp_path / "jamais-cree"
    panneau.set_log_root(absent)
    panneau.show_logs_for(NODEID_SIMPLE, (Reader("LecteurA", 0),))

    texte = panneau.logs.views[0].text()
    assert str(absent) in texte
    assert "does not exist" in texte


def test_the_panel_shows_which_file_it_opened(panneau, tmp_path):
    """Deux logs se ressemblent beaucoup : savoir duquel on parle est la
    premiere chose qu'on verifie."""
    from runner.domain.models import Reader

    ecrits = _logs_par_lecteur(tmp_path, {"LecteurA": "vu par A"})
    panneau.set_log_root(tmp_path)
    panneau.show_logs_for(NODEID_SIMPLE, (Reader("LecteurA", 0),))

    assert panneau.logs.headers[0].toolTip() == str(ecrits["LecteurA"])
