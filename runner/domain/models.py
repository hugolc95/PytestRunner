"""Types du domaine. Aucune dependance a Qt : tout est testable sans fenetre."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    """Etat d'un test pour un lecteur donne."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

    @property
    def is_final(self) -> bool:
        """Vrai si l'etat ne changera plus d'ici la fin du run."""
        return self not in (Status.PENDING, Status.RUNNING)

    @property
    def is_bad(self) -> bool:
        return self in (Status.FAILED, Status.ERROR)

    @property
    def label(self) -> str:
        return self.value.upper()


# Ordre de gravite : l'etat d'un dossier est le pire de ce qu'il contient. Un
# seul echec au fond d'une arborescence doit se voir depuis la racine.
_SEVERITE = {
    Status.PENDING: 0,
    Status.PASSED: 1,
    Status.SKIPPED: 2,
    Status.RUNNING: 3,
    Status.FAILED: 4,
    Status.ERROR: 5,
}


def worst(statuses) -> Status:
    """Etat le plus grave d'un ensemble, PENDING si l'ensemble est vide."""
    retenus = list(statuses)
    if not retenus:
        return Status.PENDING
    return max(retenus, key=lambda s: _SEVERITE[s])


class Kind(str, Enum):
    """Nature d'un noeud de l'arbre, qui decide de son icone."""

    FOLDER = "folder"
    MODULE = "module"
    CLASS = "class"
    TEST = "test"
    CASE = "case"


@dataclass
class TestNode:
    """Un noeud de l'arbre des tests.

    `nodeid` n'est renseigne que pour les feuilles executables : un dossier ou
    une fonction parametree n'en a pas, on execute ses enfants.
    """

    name: str
    kind: Kind
    nodeid: str = ""
    children: list["TestNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def leaves(self):
        """Toutes les feuilles executables sous ce noeud, lui compris."""
        if self.is_leaf:
            if self.nodeid:
                yield self
            return
        for enfant in self.children:
            yield from enfant.leaves()


@dataclass(frozen=True)
class Reader:
    """Un lecteur materiel sur lequel la suite est jouee.

    `index` fixe sa colonne dans l'arbre et sa couleur : il doit rester stable
    d'un bout a l'autre d'un run.
    """

    name: str
    index: int

    @property
    def short_name(self) -> str:
        """Nom sans le mot final `Reader`, commun a tous les lecteurs PC/SC."""
        mots = self.name.split()
        while len(mots) > 1 and mots[-1].lower() in ("reader", "lecteur"):
            mots.pop()
        return " ".join(mots) or self.name


@dataclass(frozen=True)
class RunRequest:
    """Tout ce qu'il faut pour lancer un run, sans rien connaitre de l'UI."""

    workspace: str
    interpreter: str
    nodeids: tuple[str, ...]
    readers: tuple[Reader, ...]
    config_path: str = ""

    @property
    def total_tests(self) -> int:
        return len(self.nodeids) * max(1, len(self.readers))


@dataclass(frozen=True)
class Outcome:
    """Resultat d'un test, pour un lecteur."""

    nodeid: str
    status: Status
    reader_index: int = 0


@dataclass
class ReaderReport:
    """Bilan d'un lecteur a la fin de son run."""

    reader: Reader
    exit_code: int = 0
    duration: float = 0.0
    counts: dict[Status, int] = field(default_factory=dict)
    output: str = ""
    cancelled: bool = False

    @property
    def failed(self) -> int:
        return self.counts.get(Status.FAILED, 0) + self.counts.get(Status.ERROR, 0)

    @property
    def ok(self) -> bool:
        return not self.cancelled and self.failed == 0
