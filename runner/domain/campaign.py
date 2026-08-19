"""Detection et lecture des campagnes rattachees a un workspace.

Une campagne n'est pas un mode d'interface. C'est une politique d'execution
declaree par un YAML : les tests restent dans l'arbre habituel, mais ``Run
tests`` doit respecter les setups et l'ordre des scenarios qui les couvrent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runner.domain.parsing import NodeidResolver
from runner.domain.models import CampaignPhase, CampaignRun
from runner.domain.workspace import DOSSIERS_IGNORES, SUFFIXES_YAML


@dataclass(frozen=True)
class CampaignTest:
    nodeid: str
    repeat: int = 1


@dataclass(frozen=True)
class CampaignScenario:
    name: str
    setup: str | tuple[str, ...] | None
    tests: tuple[CampaignTest, ...]


@dataclass(frozen=True)
class CampaignDefinition:
    name: str
    path: str
    workspace: str
    scenarios: tuple[CampaignScenario, ...]
    pythonpath: tuple[str, ...] = ()
    python_executable: str = ""

    @property
    def nodeids(self) -> tuple[str, ...]:
        """Nodeids uniques, dans l'ordre du YAML."""
        vus: set[str] = set()
        resultat: list[str] = []
        for scenario in self.scenarios:
            for test in scenario.tests:
                if test.nodeid not in vus:
                    vus.add(test.nodeid)
                    resultat.append(test.nodeid)
        return tuple(resultat)


