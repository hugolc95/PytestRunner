"""Bilan des repetitions, distinct du dernier run complet."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from runner.domain.models import Status
from runner.domain.stress import MODE_UNTIL_FAIL


class StressProgress(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('Surface')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(3)
        self.label = QLabel()
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setToolTip('Repetitions only. The Results cards keep the previous run summary.')
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(3)
        layout.addWidget(self.bar)
        self.hide()

    def begin(self, nodeid, cap, readers, mode, not_collected=0):
        self._name = nodeid.rsplit('::', 1)[-1]
        self._cap, self._readers, self._mode = cap, readers, mode
        # Le bandeau remplace la ligne d'etat pendant les repetitions : sans
        # cette mention, une collecte incomplete disparaissait de l'ecran
        # alors que History, lui, la retient.
        self._not_collected = not_collected
        self._ran, self._counts, self._current, self._state = 0, {}, '', 'Running'
        self.bar.setRange(0, cap * readers)
        self.bar.show()
        self.update_counts(0, {})
        self.show()

    def set_current(self, number, reader):
        self._current = f'Repetition {number}/{self._cap} · {reader}'
        self.label.setToolTip(self._current + '\nResults cards: previous run summary')

    def update_counts(self, ran, counts):
        self._ran, self._counts = ran, dict(counts)
        self.bar.setValue(sum(counts.values()))
        self.label.setText(self.summary())

    def summary(self):
        done = sum(self._counts.values())
        parts = [f'Repeat · {self._name}', self._state,
                 f'{self._ran}/{self._cap} repetitions', f'{self._readers} reader(s)',
                 f'{done}/{self._cap * self._readers} executions']
        for status in (Status.PASSED, Status.FAILED, Status.ERROR, Status.SKIPPED):
            if self._counts.get(status):
                parts.append(f'{self._counts[status]} {status.label.lower()}')
        missing = getattr(self, '_not_collected', 0)
        if missing:
            parts.append(f"Collection incomplete · {missing} file{'s' if missing != 1 else ''} not collected")
        return ' · '.join(parts)

    def finish(self, result):
        self._state = ('Stopped' if result.cancelled else
                       'Failed' if result.mode == MODE_UNTIL_FAIL and result.failed_attempts else
                       'Never failed' if result.mode == MODE_UNTIL_FAIL and result.ran == result.cap else
                       'Complete' if result.ran == result.cap else 'Ended early')
        self._ran = result.ran
        self.label.setText(self.summary())
        self.label.setToolTip('Results cards: previous run summary')
        self.bar.hide()
