"""Pont entre le domaine et Qt : threads, signaux, annulation.

C'est la SEULE couche qui connaisse les deux mondes. Les widgets ne parlent
qu'a ce service ; le domaine ignore que Qt existe. Rien de bloquant ne doit
donc jamais remonter jusqu'a un slot.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, QThread, Signal

from runner.domain import execution
from runner.domain.models import Outcome, Reader, ReaderReport, RunRequest, Status


class CollectWorker(QThread):
    """Collecte les tests d'un workspace, hors du fil de l'interface.

    Une collecte lance un vrai processus pytest : selon la suite, plusieurs
    secondes. La faire dans le fil UI gele la fenetre.
    """

    # `object` et non `list` : la collecte rapporte aussi les markers de chaque
    # test, releves pendant le meme passage de pytest.
    collected = Signal(object)
    failed = Signal(str)

    def __init__(self, workspace: str, interpreter: str, env: dict, parent=None):
        super().__init__(parent)
        self._workspace = workspace
        self._interpreter = interpreter
        self._env = env

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        try:
            collection = execution.collect(self._workspace, self._interpreter,
                                           self._env)
        except RuntimeError as exc:
            self.failed.emit(str(exc))
            return
        self.collected.emit(collection)


class _ReaderWorker(QThread):
    """Un fil par lecteur : les lecteurs tournent vraiment en meme temps.

    Le rapport public ``done`` n'est emis qu'apres ``QThread.finished``. Emettre
    ``done`` depuis ``run()`` ouvrait une petite fenetre de course : l'UI pouvait
    commencer sa finalisation pendant que Qt considerait encore le QThread comme
    actif. Un clic utilisateur au meme moment pouvait alors declencher des
    changements d'etat pendant cette phase et provoquer une fermeture native
    sous Windows.
    """

    line = Signal(int, str)
    outcome = Signal(object)
    done = Signal(object)

    def __init__(self, request: RunRequest, reader: Reader, env: dict, parent=None):
        super().__init__(parent)
        self._run = execution.ReaderRun(request, reader, env)
        self._reader = reader
        self._report: ReaderReport | None = None
        self.finished.connect(self._emit_done_after_finished)

    def cancel(self) -> None:
        self._run.cancel()

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        self._report = self._run.run(
            on_line=lambda texte: self.line.emit(self._reader.index, texte),
            on_outcome=self.outcome.emit,
        )

    def _emit_done_after_finished(self) -> None:
        """Publie le rapport seulement quand le thread Qt est reellement fini."""
        if self._report is not None:
            self.done.emit(self._report)


class RunService(QObject):
    """Orchestre un run multi-lecteur et rend compte de son avancement.

    Un seul run a la fois : `start()` sur un service deja occupe est ignore,
    ce qui evite deux suites qui se disputent le meme materiel.
    """

    started = Signal(object)          # RunRequest
    line = Signal(int, str)           # index du lecteur, ligne brute
    outcome = Signal(object)          # Outcome
    progress = Signal(int, int)       # termines, total
    profile_detail = Signal(int, str)
    profile_execution = Signal(int, int, int, str, object)  # position, retry, reader, nodeid, status
    profile_batch_report = Signal(int, int, int, object)  # first position, count, retry, report
    profile_output = Signal(int, int, int, int, str)
    reader_finished = Signal(object)  # ReaderReport
    finished = Signal(list)           # list[ReaderReport]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers: list[_ReaderWorker] = []
        self._reports: list[ReaderReport] = []
        self._done = 0
        self._total = 0
        self._seen_outcomes: set[tuple[int, str]] = set()
        self._request: RunRequest | None = None
        self._en_attente: list[_ReaderWorker] = []
        self._lances = 0
        self._profile_active = False
        self._profile_cancelled = False
        self._profile_queue: list[str] = []
        self._current_batch: list[str] = []
        self._profile_request: RunRequest | None = None
        self._profile_env: dict = {}
        self._profile_attempt = 0
        self._profile_reruns = 0
        self._profile_stop_after_failure = False
        self._profile_completed = 0
        self._profile_total = 0
        self._profile_reports: dict[int, ReaderReport] = {}

    @property
    def busy(self) -> bool:
        # La file compte autant que les fils en cours : en mode sequentiel, le
        # lecteur suivant est demarre depuis un slot, et entre la fin d'un fil
        # et ce slot il n'y a rien qui tourne. Sans la file, `busy` retomberait
        # a faux au milieu du run -- le bouton Run redeviendrait cliquable et
        # une deuxieme campagne partirait par-dessus la premiere.
        return (self._profile_active or bool(self._en_attente)
                or any(w.isRunning() for w in self._workers))

    def start(self, request: RunRequest, env: dict) -> bool:
        """Lance les lecteurs. Retourne False si un run tourne deja.

        Tous en meme temps par defaut, un fil chacun. En mode sequentiel, le
        suivant ne part qu'a la fin du precedent.
        """
        if self.busy:
            return False

        return self._start_request(request, env, emit_started=True)

    def _start_request(self, request: RunRequest, env: dict,
                       emit_started: bool) -> bool:
        """Start one physical pytest invocation for each selected reader."""
        if any(w.isRunning() for w in self._workers) or self._en_attente:
            return False

        self._workers = []
        self._reports = []
        self._done = 0
        self._seen_outcomes = set()
        self._total = request.total_tests
        self._request = request

        # Sans lecteur declare, un run anonyme : le reste du code n'a pas a
        # distinguer les deux cas.
        lecteurs = request.readers or (Reader("", 0),)

        for lecteur in lecteurs:
            worker = _ReaderWorker(request, lecteur, env, parent=self)
            worker.line.connect(self._on_live_line)
            worker.outcome.connect(self._on_outcome)
            worker.done.connect(self._on_reader_done)
            self._workers.append(worker)

        self._en_attente = list(self._workers)
        self._lances = 0
        if emit_started:
            self.started.emit(request)

        # La file est videe AVANT de demarrer quoi que ce soit : un fil peut
        # finir pendant la boucle, et trouver alors une file deja a jour.
        if request.sequential:
            self._demarrer_suivant()
        else:
            partants, self._en_attente = self._en_attente, []
            self._lances = len(partants)
            for worker in partants:
                worker.start()
        return True

    def start_profile(self, request: RunRequest, env: dict, sequence: list[str],
                      repetitions: int = 1, rerun_failures: int = 0,
                      stop_after_failure: bool = False) -> bool:
        """Run an ordered sequence, preserving duplicates and retries.

        Each sequence occurrence is a separate pytest invocation. This is the
        only reliable way to keep two identical nodeids as two distinct steps.
        The public signals still describe one logical run.
        """
        if self.busy or not sequence:
            return False
        expanded = list(sequence) * max(1, int(repetitions))
        self._profile_sequence_length = len(sequence)
        self._profile_repetitions = max(1, int(repetitions))
        self._profile_expanded_length = len(expanded)
        logical = replace(request, nodeids=tuple(expanded))
        self._profile_active = True
        self._profile_cancelled = False
        self._profile_queue = expanded
        self._profile_request = request
        self._profile_env = dict(env)
        self._profile_attempt = 0
        self._profile_reruns = max(0, int(rerun_failures))
        self._profile_stop_after_failure = bool(stop_after_failure)
        self._profile_completed = 0
        self._profile_total = logical.total_tests
        readers = request.readers or (Reader("", 0),)
        self._profile_reports = {
            reader.index: ReaderReport(reader=reader, counts={})
            for reader in readers
        }
        self.started.emit(logical)
        self._start_profile_step()
        return True

    def _next_batch(self) -> list[str]:
        """Which upcoming queue entries run together as ONE pytest invocation.

        A retry needs to react to its own step's verdict, and stopping after a
        failure must not let anything after it start -- both keep the strict
        one-nodeid-per-invocation behaviour. Without either, grouping several
        upcoming steps into a single pytest call saves pytest's own startup
        and collection cost, which is otherwise paid again for every single
        step: a profile is a sequence, so that cost is normally the dominant
        one, not the tests themselves.

        pytest collapses a nodeid repeated on its command line into a single
        run (verified: `pytest a::t a::t` collects and runs `t` once) -- so a
        batch can never contain the same nodeid twice, which is also exactly
        what keeps two occurrences of the same step in the sequence as two
        genuinely distinct executions.
        """
        if self._profile_reruns or self._profile_stop_after_failure:
            return self._profile_queue[:1]
        vus: set[str] = set()
        batch: list[str] = []
        for nodeid in self._profile_queue:
            if nodeid in vus:
                break
            vus.add(nodeid)
            batch.append(nodeid)
        return batch

    def _start_profile_step(self) -> None:
        if not self._profile_queue or self._profile_cancelled:
            self._finish_profile()
            return
        self._current_batch = self._next_batch()
        self._current_batch_positions = {nodeid: i for i, nodeid in enumerate(self._current_batch)}
        self._emit_profile_detail(-1, self._current_batch[0], preparing=True)
        request = replace(
            self._profile_request,
            nodeids=tuple(self._current_batch),
            # Per-step JUnit files would overwrite one another. The aggregate
            # history remains available through ReaderReport.
            junit_dir="",
        )
        self._start_request(request, self._profile_env, emit_started=False)

    def _on_live_line(self, reader_index: int, text: str) -> None:
        prefix = "PYTESTRUNNER_START\t"
        if self._profile_active and text.strip().startswith(prefix):
            nodeid = text.strip()[len(prefix):]
            self._emit_profile_detail(reader_index, nodeid)
            self._emit_profile_execution(reader_index, nodeid, Status.RUNNING)
        elif self._profile_active:
            self.profile_output.emit(self._profile_expanded_length - len(self._profile_queue),
                                     len(self._current_batch), self._profile_attempt, reader_index, text)
        self.line.emit(reader_index, text)

    def _emit_profile_detail(self, reader_index, nodeid, preparing=False):
        positions = getattr(self, '_current_batch_positions', None)
        if positions is None:
            positions = {value: index for index, value in enumerate(self._current_batch)}
        offset = positions.get(nodeid)
        if offset is None:
            return
        position = self._profile_expanded_length - len(self._profile_queue) + offset
        size = self._profile_sequence_length
        retry = f" · Retry {self._profile_attempt}/{self._profile_reruns}" if self._profile_attempt else ""
        self.profile_detail.emit(reader_index,
            f"Repetition {position // size + 1}/{self._profile_repetitions} · "
            f"Step {position % size + 1}/{size}{retry} · "
            f"{'Preparing: ' if preparing else ''}{nodeid}")

    def _emit_profile_execution(self, reader, nodeid, status):
        offset = self._current_batch_positions.get(nodeid)
        if offset is not None:
            position = self._profile_expanded_length - len(self._profile_queue) + offset
            self.profile_execution.emit(position, self._profile_attempt, reader, nodeid, status)

    def _finish_profile_step(self) -> None:
        failed = any(not report.ok for report in self._reports)
        label = ", ".join(self._current_batch)
        for report in self._reports:
            self.profile_batch_report.emit(self._profile_expanded_length - len(self._profile_queue),
                                           len(self._current_batch), self._profile_attempt, report)
            aggregate = self._profile_reports[report.reader.index]
            attempt_label = self._profile_attempt + 1
            aggregate.output += (
                f"\n--- {label} - attempt {attempt_label} ---\n"
                + report.output)
            aggregate.duration += report.duration
            aggregate.cancelled = aggregate.cancelled or report.cancelled

        if (failed and not self._profile_cancelled
                and self._profile_attempt < self._profile_reruns):
            self._profile_attempt += 1
            self._start_profile_step()
            return

        for report in self._reports:
            aggregate = self._profile_reports[report.reader.index]
            for status, count in report.counts.items():
                aggregate.counts[status] = aggregate.counts.get(status, 0) + count
            aggregate.exit_code = max(aggregate.exit_code, report.exit_code)
            aggregate.durations.update(report.durations)

        self._profile_completed += len(self._seen_outcomes)
        self.progress.emit(self._profile_completed, self._profile_total)
        del self._profile_queue[:len(self._current_batch)]
        self._profile_attempt = 0
        if failed and self._profile_stop_after_failure:
            self._profile_queue.clear()
        self._start_profile_step()

    def _finish_profile(self) -> None:
        reports = sorted(self._profile_reports.values(), key=lambda r: r.reader.index)
        self._profile_active = False
        self._profile_queue = []
        for report in reports:
            self.reader_finished.emit(report)
        self.finished.emit(reports)

    def _demarrer_suivant(self) -> None:
        self._lances += 1
        self._en_attente.pop(0).start()

    def cancel(self) -> None:
        """Demande l'arret. Les fils se terminent d'eux-memes ensuite."""
        # La file d'abord : sinon l'arret du lecteur en cours declencherait le
        # depart du suivant, et Stop ne s'arreterait jamais.
        self._en_attente = []
        if self._profile_active:
            self._profile_cancelled = True
        for worker in self._workers:
            worker.cancel()

    def wait(self, timeout_ms: int = 5000) -> None:
        """Attend la fin des fils. Utile a la fermeture et dans les tests."""
        for worker in self._workers:
            worker.wait(timeout_ms)

    def _on_outcome(self, outcome: Outcome) -> None:
        if self._profile_active:
            key = (outcome.reader_index, outcome.nodeid)
            self._emit_profile_execution(outcome.reader_index, outcome.nodeid, outcome.status)
            self._seen_outcomes.add(key)
            self.outcome.emit(outcome)
            self.progress.emit(
                self._profile_completed + len(self._seen_outcomes), self._profile_total)
            return
        cle = (outcome.reader_index, outcome.nodeid)
        if cle not in self._seen_outcomes:
            self._seen_outcomes.add(cle)
            self._done += 1
        self.outcome.emit(outcome)
        self.progress.emit(self._done, self._total)

    def _on_reader_done(self, rapport: ReaderReport) -> None:
        self._reports.append(rapport)
        self.reader_finished.emit(rapport)

        # Mode sequentiel : au suivant. Un run annule a vide la file, donc
        # rien ne repart derriere un Stop.
        if self._en_attente:
            self._demarrer_suivant()
            return

        # On compte les lecteurs DEMARRES, pas les lecteurs prevus : un Stop en
        # sequentiel laisse la file pleine de lecteurs qui ne partiront jamais
        # et ne rendront donc aucun rapport. Compares au nombre prevu, ils
        # empecheraient `finished` d'etre emis -- l'interface resterait en
        # « run en cours » jusqu'a la fermeture.
        if len(self._reports) == self._lances:
            # Les rapports arrivent dans l'ordre ou les lecteurs finissent ;
            # les remettre dans l'ordre des colonnes evite un bilan qui change
            # de disposition d'un run a l'autre.
            self._reports.sort(key=lambda r: r.reader.index)
            if self._profile_active:
                self._finish_profile_step()
            else:
                self.finished.emit(list(self._reports))
