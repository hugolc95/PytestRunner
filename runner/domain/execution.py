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
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from runner.domain import markers, parsing
from runner.domain.markers import Marker, marker_probe, read_probe, summarize
from runner.domain.models import Outcome, Reader, ReaderReport, RunRequest, Status
from runner.domain.reader_isolation import ENV_CONFIG, ENV_READER, reader_plugin

# Au-dela, la ligne de commande depasse la limite de Windows (32 768
# caracteres) et le lancement echoue avec une erreur incomprehensible.
MAX_NODEIDS_EN_LIGNE = 40
ENV_BUILD_NUMBER = "PYTEST_RUNNER_BUILD_NUMBER"

# Plusieurs TestSuites du meme workspace peuvent contenir les memes noms de
# modules/classes. ``importlib`` empeche pytest de reutiliser le module importe
# pour la premiere suite quand il passe a la suivante.
PYTEST_IMPORT_MODE = "--import-mode=importlib"

# Dossiers techniques a ne jamais parcourir pour chercher des conftest.py.
# Le workspace reel peut contenir un environnement Python complet : l'explorer
# a chaque collecte/run serait inutilement couteux.
_CONFTEXT_IGNORES = {
    ".git", ".hg", ".svn", ".idea", ".pytest_cache", "__pycache__",
    ".venv", "venv", "env", "node_modules", "site-packages",
}


def creation_flags() -> int:
    """Empeche l'ouverture d'une console noire derriere chaque run, sous Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _suite_import_paths(workspace: str) -> list[str]:
    """Dossiers des conftest du workspace, dans un ordre stable.

    Les TestSuites historiques ont souvent, juste a cote de leur ``conftest.py``,
    un fichier ``imports_<TestSuite>.py`` importe par un nom court :
    ``import imports_CVcertificateV3``. Le mode pytest ``importlib`` n'ajoute
    volontairement plus le dossier du conftest a ``sys.path`` ; sans ce pont,
    ces imports locaux cassent pendant la collecte.

    On ne modifie aucun test : on remet uniquement les dossiers qui sont des
    racines pytest reelles (ceux qui portent un conftest) dans PYTHONPATH. Les
    fichiers ``imports_<suite>.py`` peuvent ensuite faire exactement les memes
    ajustements de sys.path qu'en lancement unitaire/IDE.
    """
    racine = Path(workspace)
    if not racine.is_dir():
        return []

    trouves: list[str] = []
    try:
        for dossier, sous_dossiers, fichiers in os.walk(racine):
            sous_dossiers[:] = sorted(
                (nom for nom in sous_dossiers if nom.lower() not in _CONFTEXT_IGNORES),
                key=str.lower,
            )
            if "conftest.py" in fichiers:
                trouves.append(str(Path(dossier).resolve()))
    except OSError:
        return []
    return trouves



def _nodeid_file(nodeid: str) -> str:
    """Return the file part of a pytest nodeid."""
    return str(nodeid).partition("::")[0].replace("\\", "/")


def _suite_root(workspace: str, nodeid: str) -> Path:
    """Find the TestSuite boundary without assuming a fixed tree depth.

    A conftest.py living next to imports_*.py is the strongest signature used
    by the historical TestSuites. If it is absent, the nearest conftest is a
    safe pytest boundary. This keeps the runner generic.
    """
    workspace_path = Path(workspace).resolve()
    test_file = Path(workspace, _nodeid_file(nodeid)).resolve()
    folder = test_file.parent
    conftest_candidates: list[Path] = []

    while True:
        try:
            folder.relative_to(workspace_path)
        except ValueError:
            break
        if (folder / "conftest.py").is_file():
            conftest_candidates.append(folder)
            if any(folder.glob("imports_*.py")):
                return folder
        if folder == workspace_path:
            break
        folder = folder.parent

    return conftest_candidates[0] if conftest_candidates else test_file.parent


def _group_nodeids_by_suite(
        workspace: str, nodeids: tuple[str, ...]) -> list[tuple[Path, tuple[str, ...]]]:
    """Group selected nodeids by TestSuite while preserving selection order."""
    groups: list[tuple[Path, list[str]]] = []
    positions: dict[str, int] = {}
    for nodeid in nodeids:
        root = _suite_root(workspace, nodeid)
        key = os.path.normcase(str(root))
        position = positions.get(key)
        if position is None:
            positions[key] = len(groups)
            groups.append((root, [nodeid]))
        else:
            groups[position][1].append(nodeid)
    return [(root, tuple(ids)) for root, ids in groups]


def _merge_junit_files(sources: list[str], destination: str) -> None:
    """Merge per-TestSuite JUnit files into the single logical run report."""
    suites = []
    for source in sources:
        try:
            root = ET.parse(source).getroot()
        except (OSError, ET.ParseError):
            continue
        if root.tag == "testsuite":
            suites.append(root)
        else:
            suites.extend(child for child in root if child.tag == "testsuite")
    if not suites:
        return

    merged = ET.Element("testsuites")
    for attr in ("tests", "failures", "errors", "skipped"):
        merged.set(attr, str(sum(int(s.get(attr, "0") or 0) for s in suites)))
    merged.set("time", f"{sum(float(s.get('time', '0') or 0) for s in suites):.6f}")
    for suite in suites:
        merged.append(suite)

    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(merged).write(destination, encoding="utf-8", xml_declaration=True)



def _prepend_pythonpath(env: dict, paths) -> None:
    """Ajoute ``paths`` devant PYTHONPATH sans doublon, sans perdre l'existant."""
    existant = [p for p in str(env.get("PYTHONPATH", "")).split(os.pathsep) if p]
    resultat: list[str] = []
    vus: set[str] = set()
    for path in [*paths, *existant]:
        cle = os.path.normcase(os.path.abspath(path))
        if cle not in vus:
            vus.add(cle)
            resultat.append(path)
    env["PYTHONPATH"] = os.pathsep.join(resultat)


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


