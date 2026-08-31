"""Background bookkeeping for the end of a pytest run.

Large console outputs must never block the GUI, and a crash while persisting a
large output must not make the whole run disappear from history.  Metadata is
therefore committed first; console output is attached afterwards.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from runner.domain.history import History, RunEntry, _sain


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
        try:
            history = History(self._root, self._max_entries)

            # First commit the lightweight run metadata.  This is intentional:
            # on a very large suite the console output can be tens of MB.  If
            # Windows/AV/disk kills the process while that file is being
            # written, the next application launch still knows what ran and
            # what passed/failed.
            saved: list[tuple[RunEntry, str]] = []
            for entry, output in self._entries:
                saved_entry = history.add(entry, "")
                saved.append((saved_entry, output))

            # Then persist the potentially large outputs.  Update the in-memory
            # entries in one pass and rewrite the history JSON once at the end.
            changed = False
            for entry, output in saved:
                if not output:
                    continue
                name = f"{entry.id}{'_' + _sain(entry.reader) if entry.reader else ''}.log"
                path = history.racine / name
                try:
                    path.write_text(output, encoding="utf-8")
                except OSError:
                    continue

                replacement = replace(entry, output_file=str(path))
                for index, current in enumerate(history._entrees):
                    if current.id == entry.id and current.reader == entry.reader:
                        history._entrees[index] = replacement
                        changed = True
                        break

            if changed:
                history._enregistrer()
        except Exception as exc:  # history is optional; never crash the app
            self._result = (False, str(exc))
            return
        self._result = (True, "")

    def _emit_done_after_finished(self) -> None:
        """Publish completion only after QThread itself is fully stopped."""
        self.done.emit(*self._result)
