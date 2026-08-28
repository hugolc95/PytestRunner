"""Background bookkeeping for the end of a pytest run.

Writing the console output and the complete history JSON can take long enough on
Windows to block the Qt event loop.  The visible run result must stay responsive
while that disk work happens, so it lives in a dedicated QThread.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from runner.domain.history import History, RunEntry


class RunArchiveWorker(QThread):
    """Persist completed run entries without blocking the GUI thread."""

    done = pyqtSignal(bool, str)

    def __init__(self, root: Path, max_entries: int,
                 entries: tuple[tuple[RunEntry, str], ...], parent=None):
        super().__init__(parent)
        self._root = Path(root)
        self._max_entries = int(max_entries)
        self._entries = entries
        self._result: tuple[bool, str] = (False, "Run archiving did not run")
        self.finished.connect(self._emit_done_after_finished)

    def run(self) -> None:  # pragma: no cover - executes in a Qt worker thread
        try:
            history = History(self._root, self._max_entries)
            for entry, output in self._entries:
                history.add(entry, output)
        except Exception as exc:  # history is optional; never crash the app
            self._result = (False, str(exc))
            return
        self._result = (True, "")

    def _emit_done_after_finished(self) -> None:
        """Publish completion only after QThread itself is fully stopped."""
        self.done.emit(*self._result)
