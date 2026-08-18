"""Lecture de la sortie de pytest, ligne par ligne, pendant qu'elle arrive."""

from __future__ import annotations

import re

from runner.domain.models import Status

# `chemin/test_x.py::TestC::test_f[cas] PASSED [ 42%]`, et la forme de
# pytest-xdist `[gw0] [ 42%] PASSED chemin/test_x.py::test_f`.
_STATUTS = "PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"

# Le nodeid peut contenir des espaces dans les IDs de parametres, et meme un
# mot qui ressemble a un statut. On le capture donc jusqu'au DERNIER statut
# suivi d'une vraie fin de ligne pytest : raison optionnelle, puis pourcentage.
_LIGNE = re.compile(
    rf"^(?P<nodeid>.+::.+)\s+(?P<statut>{_STATUTS})\b"
    rf"(?:\s+\(.*\))?(?:\s+\[\s*\d+%\])?\s*$"
)
_LIGNE_XDIST = re.compile(
    rf"^\[gw\d+\]\s+\[\s*\d+%\]\s+(?P<statut>{_STATUTS})\s+"
    rf"(?P<nodeid>.+::.+?)\s*$"
)

_COLLECTE = re.compile(r"collected\s+(\d+)\s+item")

# XFAIL et XPASS ne sont pas des echecs : un test attendu en echec qui echoue
# est un succes. Les compter en rouge ferait paniquer pour rien.
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
    for motif in (_LIGNE, _LIGNE_XDIST):
        m = motif.match(ligne.strip())
        if m:
            statut = _TRADUCTION.get(m.group("statut"))
            if statut is not None:
                return m.group("nodeid"), statut
    return None


def parse_collected(ligne: str) -> int | None:
    """Nombre de tests annonce par `collected N items`, sinon None."""
    m = _COLLECTE.search(ligne)
    return int(m.group(1)) if m else None


def parse_collect_only(sortie: str) -> list[str]:
    """Nodeids d'un `pytest --collect-only -q`.

    La sortie se termine par un resume (`12 tests collected in 0.4s`) et peut
    contenir des avertissements : seules les lignes qui ressemblent a un nodeid
    sont retenues.
    """
    nodeids: list[str] = []
    vus: set[str] = set()

    for ligne in (sortie or "").splitlines():
        candidat = ligne.strip()
        if not candidat or "::" not in candidat:
            continue
        if candidat.startswith(("<", "=", "-", "[", "warning", "WARNING")):
            continue
        if " " in candidat:  # un vrai nodeid n'a pas d'espace avant les crochets
            avant_crochet = candidat.split("[", 1)[0]
            if " " in avant_crochet:
                continue
        if candidat not in vus:
            vus.add(candidat)
            nodeids.append(candidat)

    return nodeids
