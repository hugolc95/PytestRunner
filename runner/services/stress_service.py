"""Rejoue UN test plusieurs fois, hors du fil de l'interface.

Deux modes, deux questions differentes : "jusqu'a ce qu'il casse" s'arrete au
premier echec, pour debusquer un flaky sans attendre un cap qu'on a mis la
comme filet de securite. "N fois pile" va jusqu'au bout quoi qu'il arrive,
pour mesurer un taux de reussite -- s'arreter au premier echec fausserait ce
taux.

Un `ReaderRun` par tentative ET par lecteur, tous dans CE thread : les
tentatives sont sequentielles par nature, pas besoin d'un fil chacune -- et un
flaky qui ne se manifeste que sur un lecteur precis doit quand meme etre vu.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from runner.domain.execution import ReaderRun
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.stress import (
    MODE_UNTIL_FAIL,
    StressAttempt,
    StressReaderResult,
    StressSummary,
)


class StressRunWorker(QThread):
    """Relance un seul nodeid jusqu'a l'echec, ou exactement `cap` fois."""

    attempt_done = Signal(object)      # StressAttempt
    finished_stress = Signal(object)   # StressSummary

    def __init__(self, request: RunRequest, readers: tuple[Reader, ...], env: dict,
                mode: str, cap: int, parent=None):
        super().__init__(parent)
        self._request = request
        self._readers = tuple(readers) or (Reader("", 0),)
        self._env = env
        self._mode = mode
        self._cap = cap
        self._cancelled = False
        self._current_run: ReaderRun | None = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._current_run is not None:
            self._current_run.cancel()

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        passed = 0
        failed_attempts: list[StressAttempt] = []
        ran = 0

        for numero in range(1, self._cap + 1):
            if self._cancelled:
                break

            resultats: list[StressReaderResult] = []
            for lecteur in self._readers:
                if self._cancelled:
                    break

                self._current_run = ReaderRun(self._request, lecteur, self._env)
                statut_vu = {}

                def _sur_verdict(outcome, boite=statut_vu):
                    boite["status"] = outcome.status

                rapport = self._current_run.run(on_line=lambda ligne: None,
                                                on_outcome=_sur_verdict)
                # Rien capte (processus qui n'a pas demarre, crash avant le
                # premier verdict) : on ne peut pas dire que le test est
                # passe, mieux vaut le compter comme un echec que de fermer
                # les yeux dessus.
                statut = statut_vu.get(
                    "status", Status.PASSED if not rapport.failed else Status.FAILED)
                resultats.append(StressReaderResult(lecteur, rapport, statut))

            if not resultats:
                break
            ran = numero
            ok = all(r.ok for r in resultats)
            statut_global = Status.PASSED if ok else Status.FAILED
            tentative = StressAttempt(numero, statut_global, tuple(resultats))

            if ok:
                passed += 1
            else:
                failed_attempts.append(tentative)
            self.attempt_done.emit(tentative)

            if self._mode == MODE_UNTIL_FAIL and not ok:
                break
            if self._cancelled:
                break

        resume = StressSummary(mode=self._mode, cap=self._cap, ran=ran,
                               passed=passed, failed_attempts=failed_attempts,
                               cancelled=self._cancelled)
        self.finished_stress.emit(resume)
