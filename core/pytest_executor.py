import os
import re
import tempfile
from contextlib import contextmanager

# Windows refuse toute ligne de commande depassant 32767 caracteres :
# CreateProcess echoue alors avec "WinError 206: le nom de fichier ou son
# extension est trop long". Selectionner un dossier entier suffit largement a
# depasser cette limite, chaque nodeid pesant 40 a 100 caracteres.
#
# On bascule donc bien avant sur la syntaxe @fichier de pytest, qui lit ses
# arguments dans un fichier a raison d'un par ligne et n'a aucune limite.
MAX_INLINE_ARGS_LENGTH = 6000


@contextmanager
def pytest_nodeid_args(nodeids: list[str]):
    """Fournit les arguments pytest pour ces nodeids, sans limite de longueur.

    Passe les nodeids directement quand ils tiennent dans une ligne de commande
    raisonnable, sinon les ecrit dans un fichier temporaire passe en @fichier.
    Le fichier est supprime a la sortie du bloc.

    Les nodeids produits par pytest sont echappes en ASCII (un identifiant
    parametre "ete" accentue devient "\\xe9t\\xe9"), donc l'encodage du fichier
    n'est pas un point de rupture ici.
    """
    if sum(len(nodeid) + 1 for nodeid in nodeids) <= MAX_INLINE_ARGS_LENGTH:
        yield list(nodeids)
        return

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="pytest_nodeids_",
        delete=False,
        encoding="utf-8",
    )
    try:
        with handle:
            handle.write("\n".join(nodeids) + "\n")
        yield [f"@{handle.name}"]
    finally:
        try:
            os.remove(handle.name)
        except OSError:
            pass


# Sans pytest-xdist : "<nodeid> STATUS               [ XX%]"
_NODEID_THEN_STATUS_RE = re.compile(
    r"^\s*(?P<nodeid>.+?::.+?)\s+(?P<status>PASSED|FAILED|SKIPPED|ERROR)\b"
)

# Avec pytest-xdist (-n auto) : "[gwN] [ XX%] STATUS <nodeid>"
_STATUS_THEN_NODEID_RE = re.compile(
    r"^\s*\[gw\d+\]\s*(?:\[\s*\d+%\]\s*)?(?P<status>PASSED|FAILED|SKIPPED|ERROR)\s+(?P<nodeid>.+::.+?)\s*$"
)


# Quand les logs sont affiches en direct (log_cli = true dans pytest.ini, reglage
# courant pour du test materiel), pytest coupe la ligne en deux : il ecrit le
# nodeid, puis les enregistrements de log, puis le statut seul sur sa ligne.
#
#   test_carte.py::test_pso[nom-RSA-...-tc0]
#   ------------------------------ live log call ------------------------------
#   INFO     apdu APDU >> 00A4040007A0000000041010
#   PASSED                                                            [ 16%]
#
# Un nodeid seul sur sa ligne est donc mis en attente, et le prochain statut seul
# lui est attribue.
_LONE_NODEID_RE = re.compile(r"^\s*(?P<nodeid>\S+::\S+)\s*$")

# Statut seul : rien d'autre que le mot et un eventuel pourcentage. Cette
# exigence evite d'attraper les lignes du resume final ("FAILED chemin::test -
# raison"), qui commencent aussi par un statut mais portent leur propre nodeid.
_LONE_STATUS_RE = re.compile(
    r"^\s*(?P<status>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\s*(?:\[\s*\d+%\])?\s*$"
)


def parse_test_status_line(line: str) -> tuple[str, str] | None:
    """Detecte une ligne de resultat pytest -v et retourne (nodeid, status).

    Gere les deux formats de sortie -v de pytest : le format standard
    (nodeid puis status) et celui de pytest-xdist quand -n est utilise
    (status puis nodeid, prefixe par [gwN]).

    Ne traite que les lignes completes. Pour le cas ou pytest separe le nodeid du
    statut (logs affiches en direct), utiliser PytestOutputParser.
    """
    match = _STATUS_THEN_NODEID_RE.match(line)
    if match:
        return match.group("nodeid").strip(), match.group("status")

    match = _NODEID_THEN_STATUS_RE.match(line)
    if match:
        return match.group("nodeid").strip(), match.group("status")

    return None


# Chemin de fichier de test suivi de `::`, c'est-a-dire la partie chemin d'un
# nodeid. Le `(?=::)` garantit qu'on ne touche ni aux lignes de trace
# (`chemin/test_x.py:34: AssertionError`) ni aux messages de collecte : la ou le
# chemin complet sert a retrouver le fichier, il reste entier.
_NODEID_PATH_RE = re.compile(r"(?P<chemin>[^\s:]+(?:[/\\][^\s:]+)*\.py)(?=::)")

# Marque de troncature. Un caractere unique, pour ne pas reprendre en largeur ce
# qu'on vient d'economiser.
ELLIPSIS = "…"


def compact_path(chemin: str, levels: int = 1) -> str:
    """Ne garde que les `levels` derniers dossiers d'un chemin de fichier.

    `TSu/JC_API/Int/BioLockTestSuite/test_x.py` devient
    `…/BioLockTestSuite/test_x.py`. Le dossier conserve porte le nom de la suite,
    qui est l'information utile ; ce qui precede se repete a chaque ligne.
    """
    if levels < 0:
        return chemin

    separateur = "\\" if "\\" in chemin and "/" not in chemin else "/"
    morceaux = re.split(r"[/\\]", chemin)
    if len(morceaux) <= levels + 1:
        return chemin

    gardes = morceaux[-(levels + 1):] if levels else morceaux[-1:]
    return ELLIPSIS + separateur + separateur.join(gardes)


def compact_output_line(line: str, levels: int = 1) -> str:
    """Raccourcit les chemins des nodeids d'une ligne de sortie pytest.

    Avec une arborescence profonde, le chemin occupe l'essentiel de la ligne et
    se repete a chaque test. Seul l'affichage est concerne : la sortie brute est
    conservee telle quelle pour l'historique et les traces d'echec.
    """
    if levels < 0:
        return line
    return _NODEID_PATH_RE.sub(lambda m: compact_path(m.group("chemin"), levels), line)


class PytestOutputParser:
    """Suit la sortie de pytest -v ligne par ligne et en extrait les resultats.

    Contrairement a parse_test_status_line(), garde en memoire le dernier nodeid
    vu seul sur sa ligne, ce qui permet de rattacher un statut ecrit plus loin.
    Sans cela, un workspace qui affiche ses logs en direct ne colorait aucun test
    dans l'arbre, alors que les compteurs finaux restaient justes puisqu'ils sont
    relus dans le resume de pytest.
    """

    def __init__(self):
        self._pending_nodeid: str | None = None

    def feed(self, line: str) -> tuple[str, str] | None:
        """Retourne (nodeid, status) si cette ligne termine un test."""
        complete = parse_test_status_line(line)
        if complete:
            self._pending_nodeid = None
            return complete

        lone_status = _LONE_STATUS_RE.match(line)
        if lone_status and self._pending_nodeid:
            nodeid = self._pending_nodeid
            self._pending_nodeid = None
            return nodeid, lone_status.group("status")

        lone_nodeid = _LONE_NODEID_RE.match(line)
        if lone_nodeid:
            self._pending_nodeid = lone_nodeid.group("nodeid").strip()

        return None
