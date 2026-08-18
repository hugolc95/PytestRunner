"""Lecture de la configuration d'un workspace : lecteurs, logs, interpreteur.

Un workspace decrit comment ses tests doivent tourner. Le fichier ne s'appelle
pas toujours `config.yml` : on examine tous les YAML de la racine, les noms
standards d'abord.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from runner.domain import interpreter as interpreter_mod
from runner.domain.models import Reader

NOMS_STANDARDS = ("config.yaml", "config.yml")

# Une meme notion porte des noms differents d'un projet a l'autre. La
# comparaison ignore la casse, les tirets et les espaces.
CLES_READER = ("reader", "lecteur")
CLES_READERS = ("readers", "lecteurs", "reader_list")
CLES_LOGS = ("log_path", "log_directory", "log_dir", "logs_path", "logpath")
CLES_PYTHON = ("python_executable", "python", "interpreter")
CLES_READER_MODE = ("reader_mode", "readers_mode", "mode_lecteur")

MODE_PARALLELE = "parallel"
MODE_SEQUENTIEL = "sequential"
MODES = (MODE_PARALLELE, MODE_SEQUENTIEL)


def _normaliser(cle: str) -> str:
    return str(cle).strip().lower().replace("-", "_").replace(" ", "_")


def _charger(chemin: Path) -> dict:
    try:
        import yaml

        with open(chemin, "r", encoding="utf-8") as f:
            donnees = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return donnees if isinstance(donnees, dict) else {}


def _trouver(donnees: dict, cles: tuple[str, ...]):
    """Premiere valeur non vide portee par l'une de ces cles.

    Le niveau courant est epuise avant de descendre : un reglage pose a la
    racine prime sur celui que declarerait une sous-section.
    """
    if not isinstance(donnees, dict):
        return None
    for cle, valeur in donnees.items():
        if _normaliser(cle) in cles and valeur not in (None, "", [], {}):
            return valeur
    for valeur in donnees.values():
        if isinstance(valeur, dict):
            trouve = _trouver(valeur, cles)
            if trouve is not None:
                return trouve
    return None


def fichiers_config(workspace: str | None) -> list[Path]:
    """YAML de la racine du workspace, les noms standards en tete."""
    if not workspace:
        return []
    racine = Path(workspace)
    if not racine.is_dir():
        return []

    trouves = [racine / nom for nom in NOMS_STANDARDS if (racine / nom).is_file()]
    try:
        autres = sorted(
            (p for p in racine.iterdir()
             if p.is_file() and p.suffix.lower() in (".yml", ".yaml")
             and p.name not in NOMS_STANDARDS),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        autres = []
    return trouves + autres


@dataclass(frozen=True)
class Workspace:
    """Un dossier de tests et les reglages qui l'accompagnent."""

    path: str
    config_path: str = ""
    settings: dict = None  # type: ignore[assignment]

    @classmethod
    def load(cls, path: str, config: str = "") -> "Workspace":
        """Lit la configuration du workspace.

        `config` impose un fichier precis. Sans lui, le premier exploitable
        gagne -- ce qui suffit quand il n'y en a qu'un, et devient un tirage
        quand le projet en compte plusieurs. Un depot avec un `config.yaml`
        d'exemple a cote du vrai fichier de campagne se retrouvait alors lu a
        l'envers, avec les mauvais lecteurs et le mauvais dossier de logs, sans
        que rien ne le signale.
        """
        if config:
            demande = Path(config)
            if not demande.is_absolute():
                demande = Path(path) / demande
            if demande.is_file():
                return cls(path=path, config_path=str(demande),
                           settings=_charger(demande))
            # Le fichier retenu a ete renomme ou supprime : on retombe sur la
            # detection plutot que de rendre un workspace sans reglages.

        for candidat in fichiers_config(path):
            donnees = _charger(candidat)
            if donnees:
                return cls(path=path, config_path=str(candidat), settings=donnees)
        return cls(path=path, config_path="", settings={})

    # ------------------------------------------------------------------ lecteurs

    @property
    def readers(self) -> tuple[Reader, ...]:
        """Lecteurs a tester, le lecteur principal en tete.

        `Reader` est celui que les tests lisent aujourd'hui ; `Readers` liste
        ceux qu'on veut tester EN PLUS. Un workspace qui n'en declare aucun
        donne un tuple vide -- l'interface ne montre alors aucune notion de
        lecteur.
        """
        reglages = self.settings or {}
        noms: list[str] = []

        principal = _trouver(reglages, CLES_READER)
        if principal is not None:
            noms.append(str(principal).strip())

        supplement = _trouver(reglages, CLES_READERS)
        if isinstance(supplement, (list, tuple)):
            noms.extend(str(v).strip() for v in supplement)
        elif supplement is not None:
            noms.append(str(supplement).strip())

        # Deux fois le meme lecteur donnerait deux colonnes indiscernables.
        uniques: list[str] = []
        for nom in noms:
            if nom and nom not in uniques:
                uniques.append(nom)
        return tuple(Reader(nom, i) for i, nom in enumerate(uniques))

    @property
    def reader_mode(self) -> str:
        """Comment enchainer les lecteurs : tous a la fois, ou l'un apres l'autre.

        Parallele par defaut. Le fichier de configuration n'est plus un point
        de contention -- chaque processus en lit une copie ou sa cle `Reader`
        est deja posee (voir `reader_isolation`) -- donc rien a declarer pour
        obtenir le mode rapide.

        `reader_mode: sequential` reste possible pour ce que ce mecanisme ne
        peut pas isoler : du materiel qui ne supporte pas deux campagnes en
        meme temps, ou un workspace qui ecrit ses logs dans un fichier unique.
        """
        valeur = _trouver(self.settings or {}, CLES_READER_MODE)
        mode = str(valeur).strip().lower() if valeur is not None else ""
        return mode if mode in MODES else MODE_PARALLELE

    # -------------------------------------------------------------------- divers

    @property
    def log_root(self) -> Path:
        """Dossier ou le conftest du workspace ecrit ses .log."""
        valeur = _trouver(self.settings or {}, CLES_LOGS) or "logs"
        chemin = Path(str(valeur))
        return chemin if chemin.is_absolute() else Path(self.path) / chemin

    @property
    def declared_interpreter(self) -> str:
        """Interpreteur explicitement demande par la configuration.

        Chaine vide si le workspace n'en declare pas -- distingue « rien de
        configure » de « le Python par defaut », ce dont un reglage global
        d'interpreteur a besoin pour savoir s'il doit s'effacer devant le
        workspace ou s'appliquer.
        """
        valeur = _trouver(self.settings or {}, CLES_PYTHON)
        return str(valeur).strip() if valeur else ""

    @property
    def interpreter(self) -> str:
        """Python qui doit executer les tests.

        Celui du workspace s'il en declare un : l'interface peut tourner en
        32 bits pendant que les tests chargent des DLL 64 bits. Sinon, le
        Python par defaut -- jamais `sys.executable` sans precaution : une
        fois l'interface empaquetee, ce serait son propre exe, et le lancer
        en sous-processus rouvrirait une copie de l'interface au lieu de
        pytest.
        """
        return self.declared_interpreter or interpreter_mod.default()

    @property
    def env(self) -> dict:
        """Environnement de base des processus pytest."""
        environnement = dict(os.environ)
        environnement["PYTHONUNBUFFERED"] = "1"
        return environnement
