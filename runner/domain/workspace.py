"""Lecture de la configuration d'un workspace : lecteurs, logs, interpreteur.

Un workspace decrit comment ses tests doivent tourner. Le fichier ne s'appelle
pas toujours `config.yml` : on examine tous les YAML de la racine, les noms
standards d'abord.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from runner.domain.models import Reader

NOMS_STANDARDS = ("config.yaml", "config.yml")

# Une meme notion porte des noms differents d'un projet a l'autre. La
# comparaison ignore la casse, les tirets et les espaces.
CLES_READER = ("reader", "lecteur")
CLES_READERS = ("readers", "lecteurs", "reader_list")
CLES_LOGS = ("log_path", "log_directory", "log_dir", "logs_path", "logpath")
CLES_PYTHON = ("python_executable", "python", "interpreter")


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
    def load(cls, path: str) -> "Workspace":
        """Lit le premier fichier de configuration exploitable du workspace."""
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

    # -------------------------------------------------------------------- divers

    @property
    def log_root(self) -> Path:
        """Dossier ou le conftest du workspace ecrit ses .log."""
        valeur = _trouver(self.settings or {}, CLES_LOGS) or "logs"
        chemin = Path(str(valeur))
        return chemin if chemin.is_absolute() else Path(self.path) / chemin

    @property
    def interpreter(self) -> str:
        """Python qui doit executer les tests.

        Celui du workspace s'il en declare un : l'interface peut tourner en
        32 bits pendant que les tests chargent des DLL 64 bits.
        """
        valeur = _trouver(self.settings or {}, CLES_PYTHON)
        return str(valeur).strip() if valeur else sys.executable

    @property
    def env(self) -> dict:
        """Environnement de base des processus pytest."""
        environnement = dict(os.environ)
        environnement["PYTHONUNBUFFERED"] = "1"
        return environnement
