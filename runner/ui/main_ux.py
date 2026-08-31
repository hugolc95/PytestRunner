"""Selected UX refinements promoted from the recent UX experiment.

Only the changes explicitly retained for main live here:
- compact icon-only Browse and Load actions;
- an explicit RESULTS label and progress-style compass counter;
- keep Config / History / Allure and Stop exactly as normal text actions;
- remove the redundant bottom-right remaining counter;
- show version and copyright in its place.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel

from runner.ui import icons
from runner.ui import tokens as t
from runner.version import COPYRIGHT, __version__


def install() -> None:
    from runner.ui.main_window import MainWindow

    # -------------------------------------------------------------- top bar
    original_build_command_bar = MainWindow._build_command_bar

    def build_command_bar_selected(self):
        bar = original_build_command_bar(self)

        # Keep more room for the workspace path while reducing two frequent
        # actions to obvious icons. Config/History/Allure deliberately retain
        # their text labels: they were clearer that way during evaluation.
        self.workspace_combo.setMaximumWidth(680)

        self.browse_button.setText("")
        self.browse_button.setIcon(icons.icon("mdi.folder-open-outline", t.TEXT_MUTED))
        self.browse_button.setIconSize(QSize(17, 17))
        self.browse_button.setFixedWidth(34)
        self.browse_button.setToolTip("Browse for another workspace")

        self.load_button.setText("")
        self.load_button.setObjectName("Ghost")
        self.load_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))
        self.load_button.setIconSize(QSize(17, 17))
        self.load_button.setFixedWidth(34)
        self.load_button.setToolTip("Reload tests from this workspace  (Ctrl+O)")

        # Make the right-hand cluster self-explanatory without changing the
        # existing clickable status pills.
        results_label = QLabel("RESULTS")
        results_label.setObjectName("Faint")
        results_label.setToolTip("Run progress and verdict counters")
        self._main_results_label = results_label
        layout = bar.layout()
        index = layout.indexOf(self.compass_ring)
        if index >= 0:
            layout.insertWidget(index, results_label)

        self.compass_pct.setMinimumWidth(66)
        self.compass_pct.setToolTip("Completed test/reader executions")
        return bar

    MainWindow._build_command_bar = build_command_bar_selected

    original_restyle = MainWindow._restyle

    def restyle_selected(self) -> None:
        original_restyle(self)
        self.browse_button.setIcon(icons.icon("mdi.folder-open-outline", t.TEXT_MUTED))
        self.load_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    MainWindow._restyle = restyle_selected

    # ------------------------------------------------------ compass progress
    original_refresh_counts = MainWindow._rafraichir_compteurs

    def refresh_counts_as_progress(self) -> None:
        original_refresh_counts(self)
        total = int(getattr(self, "_main_run_total", 0) or 0)
        if total > 0:
            done = min(total, max(0, int(self.model.done())))
            self.compass_pct.setText(f"{done} / {total}")
            self.compass_pct.setToolTip(
                f"{done} of {total} expected test/reader executions completed")
        else:
            self.compass_pct.setText("—")
            self.compass_pct.setToolTip("No run yet")

    MainWindow._rafraichir_compteurs = refresh_counts_as_progress

    original_run_started = MainWindow._on_run_started

    def run_started_with_progress_total(self, request) -> None:
        self._main_run_total = request.total_tests
        original_run_started(self, request)
        # _on_run_started deliberately shows RemainingPill in the base UI;
        # this promoted UX removes it because the compass now carries the same
        # information more clearly.
        self.remaining_pill.setVisible(False)
        self._rafraichir_compteurs()

    MainWindow._on_run_started = run_started_with_progress_total

    original_load_workspace = MainWindow.load_workspace

    def load_workspace_reset_progress(self) -> None:
        self._main_run_total = 0
        original_load_workspace(self)

    MainWindow.load_workspace = load_workspace_reset_progress

    # ---------------------------------------------------- footer metadata
    original_build_status_bar = MainWindow._build_status_bar

    def build_status_bar_with_metadata(self) -> None:
        original_build_status_bar(self)

        # Replace the now-redundant bottom-right remaining counter with stable
        # build metadata. Reuse the same parent/layout so no extra status bar or
        # vertical space is introduced.
        parent = self.remaining_pill.parentWidget()
        layout = parent.layout() if parent is not None else None
        self.remaining_pill.setVisible(False)

        meta = QLabel(f"v{__version__}  ·  {COPYRIGHT}")
        meta.setObjectName("Faint")
        meta.setToolTip(f"Pytest Runner version {__version__}")
        self._version_copyright_label = meta

        if layout is not None:
            index = layout.indexOf(self.remaining_pill)
            if index >= 0:
                layout.insertWidget(index, meta)
            else:
                layout.addWidget(meta)

    MainWindow._build_status_bar = build_status_bar_with_metadata
