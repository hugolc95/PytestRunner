"""Lancement de pytest et lecture de sa sortie au fil de l'eau.

Rien ici ne connait Qt. Le suivi passe par des rappels (`on_line`,
`on_outcome`) que la couche service branche sur des signaux : le domaine reste
utilisable depuis un script ou un test.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from runner.domain import parsing
from runner.domain.models import Outcome, Reader, ReaderReport, RunRequest, Status
from runner.domain.reader_isolation import ENV_CONFIG, ENV_READER, reader_plugin

# Au-dela, la ligne de commande depasse la limite de Windows (32 768
# caracteres) et le lancement echoue avec une erreur incomprehensible.
MAX_NODEIDS_EN_LIGNE = 40


def creation_flags() -> int:
    """Empeche l'ouverture d'une console noire derriere chaque run, sous Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@contextmanager
def _fichier_arguments(nodeids: tuple[str, ...]):
    """Passe les nodeids par un fichier quand ils sont trop nombreux.

    pytest accepte `@fichier` : une ligne par argument. Le fichier doit vivre
    aussi longtemps que le processus, d'ou le gestionnaire de contexte.
    """
    if len(nodeids) <= MAX_NODEIDS_EN_LIGNE:
        yield list(nodeids)
        return

    handle, chemin = tempfile.mkstemp(prefix="runner_args_", suffix=".txt", text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write("\n".join(nodeids))
        yield [f"@{chemin}"]
    finally:
        try:
            os.unlink(chemin)
        except OSError:
            pass


def collect(workspace: str, interpreter: str, env: dict | None = None,
            timeout: float = 120.0) -> list[str]:
    """Nodeids de la suite, relatifs au workspace.

    Leve RuntimeError avec un message lisible : c'est ce message que
    l'interface affichera, il ne doit pas etre une stacktrace.
    """
    commande = [interpreter, "-m", "pytest", "--collect-only", "-q"]
    try:
        process = subprocess.run(
            commande, cwd=workspace, capture_output=True, text=True,
            timeout=timeout, env=env or os.environ.copy(),
            creationflags=creation_flags(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Python interpreter not found: {interpreter}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Collection timed out after {timeout:.0f}s. "
            "A conftest that connects to hardware at import time can hang here."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start {interpreter}: {exc}") from exc

    # 5 = aucun test collecte. Ce n'est pas une erreur, juste un dossier vide.
    if process.returncode not in (0, 5):
        sortie = process.stderr or process.stdout or ""
        if "No module named pytest" in sortie:
            raise RuntimeError(
                f"pytest is not installed in the test interpreter:\n  {interpreter}\n\n"
                f'Install it with:\n  "{interpreter}" -m pip install pytest'
            )
        raise RuntimeError(sortie.strip() or "pytest could not collect the tests.")

    return parsing.parse_collect_only(process.stdout)


class ReaderRun:
    """Un processus pytest, pour un lecteur.

    Sait s'annuler : `cancel()` peut etre appele depuis un autre fil que celui
    qui lit la sortie.
    """

    def __init__(self, request: RunRequest, reader: Reader, env: dict):
        self.request = request
        self.reader = reader
        self._env = dict(env)
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _environnement(self, dossier_plugin: str) -> dict:
        env = dict(self._env)
        if self.reader.name:
            env[ENV_READER] = self.reader.name
            if self.request.config_path:
                env[ENV_CONFIG] = self.request.config_path
        if dossier_plugin:
            ancien = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = dossier_plugin + (os.pathsep + ancien if ancien else "")
        return env

    def run(self, on_line: Callable[[str], None],
            on_outcome: Callable[[Outcome], None]) -> ReaderReport:
        """Execute le run et rend son bilan. Bloquant : a appeler hors du fil UI."""
        debut = time.monotonic()
        rapport = ReaderReport(reader=self.reader, counts={})
        lignes: list[str] = []

        # Le fichier d'arguments et le plugin doivent survivre au processus :
        # tout le run se deroule donc a l'interieur des deux contextes.
        with reader_plugin(self.request.config_path if self.reader.name else "") as (
                args_plugin, dossier_plugin), \
                _fichier_arguments(self.request.nodeids) as args_nodeids:

            commande = [
                self.request.interpreter, "-u", "-m", "pytest",
                *args_nodeids, *args_plugin, "-v", "--tb=short",
            ]

            try:
                self._process = subprocess.Popen(
                    commande, cwd=self.request.workspace,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=self._environnement(dossier_plugin),
                    creationflags=creation_flags(),
                )
            except OSError as exc:
                message = f"Could not start the test interpreter:\n  {self.request.interpreter}\n{exc}"
                on_line(message + "\n")
                rapport.exit_code = -1
                rapport.output = message
                return rapport

            for ligne in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    break
                lignes.append(ligne)
                on_line(ligne)

                resultat = parsing.parse_status_line(ligne)
                if resultat is not None:
                    nodeid, statut = resultat
                    rapport.counts[statut] = rapport.counts.get(statut, 0) + 1
                    on_outcome(Outcome(nodeid, statut, self.reader.index))

            self._process.wait()

        rapport.duration = time.monotonic() - debut
        rapport.exit_code = -1 if self._cancelled else (self._process.returncode or 0)
        rapport.cancelled = self._cancelled
        rapport.output = "".join(lignes)
        return rapport
