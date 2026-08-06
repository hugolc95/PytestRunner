import subprocess

from core.python_interpreter import resolve_interpreter, subprocess_flags


def collect_tests(workspace: str, interpreter: str | None = None) -> list[str]:
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
            "Aucun interpreteur Python n'est configure pour les tests.\n"
            "Menu Configuration > Interpreteur Python des tests..."
        )

    cmd = [
        python,
        "-m", "pytest",
        "--collect-only",
        "-q",
        "--import-mode=importlib",
    ]

    try:
        process = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            creationflags=subprocess_flags(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Interpreteur Python introuvable : {python}\n"
            "Corrigez le chemin dans le menu Configuration > Interpreteur Python des tests..."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Impossible de lancer l'interpreteur {python} : {exc}") from exc

    # returncode 5 = no tests collected, pas une vraie erreur
    if process.returncode not in (0, 5):
        output = process.stderr or process.stdout or ""
        if "No module named pytest" in output:
            raise RuntimeError(
                f"pytest n'est pas installe dans l'interpreteur des tests :\n  {python}\n\n"
                "C'est cet interpreteur-la qui doit avoir pytest, pas celui de l'interface.\n"
                f"Installez-le avec :\n  \"{python}\" -m pip install pytest"
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

    return results
