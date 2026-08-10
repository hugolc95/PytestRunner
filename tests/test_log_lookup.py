"""Recherche du fichier .log d'un test.

Le manifeste `last_run_index.json` n'est ecrit que par le conftest livre en
exemple. Un workspace reel a son propre conftest, qui ecrit ses .log dans un
sous-dossier par run sans forcement tenir ce manifeste : sans repli, l'onglet
Log restait vide.
"""

import json
import os
import time

import pytest

from gui_qt.config.config_loader import (
    find_test_log,
    find_test_log_by_search,
    nodeid_tokens,
    resolve_log_root,
)

NODEID = "NIST/TestSuiteCDS/test_PSO_CDS_RSA.py::TestSuite::test_pso[nom-RSA-mod2048-tg1-tc11]"


def make_workspace(tmp_path, log_key="LOG_PATH", log_dir="traces_apdu"):
    (tmp_path / "config.yaml").write_text(f"{log_key}: {log_dir}\n", encoding="utf-8")
    return tmp_path


def write_log(dossier, nom, contenu="trace", age_secondes=0):
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / f"{nom}.log"
    fichier.write_text(contenu, encoding="utf-8")
    if age_secondes:
        ancien = time.time() - age_secondes
        os.utime(fichier, (ancien, ancien))
    return fichier


# ------------------------------------------------------------------- decoupage

def test_a_nodeid_is_split_into_its_parts():
    assert nodeid_tokens(NODEID) == [
        "test_PSO_CDS_RSA", "TestSuite", "test_pso", "nom-RSA-mod2048-tg1-tc11",
    ]


def test_a_nodeid_without_class_is_handled():
    assert nodeid_tokens("a/test_x.py::test_f") == ["test_x", "test_f"]


def test_a_parametrized_nodeid_without_class_is_handled():
    assert nodeid_tokens("test_x.py::test_f[cas]") == ["test_x", "test_f", "cas"]


# ------------------------------------------------------- recherche sans manifeste

def test_the_log_is_found_without_any_manifest(tmp_path):
    """Le cas d'un workspace reel : des .log, pas de manifeste."""
    ws = make_workspace(tmp_path)
    attendu = write_log(
        ws / "traces_apdu" / "20260807_120000",
        "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc11",
    )

    assert find_test_log(str(ws), NODEID) == attendu


def test_the_log_of_the_most_recent_run_wins(tmp_path):
    """Les logs sont ranges par run : c'est celui qui vient de tourner qui
    interesse l'utilisateur."""
    ws = make_workspace(tmp_path)
    nom = "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc11"
    write_log(ws / "traces_apdu" / "20260101_000000", nom, "ancien", age_secondes=86400)
    recent = write_log(ws / "traces_apdu" / "20260807_120000", nom, "recent")

    assert find_test_log(str(ws), NODEID) == recent
    assert find_test_log(str(ws), NODEID).read_text(encoding="utf-8") == "recent"


def test_the_right_parameter_is_picked_among_siblings(tmp_path):
    ws = make_workspace(tmp_path)
    dossier = ws / "traces_apdu" / "run"
    write_log(dossier, "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc10")
    attendu = write_log(dossier, "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc11")
    write_log(dossier, "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc12")

    assert find_test_log(str(ws), NODEID) == attendu


@pytest.mark.parametrize("separateur", ["-", "_", "."])
def test_the_sanitizing_style_of_the_conftest_does_not_matter(tmp_path, separateur):
    """Chaque conftest assainit les nodeids a sa facon."""
    ws = make_workspace(tmp_path)
    nom = f"test_pso{separateur}nom{separateur}RSA{separateur}mod2048{separateur}tg1{separateur}tc11"
    attendu = write_log(ws / "traces_apdu" / "run", nom)

    assert find_test_log(str(ws), NODEID) == attendu


def test_a_log_of_another_test_is_not_returned(tmp_path):
    """Sans exigence sur le nom de la fonction, n'importe quel log du meme
    fichier passerait pour le bon."""
    ws = make_workspace(tmp_path)
    write_log(ws / "traces_apdu" / "run", "test_PSO_CDS_RSA_test_autre_chose")

    assert find_test_log(str(ws), NODEID) is None


def test_nothing_is_returned_when_the_log_directory_is_empty(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / "traces_apdu").mkdir()
    assert find_test_log(str(ws), NODEID) is None


def test_nothing_is_returned_when_the_log_directory_does_not_exist(tmp_path):
    ws = make_workspace(tmp_path)
    assert find_test_log(str(ws), NODEID) is None