@dataclass(frozen=True)
class Collection:
    """Ce qu'une collecte rapporte d'un workspace.

    Les markers voyagent avec les nodeids parce qu'ils sortent du MEME passage
    de pytest : une seconde collecte doublerait l'attente, et sur un conftest
    qui parle au materiel elle la doublerait pour de bon.
    """

    nodeids: tuple[str, ...] = ()
    markers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    declared: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.nodeids)

    def __iter__(self):
        return iter(self.nodeids)

    def marker_list(self) -> list[Marker]:
        return summarize(self.markers, self.declared)


def collect(workspace: str, interpreter: str, env: dict | None = None,
            timeout: float = 120.0) -> Collection:
    """Nodeids de la suite et leurs markers, relatifs au workspace.

    Leve RuntimeError avec un message lisible : c'est ce message que
    l'interface affichera, il ne doit pas etre une stacktrace.
    """
    with marker_probe() as (args_plugin, dossier_plugin, fichier_markers):
        commande = [interpreter, "-m", "pytest", "--collect-only", "-q",
                    PYTEST_IMPORT_MODE, *args_plugin]
        environnement = markers.environment(env, fichier_markers)
        _prepend_pythonpath(
            environnement,
            [dossier_plugin, *_suite_import_paths(workspace)],
        )

        try:
            process = subprocess.run(
                commande, cwd=workspace, capture_output=True, text=True,
                timeout=timeout, env=environnement,
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

        nodeids = parsing.parse_collect_only(process.stdout)
        par_nodeid, descriptions = read_probe(fichier_markers)

    # Le releve ne fait autorite que sur les tests que la collecte a listes :
    # un plugin qui aurait rate son fichier ne doit pas inventer de tests.
    connus = set(nodeids)
    par_nodeid = {k: v for k, v in par_nodeid.items() if k in connus}

    return Collection(tuple(nodeids), par_nodeid, descriptions)


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

    def _junit_path(self) -> str:
        """Ou pytest doit ecrire son JUnit XML, ou "" si on n'en veut pas.

        Un fichier par LECTEUR : deux processus pytest qui ecrivent le meme
        chemin en meme temps se marcheraient dessus, et le rapport garde ne
        serait celui de personne.
        """
        if not (self.request.run_id and self.request.junit_dir):
            return ""
        suffixe = f"_{self.reader.index}" if self.reader.name else ""
        return str(Path(self.request.junit_dir)
                   / f"{self.request.run_id}{suffixe}.xml")

    def _allure_dir_path(self) -> str:
        """Ou pytest doit ecrire les resultats allure-pytest, ou "" si on
        n'en veut pas.

        Un seul dossier pour tous les lecteurs d'un run, et un seul rapport
        genere ensuite : les fichiers allure-pytest sont nommes par UUID, deux
        lecteurs n'ecrivent donc jamais le meme fichier. Ce qui distingue un
        lecteur de l'autre DANS ce rapport commun n'est pas le dossier -- voir
        le parametre "Reader" pose sur chaque test par le plugin de
        `reader_plugin` (reader_isolation.py).
        """
        if not self.request.allure_dir:
            return ""
        dossier = Path(self.request.allure_dir)
        dossier.mkdir(parents=True, exist_ok=True)
        return str(dossier)

    def _environnement(self, dossier_plugin: str, suite_root: Path | None = None) -> dict:
        # Sous Windows, creer un processus avec un environnement partiel peut
        # retirer SYSTEMROOT et les variables dont Python a besoin pour
        # initialiser ses codecs et charger les DLL. `env` est une surcouche,
        # pas un remplacement de l'environnement du poste.
        env = dict(os.environ)
        env.update(self._env)
        if self.request.build_number is not None:
            env[ENV_BUILD_NUMBER] = str(self.request.build_number)
        if self.reader.name:
            env[ENV_READER] = self.reader.name
            if self.request.config_path:
                env[ENV_CONFIG] = self.request.config_path
        paths = [dossier_plugin]
        if suite_root is not None:
            paths.append(str(suite_root))
        else:
            paths.extend(_suite_import_paths(self.request.workspace))
        _prepend_pythonpath(env, paths)
        return env

    def run(self, on_line: Callable[[str], None],
            on_outcome: Callable[[Outcome], None]) -> ReaderReport:
        """Run one logical reader run, isolating each TestSuite in its own pytest."""
        start = time.monotonic()
        report = ReaderReport(reader=self.reader, counts={})
        output: list[str] = []
        verdicts: dict[str, Status] = {}
        resolver = parsing.NodeidResolver(self.request.nodeids)
        groups = _group_nodeids_by_suite(self.request.workspace, self.request.nodeids)
        final_junit = self._junit_path()
        partial_junits: list[str] = []

        with reader_plugin(self.request.config_path if self.reader.name else "") as (
                plugin_args, plugin_dir):
            for group_index, (suite_root, suite_nodeids) in enumerate(groups):
                if self._cancelled:
                    break

                with _fichier_arguments(suite_nodeids) as nodeid_args:
                    command = [
                        self.request.interpreter, "-u", "-m", "pytest",
                        *nodeid_args, *plugin_args,
                        "-v", "--tb=short", "--durations=0",
                    ]

                    partial_junit = ""
                    if final_junit:
                        Path(self.request.junit_dir).mkdir(parents=True, exist_ok=True)
                        handle, partial_junit = tempfile.mkstemp(
                            prefix=f"{self.request.run_id}_suite_{group_index}_",
                            suffix=".xml", dir=self.request.junit_dir)
                        os.close(handle)
                        try:
                            os.unlink(partial_junit)
                        except OSError:
                            pass
                        command.append(f"--junitxml={partial_junit}")

                    allure_dir = self._allure_dir_path()
                    if allure_dir:
                        command.append(f"--alluredir={allure_dir}")

                    try:
                        self._process = subprocess.Popen(
                            command, cwd=self.request.workspace,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1,
                            env=self._environnement(plugin_dir, suite_root),
                            creationflags=creation_flags(),
                        )
                    except OSError as exc:
                        message = (
                            "Could not start the test interpreter:\n"
                            f"  {self.request.interpreter}\n{exc}"
                        )
                        on_line(message + "\n")
                        output.append(message + "\n")
                        report.exit_code = -1
                        break

                    skip_blank_after_protocol = False
                    for line in iter(self._process.stdout.readline, ""):
                        if self._cancelled:
                            break
                        result = parsing.parse_status_line(line)
                        protocol = parsing.is_outcome_protocol_line(line)
                        if protocol:
                            skip_blank_after_protocol = True
                        elif skip_blank_after_protocol and not line.strip():
                            skip_blank_after_protocol = False
                        else:
                            skip_blank_after_protocol = False
                            output.append(line)
                            on_line(line)

                        if result is not None:
                            nodeid, status = result
                            nodeid = resolver.resolve(nodeid)
                            previous = verdicts.get(nodeid)
                            if previous is status:
                                continue
                            if previous is not None:
                                remaining = report.counts.get(previous, 0) - 1
                                if remaining > 0:
                                    report.counts[previous] = remaining
                                else:
                                    report.counts.pop(previous, None)
                            verdicts[nodeid] = status
                            report.counts[status] = report.counts.get(status, 0) + 1
                            on_outcome(Outcome(nodeid, status, self.reader.index))

                    if self._cancelled and self._process.poll() is None:
                        try:
                            self._process.terminate()
                        except OSError:
                            pass
                    self._process.wait()

                    if partial_junit and Path(partial_junit).is_file():
                        partial_junits.append(partial_junit)

                    code = self._process.returncode or 0
                    if code != 0 and report.exit_code == 0:
                        report.exit_code = code
                    # A failing TestSuite must not hide results from later
                    # selected suites in the same logical run.

        report.duration = time.monotonic() - start
        if self._cancelled:
            report.exit_code = -1
        report.cancelled = self._cancelled
        report.output = "".join(output)
        report.durations = {
            resolver.resolve(nodeid): duration
            for nodeid, duration in parsing.parse_durations(report.output).items()
        }

        if final_junit and partial_junits:
            _merge_junit_files(partial_junits, final_junit)
            for path in partial_junits:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            if Path(final_junit).is_file():
                report.junit_path = final_junit
        return report
