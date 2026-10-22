"""Compact tree actions grouped by search, selection and presentation."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QFrame, QMenu

from runner.ui import icons, tokens as t


class TreeToolbarController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.menu = QMenu(window)
        self.menu.aboutToShow.connect(self.populate_menu)
        self.button = window._quiet('mdi.dots-horizontal', 'More tree actions', self.open_menu)
        layout = window.tree_toolbar.layout()
        while layout.count():
            layout.takeAt(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SPACE_1)
        layout.addWidget(window.search, 1)
        self.separator(layout)
        layout.addWidget(window.disabled_tests.button)
        self.separator(layout, window.disabled_tests.button)
        layout.addWidget(window.select_all_button)
        layout.addWidget(window.select_none_button)
        self.selection_separator = self.separator(layout)
        layout.addWidget(window.expand_button)
        layout.addWidget(window.collapse_button)
        layout.addWidget(window.tree_results.button)
        layout.addWidget(self.button)
        window.tree_toolbar.installEventFilter(self)
        # The search counter only occupies space when there is a query.
        window.search.counter.setVisible(bool(window.search.field.text().strip()))
        window.search.field.textChanged.connect(
            lambda text: window.search.counter.setVisible(bool(text.strip())))
        window.search.field.textChanged.connect(self.search_visibility)
        self.search_visibility(window.search.field.text())
        # The magnifier already lives inside the input. One toggle is enough
        # to switch between names and failure output, without a second loupe.
        window.search.tests_button.hide()
        window.search.failures_button.clicked.disconnect()
        window.search.failures_button.clicked.connect(lambda: window.search._set_scope(
            'tests' if window.search.scope == 'failures' else 'failures'))
        window.search.failures_button.setToolTip(
            'Search inside failure output · click again to search test names')
        window.profile_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        window.profile_tree.customContextMenuRequested.connect(self.profile_menu)

    def separator(self, layout, follows=None):
        line = QFrame()
        line.setObjectName('Separator')
        line.setFrameShape(QFrame.VLine)
        line.setFixedHeight(18)
        layout.addWidget(line)
        if follows is not None:
            # Conditional deactivation action must not leave an empty group.
            follows.installEventFilter(self)
            self.conditional_separator = line
            self.conditional_button = follows
            line.setVisible(not follows.isHidden())
        return line

    def eventFilter(self, watched, event):
        if watched is self.window.tree_toolbar and event.type() == QEvent.Resize:
            self.adapt(event.size().width())
        if watched is getattr(self, 'conditional_button', None):
            if event.type() in (QEvent.Show, QEvent.Hide, QEvent.ShowToParent, QEvent.HideToParent):
                self.conditional_separator.setVisible(not watched.isHidden())
        return super().eventFilter(watched, event)

    def search_visibility(self, text):
        for button in (self.window.search.prev_button, self.window.search.next_button):
            button.setVisible(bool(text.strip()))

    def adapt(self, width):
        # Keep a useful search field and the eraser even with a narrow split.
        w = self.window
        for button in (w.expand_button, w.collapse_button):
            button.setVisible(width >= 620)
        for button in (w.select_all_button, w.select_none_button):
            button.setVisible(width >= 430)
        self.selection_separator.setVisible(width >= 430)

    def populate_menu(self):
        w = self.window
        self.menu.clear()
        w.tree_results.refresh()
        self.menu.addAction(w.tree_results.action)
        self.menu.addSeparator()
        for button in (w.select_all_button, w.select_none_button,
                       w.expand_button, w.collapse_button):
            if button.isHidden():
                action = self.menu.addAction(button.icon(), button.toolTip(), button.click)
                action.setEnabled(button.isEnabled())
        differences = self.menu.addAction(icons.icon('mdi.call-split', t.TEXT_MUTED),
                                          'Select tests where readers disagree', w.select_divergent)
        differences.setEnabled(w.act_diverge.isEnabled() and w.select_all_button.isEnabled())
        self.menu.addSeparator()
        for text, scope in [('Search by test name', 'tests'), ('Search in failure output', 'failures')]:
            action = self.menu.addAction(text, lambda checked=False, scope=scope: w.search._set_scope(scope))
            action.setCheckable(True)
            action.setChecked(w.search.scope == scope)

    def open_menu(self):
        self.menu.popup(self.button.mapToGlobal(self.button.rect().bottomLeft()))

    def profile_menu(self, point):
        self.window.tree_results.refresh()
        menu = QMenu(self.window)
        menu.addAction(self.window.tree_results.action)
        menu.exec(self.window.profile_tree.viewport().mapToGlobal(point))

    def restyle(self):
        self.button.setIcon(icons.icon('mdi.dots-horizontal', t.TEXT_MUTED))
