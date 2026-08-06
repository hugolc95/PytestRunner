"""Windows refuse une ligne de commande de plus de 32767 caracteres et echoue
avec "WinError 206: le nom de fichier ou son extension est trop long".

Selectionner un dossier entier suffit a depasser cette limite : quelques
centaines de nodeids de 40 a 100 caracteres y suffisent. Les nodeids partent
donc dans un fichier d'arguments des que la ligne devient longue.
"""

import os
import subprocess
import sys

import pytest

from core.pytest_executor import MAX_INLINE_ARGS_LENGTH, pytest_nodeid_args


def make_nodeids(count: int, width: int = 80) -> list[str]:
    return [f"paquet/test_fichier_{i:04d}.py::test_fonction_{i:04d}".ljust(width, "x") for i in range(count)]


def test_short_selection_stays_on_the_command_line():
    nodeids = ["tests/test_a.py::test_un", "tests/test_b.py::test_deux"]
    with pytest_nodeid_args(nodeids) as args:
        assert args == nodeids


def test_empty_selection_is_handled():
    with pytest_nodeid_args([]) as args:
        assert args == []


def test_long_selection_switches_to_an_argument_file():
    nodeids = make_nodeids(500)
    assert sum(len(n) + 1 for n in nodeids) > MAX_INLINE_ARGS_LENGTH

    with pytest_nodeid_args(nodeids) as args:
        assert len(args) == 1
        assert args[0].startswith("@")
        assert os.path.isfile(args[0][1:])


def test_the_argument_file_contains_every_nodeid():
    nodeids = make_nodeids(500)
    with pytest_nodeid_args(nodeids) as args:
        written = open(args[0][1:], encoding="utf-8").read().splitlines()
    assert written == nodeids


def test_the_argument_file_is_removed_afterwards():
    with pytest_nodeid_args(make_nodeids(500)) as args:
        path = args[0][1:]
    assert not os.path.exists(path)


def test_the_argument_file_is_removed_even_on_error():
    """Sinon une erreur pendant un run laisserait des fichiers derriere elle."""
    path = None
    with pytest.raises(RuntimeError):
        with pytest_nodeid_args(make_nodeids(500)) as args:
            path = args[0][1:]
            raise RuntimeError("run interrompu")

    assert path and not os.path.exists(path)


def test_the_boundary_is_respected():
    just_under = ["a" * 99] * 60          # 6000 caracteres exactement
    assert sum(len(n) + 1 for n in just_under) == MAX_INLINE_ARGS_LENGTH
    with pytest_nodeid_args(just_under) as args:
        assert args == just_under

    just_over = just_under + ["b" * 99]
    with pytest_nodeid_args(just_over) as args:
        assert args[0].startswith("@")


def test_pytest_really_runs_a_selection_too_long_for_a_command_line(tmp_path):
    """Verification de bout en bout : la selection depasse la limite Windows,
    et pytest execute quand meme exactement les tests demandes."""
    source = "\n".join(f"def test_fonction_{i:04d}():\n    assert True\n" for i in range(400))
    (tmp_path / "test_beaucoup.py").write_text(source, encoding="utf-8")

    nodeids = [f"test_beaucoup.py::test_fonction_{i:04d}" for i in range(400)]
    assert sum(len(n) + 1 for n in nodeids) > 32767 // 3  # bien au-dela du raisonnable

    with pytest_nodeid_args(nodeids) as args:
        assert args[0].startswith("@"), "ce volume doit passer par un fichier"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-q", "--import-mode=importlib"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stdout
    assert "400 passed" in result.stdout
