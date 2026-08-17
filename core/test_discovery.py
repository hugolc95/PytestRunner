import os
import subprocess

from core.markers import Collection, marker_probe, read_probe
from core.python_interpreter import resolve_interpreter, subprocess_flags
from core.workspace_config import import_mode_args, pytest_env

_ENV_MARKERS = "PYTESTRUNNER_MARKERS_OUT"


def collect_tests(workspace: str, interpreter: str | None = None) -> list[str]:
    """Nodeids seuls. Voir `collect_details` pour les markers qui vont avec."""
    return list(collect_details(workspace, interpreter).nodeids)


def collect_details(workspace: str, interpreter: str | None = None) -> Collection:
    """
    Collecte les tests avec pytest et retourne les nodeids RELATIFS au workspace.

    Exemple:
        tests/test_api.py::test_login[admin]

    Important:
        On ne convertit plus en chemins absolus. Comme pytest est lance avec
        cwd=workspace, les nodeids relatifs sont les plus stables et ils matchent
        aussi les lignes de sortie pytest -v.

    `interpreter` permet de collecter avec un autre Python que celui du GUI ;
    par defaut on resout selon config.yml puis le Python courant.
    """
    python = interpreter or resolve_interpreter(workspace=workspace)

    if not python:
        raise RuntimeError(
            "No Python interpreter is configured for the tests.\n"
            "Settings > Test Python interpreter... menu"
        )

    # Les markers sont releves pendant CE passage : une seconde collecte
    # doublerait l'attente, et sur un conftest qui parle au materiel elle la
    # doublerait pour de bon.
    with marker_probe() as (args_plugin, dossier_plugin, fichier_markers):
        cmd = [
            python,
            "-m", "pytest",
            "--collect-only",
            "-q",
            # Pas de --import-mode impose : le defaut de pytest (prepend) insere le
            # dossier du fichier de test en tete de sys.path, ce dont dependent les
            # suites dont le conftest importe un module voisin. Un workspace qui a
            # besoin d'importlib le declare dans sa configuration.
            *import_mode_args(workspace),
            *args_plugin,
        ]

        env = dict(pytest_env(workspace))
        env[_ENV_MARKERS] = fichier_markers
        ancien = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = dossier_plugin + (os.pathsep + ancien if ancien else "")

        try:
            process = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                env=env,
                creationflags=subprocess_flags(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Python interpreter not found: {python}\n"
                "Fix the path in the Settings > Test Python interpreter... menu."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Could not start the interpreter {python}: {exc}") from exc

        markers_par_nodeid, descriptions = read_probe(fichier_markers)

    # returncode 5 = no tests collected, pas une vraie erreur
    if process.returncode not in (0, 5):
        output = process.stderr or process.stdout or ""
        if "No module named pytest" in output:
            raise RuntimeError(
                f"pytest is not installed in the test interpreter:\n  {python}\n\n"
                "It's THIS interpreter that must have pytest, not the interface's.\n"
                f"Install it with:\n  \"{python}\" -m pip install pytest"
            )
        raise RuntimeError(output)

    results: list[str] = []
    seen: set[str] = set()

    for line in process.stdout.splitlines():
        nodeid = line.strip()
        if not nodeid:
            continue
        if "::" not in nodeid:
            continue
        # Ignore les lignes parasites pytest, warnings, resume, etc.
        if nodeid.startswith(("=", "<", "ERROR", "FAILED")):
            continue
        normalized = nodeid.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)

    # Le releve ne fait autorite que sur les tests que la collecte a listes :
    # un plugin qui aurait rate son fichier ne doit pas inventer de tests.
    markers_par_nodeid = {k: v for k, v in markers_par_nodeid.items() if k in seen}

    return Collection(tuple(results), markers_par_nodeid, descriptions)