def test_txt_logs_are_accepted_too(tmp_path):
    ws = make_workspace(tmp_path)
    dossier = ws / "traces_apdu" / "run"
    dossier.mkdir(parents=True)
    attendu = dossier / "test_pso_nom-RSA-mod2048-tg1-tc11.txt"
    attendu.write_text("trace", encoding="utf-8")

    assert find_test_log_by_search(str(ws), NODEID) == attendu


# ------------------------------------------------------------- avec un manifeste

def test_the_manifest_is_used_when_present(tmp_path):
    """Il est exact et immediat : il reste prioritaire sur la recherche."""
    ws = make_workspace(tmp_path)
    racine = ws / "traces_apdu"
    vise = write_log(racine, "peu_importe_le_nom")
    # Un fichier que la recherche prefererait, pour prouver que le manifeste gagne.
    write_log(racine / "run", "test_PSO_CDS_RSA_test_pso_nom-RSA-mod2048-tg1-tc11")
    (racine / "last_run_index.json").write_text(
        json.dumps({NODEID: str(vise)}), encoding="utf-8"
    )

    assert find_test_log(str(ws), NODEID) == vise


def test_a_manifest_without_this_test_falls_back_to_searching(tmp_path):
    ws = make_workspace(tmp_path)
    racine = ws / "traces_apdu"
    racine.mkdir()
    (racine / "last_run_index.json").write_text(
        json.dumps({"autre/test_y.py::test_z": "/nulle/part.log"}), encoding="utf-8"
    )
    attendu = write_log(racine / "run", "test_pso_nom-RSA-mod2048-tg1-tc11")

    assert find_test_log(str(ws), NODEID) == attendu


def test_a_broken_manifest_falls_back_to_searching(tmp_path):
    ws = make_workspace(tmp_path)
    racine = ws / "traces_apdu"
    racine.mkdir()
    (racine / "last_run_index.json").write_text("{ pas du json", encoding="utf-8")
    attendu = write_log(racine / "run", "test_pso_nom-RSA-mod2048-tg1-tc11")

    assert find_test_log(str(ws), NODEID) == attendu


# ------------------------------------------------- le chemin vient bien du yml

def test_the_search_uses_the_directory_from_the_configuration(tmp_path):
    ws = make_workspace(tmp_path, log_dir="mes_traces")
    assert resolve_log_root(str(ws)) == ws / "mes_traces"

    attendu = write_log(ws / "mes_traces" / "run", "test_pso_nom-RSA-mod2048-tg1-tc11")
    assert find_test_log(str(ws), NODEID) == attendu


def test_logs_outside_the_configured_directory_are_ignored(tmp_path):
    """Chercher partout ferait remonter les logs d'un autre outil."""
    ws = make_workspace(tmp_path, log_dir="mes_traces")
    (ws / "mes_traces").mkdir()
    write_log(ws / "ailleurs", "test_pso_nom-RSA-mod2048-tg1-tc11")

    assert find_test_log(str(ws), NODEID) is None


# ------------------------- fichier de configuration au nom non standard

def test_the_log_path_is_read_from_a_config_with_another_name(tmp_path):
    """Le defaut signale : l'onglet Log restait vide.

    resolve_log_root() ne lisait que config.yml / config.yaml. Un projet dont la
    configuration s'appelle configWorkspace.yml voyait son LOG_PATH ignore, et
    les logs cherches dans `<workspace>/logs`, qui n'existe pas.
    """
    (tmp_path / "configWorkspace.yml").write_text("LOG_PATH: Traces\n", encoding="utf-8")
    assert resolve_log_root(str(tmp_path)) == tmp_path / "Traces"


def test_a_yaml_without_log_path_does_not_shadow_the_right_one(tmp_path):
    """Le premier YAML venu ne doit pas faire conclure a une absence de reglage."""
    (tmp_path / "aaa_autre.yml").write_text("Mode: PERSO\n", encoding="utf-8")
    (tmp_path / "configWorkspace.yml").write_text("LOG_PATH: Traces\n", encoding="utf-8")

    assert resolve_log_root(str(tmp_path)) == tmp_path / "Traces"


def test_the_chosen_config_file_takes_precedence(tmp_path):
    """Celui que l'utilisateur a designe dans "Ouvrir la configuration"."""
    (tmp_path / "config.yml").write_text("LOG_PATH: mauvais\n", encoding="utf-8")
    choisi = tmp_path / "configWorkspace.yml"
    choisi.write_text("LOG_PATH: bon\n", encoding="utf-8")

    assert resolve_log_root(str(tmp_path), str(choisi)) == tmp_path / "bon"


def test_a_log_path_inside_a_section_is_found(tmp_path):
    """Les configurations reelles rangent leurs reglages par section."""
    (tmp_path / "config.yml").write_text(
        "General:\n  LOG_PATH: Traces\n", encoding="utf-8")
    assert resolve_log_root(str(tmp_path)) == tmp_path / "Traces"


