"""Small UX refinements that can be evaluated without disturbing main.

This branch intentionally keeps the behaviour changes isolated so they are easy
to review or discard after trying the interface for real.
"""

from __future__ import annotations

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QLabel

from runner.ui import icons
from runner.ui import tokens as t


def install() -> None:
    from runner.ui.main_window import MainWindow

    # ------------------------------------------------------------------
    # Compact workspace/results bar
    # ------------------------------------------------------------------
    original_build_command_bar = MainWindow._build_command_bar

    def build_command_bar_compact(self):
        bar = original_build_command_bar(self)

        self.workspace_combo.setMaximumWidth(680)

        self.browse_button.setText("Change…")
        self.browse_button.setToolTip("Choose another workspace")

        for button, glyph, tooltip in (
            (self.load_button, "mdi.refresh", "Reload tests"),
            (self.config_button, "mdi.cog-outline", "Workspace configuration"),
            (self.history_button, "mdi.history", "Run history  (Ctrl+H)"),
            (self.allure_button, "mdi.file-chart-outline", "Allure — available after a run"),
        ):
            button.setText("")
            button.setIcon(icons.icon(glyph, t.TEXT_MUTED))
            button.setIconSize(QSize(17, 17))
            button.setFixedWidth(34)
            button.setToolTip(tooltip)

        # Allure has no meaningful action before a run has produced results.
        self.allure_button.setEnabled(False)

        # Give the compact cluster on the right an explicit meaning. The
        # individual status pills keep their tooltips/click-to-filter behaviour.
        results_label = QLabel("RESULTS")
        results_label.setObjectName("Faint")
        results_label.setToolTip("Run progress and verdict counters")
        self._ux_results_label = results_label
        layout = bar.layout()
        index = layout.indexOf(self.compass_ring)
        if index >= 0:
            layout.insertWidget(index, results_label)

        self.compass_pct.setMinimumWidth(66)
        self.compass_pct.setToolTip("Completed test/reader executions")
        return bar

    MainWindow._build_command_bar = build_command_bar_compact

    original_restyle = MainWindow._restyle

    def restyle_compact_bar(self) -> None:
        original_restyle(self)
        for button, glyph in (
            (self.load_button, "mdi.refresh"),
            (self.config_button, "mdi.cog-outline"),
            (self.history_button, "mdi.history"),
            (self.allure_button, "mdi.file-chart-outline"),
        ):
            button.setIcon(icons.icon(glyph, t.TEXT_MUTED))

    MainWindow._restyle = restyle_compact_bar

    # ------------------------------------------------------------------
    # Compass means progress; pills mean verdicts
    # ------------------------------------------------------------------
    original_refresh_counts = MainWindow._rafraichir_compteurs

    def refresh_counts_as_progress(self) -> None:
        original_refresh_counts(self)
        total = int(getattr(self, "_ux_run_total", 0) or 0)
        if total > 0:
            done = min(total, max(0, int(self.model.done())))
            self.compass_pct.setText(f"{done} / {total}")
            self.compass_pct.setToolTip(
                f"{done} of {total} expected test/reader executions completed")
        else:
            self.compass_pct.setText("—")
            self.compass_pct.setToolTip("No run yet")

    MainWindow._rafraichir_compteurs = refresh_counts_as_progress

    # ------------------------------------------------------------------
    # Contextual actions: Stop only while something is actually running;
    # Allure only once the current run can have produced Allure data.
    # ------------------------------------------------------------------
    original_build_run_bar = MainWindow._build_run_bar

    def build_run_bar_contextual(self):
        bar = original_build_run_bar(self)
        self.stop_button.setVisible(False)
        return bar

    MainWindow._build_run_bar = build_run_bar_contextual

    original_run_started = MainWindow._on_run_started

    def run_started_contextual(self, request) -> None:
        self._ux_run_total = request.total_tests
        self.stop_button.setVisible(True)
        self.allure_button.setEnabled(False)
        self.allure_button.setToolTip("Allure — available after this run finishes")
        original_run_started(self, request)
        # The wrapped refresh above turns the old pass-rate label into 0 / N.
        self._rafraichir_compteurs()

    MainWindow._on_run_started = run_started_contextual

    original_run_finished = MainWindow._on_run_finished

    def run_finished_contextual(self, reports) -> None:
        # Hide Stop as soon as the service says the run is over. The end-run
        # feedback wrapper may still defer history/log bookkeeping by one Qt turn.
        self.stop_button.setVisible(False)
        original_run_finished(self, reports)
        available = bool(self._last_allure_dir)
        self.allure_button.setEnabled(available)
        self.allure_button.setToolTip(
            "Open the Allure report of the last run"
            if available else
            "Allure is unavailable for this test interpreter/run")

    MainWindow._on_run_finished = run_finished_contextual

    original_load_workspace = MainWindow.load_workspace

    def load_workspace_contextual(self) -> None:
        self.allure_button.setEnabled(False)
        self.allure_button.setToolTip("Allure — available after a run")
        self._ux_run_total = 0
        original_load_workspace(self)

    MainWindow.load_workspace = load_workspace_contextual

    # Stress runs use a different worker than the normal RunService, so make
    # Stop contextual there too.
    original_start_stress = MainWindow._lancer_stress

    def start_stress_contextual(self, nodeid: str, mode: str, cap: int) -> None:
        original_start_stress(self, nodeid, mode, cap)
        if self._stress_worker is not None:
            self.stop_button.setVisible(True)

    MainWindow._lancer_stress = start_stress_contextual

    original_finish_stress = MainWindow._sur_fin_stress

    def finish_stress_contextual(self, summary) -> None:
        original_finish_stress(self, summary)
        self.stop_button.setVisible(False)

    MainWindow._sur_fin_stress = finish_stress_contextual
