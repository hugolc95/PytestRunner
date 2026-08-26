"""Ce qu'une serie de tentatives sur un meme test a donne.

Aucun Qt ici : c'est la couche `services` (stress_service.py) qui rejoue les
tentatives sur un fil et transporte ces objets par signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from runner.domain.models import Status

MODE_UNTIL_FAIL = "until_fail"
MODE_N_TIMES = "n_times"


@dataclass
class StressAttempt:
    """Ce qu'une tentative a donne."""

    number: int
    status: Status
    output: str

    @property
    def ok(self) -> bool:
        return self.status is Status.PASSED


@dataclass
class StressSummary:
    """Bilan rendu une fois la serie terminee."""

    mode: str
    cap: int
    ran: int = 0
    passed: int = 0
    failed_attempts: list[StressAttempt] = field(default_factory=list)
    cancelled: bool = False
