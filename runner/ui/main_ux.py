"""Selected UX refinements promoted from the recent UX experiment."""
from __future__ import annotations
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTreeView, QTreeWidget
from runner.domain.models import Status
from runner.ui import icons
from runner.ui import tokens as t
from runner.version import COPYRIGHT, __version__

def install() -> None:
    from runner.ui.main_window import MainWindow
    from runner.ui.history_dashboard import HistoryWindow, RunCard
    from runner.ui.interpreter_dialog import InterpreterDialog

    original_build_navigation = MainWindow._build_navigation
    def build_navigation_with_colorblind_theme(self):
        navigation = original_build_navigation(self)
        self.colorblind_theme_button = QPushButton()
        self.colorblind_theme_button.setObjectName("NavigationUtilityIcon")
        self.colorblind_theme_button.setFixedSize(t.ICON_BUTTON, t.ICON_BUTTON)
        self.colorblind_theme_button.setCheckable(True)
        self.colorblind_theme_button.setCursor(Qt.PointingHandCursor)
        def toggle_colorblind_theme(checked=False):
            base = t.base_theme()
            self.apply_theme(base if t.is_colorblind() else f"{base}_colorblind")
        self.colorblind_theme_button.clicked.connect(toggle_colorblind_theme)
        root_layout=navigation.layout(); utility_layout=None
        if root_layout is not None:
            for index in range(root_layout.count()):
                nested=root_layout.itemAt(index).layout()
                if nested is not None and nested.indexOf(self.page_theme_button)>=0:
                    utility_layout=nested; break
        if utility_layout is not None: utility_layout.addWidget(self.colorblind_theme_button)
        return navigation
    MainWindow._build_navigation=build_navigation_with_colorblind_theme

    def toggle_theme_independent(self):
        target="light" if t.is_dark() else "dark"
        if t.is_colorblind(): target += "_colorblind"
        self.apply_theme(target)
    MainWindow.toggle_theme=toggle_theme_independent

    original_build_command_bar=MainWindow._build_command_bar
    def build_command_bar_selected(self):
        bar=original_build_command_bar(self); self.workspace_combo.setMaximumWidth(680)
        self.browse_button.setText(""); self.browse_button.setIcon(icons.icon("mdi.folder-open-outline",t.TEXT_MUTED)); self.browse_button.setIconSize(QSize(17,17)); self.browse_button.setFixedWidth(34); self.browse_button.setToolTip("Browse for another workspace")
        self.load_button.setText(""); self.load_button.setObjectName("Ghost"); self.load_button.setIcon(icons.icon("mdi.refresh",t.TEXT_MUTED)); self.load_button.setIconSize(QSize(17,17)); self.load_button.setFixedWidth(34); self.load_button.setToolTip("Reload tests from this workspace  (Ctrl+O)")
        results_label=QLabel("RESULTS"); results_label.setObjectName("Faint"); results_label.setToolTip("Run progress and verdict counters"); self._main_results_label=results_label
        layout=bar.layout(); index=layout.indexOf(self.compass_ring)
        if index>=0: layout.insertWidget(index,results_label)
        self.compass_pct.setMinimumWidth(66); self.compass_pct.setToolTip("Completed test/reader executions")
        return bar
    MainWindow._build_command_bar=build_command_bar_selected

    # History cards used an exact `current_theme() == "light"` test.  With
    # light_colorblind that selected the dark banner, leaving dark metadata on
    # a dark background (the invisible run number/time visible in field tests).
    original_card_restyle=RunCard.restyle
    def card_restyle_accessible(self):
        original_card_restyle(self)
        entry=self.group.entries[0] if self.group.entries else None
        is_profile=bool(entry and entry.run_kind=="profile")
        is_selected=bool(entry and entry.run_kind=="classic")
        light=t.base_theme()=="light"
        if is_profile:
            foreground="#5b21b6" if light else "#bd9aff"
            background="#eee5ff" if light else "#302343"
        elif is_selected:
            foreground="#004f91" if light else "#91bfff"
            background="#dcecff" if light else "#203249"
        else:
            foreground=t.TEXT_MUTED; background=t.BG_RAISED
        self.origin_label.setStyleSheet(
            f"font-family:'Segoe UI';font-size:{t.TEXT_XS}px;font-weight:700;"
            f"background:transparent;border:none;color:{foreground};")
        self.origin_banner.setStyleSheet(
            f"QFrame#HistoryOriginBanner {{background:{background};border:none;"
            f"border-top-left-radius:{t.RADIUS_MD}px;"
            f"border-top-right-radius:{t.RADIUS_MD}px;}}")
    RunCard.restyle=card_restyle_accessible

    original_history_restyle=HistoryWindow.restyle
    def history_restyle_selected(self):
        original_history_restyle(self); passed=t.status_color(Status.PASSED)
        self.passed_value.setStyleSheet(f"font-size:22px;font-weight:700;color:{passed};background:transparent;")
        self.success_value.setStyleSheet(f"font-size:14px;font-weight:700;color:{passed};background:transparent;")
    HistoryWindow.restyle=history_restyle_selected

    # The embedded Python page is built before the persisted theme is restored.
    # Its per-widget styles therefore kept dark-theme text after switching to
    # light. Repaint every explicit label from the active tokens on each theme
    # change instead of relying on the construction-time values.
    def interpreter_restyle(self):
        labels=self.findChildren(QLabel)
        for label in labels:
            if label is self.status_label or label is self.override_label:
                continue
            label.setStyleSheet(f"color:{t.TEXT};background:transparent;")
        status_text=self.status_label.text()
        if status_text:
            # Probe errors are already identifiable by their content/state in
            # normal use; use the normal readable text colour for neutral info.
            self.status_label.setStyleSheet(f"color:{t.TEXT_MUTED};background:transparent;")
        else:
            self.status_label.setStyleSheet(f"color:{t.TEXT_MUTED};background:transparent;")
        if self.override_label.isVisible():
            self.override_label.setStyleSheet(
                f"color:{t.status_color(Status.SKIPPED)};background:transparent;")
    InterpreterDialog.restyle=interpreter_restyle

    original_restyle=MainWindow._restyle
    def restyle_selected(self):
        original_restyle(self)
        self.browse_button.setIcon(icons.icon("mdi.folder-open-outline",t.TEXT_MUTED)); self.load_button.setIcon(icons.icon("mdi.refresh",t.TEXT_MUTED))
        tree_icon_size=QSize(t.TREE_ICON_SIZE,t.TREE_ICON_SIZE)
        for tree in self.findChildren(QTreeView): tree.setIconSize(tree_icon_size)
        for tree in self.findChildren(QTreeWidget): tree.setIconSize(tree_icon_size)
        if hasattr(self,"history_dashboard"): self.history_dashboard.restyle()
        for interpreter in self.findChildren(InterpreterDialog): interpreter.restyle()
        if hasattr(self,"colorblind_theme_button"):
            active=t.is_colorblind(); self.colorblind_theme_button.setChecked(active)
            self.colorblind_theme_button.setIcon(icons.icon("mdi.eye-outline",t.ACCENT if active else t.TEXT_MUTED))
            self.colorblind_theme_button.setToolTip("Colorblind-friendly colors enabled" if active else "Use colorblind-friendly colors")
    MainWindow._restyle=restyle_selected

    original_refresh_counts=MainWindow._rafraichir_compteurs
    def refresh_counts_as_progress(self):
        original_refresh_counts(self); total=int(getattr(self,"_main_run_total",0) or 0)
        if getattr(self,'_profile_count_statuses',None) is not None: total=self._profile_execution_total
        if total>0:
            done=min(total,max(0,int(self._completed_executions()))); self.compass_pct.setText(f"{done} / {total}"); self.compass_pct.setToolTip(f"{done} of {total} expected test/reader executions completed")
        else: self.compass_pct.setText("—"); self.compass_pct.setToolTip("No run yet")
    MainWindow._rafraichir_compteurs=refresh_counts_as_progress
    original_run_started=MainWindow._on_run_started
    def run_started_with_progress_total(self,request):
        self._main_run_total=request.total_tests; original_run_started(self,request); self.remaining_pill.setVisible(False); self._rafraichir_compteurs()
    MainWindow._on_run_started=run_started_with_progress_total
    original_load_workspace=MainWindow.load_workspace
    def load_workspace_reset_progress(self): self._main_run_total=0; original_load_workspace(self)
    MainWindow.load_workspace=load_workspace_reset_progress
    original_build_status_bar=MainWindow._build_status_bar
    def build_status_bar_with_metadata(self):
        original_build_status_bar(self); parent=self.remaining_pill.parentWidget(); layout=parent.layout() if parent is not None else None; self.remaining_pill.setVisible(False)
        meta=QLabel(f"v{__version__}  ·  {COPYRIGHT}"); meta.setObjectName("Faint"); meta.setToolTip(f"Pytest Runner version {__version__}"); self._version_copyright_label=meta
        if layout is not None:
            index=layout.indexOf(self.remaining_pill); layout.insertWidget(index,meta) if index>=0 else layout.addWidget(meta)
    MainWindow._build_status_bar=build_status_bar_with_metadata
