"""Lecture de la sortie de pytest, ligne par ligne, pendant qu'elle arrive."""

from __future__ import annotations

import re

from runner.domain.ansi import strip_ansi
from runner.domain.models import Status

OUTCOME_PREFIX = "PYTESTRUNNER_OUTCOME\t"

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
    nue = strip_ansi(ligne).strip()

    # Le plugin interne emet ce format independant de l'apparence choisie par
    # pytest (couleurs, plugins de terminal, pourcentage, xdist...). C'est la
    # source la plus fiable : le nodeid vient directement de l'objet pytest.
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

    Pytest peut presenter le meme fichier relativement a deux ``rootdir``
    differents entre la collecte et l'execution. Sous Windows, un plugin peut
    en plus rendre le chemin absolu, changer la casse du lecteur ou employer
    des antislashs. L'ancien code exigeait une egalite caractere par caractere :
    le verdict arrivait bien, mais l'arbre le rejetait et tous les compteurs
    restaient a zero.

    La partie Python du nodeid (classe, fonction et parametre) reste comparee
    exactement. Seul le chemin est normalise, et un suffixe n'est accepte que
    s'il designe un UNIQUE test collecte. En cas d'ambiguite on rend la valeur
    recue : l'interface pourra la signaler au lieu d'affecter le mauvais test.
    L'index est construit une seule fois par lecteur. Sur une suite de 10 000
    tests, reparcourir toute la collecte pour chacun des 10 000 verdicts
    recreerait exactement le gel que cette classe doit corriger.
    """

    @staticmethod
    def _morceaux(nodeid: str):
        chemin, separateur, reste = nodeid.partition("::")
        if not separateur:
            return (), ""
        # Le chemin seul est insensible a la casse : c'est necessaire sur
        # Windows, sans rendre les noms de tests/IDs de parametres permissifs.
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

        candidats: list[str] = []
        for chemin_connu, connu in self._par_reste.get(reste_recu, ()):
            commun = min(len(chemin_recu), len(chemin_connu))
            if chemin_recu[-commun:] == chemin_connu[-commun:]:
                candidats.append(connu)

        return candidats[0] if len(candidats) == 1 else reported


def resolve_collected_nodeid(reported: str, collected) -> str:
    """Raccourci sans etat, pratique hors d'une boucle de resultats."""
    return NodeidResolver(collected).resolve(reported)


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


# `0.05s call     tests/test_x.py::test_f`. `--durations=0` (pose sur chaque
# run) demande a pytest LUI-MEME de chronometrer chaque test -- rien ici ne
# mesure quoi que ce soit, on relit juste son calcul.
_DUREE = re.compile(
    r"^(?P<duree>\d+\.\d+)s\s+(?:setup|call|teardown)\s+(?P<nodeid>.+?)\s*$"
)


def parse_durations(sortie: str) -> dict[str, float]:
    """Duree totale de chaque test, sommee sur ses phases setup/call/teardown.

    Sommer les trois plutot que ne garder que `call` : un test dont la
    fixture met une seconde a se preparer est tout aussi lent a l'usage, meme
    si son corps est instantane.

    `--durations-min` (0.005s par defaut) cache les tests les plus rapides de
    ce releve : ils n'apparaissent simplement pas ici, plutot que d'y figurer
    a zero.
    """
    durees: dict[str, float] = {}
    for ligne in (sortie or "").splitlines():
        m = _DUREE.match(strip_ansi(ligne).strip())
        if m is not None:
            durees[m.group("nodeid")] = durees.get(m.group("nodeid"), 0.0) + float(
                m.group("duree"))
    return durees
