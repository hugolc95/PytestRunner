"""Run-page layout using the existing controls and their existing signals."""
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QPushButton, QPlainTextEdit, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QEvent, QSize, Qt, QTimer

from runner.ui import tokens as t
from runner.ui import icons
from runner.ui.qt_safety import tolerate_destruction


class ResponsiveAtr(QWidget):
    """Keep the ATR visible inline with compact, adaptive text."""
    def __init__(self, field):
        super().__init__()
        self.field = field
        field.maximum_text_size = 10
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(0)
        self.stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        field._refresh_action.setVisible(False)
        self.stack.addWidget(field)
        self.button = QPushButton("ATR…")
        self.button.setToolTip("Show the full card ATR and diagnostic details")
        self.button.clicked.connect(self.open_details)
        self.stack.addWidget(self.button)
        row.addWidget(self.stack, 1)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("AtrRefresh")
        self.refresh_button.setFixedSize(t.CONTROL_SM, t.CONTROL_SM)
        self.refresh_button.setIconSize(QSize(16, 16))
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.setAccessibleName("Refresh ATR")
        self.refresh_button.setToolTip("Read the card again")
        self.refresh_button.clicked.connect(lambda: field.refresh())
        row.addWidget(self.refresh_button)
        field.textChanged.connect(lambda: QTimer.singleShot(0, self.update_presentation))
        self.restyle()

    def restyle(self):
        self.refresh_button.setIcon(icons.icon("mdi.refresh", t.TEXT_MUTED))

    def set_bottom_bar(self, enabled):
        self.field.setProperty("bottomBar", enabled)
        self.field.bottom_bar = enabled
        self.field.maximum_text_size = t.TEXT_SM if enabled else 10
        self.refresh_button.setProperty("bottomBar", enabled)
        row = self.layout()
        row.removeWidget(self.refresh_button)
        if enabled:
            row.insertWidget(0, self.refresh_button)
        else:
            row.addWidget(self.refresh_button)
        row.setSpacing(6 if enabled else 2)
        height = 20 if enabled else t.CONTROL_SM
        self.refresh_button.setFixedSize(height, height)
        icon_size = 14 if enabled else 16
        self.refresh_button.setIconSize(QSize(icon_size, icon_size))
        self.setMaximumHeight(20 if enabled else 16777215)
        self.stack.setMaximumHeight(20 if enabled else 16777215)
        self.field.style().unpolish(self.field)
        self.field.style().polish(self.field)
        self.refresh_button.style().unpolish(self.refresh_button)
        self.refresh_button.style().polish(self.refresh_button)
        self.field._fit()

    def update_presentation(self):
        # Never replace the ATR with an extra button, even in narrow windows.
        # The read-only field supports selection/copy and horizontal scrolling.
        self.stack.setCurrentIndex(0)
        self.field._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_presentation()

    def open_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Card ATR")
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        def sync():
            text = self.field.text() + "\n\n" + self.field.toolTip()
            if details.toPlainText() != text:
                details.setPlainText(text)
        sync()
        layout.addWidget(details)
        buttons = QHBoxLayout()
        copy = QPushButton("Copy ATR")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.field.text()))
        buttons.addWidget(copy)
        close = QPushButton("Close")
        close.clicked.connect(dialog.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.resize(520, 230)
        from PySide6.QtCore import Qt
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        timer = QTimer(dialog)
        timer.timeout.connect(sync)
        timer.start(500)
        dialog.show()


class StructuredRunHeader(QWidget):
    def __init__(self, window, command_bar, run_bar):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(t.SPACE_3)
        self._compact = None
        self._dense = None
        # Evalue une fois la mise en page posee : pendant un redimensionnement,
        # l'en-tete passe par des hauteurs transitoires qui faisaient grossir
        # la fenetre a chaque etape.
        self._whole_timer = QTimer(self)
        self._whole_timer.setSingleShot(True)
        self._whole_timer.setInterval(40)
        self._whole_timer.timeout.connect(self._keep_whole)

        self.environment, environment = self._panel("ENVIRONMENT")
        self.execution, execution = self._panel("EXECUTION")
        self.results, results = self._panel("RESULTS")
        environment_fields = QGridLayout()
        environment_fields.setContentsMargins(0, 0, 0, 0)
        environment_fields.setHorizontalSpacing(t.SPACE_3)
        environment_fields.setVerticalSpacing(t.SPACE_1)
        workspace_column = QVBoxLayout()
        workspace_column.setSpacing(t.SPACE_1)
        workspace_column.setAlignment(Qt.AlignTop)
        self.reader_fields = QWidget()
        reader_column = QVBoxLayout(self.reader_fields)
        reader_column.setContentsMargins(0, 0, 0, 0)
        reader_column.setSpacing(t.SPACE_2)
        reader_column.setAlignment(Qt.AlignTop)
        environment_fields.addLayout(workspace_column, 0, 0, Qt.AlignTop)
        self.environment_fields = environment_fields
        self.workspace_column = workspace_column
        self._window = window
        environment_fields.setColumnStretch(0, 1)
        environment.addLayout(environment_fields)

        # Reparent the actual controls; do not duplicate actions or state.
        window.workspace_combo.setMinimumWidth(180)
        window.workspace_combo.setMaximumWidth(16777215)
        self._move(workspace_column, window.workspace_combo)
        for button, text in ((window.browse_button, "Browse…"),
                             (window.load_button, "Collect")):
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setText(text)
        workspace_actions = QHBoxLayout()
        workspace_actions.setSpacing(t.SPACE_2)
        for control in (window.browse_button, window.load_button,
                        window.config_button, window.history_button):
            self._move(workspace_actions, control)
        workspace_actions.addStretch()
        window.run_name_stack.setMinimumWidth(90)
        window.run_name_stack.setMaximumWidth(260)
        window.run_name_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._move(workspace_actions, window.run_name_stack)
        workspace_column.addLayout(workspace_actions)

        window.reader_controls.layout().setContentsMargins(0, 0, 0, 0)
        reader_layout = window.reader_controls.layout()
        reader_layout.setSizeConstraint(QLayout.SetMinimumSize)
        while reader_layout.count():
            item = reader_layout.takeAt(0)
            if isinstance(item.widget(), QLabel):
                item.widget().hide()
        reader_layout.addWidget(window.reader_selector, 0, 1)
        window.reader_selector.setMinimumContentsLength(16)
        window.reader_selector.setMaximumWidth(16777215)
        window.reader_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.atr_presentation = ResponsiveAtr(window.reader_atr)
        # A full-width compact line keeps long ATRs readable without squeezing
        # the reader name or falling back to the ATR details button.
        reader_layout.addWidget(self.atr_presentation, 1, 1)
        reader_layout.setColumnStretch(0, 0)
        reader_layout.setColumnStretch(1, 2)
        reader_layout.setColumnStretch(2, 0)
        execution_fields = QHBoxLayout()
        execution_fields.setContentsMargins(0, 0, 0, 0)
        execution_fields.setSpacing(t.SPACE_2)
        execution_fields.setAlignment(Qt.AlignTop)
        window.readers_bar.set_integrated()
        self._move(reader_column, window.readers_bar)
        reader_layout.addWidget(self.reader_fields, 2, 1)
        reader_layout.setVerticalSpacing(t.SPACE_1)
        # Launch controls form the left column; inspection and selection share
        # the right column in selector / ATR / run-readers order.
        command_fields = QWidget()
        command_fields.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        commands = QVBoxLayout(command_fields)
        commands.setContentsMargins(0, 0, 0, 0)
        commands.setSpacing(t.SPACE_2)
        commands.setAlignment(Qt.AlignTop)
        window.run_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        window.pause_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._move(commands, window.launch_stack)
        secondary = QHBoxLayout()
        secondary.setSpacing(t.SPACE_1)
        for control in (window.stop_button, window.rerun_button):
            self._move(secondary, control)
        commands.addLayout(secondary)
        self._move(commands, window.profile_chip)
        commands.addStretch()
        execution_fields.addWidget(command_fields, 0, Qt.AlignTop)
        self._move(execution_fields, window.reader_controls)
        execution_fields.setStretch(1, 1)
        execution_fields.addStretch(0)
        self.commands = commands
        self.execution_fields = execution_fields
        self.execution_heading = QHBoxLayout()
        heading = execution.takeAt(0).widget()
        self.execution_heading.addWidget(heading)
        self.execution_heading.addStretch()
        execution.insertLayout(0, self.execution_heading)
        self.run_config_button = window.reader_config_button
        self.run_config_button.setToolTip("Open this run’s independent YAML configuration")
        self._reader_mode = None
        execution.addLayout(execution_fields)
        execution.addStretch()

        progress = QHBoxLayout()
        progress.setSpacing(t.SPACE_2)
        # Share the heading row with the ring instead of reserving a separate
        # line above it. Result actions stay together on the left.
        result_heading = results.takeAt(0).widget()
        self.result_heading = result_heading
        result_heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        result_actions = QVBoxLayout()
        result_actions.setSpacing(t.SPACE_1)
        result_actions.addWidget(result_heading, 0, Qt.AlignTop)
        result_buttons = QHBoxLayout()
        result_buttons.setSpacing(t.SPACE_2)
        self._move(result_buttons, window.view_failures_button)
        self._move(result_buttons, window.view_differences_button)
        self._move(result_buttons, window.collection_errors_button)
        result_buttons.addStretch()
        result_actions.addLayout(result_buttons)
        result_actions.addStretch()
        progress.addLayout(result_actions, 1)
        self._move(progress, window.compass_pct)
        self._move(progress, window.compass_ring)
        progress.setAlignment(window.compass_ring, Qt.AlignRight | Qt.AlignTop)
        results.addLayout(progress)
        self._result_progress = progress
        self._result_buttons = result_buttons
        self._result_actions = result_actions
        # Les cinq compteurs restent visibles, NOT RUN compris. En grande
        # fenetre, la carte Results est une colonne etroite : sur une seule
        # rangee ils tombaient en 11 px sur deux lignes. Ils y passent sur deux
        # rangees lisibles ; la ligne compacte garde une rangee unique.
        counters = QGridLayout()
        counters.setHorizontalSpacing(t.SPACE_1)
        counters.setVerticalSpacing(t.SPACE_1)
        self._result_pills = tuple(window.pills.values())
        for pill in self._result_pills:
            pill.set_compact(True)
        results.addLayout(counters)
        self._counters = counters
        self._counter_columns = None
        self._place_counters(len(self._result_pills))
        results.addStretch()

        # Keep any legacy decoration owned, but never visible in the page.
        for old in (command_bar, run_bar):
            old.setParent(self)
            old.hide()
        self._arrange(False)
        self.update_environment()

    def update_environment(self):
        visible = not self._window.readers_bar.isHidden()
        self.reader_fields.setVisible(visible)
        reader_mode = not self._window.reader_controls.isHidden()
        if reader_mode != self._reader_mode:
            self._reader_mode = reader_mode
            self.commands.setDirection(QBoxLayout.TopToBottom if reader_mode else QBoxLayout.LeftToRight)
            self.execution_fields.removeWidget(self.run_config_button)
            self._window.reader_controls.layout().removeWidget(self.run_config_button)
            self.execution_fields.setStretch(2, 0 if reader_mode else 1)
            if reader_mode:
                self._window.reader_controls.layout().addWidget(self.run_config_button, 0, 0)
            else:
                self.execution_fields.addWidget(self.run_config_button)
            self.run_config_button.show()

    def set_repeat_context(self, active, has_previous=True):
        self.result_heading.setText('RESULTS · PREVIOUS RUN' if active and has_previous else
                        'RESULTS · NO PREVIOUS RUN' if active else 'RESULTS')

    @staticmethod
    def _panel(title):
        panel = QFrame()
        panel.setObjectName("Surface")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        layout.setSpacing(t.SPACE_1)
        layout.setAlignment(Qt.AlignTop)
        heading = QLabel(title)
        heading.setObjectName("Faint")
        layout.addWidget(heading)
        return panel, layout

    @staticmethod
    def _move(layout, widget, *position):
        explicitly_hidden = widget.isHidden()
        layout.addWidget(widget, *position)
        widget.setVisible(not explicitly_hidden)

    def _arrange(self, compact):
        if compact == self._compact:
            return
        self._compact = compact
        for panel in (self.environment, self.execution, self.results):
            self._grid.removeWidget(panel)
        # Empilees, les trois cartes prenaient 340 px de haut : a 800 x 560
        # elles etaient ecrasees (bouton Run sans texte, Collect sur le champ).
        # Sur toute la largeur, le chemin et ses actions tiennent sur une ligne.
        self.workspace_column.setDirection(
            QBoxLayout.LeftToRight if compact == "stacked" else QBoxLayout.TopToBottom)
        self.workspace_column.setStretch(0, 1 if compact == "stacked" else 0)
        # Sur une meme ligne, la largeur souhaitee du champ suivait la longueur
        # du chemin et reduisait « Run name » a 90 px (« Valid… »). Le chemin
        # cede la place en premier ; il reste lisible au survol et a l'ouverture.
        # La pile du nom annonce une largeur souhaitee nulle : il lui faut un
        # minimum a elle, le chemin prenant tout le reste de la ligne.
        combo = self._window.workspace_combo
        if compact == "stacked":
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            self._window.run_name_stack.setMinimumWidth(180)
        else:
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
            self._window.run_name_stack.setMinimumWidth(90)
        self._whole_timer.start()
        if compact == "stacked":
            for row, panel in enumerate((self.environment, self.execution, self.results)):
                self._grid.addWidget(panel, row, 0)
            for column in range(3):
                self._grid.setColumnStretch(column, 1 if column == 0 else 0)
            return
        self._grid.addWidget(self.environment, 0, 0)
        self._grid.addWidget(self.execution, 0, 1)
        if compact:
            self._grid.addWidget(self.results, 1, 0, 1, 2)
        else:
            self._grid.addWidget(self.results, 0, 2)
        for column in range(3):
            self._grid.setColumnStretch(column, 0 if compact and column == 2 else
                                        5 if column == 1 else 4)

    def _place_counters(self, columns):
        if columns == self._counter_columns:
            return
        self._counter_columns = columns
        for pill in self._result_pills:
            self._counters.removeWidget(pill)
        for index, pill in enumerate(self._result_pills):
            explicitly_hidden = pill.isHidden()
            self._counters.addWidget(pill, index // columns, index % columns)
            pill.setVisible(not explicitly_hidden)
        for column in range(len(self._result_pills)):
            self._counters.setColumnStretch(column, 1 if column < columns else 0)

    def _keep_whole(self):
        """La fenetre ne descend pas sous la hauteur que l'en-tete exige.

        `MainWindow` autorise 800 x 560, ce qui suffit cote a cote mais pas
        empile : Qt ecrasait alors les cartes sous leur minimum et les
        controles se chevauchaient (Run sans texte, Collect sur le chemin). La
        fenetre garde la hauteur qui manque, puis retrouve son minimum
        d'origine des que l'en-tete tient de nouveau.
        """
        top = self.window()
        if top is self or not self.isVisible():
            return
        base = top.property("runHeaderBaseMinimumHeight")
        if base is None:
            base = top.minimumHeight()
            top.setProperty("runHeaderBaseMinimumHeight", base)
        # Changer de disposition ne redonne pas tout de suite sa hauteur a
        # l'en-tete : sans cette mise en page explicite, il paraissait ecrase
        # alors que la place existait, et la fenetre grandissait pour rien.
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().activate()
        needed = self.minimumSizeHint().height()
        if self.height() < needed:
            # Le reste de la page est deja a son minimum quand l'en-tete est
            # ecrase. Calcul absolu, jamais cumule : deux appels en attente
            # ajoutaient chacun le manque et la fenetre grandissait sans fin.
            top.setMinimumHeight(max(base, top.height() - self.height() + needed))
        elif self._compact != "stacked" and top.minimumHeight() > base:
            top.setMinimumHeight(base)

    @tolerate_destruction(False)
    def event(self, event):
        # Les lecteurs n'arrivent qu'apres la collecte : la carte Execution
        # grandit alors sans que l'en-tete change de taille, donc sans
        # resizeEvent. Sa demande de mise en page suffit a reverifier.
        # Pendant la destruction de la fenetre, chaque enfant detruit envoie
        # encore LayoutRequest : le minuteur peut deja ne plus exister.
        if event.type() == QEvent.LayoutRequest and isValid(self._whole_timer):
            self._whole_timer.start()
        return super().event(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._whole_timer.start()
        dense = event.size().width() < 1260
        if dense != self._dense:
            self._dense = dense
            self._window.compass_ring.set_compact(dense)
            self.results.layout().setDirection(QBoxLayout.LeftToRight if dense else QBoxLayout.TopToBottom)
            for pill in self._result_pills:
                pill.set_header_density(True if dense else "medium")
            self._place_counters(len(self._result_pills) if dense else 3)
            for button, text, glyph in (
                    (self._window.view_failures_button, 'View failures', 'mdi.alert-circle-outline'),
                    (self._window.view_differences_button, 'View differences', 'mdi.call-split'),
                    (self._window.collection_errors_button, self._window.collection_errors_button.text(), 'mdi.file-alert-outline')):
                if dense and button.text():
                    button.setProperty('fullLabel', button.text())
                button.setText('' if dense else button.property('fullLabel') or text)
                button.setIcon(icons.icon(glyph, t.TEXT_MUTED))
                button.setMaximumWidth(32 if dense else 16777215)
            self.results.setMinimumWidth(0)
            # En ligne compacte, le titre (taille Ignored) cedait toute sa place
            # aux compteurs et ne montrait plus que « RE ».
            self.result_heading.setMinimumWidth(
                self.result_heading.fontMetrics().horizontalAdvance("RESULTS") + 4 if dense else 0)
        if dense:
            margins = self.results.layout().contentsMargins()
            required = (self._result_progress.minimumSize().width() + self._counters.minimumSize().width()
                        + self.results.layout().spacing() + margins.left() + margins.right())
            self.results.layout().setDirection(QBoxLayout.TopToBottom if event.size().width() < required else QBoxLayout.LeftToRight)
            self._arrange('stacked' if event.size().width() < 740 else True)
            return
        counter_width = self._counters.minimumSize().width()
        self.results.setMinimumWidth(counter_width + 2 * t.SPACE_3)
        required = sum(max(panel.minimumWidth(), panel.minimumSizeHint().width()) for panel in
                       (self.environment, self.execution, self.results))
        pair_width = sum(max(panel.minimumWidth(), panel.minimumSizeHint().width())
                         for panel in (self.environment, self.execution))
        width = event.size().width()
        self._arrange("stacked" if width < pair_width + self._grid.spacing() else
                      width < required + 2 * self._grid.spacing())
