"""Lecture de la sortie de pytest, ligne par ligne, pendant qu'elle arrive."""

from __future__ import annotations

import re

from runner.domain.ansi import strip_ansi
from runner.domain.models import Status

OUTCOME_PREFIX = "PYTESTRUNNER_OUTCOME\t"

_STATUTS = "PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"

_LIGNE = re.compile(
    rf"^(?P<nodeid>.+::.+)\s+(?P<statut>{_STATUTS})\b"
    rf"(?:\s+\(.*\))?(?:\s+\[\s*\d+%\])?\s*$"
)
_LIGNE_XDIST = re.compile(
    rf"^\[gw\d+\]\s+\[\s*\d+%\]\s+(?P<statut>{_STATUTS})\s+"
    rf"(?P<nodeid>.+::.+?)\s*$"
)

_COLLECTE = re.compile(r"collected\s+(\d+)\s+item")

_TRADUCTION = {
    "PASSED": Status.PASSED,
    "XPASS": Status.PASSED,
    "XFAIL": Status.SKIPPED,
    "SKIPPED": Status.SKIPPED,
    "FAILED": Status.FAILED,
    "ERROR": Status.ERROR,
}


def parse_status_line(ligne: str) -> tuple[str, Status] | None:
    """(nodeid, statut) si cette ligne cloture un test, sinon None."""
    nue = strip_ansi(ligne).strip()

    if nue.startswith(OUTCOME_PREFIX):
        morceaux = nue.split("\t", 2)
        if len(morceaux) == 3:
            statut = _TRADUCTION.get(morceaux[1])
            if statut is not None and morceaux[2]:
                return morceaux[2], statut

    for motif in (_LIGNE, _LIGNE_XDIST):
        m = motif.match(nue)
        if m:
            statut = _TRADUCTION.get(m.group("statut"))
            if statut is not None:
                return m.group("nodeid"), statut
    return None


def is_outcome_protocol_line(ligne: str) -> bool:
    """Vrai pour une ligne de transport interne, a ne pas montrer a l'UI."""
    return strip_ansi(ligne).strip().startswith(OUTCOME_PREFIX)


class NodeidResolver:
    """Rapproche les nodeids du run de ceux conserves pendant la collecte.

    Le chemin est normalise, tandis que la partie classe/fonction/parametre est
    comparee exactement. Dans certains workspaces historiques, pytest peut
    toutefois rapporter le nom de la mauvaise TestSuite tout en conservant
    exactement la bonne partie Python. Quand cette partie designe UN SEUL test
    parmi ceux demandes au run, elle suffit pour rattacher le verdict a la bonne
    ligne. En cas d'ambiguite, aucune correction n'est faite.
    """

    @staticmethod
    def _morceaux(nodeid: str):
        chemin, separateur, reste = nodeid.partition("::")
        if not separateur:
            return (), ""
        chemin = re.sub(r"/+", "/", chemin.replace("\\", "/"))
        parties = tuple(
            partie.casefold() for partie in chemin.split("/")
            if partie and partie != "."
        )
        return parties, reste

    def __init__(self, collected):
        self._exact: set[str] = set()
        self._par_reste: dict[str, list[tuple[tuple[str, ...], str]]] = {}
        for nodeid in collected:
            connu = str(nodeid)
            self._exact.add(connu)
            chemin, reste = self._morceaux(connu)
            if chemin and reste:
                self._par_reste.setdefault(reste, []).append((chemin, connu))

    def resolve(self, reported: str) -> str:
        reported = strip_ansi(str(reported or "")).strip()
        if reported in self._exact:
            return reported

        chemin_recu, reste_recu = self._morceaux(reported)
        if not chemin_recu or not reste_recu:
            return reported

        memes_tests = self._par_reste.get(reste_recu, ())

        # Chemin normal : meme suffixe de chemin + meme partie Python.
        candidats: list[str] = []
        for chemin_connu, connu in memes_tests:
            commun = min(len(chemin_recu), len(chemin_connu))
            if chemin_recu[-commun:] == chemin_connu[-commun:]:
                candidats.append(connu)
        if len(candidats) == 1:
            return candidats[0]

        # Cas vu en environnement reel : pytest rapporte
        #   .../BioLockTestSuite::Test_Class::test_body[...]
        # alors que le run a demande
        #   .../CVCertificateV3::Test_Class::test_body[...]
        # Si classe/fonction/parametre ne correspond qu'a UNE feuille demandee,
        # on peut la retrouver sans risque. S'il y en a plusieurs, on conserve
        # le nodeid recu pour ne jamais colorer le mauvais test.
        if len(memes_tests) == 1:
            return memes_tests[0][1]

        return reported


def resolve_collected_nodeid(reported: str, collected) -> str:
    """Raccourci sans etat, pratique hors d'une boucle de resultats."""
    return NodeidResolver(collected).resolve(reported)


def parse_collected(ligne: str) -> int | None:
    """Nombre de tests annonce par `collected N items`, sinon None."""
    m = _COLLECTE.search(ligne)
    return int(m.group(1)) if m else None


def parse_collect_only(sortie: str) -> list[str]:
    """Nodeids d'un `pytest --collect-only -q`."""
    nodeids: list[str] = []
    vus: set[str] = set()

    for ligne in (sortie or "").splitlines():
        candidat = ligne.strip()
        if not candidat or "::" not in candidat:
            continue
        if candidat.startswith(("<", "=", "-", "[", "warning", "WARNING")):
            continue
        if " " in candidat:
            avant_crochet = candidat.split("[", 1)[0]
            if " " in avant_crochet:
                continue
        if candidat not in vus:
            vus.add(candidat)
            nodeids.append(candidat)

    return nodeids


_DUREE = re.compile(
    r"^(?P<duree>\d+\.\d+)s\s+(?:setup|call|teardown)\s+(?P<nodeid>.+?)\s*$"
)


def parse_durations(sortie: str) -> dict[str, float]:
    """Duree totale de chaque test, sommee sur ses phases setup/call/teardown."""
    durees: dict[str, float] = {}
    for ligne in (sortie or "").splitlines():
        m = _DUREE.match(strip_ansi(ligne).strip())
        if m is not None:
            durees[m.group("nodeid")] = durees.get(m.group("nodeid"), 0.0) + float(
                m.group("duree"))
    return durees
