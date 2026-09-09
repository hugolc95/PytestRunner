"""Selected UX refinements promoted from the recent UX experiment.

Only the changes explicitly retained for main live here:
- compact icon-only Browse and Load actions;
- an explicit RESULTS label and progress-style compass counter;
- keep Config / History / Allure and Stop exactly as normal text actions;
- remove the redundant bottom-right remaining counter;
- show version and copyright in its place;
- expose a dedicated colorblind-friendly theme toggle in the navigation.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t
from runner.version import COPYRIGHT, __version__


def install() -> None:
    from runner.ui.main_window import MainWindow
    from runner.ui.history_dashboard import HistoryWindow

    # --------------------------------------------------------- accessibility
    original_build_navigation = MainWindow._build_navigation

    def build_navigation_with_colorblind_theme(self):
        navigation = original_build_navigation(self)

        self.colorblind_theme_button = QPushButton()
        self.colorblind_theme_button.setObjectName("NavigationUtilityIcon")
        self.colorblind_theme_button.setFixedSize(t.ICON_BUTTON, t.ICON_BUTTON)
        self.colorblind_theme_button.setCheckable(True)
        self.colorblind_theme_button.setCursor(Qt.PointingHandCursor)

        def toggle_colorblind_theme(checked=False) -> None:
            if t.current_theme() == "colorblind":
                self.apply_theme(getattr(self, "_theme_before_colorblind", "dark"))
            else:
                self._theme_before_colorblind = t.current_theme()
                self.apply_theme("colorblind")

        self.colorblind_theme_button.clicked.connect(toggle_colorblind_theme)

        # The two utility buttons from the base UI live in a nested layout.
        # Find that layout rather than relying on its numeric position: this
        # keeps the accessibility button stable if another navigation row is
        # inserted later.
        root_layout = navigation.layout()
        utility_layout = None
        if root_layout is not None:
            for index in range(root_layout.count()):
                nested = root_layout.itemAt(index).layout()
                if nested is not None and nested.indexOf(self.page_theme_button) >= 0:
                    utility_layout = nested
                    break
        if utility_layout is not None:
            utility_layout.addWidget(self.colorblind_theme_button)

        return navigation

    MainWindow._build_navigation = build_navigation_with_colorblind_theme

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

    # The History summary labels had their PASSED color frozen when the page
    # was constructed. Startup constructs the page in dark mode and restores
    # the saved theme afterwards, so these two labels could stay green even
    # after switching to the colorblind palette. Repaint them on every theme
    # change just like the History cards already do.
    original_history_restyle = HistoryWindow.restyle

    def history_restyle_selected(self) -> None:
        original_history_restyle(self)
        passed = t.status_color(Status.PASSED)
        self.passed_value.setStyleSheet(
            f"font-size:22px;font-weight:700;color:{passed};"
            "background:transparent;")
        self.success_value.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{passed};"
            "background:transparent;")

    HistoryWindow.restyle = history_restyle_selected

    original_restyle = MainWindow._restyle

    def restyle_selected(self) -> None:
        original_restyle(self)
        self.browse_button.setIcon(icons.icon("mdi.folder-open-outline", t.TEXT_MUTED))
        self.load_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

        # The integrated History dashboard is a child of history_page rather
        # than history_page itself, so the base MainWindow restyle does not
        # automatically repaint its per-widget styles.
        if hasattr(self, "history_dashboard"):
            self.history_dashboard.restyle()

        if hasattr(self, "colorblind_theme_button"):
            active = t.current_theme() == "colorblind"
            self.colorblind_theme_button.setChecked(active)
            self.colorblind_theme_button.setIcon(icons.icon(
                "mdi.eye-outline", t.ACCENT if active else t.TEXT_MUTED))
            self.colorblind_theme_button.setToolTip(
                "Colorblind-friendly colors enabled"
                if active else "Use colorblind-friendly colors")

    MainWindow._restyle = restyle_selected

    # ------------------------------------------------------ compass progress
    original_refresh_counts = MainWindow._rafraichir_compteurs

    def refresh_counts_as_progress(self) -> None:
        original_refresh_counts(self)
        total = int(getattr(self, "_main_run_total", 0) or 0)
        if getattr(self, '_profile_count_statuses', None) is not None:
            total = self._profile_execution_total
        if total > 0:
            done = min(total, max(0, int(self._completed_executions())))
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