def test_a_root_log_path_wins_over_a_sections_one(tmp_path):
    (tmp_path / "config.yml").write_text(
        "LOG_PATH: racine\nDebug:\n  LOG_PATH: section\n", encoding="utf-8")
    assert resolve_log_root(str(tmp_path)) == tmp_path / "racine"


# ------------------- dossier horodate et arborescence recreee dedans

ARBRE = "Test_Suite_CryptoLib/NIST_Tests/TestSuiteCDS/test_PSO_CDS_RSA/TestSuitePSOCDS_RSA"
NODEID_ARBRE = ("Test_Suite_CryptoLib/NIST_Tests/TestSuiteCDS/test_PSO_CDS_RSA.py"
                "::TestSuitePSOCDS_RSA::test_PSO_CDS_RSA_STD[err-RSA-AFT-mod3072-tg2-tc25]")


def _run_horodate(racine, horodatage, cas, contenu="trace", age=0):
    """Reproduit ce que fait le conftest : un dossier par run, et dedans
    l'arborescence des tests."""
    dossier = racine / horodatage / ARBRE
    return write_log(dossier, f"test_PSO_CDS_RSA_STD_{cas}", contenu, age)


def test_a_log_inside_the_recreated_tree_is_found(tmp_path):
    """Le rapprochement ne portait que sur le nom du fichier. Or le conftest
    recree l'arborescence des tests, donc une partie de l'identite du test est
    portee par les dossiers."""
    make_workspace(tmp_path, log_dir="Traces")
    attendu = _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                            "err-RSA-AFT-mod3072-tg2-tc25")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == attendu


def test_the_most_recent_timestamped_run_wins(tmp_path):
    """Deux runs contiennent le meme test : c'est celui qui vient de tourner
    qu'on veut lire, pas celui d'hier."""
    make_workspace(tmp_path, log_dir="Traces")
    _run_horodate(tmp_path / "Traces", "2026-08-06_09-00-00",
                  "err-RSA-AFT-mod3072-tg2-tc25", "vieux", age=86400)
    recent = _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                           "err-RSA-AFT-mod3072-tg2-tc25", "recent")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == recent


def test_a_neighbour_case_is_not_returned(tmp_path):
    """Tout le dossier partage le nom de la fonction : seul le parametre
    distingue les cas."""
    make_workspace(tmp_path, log_dir="Traces")
    attendu = _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                            "err-RSA-AFT-mod3072-tg2-tc25")
    _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                  "nom-RSA-AFT-mod2048-tg1-tc4")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == attendu


def test_a_generic_log_beside_the_case_is_not_preferred(tmp_path):
    """Un setup.log voisin partage tout le chemin : c'est le nom du fichier qui
    doit departager."""
    make_workspace(tmp_path, log_dir="Traces")
    attendu = _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                            "err-RSA-AFT-mod3072-tg2-tc25")
    write_log(tmp_path / "Traces" / "2026-08-07_18-11-23" / ARBRE, "setup")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == attendu


def test_the_case_can_be_a_directory_of_its_own(tmp_path):
    """Certains conftest poussent l'arborescence jusqu'au cas, et nomment le
    fichier de facon generique."""
    make_workspace(tmp_path, log_dir="Traces")
    dossier = (tmp_path / "Traces" / "2026-08-07_18-11-23" / ARBRE
               / "test_PSO_CDS_RSA_STD" / "err-RSA-AFT-mod3072-tg2-tc25")
    attendu = write_log(dossier, "test")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == attendu


def test_an_old_run_does_not_exhaust_the_scan(tmp_path):
    """Un plafond global de fichiers laissait des mois d'historique consommer le
    budget avant meme d'atteindre le run du jour."""
    from gui_qt.config.config_loader import MAX_LOG_FILES_SCANNED

    make_workspace(tmp_path, log_dir="Traces")
    vieux = tmp_path / "Traces" / "2026-01-01_00-00-00"
    for i in range(MAX_LOG_FILES_SCANNED + 50):
        write_log(vieux, f"bruit_{i}", age_secondes=86400)

    recent = _run_horodate(tmp_path / "Traces", "2026-08-07_18-11-23",
                           "err-RSA-AFT-mod3072-tg2-tc25")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == recent


def test_a_conftest_that_does_not_timestamp_still_works(tmp_path):
    """La racine elle-meme est examinee en dernier."""
    make_workspace(tmp_path, log_dir="Traces")
    attendu = write_log(tmp_path / "Traces",
                        "test_PSO_CDS_RSA_STD_err-RSA-AFT-mod3072-tg2-tc25")

    assert find_test_log(str(tmp_path), NODEID_ARBRE) == attendu
