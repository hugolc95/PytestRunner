"""Comparaison semantique de logs produits par plusieurs lecteurs.

Deux executions identiques ne donnent presque jamais deux fichiers identiques :
horodatages, durees et nom du lecteur changent sans expliquer un comportement.
Ce module retire ce bruit avant d'aligner les lignes, mais rend les indices du
texte ORIGINAL afin que l'interface puisse surligner exactement ce qui compte.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from runner.domain.ansi import strip_ansi


_TIMESTAMP = re.compile(
    r"(?<!\d)(?:\d{4}[-/.]\d{2}[-/.]\d{2}[ T])?"
    r"\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?"
    r"(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?(?!\d)"
)
_DATE = re.compile(r"(?<!\d)\d{4}[-/.]\d{2}[-/.]\d{2}(?!\d)")
_DURATION = re.compile(
    r"(?<![\w.])\d+(?:[.,]\d+)?\s*"
    r"(?:ns|[µμ]s|us|ms|msec|s|sec|secs|seconds?|min|mins|minutes?)\b",
    re.IGNORECASE,
)
_NAMED_VOLATILE = re.compile(
    r"\b(?:timestamp|time|datetime|elapsed|duration)\s*[:=]\s*"
    r"(?:\d+(?:[.,]\d+)?|\S+)",
    re.IGNORECASE,
)
_SEPARATOR = re.compile(r"([=\-_*])\1{5,}")
_ERROR = re.compile(
    r"(?:^|[\s\[|:-])(?:ERROR|ERRO|CRITICAL|FATAL)(?:\s|\]|:|-)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LogDifferences:
    """Indices differents et indices d'erreur, une paire par log."""

    changed: tuple[frozenset[int], ...]
    errors: tuple[frozenset[int], ...]

    @property
    def any(self) -> bool:
        return any(self.changed)


def normalize_line(line: str, ignored_tokens=()) -> str:
    """Forme comparable d'une ligne, sans les valeurs volatiles connues."""
    normalized = strip_ansi(str(line or ""))

    # Le nom du lecteur est une dimension de la comparaison, pas une
    # difference de comportement. Le plus long d'abord evite que `Reader`
    # ne decoupe `Cosmo11Secured Reader` avant son remplacement complet.
    for token in sorted({str(t) for t in ignored_tokens if str(t)},
                        key=len, reverse=True):
        normalized = re.sub(re.escape(token), "<reader>", normalized,
                            flags=re.IGNORECASE)

    normalized = _TIMESTAMP.sub("<timestamp>", normalized)
    normalized = _DATE.sub("<date>", normalized)
    normalized = _NAMED_VOLATILE.sub("<volatile>", normalized)
    normalized = _DURATION.sub("<duration>", normalized)
    normalized = _SEPARATOR.sub(r"\1\1\1", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def is_error_line(line: str) -> bool:
    """Vrai pour les niveaux de log qui doivent attirer l'oeil en premier."""
    return _ERROR.search(strip_ansi(str(line or ""))) is not None


def compare_logs(texts, ignored_tokens=()) -> LogDifferences:
    """Aligne plusieurs logs et rend les lignes reellement differentes.

    Le premier log sert de reference. ``SequenceMatcher`` aligne les blocs
    communs : une ligne inseree ne decale donc pas artificiellement toutes les
    suivantes. Avec plus de deux lecteurs, l'union des comparaisons au premier
    met en evidence toute divergence observee.
    """
    lines = [str(text or "").replace("\r\n", "\n").replace("\r", "").splitlines()
             for text in texts]
    normalized = [
        [normalize_line(line, ignored_tokens) for line in log]
        for log in lines
    ]
    changed = [set() for _ in lines]

    if lines:
        for position in range(1, len(lines)):
            # Les logs APDU repetent enormement les memes separateurs et
            # libelles. Le filtre automatique de SequenceMatcher evite un
            # cout quadratique sur plusieurs milliers de lignes ; les etapes,
            # valeurs et erreurs distinctives restent, elles, alignees.
            matcher = SequenceMatcher(
                None, normalized[0], normalized[position], autojunk=True)
            for tag, a0, a1, b0, b1 in matcher.get_opcodes():
                if tag == "equal":
                    continue
                # SequenceMatcher peut englober une ligne pourtant identique
                # dans un `replace` lorsque le log repete souvent le meme
                # libelle (`Expected Status`, separateur...). Les annuler par
                # valeur dans CE bloc evite ces faux positifs sans masquer une
                # occurrence reellement ajoutee ou retiree.
                right_counts = Counter(normalized[position][b0:b1])
                for index in range(a0, a1):
                    value = normalized[0][index]
                    if right_counts[value]:
                        right_counts[value] -= 1
                    else:
                        changed[0].add(index)

                left_counts = Counter(normalized[0][a0:a1])
                for index in range(b0, b1):
                    value = normalized[position][index]
                    if left_counts[value]:
                        left_counts[value] -= 1
                    else:
                        changed[position].add(index)

    errors = [
        {index for index in indices if is_error_line(log[index])}
        for log, indices in zip(lines, changed)
    ]
    return LogDifferences(
        tuple(frozenset(indices) for indices in changed),
        tuple(frozenset(indices) for indices in errors),
    )
