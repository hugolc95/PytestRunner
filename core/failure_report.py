"""
Extraction de la trace d'echec d'un test specifique depuis la sortie
console complete d'un run pytest (--tb=short -v).

Format pytest (section FAILURES) :

    ================================== FAILURES ===================================
    ______________________________ test_login[user] _______________________________
    <fichier>:<ligne>: in test_login
        assert v == "admin"
    E   AssertionError: assert 'user' == 'admin'
    ________________________ TestGroup.test_fails_in_class ________________________
    ...
    =========================== short test summary info ===========================

Le label de chaque bloc correspond a la partie du nodeid apres le premier
"::", jointe par des points (ex: "test_login[user]", ou
"TestGroup.test_fails_in_class" pour une methode de classe).
"""

import re

_FAILURES_HEADER_RE = re.compile(r"^=+\s*FAILURES\s*=+\s*$", re.MULTILINE)
_SUMMARY_HEADER_RE = re.compile(r"^=+\s*short test summary info\s*=+\s*$", re.MULTILINE)
_BLOCK_HEADER_RE = re.compile(r"^_{3,} (.+?) _{3,}\s*$", re.MULTILINE)


def _failure_label(nodeid: str) -> str:
    parts = nodeid.replace("\\", "/").split("::")
    return ".".join(parts[1:]) if len(parts) > 1 else nodeid


def extract_failure_traceback(output_text: str, nodeid: str) -> str | None:
    """Retourne la trace d'echec d'un nodeid precis, ou None si introuvable
    (test non lance, test passe, ou section FAILURES absente de la sortie)."""
    if not output_text:
        return None

    start_match = _FAILURES_HEADER_RE.search(output_text)
    if not start_match:
        return None

    end_match = _SUMMARY_HEADER_RE.search(output_text, start_match.end())
    section = output_text[start_match.end(): end_match.start() if end_match else len(output_text)]

    label = _failure_label(nodeid)
    headers = list(_BLOCK_HEADER_RE.finditer(section))
    for index, header in enumerate(headers):
        if header.group(1).strip() != label:
            continue
        block_start = header.end()
        block_end = headers[index + 1].start() if index + 1 < len(headers) else len(section)
        return section[block_start:block_end].strip("\n")

    return None
