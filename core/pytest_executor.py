import re

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
