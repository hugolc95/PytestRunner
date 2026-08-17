"""Tri des lignes de la console : quoi montrer selon ce qu'on cherche.

Une sortie pytest verbeuse melange trois choses de nature differente : des
verdicts ligne a ligne, des traces d'echec, et la charpente du run (ce qui a
ete collecte, les bannieres, le bilan). Sur un run reel de 160 tests dont 44
en echec, les verdicts font a eux seuls 160 des 292 lignes -- et ils sont deja
dans l'arbre, en couleur, colonne par colonne.

Filtrer n'est pas cacher : le tampon complet reste intact, seule la vue change.
On raisonne ici sur des chaines, sans Qt : chaque regle est verifiable.
"""

from __future__ import annotations

import re
from enum import Enum

from runner.domain.ansi import strip_ansi
from runner.domain.failures import is_failure_section, section_of
from runner.domain.models import Status
from runner.domain.parsing import parse_status_line


class Lens(str, Enum):
    """Ce qu'on veut voir de la sortie."""

    ALL = "all"
    PROBLEMS = "problems"
    OUTLINE = "outline"

    @property
    def label(self) -> str:
        return {"all": "All", "problems": "Problems", "outline": "Outline"}[self.value]


# Le titre d'un bloc d'echec : `____ TestC.test_f ____`.
_ENTETE = re.compile(r"^_{3,}\s+.+?\s+_{3,}$")

# Le cadre d'une trace : `chemin/test_x.py:42: AssertionError`.
_TRACE = re.compile(r"^\S+\.py:\d+:")

# Le resume final : `FAILED test_x.py::test_f - AssertionError: ...`.
_RESUME = re.compile(r"^(FAILED|ERROR)\s+\S+")

_COLLECTE = re.compile(r"\bcollected\s+\d+\s+item")


def _est_probleme(nue: str) -> bool:
    """Vrai si la ligne, prise seule, participe a l'explication d'un echec."""
    if not nue:
        return False
    if nue == "E" or nue.startswith("E "):
        return True
    if nue.startswith(">") or _TRACE.match(nue) or _RESUME.match(nue):
        return True
    if _ENTETE.match(nue):
        return True
    resultat = parse_status_line(nue)
    return resultat is not None and resultat[1] in (Status.FAILED, Status.ERROR)


def _est_charpente(nue: str) -> bool:
    """Vrai si la ligne dit la forme du run plutot que son detail."""
    if not nue:
        return False
    if section_of(nue) is not None or _RESUME.match(nue):
        return True
    return bool(_COLLECTE.search(nue))


class LensFilter:
    """Decide ligne par ligne, en se souvenant de la section en cours.

    Une decision sans memoire ne suffit pas. Avec `--tb=short`, la ligne de
    code qui a echoue n'est precedee d'aucun marqueur : elle est simplement
    indentee sous son cadre. Prise isolement elle est indiscernable d'une ligne
    de bruit, alors qu'elle dit exactement ce qui s'est passe. Une fois entre
    dans `FAILURES` ou `ERRORS`, on garde donc tout jusqu'a la banniere
    suivante.
    """

    def __init__(self, lens: Lens = Lens.ALL):
        self.lens = lens
        self._dans_section = False

    def reset(self) -> None:
        self._dans_section = False

    def keep(self, ligne: str) -> bool:
        if self.lens is Lens.ALL:
            return True

        nue = strip_ansi(ligne).strip()
        titre = section_of(nue)

        if self.lens is Lens.OUTLINE:
            self._dans_section = False
            return _est_charpente(nue)

        if titre is not None:
            self._dans_section = is_failure_section(titre)
            return True
        return self._dans_section or _est_probleme(nue)


def keep(ligne: str, lens: Lens) -> bool:
    """Decision sans memoire, pour une ligne isolee.

    Utile aux tests et aux cas ou l'on n'a pas le flux entier ; le rendu de la
    console passe, lui, par `LensFilter`.
    """
    return LensFilter(lens).keep(ligne)


def apply_lens(lignes, lens: Lens) -> list[str]:
    """Les lignes retenues. `ALL` rend la liste telle quelle."""
    if lens is Lens.ALL:
        return list(lignes)
    filtre = LensFilter(lens)
    return [ligne for ligne in lignes if filtre.keep(ligne)]
