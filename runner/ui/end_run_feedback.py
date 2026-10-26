"""Keep end-of-run feedback immediate and the Qt event loop responsive."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer

from runner.domain.duration import format_duration
from runner.domain import history
from runner.domain.history import RunEntry
from runner.domain.models import failure_summary
from runner.services.finalize_service import RunArchiveWorker
from runner.ui.widgets import ErrorDialog


def install() -> None:
    """Install responsive end-of-run handling before MainWindow is created."""
    from runner.ui.main_window import MainWindow

    original_started = MainWindow._on_run_started
    original_outcome = MainWindow._on_outcome
    original_progress = MainWindow._on_progress

    def remember_run_for_archive(self, request) -> None:
        # Keep exactly what was launched.  Reading the complete tree again at
        # the end was both wrong for partial selections and expensive on very
        # large suites.
        self._archive_run_nodeids = tuple(request.nodeids)
        self._archive_statuses_by_reader = {}
        self._archive_executions_by_reader = {}
        self._archive_run_name = getattr(self, "_pending_run_name", "")
        profile = self._running_execution_profile
        self._archive_profile_name = profile.name if profile else ""
        self._archive_run_kind = "profile" if profile else "classic"
        self._archive_save_logs = profile.reports.save_complete_logs if profile else True
        self._archive_failed_by_reader = {
            reader.index: set() for reader in request.readers
        }
        original_started(self, request)

    def remember_outcome_for_archive(self, outcome) -> None:
        original_outcome(self, outcome)
        self._archive_statuses_by_reader.setdefault(outcome.reader_index, {})[outcome.nodeid] = outcome.status.name
        self._archive_executions_by_reader.setdefault(outcome.reader_index, []).append((outcome.nodeid, outcome.status.name))
        failures = getattr(self, "_archive_failed_by_reader", None)
        if failures is None:
            return
        bucket = failures.setdefault(outcome.reader_index, set())
        if outcome.status.is_bad:
            bucket.add(outcome.nodeid)
        else:
            # The latest final verdict wins if pytest reports a node more than
            # once (setup/retry/plugin behaviour).
            bucket.discard(outcome.nodeid)

    def progress_with_finalizing_state(self, done: int, total: int) -> None:
        original_progress(self, done, total)
        if total > 0 and done >= total and self.service.busy:
            self._set_status_live("Finalizing run…")

    def _archive_entries(self, rapports: list) -> tuple[tuple[RunEntry, str], ...]:
        """Snapshot only cheap, already-cached data on the GUI thread."""
        if self._run_id is None or self.workspace is None:
            return ()

        played = tuple(getattr(self, "_archive_run_nodeids", ()))
        failed_by_reader = getattr(self, "_archive_failed_by_reader", {})
        entries: list[tuple[RunEntry, str]] = []
        now = time.time()
        for report in rapports:
            if report.cancelled:
                continue
            entry = history.RunEntry(
                id=self._run_id,
                timestamp=now,
                workspace=self.workspace.path,
                build_number=self._build_number,
                log_root=str(getattr(self, "_archive_log_root", None) or self.workspace.log_root),
                reader=report.reader.name,
                duration=report.duration,
                exit_code=report.exit_code,
                counts={status.name: count for status, count in report.counts.items()},
                nodeids=played,
                test_statuses=dict(getattr(self, '_archive_statuses_by_reader', {}).get(report.reader.index, {})),
                executions=tuple(getattr(self, '_archive_executions_by_reader', {}).get(report.reader.index, ())),
                failed_nodeids=tuple(sorted(
                    failed_by_reader.get(report.reader.index, ()))),
                junit_path=report.junit_path,
                run_kind=getattr(self, "_archive_run_kind", "unknown"),
                profile_name=getattr(self, "_archive_profile_name", ""),
                run_name=getattr(self, "_archive_run_name", ""),
                replay_profile=getattr(self, "_archive_replay_profile", None),
            )
            entries.append((entry, report.output if getattr(self, "_archive_save_logs", True) else ""))
        return tuple(entries)

    def finish_with_background_archive(self, rapports: list) -> None:
        self._show_failure_actions(rapports)
        self._elapsed.stop()
        self.progress.setVisible(False)
        self.remaining_pill.setVisible(False)

        cancelled = any(r.cancelled for r in rapports)
        counts = {}
        for rapport in rapports:
            for status, count in rapport.counts.items():
                counts[status] = counts.get(status, 0) + count
        failures = failure_summary(counts)
        # Erreurs qui ne sont le verdict d'aucun test : test supprime depuis la
        # collecte, interpreteur introuvable, conftest casse... pytest n'a
        # alors rien rapporte, et sans elles le run finissait sur "All tests
        # passed", sans un mot.
        global_errors = [
            f"{r.reader.name or 'Test interpreter'}\n{issue}"
            for r in rapports if not r.cancelled for issue in r.issues
        ]
        if cancelled:
            summary = "Run stopped"
        elif global_errors:
            summary = "Execution completed with errors"
        elif failures:
            summary = failures
        else:
            summary = "All tests passed"

        self._set_status_idle(f"{summary} · {format_duration(self._seconds, precision=0)}")
        self.elapsed_label.clear()
        if not cancelled:
            self._notifier_fin_de_run(summary)
        if global_errors:
            # Apres la fin de cette methode : la boite est modale, et l'archivage
            # et la remise a zero des actions ne doivent pas attendre sa fermeture.
            texte = "\n\n".join(dict.fromkeys(global_errors))
            QTimer.singleShot(0, lambda: ErrorDialog.show_diagnostics(
                self, "Execution error", texte, self.results.show_output))

        entries = _archive_entries(self, rapports)
        self._running_execution_profile = None
        self._run_id = None
        self._build_number = None
        self._archive_run_nodeids = ()
        self._archive_failed_by_reader = {}

        def finish_lightweight_bookkeeping() -> None:
            self.results.refresh_logs()
            self._update_actions()

        if not entries:
            QTimer.singleShot(0, finish_lightweight_bookkeeping)
            return

        # History can be read while the worker runs, but destructive history
        # actions must not race with its atomic JSON replacement.
        self.history_button.setEnabled(False)
        worker = RunArchiveWorker(
            self.history.racine, self.history.max_entrees, entries, self)
        self._archive_worker = worker

        def archive_done(ok: bool, detail: str) -> None:
            self.history.reload()
            self._archive_worker = None
            self.history_button.setEnabled(True)
            if not ok:
                # Archiving is non-fatal, but losing a run must no longer be
                # silent. Keep the main result visible and report the storage
                # problem in the status line.
                self.status_label.setText(
                    "Run finished, but history could not be fully saved"
                    + (f": {detail}" if detail else ""))
            finish_lightweight_bookkeeping()

        self._archive_done_slot = archive_done
        worker.done.connect(archive_done)
        worker.start()

    MainWindow._on_run_started = remember_run_for_archive
    MainWindow._on_outcome = remember_outcome_for_archive
    MainWindow._on_progress = progress_with_finalizing_state
    MainWindow._on_run_finished = finish_with_background_archive
