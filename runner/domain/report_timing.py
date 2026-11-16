"""Retrouver les mesures archivees sans confondre repetitions et relances."""
from collections import Counter
import math
import re

from runner.domain.parsing import NodeidResolver, parse_durations

_BATCH = re.compile(r'^--- (.+) - attempt ([1-9][0-9]*) ---$', re.MULTILINE)


def valid_duration(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _batch_end(label, sequence, start):
    offset = 0
    for end in range(start, len(sequence)):
        nodeid = sequence[end]
        if not label.startswith(nodeid, offset):
            break
        offset += len(nodeid)
        if offset == len(label):
            return end + 1
        if not label.startswith(', ', offset):
            break
        offset += 2
    return None


def archived_timings(text, sequence):
    """Cle (position, tentative), ou (position, None) si une seule mesure.

    Les en-tetes de lots proviennent du service : ils portent les nodeids
    originaux, contrairement au releve pytest qui peut changer de racine.
    """
    matches = list(_BATCH.finditer(text))
    timings = {}
    if not matches:
        frequencies = Counter(sequence)
        resolver = NodeidResolver(sequence)
        positions = {nodeid: i for i, nodeid in enumerate(sequence) if frequencies[nodeid] == 1}
        for nodeid, duration in parse_durations(text).items():
            nodeid = resolver.resolve(nodeid)
            if nodeid in positions and valid_duration(duration):
                timings[positions[nodeid], None] = duration
        return timings
    cursor = 0
    previous = None
    for index, match in enumerate(matches):
        label, attempt = match.group(1), int(match.group(2)) - 1
        start = cursor if attempt == 0 else previous[0] if previous else len(sequence)
        end = _batch_end(label, sequence, start)
        if end is None or (attempt and (not previous or previous != (start, end, label))):
            previous = None
            continue
        if attempt == 0:
            cursor = end
            previous = (start, end, label)
        section = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        batch = sequence[start:end]
        resolver = NodeidResolver(batch)
        positions = {nodeid: position for position, nodeid in enumerate(batch, start)}
        for nodeid, duration in parse_durations(section).items():
            nodeid = resolver.resolve(nodeid)
            if nodeid in positions and valid_duration(duration):
                timings[positions[nodeid], attempt] = duration
    return timings
