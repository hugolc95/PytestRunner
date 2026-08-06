from pathlib import Path

from gui_qt.config.config_loader import discover_config_candidates, find_config_yaml
from gui_qt.dialogs import resolve_config_to_open


def test_no_candidates_in_an_empty_workspace(tmp_path):
    assert discover_config_candidates(str(tmp_path)) == []


def test_standard_names_come_first(tmp_path):
    (tmp_path / "aaa.yml").write_text("", encoding="utf-8")
    (tmp_path / "config.yml").write_text("", encoding="utf-8")

    names = [p.name for p in discover_config_candidates(str(tmp_path))]
    assert names == ["config.yml", "aaa.yml"]


def test_non_standard_names_are_found_and_sorted(tmp_path):
    for name in ("zebra.yaml", "alpha.yml", "Beta.yml"):
        (tmp_path / name).write_text("", encoding="utf-8")

    names = [p.name for p in discover_config_candidates(str(tmp_path))]
    assert names == ["alpha.yml", "Beta.yml", "zebra.yaml"]


def test_only_yaml_files_are_candidates(tmp_path):
    for name in ("notes.txt", "script.py", "settings.json", "real.yml"):
        (tmp_path / name).write_text("", encoding="utf-8")

    assert [p.name for p in discover_config_candidates(str(tmp_path))] == ["real.yml"]


def test_directories_are_not_candidates(tmp_path):
    (tmp_path / "stuff.yml").mkdir()
    assert discover_config_candidates(str(tmp_path)) == []


def test_missing_workspace_is_handled(tmp_path):
    assert discover_config_candidates(str(tmp_path / "nope")) == []


def test_standard_name_is_opened_without_asking(tmp_path):
    (tmp_path / "config.yml").write_text("", encoding="utf-8")
    (tmp_path / "other.yml").write_text("", encoding="utf-8")

    # parent=None : si la fonction essayait d'ouvrir une boite de dialogue,
    # le test le revelerait au lieu de passer silencieusement.
    chosen = resolve_config_to_open(None, str(tmp_path))
    assert chosen == tmp_path / "config.yml"


def test_a_single_non_standard_yaml_is_opened_without_asking(tmp_path):
    """Le cas signale : le fichier de config ne s'appelle pas config.yml."""
    (tmp_path / "parametres_projet.yaml").write_text("log_directory: logs\n", encoding="utf-8")

    chosen = resolve_config_to_open(None, str(tmp_path))
    assert chosen == tmp_path / "parametres_projet.yaml"


def test_a_remembered_file_wins_over_detection(tmp_path):
    (tmp_path / "config.yml").write_text("", encoding="utf-8")
    remembered = tmp_path / "prefere.yaml"
    remembered.write_text("", encoding="utf-8")

    chosen = resolve_config_to_open(None, str(tmp_path), remembered=str(remembered))
    assert chosen == remembered


def test_a_remembered_file_that_vanished_falls_back_to_detection(tmp_path):
    (tmp_path / "config.yml").write_text("", encoding="utf-8")

    chosen = resolve_config_to_open(None, str(tmp_path), remembered=str(tmp_path / "disparu.yaml"))
    assert chosen == tmp_path / "config.yml"


def test_find_config_yaml_still_only_accepts_standard_names(tmp_path):
    """resolve_log_root() et le conftest du workspace s'appuient dessus :
    l'elargir desynchroniserait le GUI et les tests sur l'emplacement des logs."""
    (tmp_path / "autre.yml").write_text("", encoding="utf-8")
    assert find_config_yaml(str(tmp_path)) is None

    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    assert find_config_yaml(str(tmp_path)) == tmp_path / "config.yaml"


def test_candidates_are_paths(tmp_path):
    (tmp_path / "config.yml").write_text("", encoding="utf-8")
    assert all(isinstance(p, Path) for p in discover_config_candidates(str(tmp_path)))
