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


def parse_test_status_line(line: str) -> tuple[str, str] | None:
    """Detecte une ligne de resultat pytest -v et retourne (nodeid, status).

    Gere les deux formats de sortie -v de pytest : le format standard
    (nodeid puis status) et celui de pytest-xdist quand -n est utilise
    (status puis nodeid, prefixe par [gwN]).
    """
    match = _STATUS_THEN_NODEID_RE.match(line)
    if match:
        return match.group("nodeid").strip(), match.group("status")

    match = _NODEID_THEN_STATUS_RE.match(line)
    if match:
        return match.group("nodeid").strip(), match.group("status")

    return None
