"""Make the end of a run feel immediate without lying about pytest state.

The final test verdict can arrive slightly before the pytest process has fully
exited (teardown, durations/JUnit flush, process shutdown). Once the process is
done, the UI also archives the run and refreshes logs. Those bookkeeping steps
must not keep the visible status on "Running" or delay the desktop notification.
"""

from __future__ import annotations

from PyQt5.QtCore import QTimer


def install() -> None:
    """Install faster end-of-run feedback before MainWindow is created."""
    from runner.ui.main_window import MainWindow

    original_progress = MainWindow._on_progress

    def progress_with_finalizing_state(self, done: int, total: int) -> None:
        original_progress(self, done, total)
        # All expected verdicts are in, but pytest may still be flushing its
        # own end-of-session work. "Running" is misleading at that point.
        if total > 0 and done >= total and self.service.busy:
            self._set_status_live("Finalizing run…")

    def finish_with_immediate_feedback(self, rapports: list) -> None:
        """Show completion first, do bookkeeping on the next event-loop turn.

        The previous implementation archived synchronously before changing the
        status and before sending the notification. On larger histories/logs,
        the user therefore saw "Running" after the last test had finished.
        """
        self._elapsed.stop()
        self.progress.setVisible(False)
        self.remaining_pill.setVisible(False)

        annule = any(r.cancelled for r in rapports)
        echecs = sum(r.failed for r in rapports)
        if annule:
            resume = "Run stopped"
        elif echecs:
            resume = f"{echecs} failed"
        else:
            resume = "All tests passed"

        # Visible completion and desktop feedback happen immediately.
        self._set_status_idle(f"{resume} · {self._seconds}s")
        self.elapsed_label.clear()
        if not annule:
            self._notifier_fin_de_run(resume)

        # Keep actions disabled until bookkeeping is complete, but give Qt one
        # event-loop turn first so the final status/notification can render.
        def finalize() -> None:
            self._archiver(rapports)
            self.results.refresh_logs()
            if self._last_allure_dir:
                self._lancer_generation_allure(ouvrir_apres=False)
            self._update_actions()

        QTimer.singleShot(0, finalize)

    MainWindow._on_progress = progress_with_finalizing_state
    MainWindow._on_run_finished = finish_with_immediate_feedback
