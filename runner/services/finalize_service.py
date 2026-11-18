"""Background bookkeeping for the end of a pytest run.

Large console outputs must never block the GUI, and a crash while persisting a
large output must not make the whole run disappear from history.  Metadata is
therefore committed first; console output is attached afterwards.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QThread, Signal

from runner.domain.history import History, RunEntry, _sain

_ARCHIVE_LOCK = Lock()


class RunArchiveWorker(QThread):
    """Persist completed run entries without blocking the GUI thread."""

    done = Signal(bool, str)

    def __init__(self, root: Path, max_entries: int,
                 entries: tuple[tuple[RunEntry, str], ...], parent=None):
        super().__init__(parent)
        self._root = Path(root)
        self._max_entries = int(max_entries)
        self._entries = entries
        self._result: tuple[bool, str] = (False, "Run archiving did not run")
        self.finished.connect(self._emit_done_after_finished)

    def run(self) -> None:  # pragma: no cover - executes in a Qt worker thread
        # Plusieurs runs peuvent finir pendant une sauvegarde lente. Un seul
        # archivage travaille a la fois, sans occuper le fil de l'interface.
        with _ARCHIVE_LOCK:
            self._persist()

    def _persist(self) -> None:
        try:
            history = History(self._root, self._max_entries)

            # First commit the lightweight run metadata.  This is intentional:
            # on a very large suite the console output can be tens of MB.  If
            # Windows/AV/disk kills the process while that file is being
            # written, the next application launch still knows what ran and
            # what passed/failed.
            saved = []
            for entry, output in self._entries:
                saved_entry = history.add(replace(entry, analysis_data=None), "")
                saved.append((saved_entry, output, entry.analysis_data))

            # Les fichiers lourds sont captures avant de fusionner leurs
            # chemins avec l'index courant, qui a pu etre edite entre-temps.
            completed = []
            indexes = {}
            for entry, output, analysis in saved:
                if analysis is not None:
                    from runner.domain.report_capture import persist_analysis
                    from runner.domain.log_index import RunLogIndex
                    key = entry.log_root, entry.build_number
                    if entry.log_root and entry.build_number is not None and key not in indexes:
                        indexes[key] = RunLogIndex(Path(entry.log_root), entry.build_number)
                    entry = persist_analysis(replace(entry, analysis_data=analysis), history.racine,
                                             log_index=indexes.get(key))
                if output:
                    name = f"{entry.id}{'_' + _sain(entry.reader) if entry.reader else ''}.log"
                    path = history.racine / name
                    try:
                        path.write_text(output, encoding="utf-8")
                        entry = replace(entry, output_file=str(path))
                    except OSError:
                        pass
                completed.append(entry)

            if completed:
                history.attach_archive(completed)
        except Exception as exc:  # history is optional; never crash the app
            self._result = (False, str(exc))
            return
        finally:
            self._entries = ()
        self._result = (True, "")

    def _emit_done_after_finished(self) -> None:
        """Publish completion only after QThread itself is fully stopped."""
        self.done.emit(*self._result)
