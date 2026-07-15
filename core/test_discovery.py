import subprocess
import sys


def collect_tests(workspace: str) -> list[str]:
    """
    Collecte les tests avec pytest et retourne les nodeids RELATIFS au workspace.

    Exemple:
        tests/test_api.py::test_login[admin]

    Important:
        On ne convertit plus en chemins absolus. Comme pytest est lance avec
        cwd=workspace, les nodeids relatifs sont les plus stables et ils matchent
        aussi les lignes de sortie pytest -v.
    """
    cmd = [
        sys.executable,
        "-m", "pytest",
        "--collect-only",
        "-q",
        "--import-mode=importlib",
    ]

    process = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
    )

    # returncode 5 = no tests collected, pas une vraie erreur
    if process.returncode not in (0, 5):
        raise RuntimeError(process.stderr or process.stdout)

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
