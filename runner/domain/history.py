"""Historique des runs : ce qui a tourne, quand, et ce qui a change depuis.

Un verdict seul ne dit pas grand-chose. Ce qu'on veut savoir devant un rouge,
c'est s'il est nouveau -- et devant un vert, s'il tient d'un run a l'autre. Il
faut pour cela garder une trace de chaque run, avec sa sortie.

L'historique vit dans le dossier de l'utilisateur, JAMAIS dans le workspace
teste : l'outil s'utilise sur des depots qui ne sont pas les siens, et y
deposer des fichiers finirait dans un commit.

Un run par LECTEUR : chacun a ses compteurs, sa sortie, son verdict. Un total
agrege masquerait lequel a echoue, ce qui est justement la question quand on
teste la meme suite sur deux lecteurs.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from runner.domain.models import Status

# Nombre d'entrees gardees. Au-dela, l'historique se relit mal et pese pour
# rien : ce qu'on compare est toujours recent.
MAX_ENTREES = 300

# Runs examines par defaut pour reperer un test instable.
FENETRE_FLAKY = 50


def dossier() -> Path:
    """Dossier de stockage, cree si besoin."""
    base = Path.home() / ".pytest_runner" / "history"
    base.mkdir(parents=True, exist_ok=True)
    return base


_compteur = itertools.count()


def nouvel_identifiant() -> str:
    """Identifiant lisible et unique, qui sert aussi de nom de fichier.

    L'horodatage seul ne suffit pas : deux appels dans la meme milliseconde
    rendaient la meme chaine. Deux runs porteraient alors le meme identifiant
    et le meme nom de fichier JUnit -- l'un ecraserait l'autre, et les
    retrouver dans l'historique deviendrait impossible. Le compteur ferme la
    porte plutot que de parier sur l'horloge.
    """
    return (time.strftime("%Y%m%d_%H%M%S")
            + f"_{int(time.time() * 1000) % 1000:03d}"
            + f"_{next(_compteur):03d}")


@dataclass(frozen=True)
class RunEntry:
    """Un run termine, pour un lecteur."""

    id: str
    timestamp: float
    workspace: str
    reader: str = ""
    duration: float = 0.0
    exit_code: int = 0
    counts: dict = field(default_factory=dict)
    nodeids: tuple[str, ...] = ()
    failed_nodeids: tuple[str, ...] = ()
    output_file: str = ""
    junit_path: str = ""

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def count(self, statut: Status) -> int:
        return int(self.counts.get(statut.name, 0))

    @property
    def ok(self) -> bool:
        return self.count(Status.FAILED) == 0 and self.count(Status.ERROR) == 0

    @property
    def label(self) -> str:
        quand = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))
        return f"{quand} — {self.reader}" if self.reader else quand

    @property
    def summary(self) -> str:
        return (f"{self.count(Status.PASSED)} passed, "
                f"{self.count(Status.FAILED)} failed, "
                f"{self.count(Status.SKIPPED)} skipped, "
                f"{self.count(Status.ERROR)} error")

    def output(self) -> str:
        """La sortie console du run, relue depuis son fichier."""
        if not self.output_file:
            return ""
        try:
            return Path(self.output_file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def to_json(self) -> dict:
        return {
            "id": self.id, "timestamp": self.timestamp,
            "workspace": self.workspace, "reader": self.reader,
            "duration": self.duration, "exit_code": self.exit_code,
            "counts": dict(self.counts),
            "nodeids": list(self.nodeids),
            "failed_nodeids": list(self.failed_nodeids),
            "output_file": self.output_file, "junit_path": self.junit_path,
        }

    @classmethod
    def from_json(cls, donnees: dict) -> "RunEntry | None":
        """Relit une entree. None si elle est inexploitable.

        Un fichier ecrit par une version plus ancienne, ou tronque par une
        coupure, ne doit pas priver de tout l'historique.
        """
        try:
            return cls(
                id=str(donnees["id"]),
                timestamp=float(donnees.get("timestamp", 0.0)),
                workspace=str(donnees.get("workspace", "")),
                reader=str(donnees.get("reader", "")),
                duration=float(donnees.get("duration", 0.0)),
                exit_code=int(donnees.get("exit_code", 0)),
                counts={str(c): int(v)
                        for c, v in (donnees.get("counts") or {}).items()},
                nodeids=tuple(donnees.get("nodeids") or ()),
                failed_nodeids=tuple(donnees.get("failed_nodeids") or ()),
                output_file=str(donnees.get("output_file", "")),
                junit_path=str(donnees.get("junit_path", "")),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            # `AttributeError` compte autant que les autres : un `counts`
            # devenu une chaine repond a `.items()` par une exception d'un
            # troisieme genre, et non rattrapee elle empechait l'application
            # de demarrer -- pas seulement de lire cette entree.
            return None


@dataclass(frozen=True)
class Comparison:
    """Ce qui a change entre deux runs."""

    older: RunEntry
    newer: RunEntry
    newly_failed: tuple[str, ...]
    newly_fixed: tuple[str, ...]
    still_failing: tuple[str, ...]

    @property
    def unchanged(self) -> bool:
        return not (self.newly_failed or self.newly_fixed)


def compare(a: RunEntry, b: RunEntry) -> Comparison:
    """Compare deux runs, le plus ancien servant de reference.

    L'ordre est deduit de l'horodatage et non de celui des arguments : « ce
    test s'est mis a echouer » et « ce test est repare » sont deux phrases
    inversees l'une de l'autre, et se tromper de sens rend le resultat
    trompeur plutot que faux.
    """
    ancien, recent = sorted((a, b), key=lambda e: e.timestamp)
    avant = set(ancien.failed_nodeids)
    apres = set(recent.failed_nodeids)
    return Comparison(
        older=ancien, newer=recent,
        newly_failed=tuple(sorted(apres - avant)),
        newly_fixed=tuple(sorted(avant - apres)),
        still_failing=tuple(sorted(avant & apres)),
    )


@dataclass(frozen=True)
class FlakyTest:
    """Un test dont le verdict ne tient pas d'un run a l'autre, SUR UN LECTEUR."""

    nodeid: str
    seen: int
    failed: int
    reader: str = ""

    @property
    def ratio(self) -> float:
        return self.failed / self.seen if self.seen else 0.0


class History:
    """Les runs enregistres, sur disque."""

    def __init__(self, racine: Path | None = None, max_entrees: int = MAX_ENTREES):
        self.racine = Path(racine) if racine is not None else dossier()
        self.racine.mkdir(parents=True, exist_ok=True)
        self.max_entrees = max_entrees
        self._entrees: list[RunEntry] = []
        self._charger()

    @property
    def fichier(self) -> Path:
        return self.racine / "run_history.json"

    # ------------------------------------------------------------- lecture

    def _charger(self) -> None:
        try:
            brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._entrees = []
            return
        if not isinstance(brut, list):
            self._entrees = []
            return
        # Les entrees illisibles sont ecartees une par une : une seule ligne
        # abimee ne doit pas emporter tout l'historique.
        lues = (RunEntry.from_json(d) for d in brut if isinstance(d, dict))
        self._entrees = [e for e in lues if e is not None]

    def entries(self) -> list[RunEntry]:
        """Les runs, du plus recent au plus ancien."""
        return list(self._entrees)

    def find(self, identifiant: str) -> RunEntry | None:
        for entree in self._entrees:
            if entree.id == identifiant:
                return entree
        return None

    # ------------------------------------------------------------ ecriture

    def _enregistrer(self) -> None:
        """Ecrit par un temporaire remplace d'un bloc.

        Ecrire en place laisse un JSON tronque si le processus s'arrete au
        mauvais moment -- et c'est tout l'historique qui devient illisible.
        """
        temporaire = self.fichier.with_suffix(".tmp")
        try:
            temporaire.write_text(
                json.dumps([e.to_json() for e in self._entrees],
                           indent=2, ensure_ascii=False),
                encoding="utf-8")
            temporaire.replace(self.fichier)
        except OSError:
            # L'historique est un confort : il ne doit jamais faire echouer un
            # run qui, lui, s'est bien passe.
            try:
                temporaire.unlink()
            except OSError:
                pass

    def add(self, entry: RunEntry, output: str = "") -> RunEntry:
        """Enregistre un run, avec sa sortie console dans un fichier a part."""
        if output:
            nom = f"{entry.id}{'_' + _sain(entry.reader) if entry.reader else ''}.log"
            chemin = self.racine / nom
            try:
                chemin.write_text(output, encoding="utf-8")
                entry = replace(entry, output_file=str(chemin))
            except OSError:
                entry = replace(entry, output_file="")

        self._entrees.insert(0, entry)
        self._oublier(self._entrees[self.max_entrees:])
        self._entrees = self._entrees[:self.max_entrees]
        self._enregistrer()
        return entry

    def clear(self) -> None:
        """Efface tout, fichiers de sortie compris."""
        self._oublier(self._entrees)
        self._entrees = []
        self._enregistrer()

    def _oublier(self, entrees) -> None:
        """Supprime les fichiers des entrees qui sortent de l'historique.

        Sans cela le dossier grossirait indefiniment avec des .log que plus
        aucune entree ne designe -- invisibles, et jamais nettoyes.
        """
        for entree in entrees:
            for chemin in (entree.output_file, entree.junit_path):
                if not chemin:
                    continue
                try:
                    os.remove(chemin)
                except OSError:
                    pass

    # -------------------------------------------------------------- analyse

    def flaky(self, fenetre: int = FENETRE_FLAKY) -> list[FlakyTest]:
        """Tests dont le verdict change d'un run a l'autre, LECTEUR PAR LECTEUR.

        Un test toujours rouge n'est pas instable : il est casse, et c'est une
        autre conversation. Seuls comptent ceux qui passent PARFOIS.

        Le decoupage par lecteur n'est pas un detail. Un test qui echoue
        toujours sur un lecteur et passe toujours sur l'autre est parfaitement
        REPRODUCTIBLE : c'est une difference entre lecteurs, que l'arbre montre
        deja par ailleurs. Compte tous lecteurs confondus, il ressortait a 50 %
        d'echec au milieu des vrais tests instables -- et envoyait chercher un
        alea qui n'existe pas.
        """
        vus: dict[tuple[str, str], int] = {}
        rates: dict[tuple[str, str], int] = {}

        for entree in self._entrees[:fenetre]:
            echecs = set(entree.failed_nodeids)
            for nodeid in entree.nodeids:
                clef = (entree.reader, nodeid)
                vus[clef] = vus.get(clef, 0) + 1
                if nodeid in echecs:
                    rates[clef] = rates.get(clef, 0) + 1

        instables = [FlakyTest(nodeid, total, rates.get(clef, 0), reader)
                     for clef, total in vus.items()
                     for reader, nodeid in (clef,)
                     if 0 < rates.get(clef, 0) < total]
        instables.sort(key=lambda f: (-f.ratio, f.nodeid, f.reader))
        return instables


def _sain(nom: str) -> str:
    """Nom de lecteur utilisable dans un nom de fichier."""
    return "".join(c if c.isalnum() else "_" for c in str(nom)).strip("_")[:40]
