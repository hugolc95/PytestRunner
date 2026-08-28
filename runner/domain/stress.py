"""Ce qu'une serie de tentatives sur un meme test a donne.

Aucun Qt ici : c'est la couche `services` (stress_service.py) qui rejoue les
tentatives sur un fil et transporte ces objets par signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from runner.domain.models import Reader, ReaderReport, Status

MODE_UNTIL_FAIL = "until_fail"
MODE_N_TIMES = "n_times"


@dataclass
class StressReaderResult:
    """Ce qu'un seul lecteur a donne pour une tentative.

    Porte le `ReaderReport` complet (duree, exit code, JUnit...) pour que
    chaque tentative puisse s'archiver dans l'historique exactement comme un
    run normal -- un lecteur, une entree."""

    reader: Reader
    report: ReaderReport
    status: Status

    @property
    def ok(self) -> bool:
        return self.status is Status.PASSED


@dataclass
class StressAttempt:
    """Ce qu'une tentative a donne, un `StressReaderResult` par lecteur
    sollicite. En echec des qu'UN lecteur l'est -- un flaky qui ne se
    manifeste que sur un materiel precis doit quand meme arreter "Run until
    it fails" et compter comme un echec pour "Run N times"."""

    number: int
    status: Status
    reports: tuple[StressReaderResult, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is Status.PASSED

    @property
    def output(self) -> str:
        return "\n".join(r.report.output for r in self.reports)


@dataclass
class StressSummary:
    """Bilan rendu une fois la serie terminee."""

    mode: str
    cap: int
    ran: int = 0
    passed: int = 0
    failed_attempts: list[StressAttempt] = field(default_factory=list)
    cancelled: bool = False
