"""Lancement de pytest et lecture de sa sortie au fil de l'eau.

Rien ici ne connait Qt. Le suivi passe par des rappels (`on_line`,
`on_outcome`) que la couche service branche sur des signaux : le domaine reste
utilisable depuis un script ou un test.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from runner.domain import logs as logs_mod
from runner.domain import markers, parsing
from runner.domain.markers import Marker, marker_probe, read_probe, summarize
from runner.domain.models import (
    Outcome,
    PhaseReport,
    Reader,
    ReaderReport,
    RunRequest,
    Status,
    worst,
)
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
                    *args_plugin]
        environnement = markers.environment(env, fichier_markers)
        ancien = environnement.get("PYTHONPATH", "")
        environnement["PYTHONPATH"] = dossier_plugin + (
            os.pathsep + ancien if ancien else "")

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

    def _environnement(self, dossier_plugin: str) -> dict:
        # Sous Windows, creer un processus avec un environnement partiel peut
        # retirer SYSTEMROOT et les variables dont Python a besoin pour
        # initialiser ses codecs et charger les DLL. `env` est une surcouche,
        # pas un remplacement de l'environnement du poste.
        env = dict(os.environ)
        env.update(self._env)
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
        if self.request.campaigns:
            return self._run_campaigns(on_line, on_outcome)

        debut = time.monotonic()
        rapport = ReaderReport(reader=self.reader, counts={})
        lignes: list[str] = []
        verdicts: dict[str, Status] = {}
        saut_apres_protocole = False
        nodeids = parsing.NodeidResolver(self.request.nodeids)

        # Le fichier d'arguments et le plugin doivent survivre au processus :
        # tout le run se deroule donc a l'interieur des deux contextes.
        with reader_plugin(self.request.config_path if self.reader.name else "") as (
                args_plugin, dossier_plugin), \
                _fichier_arguments(self.request.nodeids) as args_nodeids:

            junit = self._junit_path()
            commande = [
                self.request.interpreter, "-u", "-m", "pytest",
                *args_nodeids, *args_plugin, "-v", "--tb=short",
            ]
            if junit:
                # Option native de pytest : le XML est ecrit par lui, pas
                # reconstruit a partir des compteurs. Aucune dependance, et un
                # fichier que les serveurs d'integration savent deja lire.
                commande.append(f"--junitxml={junit}")

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
                resultat = parsing.parse_status_line(ligne)

                # Le protocole alimente l'arbre mais ne pollue ni la console,
                # ni l'onglet Output, ni l'historique conserve.
                protocole = parsing.is_outcome_protocol_line(ligne)
                if protocole:
                    saut_apres_protocole = True
                elif saut_apres_protocole and not ligne.strip():
                    # pytest termine ensuite la ligne de son terminal. Le saut
                    # initial du protocole l'a deja fait : masquer ce doublon.
                    saut_apres_protocole = False
                else:
                    saut_apres_protocole = False
                    lignes.append(ligne)
                    on_line(ligne)

                if resultat is not None:
                    nodeid, statut = resultat
                    # Le tree conserve les nodeids de la collecte. Pytest et
                    # certains plugins peuvent rendre le meme test avec un
                    # chemin absolu, un autre rootdir ou des antislashs :
                    # remettre ici l'identifiant collecte garde toute la
                    # chaine (tree, Detail, compteurs, progression) coherente.
                    nodeid = nodeids.resolve(nodeid)
                    precedent = verdicts.get(nodeid)
                    if precedent is statut:
                        continue
                    if precedent is not None:
                        restant = rapport.counts.get(precedent, 0) - 1
                        if restant > 0:
                            rapport.counts[precedent] = restant
                        else:
                            rapport.counts.pop(precedent, None)
                    verdicts[nodeid] = statut
                    rapport.counts[statut] = rapport.counts.get(statut, 0) + 1
                    on_outcome(Outcome(nodeid, statut, self.reader.index))

            self._process.wait()

        rapport.duration = time.monotonic() - debut
        rapport.exit_code = -1 if self._cancelled else (self._process.returncode or 0)
        rapport.cancelled = self._cancelled
        rapport.output = "".join(lignes)
        # Le chemin n'est retenu que si pytest a VRAIMENT ecrit le fichier :
        # un run annule avant la fin n'en laisse pas, et l'historique
        # proposerait alors un export qui echouerait au moment du clic.
        if junit and Path(junit).is_file():
            rapport.junit_path = junit
        return rapport

    def _run_campaigns(self, on_line: Callable[[str], None],
                       on_outcome: Callable[[Outcome], None]) -> ReaderReport:
        """Execute les setups et batches pytest sans exposer un second mode UI."""
        debut = time.monotonic()
        rapport = ReaderReport(reader=self.reader, counts={})
        toute_sortie: list[str] = []
        occurrence = 0

        def publier(texte: str, phase_lines: list[str] | None = None) -> None:
            toute_sortie.append(texte)
            if phase_lines is not None:
                phase_lines.append(texte)
            on_line(texte)

        with reader_plugin(self.request.config_path if self.reader.name else "") as (
                args_plugin, dossier_plugin):

            # Un clic sur la racine peut melanger tests ordinaires et campagne.
            # Les ordinaires gardent le comportement historique, puis chaque
            # campagne prend la main avec son propre ordre.
            if self.request.regular_nodeids:
                lignes: list[str] = []
                publier("\n===== Regular pytest tests =====\n", lignes)
                occurrence = self._campaign_pytest(
                    self.request.regular_nodeids, self.request.workspace,
                    self.request.interpreter, (), args_plugin, dossier_plugin,
                    "", "", "Regular tests", occurrence, rapport, lignes,
                    publier, on_outcome)

            for campagne in self.request.campaigns:
                interpreteur = campagne.python_executable or self.request.interpreter
                for phase in campagne.phases:
                    if self._cancelled:
                        break
                    lignes: list[str] = []
                    logs_avant = self._campaign_log_state(phase.nodeids)
                    publier(
                        f"\n===== {campagne.name} · {phase.name} =====\n", lignes)
                    setup_ok = True
                    if phase.setup:
                        publier(f"--- Setup: {self._display_command(phase.setup)} ---\n",
                                lignes)
                        code = self._campaign_setup(
                            phase.setup, campagne.workspace, interpreteur,
                            campagne.pythonpath, args_plugin, dossier_plugin,
                            lignes, publier)
                        setup_ok = code == 0

                    statuts_phase: dict[str, Status] = {}
                    if setup_ok and not self._cancelled:
                        occurrence = self._campaign_pytest(
                            phase.nodeids, campagne.workspace, interpreteur,
                            campagne.pythonpath, args_plugin, dossier_plugin,
                            campagne.name, phase.id, phase.name, occurrence,
                            rapport, lignes, publier, on_outcome,
                            statuts_phase)
                    elif not self._cancelled:
                        publier("Setup failed: pytest batch skipped.\n", lignes)
                        for nodeid in phase.nodeids:
                            occurrence += 1
                            statuts_phase[nodeid] = Status.ERROR
                            rapport.counts[Status.ERROR] = (
                                rapport.counts.get(Status.ERROR, 0) + 1)
                            on_outcome(Outcome(
                                nodeid, Status.ERROR, self.reader.index,
                                campagne.name, phase.id, phase.name, occurrence))

                    contenus_logs, chemins_logs = self._campaign_logs(
                        phase.nodeids, logs_avant)
                    rapport.phases.append(PhaseReport(
                        phase.id, phase.name, campagne.name,
                        "".join(lignes), statuts_phase, setup_ok,
                        contenus_logs, chemins_logs))

                if self._cancelled:
                    break

        rapport.duration = time.monotonic() - debut
        rapport.cancelled = self._cancelled
        rapport.exit_code = -1 if self._cancelled else (
            1 if any(status.is_bad for phase in rapport.phases
                     for status in phase.statuses.values()) else 0)
        rapport.output = "".join(toute_sortie)
        return rapport

    def _campaign_log_state(self, nodeids: tuple[str, ...]) -> dict[str, tuple[str, int, int]]:
        if not self.request.log_root:
            return {}
        etat: dict[str, tuple[str, int, int]] = {}
        for nodeid in dict.fromkeys(nodeids):
            chemin = logs_mod.find_test_log(
                Path(self.request.log_root), nodeid, self.reader.name)
            if chemin is None:
                continue
            try:
                info = chemin.stat()
                etat[nodeid] = (str(chemin), info.st_mtime_ns, info.st_size)
            except OSError:
                continue
        return etat

    def _campaign_logs(self, nodeids: tuple[str, ...],
                       avant: dict[str, tuple[str, int, int]]) -> tuple[dict[str, str], dict[str, str]]:
        """Fige les logs avant que la configuration suivante ne les ecrase."""
        if not self.request.log_root:
            return {}, {}
        contenus: dict[str, str] = {}
        chemins: dict[str, str] = {}
        for nodeid in dict.fromkeys(nodeids):
            chemin = logs_mod.find_test_log(
                Path(self.request.log_root), nodeid, self.reader.name)
            if chemin is None:
                continue
            try:
                info = chemin.stat()
                courant = (str(chemin), info.st_mtime_ns, info.st_size)
                if avant.get(nodeid) == courant:
                    # Ce fichier appartenait a un ancien run : l'afficher sous
                    # la configuration courante donnerait un diagnostic faux.
                    continue
                contenus[nodeid] = chemin.read_text(
                    encoding="utf-8", errors="replace")
                chemins[nodeid] = str(chemin)
            except OSError:
                continue
        return contenus, chemins

    @staticmethod
    def _display_command(command: str | tuple[str, ...]) -> str:
        return (command if isinstance(command, str)
                else " ".join(shlex.quote(part) for part in command))

    def _campaign_env(self, dossier_plugin: str,
                      pythonpath: tuple[str, ...]) -> dict:
        env = self._environnement(dossier_plugin)
        ajouts = [str(path) for path in pythonpath if str(path).strip()]
        ancien = env.get("PYTHONPATH", "")
        if ancien:
            ajouts.append(ancien)
        if ajouts:
            env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(ajouts))
        return env

    def _campaign_setup(self, setup: str | tuple[str, ...], workspace: str,
                        interpreter: str, pythonpath: tuple[str, ...],
                        args_plugin: list[str], dossier_plugin: str,
                        lignes: list[str], publier) -> int:
        if isinstance(setup, tuple):
            commande = list(setup)
        else:
            cible = setup.strip()
            premier = shlex.split(cible)[0] if cible else ""
            fichier = premier.split("::", 1)[0]
            pytest_target = "::" in cible or Path(fichier).name.startswith("test_")
            if pytest_target:
                commande = [interpreter, "-u", "-m", "pytest", cible,
                            *args_plugin, "-v", "--tb=short"]
            elif cible.endswith(".py") and (Path(workspace) / cible).is_file():
                commande = [interpreter, cible]
            else:
                commande = shlex.split(cible)
        return self._campaign_process(
            commande, workspace, self._campaign_env(dossier_plugin, pythonpath),
            lignes, publier)

    def _campaign_process(self, commande: list[str], workspace: str, env: dict,
                          lignes: list[str], publier,
                          on_result=None) -> int:
        try:
            self._process = subprocess.Popen(
                commande, cwd=workspace, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, env=env,
                creationflags=creation_flags())
        except OSError as exc:
            publier(f"Could not start {' '.join(commande)}:\n{exc}\n", lignes)
            return -1

        assert self._process.stdout is not None
        saut_apres_protocole = False
        for ligne in iter(self._process.stdout.readline, ""):
            if self._cancelled:
                break
            if on_result is not None:
                on_result(ligne)
            protocole = parsing.is_outcome_protocol_line(ligne)
            if protocole:
                saut_apres_protocole = True
                continue
            if saut_apres_protocole and not ligne.strip():
                saut_apres_protocole = False
                continue
            saut_apres_protocole = False
            publier(ligne, lignes)
        if self._cancelled and self._process.poll() is None:
            self._process.terminate()
        self._process.wait()
        return -1 if self._cancelled else int(self._process.returncode or 0)

    def _campaign_pytest(
            self, nodeids: tuple[str, ...], workspace: str, interpreter: str,
            pythonpath: tuple[str, ...], args_plugin: list[str],
            dossier_plugin: str, campaign: str, phase_id: str, phase_name: str,
            occurrence: int, rapport: ReaderReport, lignes: list[str], publier,
            on_outcome: Callable[[Outcome], None],
            phase_statuses: dict[str, Status] | None = None) -> int:
        statuts = phase_statuses if phase_statuses is not None else {}
        resolver = parsing.NodeidResolver(nodeids)
        attendus: dict[str, int] = {}
        recus: dict[str, int] = {}
        for nodeid in nodeids:
            attendus[nodeid] = attendus.get(nodeid, 0) + 1

        def resultat(ligne: str) -> None:
            nonlocal occurrence
            lu = parsing.parse_status_line(ligne)
            if lu is None:
                return
            nodeid, status = lu
            nodeid = resolver.resolve(nodeid)
            if recus.get(nodeid, 0) >= attendus.get(nodeid, 1):
                return
            recus[nodeid] = recus.get(nodeid, 0) + 1
            occurrence += 1
            statuts[nodeid] = worst((statuts.get(nodeid, Status.PENDING), status))
            rapport.counts[status] = rapport.counts.get(status, 0) + 1
            on_outcome(Outcome(
                nodeid, status, self.reader.index, campaign, phase_id,
                phase_name, occurrence))

        with _fichier_arguments(nodeids) as args_nodeids:
            commande = [interpreter, "-u", "-m", "pytest", *args_nodeids,
                        *args_plugin, "--keep-duplicates", "-v", "--tb=short"]
            self._campaign_process(
                commande, workspace,
                self._campaign_env(dossier_plugin, pythonpath), lignes,
                publier, resultat)
        return occurrence