def _charger(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as fichier:
        donnees = yaml.safe_load(fichier) or {}
    return donnees if isinstance(donnees, dict) else {}


def _commande(value: Any) -> str | tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        return tuple(str(element) for element in value)
    raise ValueError(f"Invalid campaign setup command: {value!r}")


def _normalized_parts(chemin: str) -> tuple[str, ...]:
    """Composants d'un chemin, casse et separateurs ignores, `.`/`..` retires.

    Une entree `tests:` qui designe un dossier ou un fichier entier suit le
    meme repere que `config:` : relative au fichier Campaign, `..` compris.
    Ce n'est pas un chemin disque a resoudre -- seuls les noms de dossiers
    traverses comptent pour retrouver les tests qu'ils contiennent, et `..`
    n'en est jamais un.
    """
    brut = chemin.replace("\\", "/")
    return tuple(partie.casefold() for partie in brut.split("/")
                if partie and partie not in (".", ".."))


def _expand_path_entry(chemin: str,
                       fichiers_collectes: list[tuple[tuple[str, ...], str]],
                       ) -> list[str]:
    """Nodeids collectes couverts par une entree `tests:` sans ``::``.

    Une campagne peut lister un dossier entier ou un fichier ``.py`` complet
    plutot qu'un nodeid precis -- plus court a ecrire, et plus resistant : un
    test ajoute au dossier plus tard entre dans la campagne sans toucher au
    YAML. Le dossier/fichier est repere par SES noms de composants, cherches
    dans le chemin de chaque test collecte -- une correspondance exacte de
    caracteres se romprait a la premiere difference de rootdir ou d'antislash.
    """
    cibles = _normalized_parts(chemin)
    if not cibles:
        return []

    est_fichier = cibles[-1].endswith(".py")
    trouves: list[str] = []
    for parties, nodeid in fichiers_collectes:
        if est_fichier:
            if parties[-len(cibles):] == cibles:
                trouves.append(nodeid)
        else:
            n = len(cibles)
            if any(parties[i:i + n] == cibles for i in range(len(parties) - n)):
                trouves.append(nodeid)
    return trouves


def _test(value: Any) -> CampaignTest:
    if isinstance(value, str):
        return CampaignTest(value.strip())
    if isinstance(value, dict):
        nodeid = value.get("nodeid") or value.get("test") or value.get("path")
        if not nodeid:
            raise ValueError(f"Campaign test misses nodeid/test/path: {value!r}")
        return CampaignTest(str(nodeid).strip(), max(1, int(value.get("repeat", 1))))
    raise ValueError(f"Invalid campaign test: {value!r}")


def load_campaign(path: str | Path, collected=()) -> CampaignDefinition:
    """Charge un YAML Campaign et ramene ses nodeids vers ceux de l'arbre."""
    fichier = Path(path).resolve()
    donnees = _charger(fichier)
    bruts = donnees.get("scenarios") or donnees.get("campaign")
    if not isinstance(bruts, list):
        raise ValueError("Campaign YAML must contain a 'scenarios:' list.")

    racine = Path(str(donnees.get("workspace") or donnees.get("root") or "."))
    if not racine.is_absolute():
        racine = (fichier.parent / racine).resolve()

    resolver = NodeidResolver(collected)
    # Index des tests collectes par composants de CHEMIN, pour les entrees
    # `tests:` qui designent un dossier ou un fichier entier plutot qu'un seul
    # nodeid. Construit une fois : le refaire pour chaque entree reparcourrait
    # toute la collecte a chaque ligne du YAML.
    fichiers_collectes = [
        (parties, str(nodeid)) for nodeid in collected
        for parties, reste in (NodeidResolver._morceaux(str(nodeid)),)
        if parties and reste
    ]

    scenarios: list[CampaignScenario] = []
    for position, brut in enumerate(bruts, 1):
        if not isinstance(brut, dict):
            raise ValueError(f"Campaign scenario #{position} must be an object.")
        tests_bruts = brut.get("tests") or []
        if not isinstance(tests_bruts, list):
            raise ValueError(f"Campaign scenario #{position} tests must be a list.")
        tests = []
        for entree in tests_bruts:
            test = _test(entree)
            if "::" in test.nodeid:
                tests.append(CampaignTest(resolver.resolve(test.nodeid), test.repeat))
                continue
            # Un dossier ou un fichier .py entier : chaque test qu'il contient
            # rejoint la campagne, avec le meme nombre de repetitions. Une
            # entree qui ne couvre rien du tout (chemin errone, dossier encore
            # vide) est ignoree plutot que de garder un identifiant qu'aucun
            # test ne portera jamais.
            for nodeid_resolu in _expand_path_entry(test.nodeid, fichiers_collectes):
                tests.append(CampaignTest(nodeid_resolu, test.repeat))
        scenarios.append(CampaignScenario(
            str(brut.get("name") or f"Configuration {position}"),
            _commande(brut.get("setup") or brut.get("config") or brut.get("script")),
            tuple(tests),
        ))

    pythonpath_brut = donnees.get("pythonpath") or donnees.get("python_path") or ()
    if isinstance(pythonpath_brut, str):
        pythonpath_brut = (pythonpath_brut,)
    chemins: list[str] = []
    for entree in pythonpath_brut if isinstance(pythonpath_brut, (list, tuple)) else ():
        chemin = Path(str(entree))
        if not chemin.is_absolute():
            chemin = racine / chemin
        chemins.append(str(chemin.resolve()))
    if str(racine) not in chemins:
        chemins.insert(0, str(racine))

    return CampaignDefinition(
        name=str(donnees.get("name") or fichier.stem),
        path=str(fichier),
        workspace=str(racine),
        scenarios=tuple(scenarios),
        pythonpath=tuple(chemins),
        python_executable=str(donnees.get("python") or donnees.get("python_executable") or "").strip(),
    )


def discover_campaigns(workspace: str, collected=()) -> tuple[CampaignDefinition, ...]:
    """Trouve les ``campaign.yml`` valides, y compris dans les sous-dossiers.

    Les autres YAML du workspace ne sont jamais interpretes comme campagne :
    un fichier de lecteurs ou de configuration peut lui aussi contenir des
    listes et ne doit pas faire apparaitre un faux badge dans l'arbre.
    """
    racine = Path(workspace)
    if not racine.is_dir():
        return ()
    candidats: list[Path] = []
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        sous_dossiers[:] = [nom for nom in sous_dossiers
                            if nom.lower() not in DOSSIERS_IGNORES]
        for nom in fichiers:
            chemin = Path(dossier) / nom
            if (chemin.suffix.lower() in SUFFIXES_YAML
                    and "campaign" in chemin.stem.lower()):
                candidats.append(chemin)

    campagnes: list[CampaignDefinition] = []
    for chemin in sorted(candidats, key=lambda p: p.as_posix().lower()):
        try:
            campagne = load_campaign(chemin, collected)
        except (OSError, ValueError, TypeError):
            continue
        if campagne.scenarios and campagne.nodeids:
            campagnes.append(campagne)
    return tuple(campagnes)


def memberships(campaigns: tuple[CampaignDefinition, ...]) -> dict[str, str]:
    """Nodeid -> fichier Campaign, pour le badge et le routage du run."""
    resultat: dict[str, str] = {}
    for campagne in campaigns:
        for nodeid in campagne.nodeids:
            resultat.setdefault(nodeid, campagne.path)
    return resultat


def build_runs(campaigns: tuple[CampaignDefinition, ...], selected) -> tuple[
        tuple[CampaignRun, ...], tuple[str, ...]]:
    """Construit le plan Campaign et rend aussi les tests restes ordinaires."""
    selection = tuple(selected)
    selection_set = set(selection)
    couverts: set[str] = set()
    runs: list[CampaignRun] = []

    for campagne_index, campagne in enumerate(campaigns):
        phases: list[CampaignPhase] = []
        for phase_index, scenario in enumerate(campagne.scenarios):
            nodeids: list[str] = []
            for test in scenario.tests:
                if test.nodeid not in selection_set:
                    continue
                nodeids.extend([test.nodeid] * test.repeat)
                couverts.add(test.nodeid)
            if not nodeids:
                continue
            phases.append(CampaignPhase(
                id=f"{campagne_index}:{phase_index}",
                name=scenario.name,
                setup=scenario.setup,
                nodeids=tuple(nodeids),
            ))
        if phases:
            runs.append(CampaignRun(
                name=campagne.name,
                path=campagne.path,
                workspace=campagne.workspace,
                phases=tuple(phases),
                pythonpath=campagne.pythonpath,
                python_executable=campagne.python_executable,
            ))

    ordinaires = tuple(nodeid for nodeid in selection if nodeid not in couverts)
    return tuple(runs), ordinaires
