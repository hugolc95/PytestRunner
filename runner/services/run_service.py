"""Pont entre le domaine et Qt : threads, signaux, annulation.

C'est la SEULE couche qui connaisse les deux mondes. Les widgets ne parlent
qu'a ce service ; le domaine ignore que Qt existe. Rien de bloquant ne doit
donc jamais remonter jusqu'a un slot.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from runner.domain import execution
from runner.domain.models import Outcome, Reader, ReaderReport, RunRequest


class CollectWorker(QThread):
    """Collecte les tests d'un workspace, hors du fil de l'interface.

    Une collecte lance un vrai processus pytest : selon la suite, plusieurs
    secondes. La faire dans le fil UI gele la fenetre.
    """

    # `object` et non `list` : la collecte rapporte aussi les markers de chaque
    # test, releves pendant le meme passage de pytest.
    collected = pyqtSignal(object)
    failed = pyqtSignal(str)

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
    """Un fil par lecteur : les lecteurs tournent vraiment en meme temps."""

    line = pyqtSignal(int, str)
    outcome = pyqtSignal(object)
    done = pyqtSignal(object)

    def __init__(self, request: RunRequest, reader: Reader, env: dict, parent=None):
        super().__init__(parent)
        self._run = execution.ReaderRun(request, reader, env)
        self._reader = reader

    def cancel(self) -> None:
        self._run.cancel()

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        rapport = self._run.run(
            on_line=lambda texte: self.line.emit(self._reader.index, texte),
            on_outcome=self.outcome.emit,
        )
        self.done.emit(rapport)


class RunService(QObject):
    """Orchestre un run multi-lecteur et rend compte de son avancement.

    Un seul run a la fois : `start()` sur un service deja occupe est ignore,
    ce qui evite deux suites qui se disputent le meme materiel.
    """

    started = pyqtSignal(object)          # RunRequest
    line = pyqtSignal(int, str)           # index du lecteur, ligne brute
    outcome = pyqtSignal(object)          # Outcome
    progress = pyqtSignal(int, int)       # termines, total
    reader_finished = pyqtSignal(object)  # ReaderReport
    finished = pyqtSignal(list)           # list[ReaderReport]

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

    @property
    def busy(self) -> bool:
        # La file compte autant que les fils en cours : en mode sequentiel, le
        # lecteur suivant est demarre depuis un slot, et entre la fin d'un fil
        # et ce slot il n'y a rien qui tourne. Sans la file, `busy` retomberait
        # a faux au milieu du run -- le bouton Run redeviendrait cliquable et
        # une deuxieme campagne partirait par-dessus la premiere.
        return bool(self._en_attente) or any(w.isRunning() for w in self._workers)

    def start(self, request: RunRequest, env: dict) -> bool:
        """Lance les lecteurs. Retourne False si un run tourne deja.

        Tous en meme temps par defaut, un fil chacun. En mode sequentiel, le
        suivant ne part qu'a la fin du precedent.
        """
        if self.busy:
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
            worker.line.connect(self.line)
            worker.outcome.connect(self._on_outcome)
            worker.done.connect(self._on_reader_done)
            self._workers.append(worker)

        self._en_attente = list(self._workers)
        self._lances = 0
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

    def _demarrer_suivant(self) -> None:
        self._lances += 1
        self._en_attente.pop(0).start()

    def cancel(self) -> None:
        """Demande l'arret. Les fils se terminent d'eux-memes ensuite."""
        # La file d'abord : sinon l'arret du lecteur en cours declencherait le
        # depart du suivant, et Stop ne s'arreterait jamais.
        self._en_attente = []
        for worker in self._workers:
            worker.cancel()

    def wait(self, timeout_ms: int = 5000) -> None:
        """Attend la fin des fils. Utile a la fermeture et dans les tests."""
        for worker in self._workers:
            worker.wait(timeout_ms)

    def _on_outcome(self, outcome: Outcome) -> None:
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
            self.finished.emit(list(self._reports))
