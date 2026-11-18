"""Comparaison independante : les logs de l'interface restent consultables."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QVBoxLayout, QWidget,
)

from runner.ui import tokens as t
from runner.ui.external_log import open_in_notepad_plus_plus
from runner.ui.results_panel import ReaderViews


class LogComparisonWindow(QMainWindow):
    closed = Signal()

    def __init__(self, source):
        super().__init__(source.window(), Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Compare reader logs · Pytest Runner')
        self.setMinimumSize(640, 400)
        self._source = source
        source.destroyed.connect(self._source_destroyed)
        self._snapshot = None
        self._settings = getattr(source.window(), 'settings', None)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel('Compare reader logs')
        title.setObjectName('PageTitle')
        top.addWidget(title)
        top.addStretch()
        self.follow = QCheckBox('Follow selected test')
        self.follow.setChecked(True)
        self.follow.setToolTip('Follow selections in this run. Uncheck to keep this comparison while selecting other tests.')
        self.follow.toggled.connect(self._follow_changed)
        top.addWidget(self.follow)
        self.load_selected = QPushButton('Load selected test')
        self.load_selected.setToolTip('Replace this pinned comparison with the test selected in the main window.')
        self.load_selected.clicked.connect(lambda: self.update_from_source(force=True))
        self.load_selected.hide()
        top.addWidget(self.load_selected)
        root.addLayout(top)
        self.test_label = QLabel()
        self.test_label.setTextFormat(Qt.PlainText)
        self.test_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.test_label.setWordWrap(True)
        root.addWidget(self.test_label)
        self.readers = ReaderViews(Qt.Horizontal, sync_scroll=True, show_lens=False,
                                  highlight_differences=True, external_open=True)
        self.readers.compare.setChecked(True)
        self.readers.compare.hide()
        self.readers.open_file_requested.connect(self._open_log)
        self.readers.wrap_all.setChecked(source.logs._wrap_lines)
        root.addWidget(self.readers, 1)
        self.setCentralWidget(page)
        self._close_shortcut = QShortcut(QKeySequence('Ctrl+W'), self)
        self._close_shortcut.activated.connect(self.close)
        available = source.screen().availableGeometry()
        self.resize(min(1440, available.width() - 40), min(840, available.height() - 64))
        geometry = self._settings.value('logs/comparison_geometry') if self._settings else None
        if geometry is not None:
            self.restoreGeometry(geometry)
        if not any(screen.availableGeometry().intersected(self.frameGeometry()).width() >= 160
                   and screen.availableGeometry().intersected(self.frameGeometry()).height() >= 80
                   for screen in QApplication.screens()):
            self.move(available.center() - self.rect().center())
        self.restyle()

    def _follow_changed(self, checked):
        self.load_selected.setVisible(not checked)
        if checked:
            self.update_from_source()

    def update_from_source(self, *, force=False):
        if self._source is None:
            return
        if not force and not self.follow.isChecked():
            return
        source = self._source
        readers = source._readers
        nodeid = getattr(source.logs, 'context_nodeid', '') or source._nodeid
        records = tuple((view.text(), source.logs.headers[index].text(),
                         source.logs._paths[index], view._tronque_source)
                        for index, view in enumerate(source.logs.views[:max(1, len(readers))]))
        snapshot = (nodeid, readers, records, getattr(source, '_comparison_workspace', ''),
                    getattr(source, '_comparison_context', ''))
        if snapshot == self._snapshot:
            return
        previous = self._snapshot
        changed_test = previous is None or (nodeid, snapshot[3:]) != (previous[0], previous[3:])
        self._snapshot = snapshot
        title = nodeid.replace('::', ' › ') or 'No test selected'
        self.test_label.setText(title + ('\n' + snapshot[4] if snapshot[4] else ''))
        self.test_label.setToolTip(snapshot[3] + '\n' + nodeid)
        self.setWindowTitle((nodeid.rsplit('::', 1)[-1] + ' · ' if nodeid else '') +
                            'Compare logs · Pytest Runner')
        # Mettre a jour les colonnes ensemble : un seul calcul des ecarts,
        # sans comparer les nouveaux logs aux anciens lecteurs entre-temps.
        self.readers._suspend_difference_refresh = True
        try:
            if self.readers._readers != readers:
                self.readers.set_readers(readers)
            for index, (text, title, path, truncated) in enumerate(records):
                old = previous[2][index] if previous and index < len(previous[2]) else None
                if not changed_test and old == records[index]:
                    continue
                reader_index = readers[index].index if readers else index
                self.readers.set_text(reader_index, text, title, str(path) if path else '')
                view = self.readers.views[index]
                view._tronque_source = truncated
                view._update_counter()
                if changed_test and view.search is not None:
                    view.search.refresh()
        finally:
            self.readers._suspend_difference_refresh = False
        self.readers.compare.hide()
        self.readers._update_difference_highlights(reveal=changed_test)

    def _open_log(self, index):
        path = self.readers.path_at(index)
        if path is not None:
            open_in_notepad_plus_plus(self, path)

    def restyle(self):
        self.test_label.setStyleSheet(f'color:{t.TEXT_MUTED};background:transparent;')
        self.readers.restyle()
        self.readers.compare.hide()

    def _source_destroyed(self):
        self._source = None
        self.close()

    def closeEvent(self, event):
        if self._source is not None and self._settings is not None:
            self._settings.setValue('logs/comparison_geometry', self.saveGeometry())
        if self._source is not None:
            self.closed.emit()
        # Qt peut encore avoir un rendu en attente pour cette fenetre native.
        # La detacher de son proprietaire avant la destruction differee evite
        # d'invalider le backing store du panneau qui reste ouvert.
        self.hide()
        self.setParent(None, Qt.Window)
        super().closeEvent(event)
