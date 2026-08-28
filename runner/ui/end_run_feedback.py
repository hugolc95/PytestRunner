"""Keep end-of-run feedback immediate and the Qt event loop responsive."""

from __future__ import annotations

import time

from PyQt5.QtCore import QTimer

from runner.domain import history
from runner.domain.history import RunEntry
from runner.services.finalize_service import RunArchiveWorker


def install() -> None:
    """Install responsive end-of-run handling before MainWindow is created."""
    from runner.ui.main_window import MainWindow

    original_progress = MainWindow._on_progress

    def progress_with_finalizing_state(self, done: int, total: int) -> None:
        original_progress(self, done, total)
        if total > 0 and done >= total and self.service.busy:
            self._set_status_live("Finalizing run…")

    def _archive_entries(self, rapports: list) -> tuple[tuple[RunEntry, str], ...]:
        """Snapshot everything the background writer needs while still on GUI."""
        if self._run_id is None or self.workspace is None:
            return ()

        played = tuple(self.model.nodeids())
        entries: list[tuple[RunEntry, str]] = []
        for report in rapports:
            if report.cancelled:
                continue
            entry = history.RunEntry(
                id=self._run_id,
                timestamp=time.time(),
                workspace=self.workspace.path,
                build_number=self._build_number,
                log_root=str(self.workspace.log_root),
                reader=report.reader.name,
                duration=report.duration,
                exit_code=report.exit_code,
                counts={status.name: count for status, count in report.counts.items()},
                nodeids=played,
                failed_nodeids=tuple(
                    self.model.failed_nodeids_for(report.reader.index)),
                junit_path=report.junit_path,
            )
            entries.append((entry, report.output))
        return tuple(entries)

    def finish_with_background_archive(self, rapports: list) -> None:
        self._elapsed.stop()
        self.progress.setVisible(False)
        self.remaining_pill.setVisible(False)

        cancelled = any(r.cancelled for r in rapports)
        failures = sum(r.failed for r in rapports)
        if cancelled:
            summary = "Run stopped"
        elif failures:
            summary = f"{failures} failed"
        else:
            summary = "All tests passed"

        self._set_status_idle(f"{summary} · {self._seconds}s")
        self.elapsed_label.clear()
        if not cancelled:
            self._notifier_fin_de_run(summary)

        entries = _archive_entries(self, rapports)
        self._run_id = None
        self._build_number = None

        def finish_lightweight_bookkeeping() -> None:
            # These operations are deliberately kept on the GUI thread because
            # they touch widgets. They are small; the heavy history/output disk
            # writes happen in RunArchiveWorker instead.
            self.results.refresh_logs()
            if self._last_allure_dir:
                self._lancer_generation_allure(ouvrir_apres=False)
            self._update_actions()

        if not entries:
            QTimer.singleShot(0, finish_lightweight_bookkeeping)
            return

        # History can be opened while the archive is running, but destructive
        # history actions must not race with the atomic JSON replacement.
        self.history_button.setEnabled(False)
        worker = RunArchiveWorker(
            self.history.racine, self.history.max_entrees, entries, self)
        self._archive_worker = worker

        def archive_done(_ok: bool, _detail: str) -> None:
            # The worker's done signal is emitted only after QThread.finished,
            # so dropping this reference cannot destroy a running QThread.
            self.history.reload()
            self._archive_worker = None
            self.history_button.setEnabled(True)
            finish_lightweight_bookkeeping()

        self._archive_done_slot = archive_done
        worker.done.connect(archive_done)
        worker.start()

    MainWindow._on_progress = progress_with_finalizing_state
    MainWindow._on_run_finished = finish_with_background_archive
