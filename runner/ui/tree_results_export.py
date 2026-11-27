"""Export du tree principal sans changer sa selection ni son affichage."""
from datetime import datetime
from pathlib import Path
from weakref import ref

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox
from shiboken6 import isValid

from runner.domain.models import Reader, Status
from runner.domain.report_timing import valid_duration
from runner.domain.tree_results_export import TreeExportRow, TreeResult, TreeSnapshot
from runner.services.tree_results_service import TreeResultsExportWorker


def snapshot_tree(window):
    model = window.model
    readers = model.readers or (Reader('', 0),)
    rows = []
    def visit(row, parents=()):
        path = parents + (row.node.name,)
        results = []
        if row.node.nodeid:
            for reader in readers:
                status = model.status_for(row, reader.index)
                # PENDING n'est pas un verdict NOT_RUN : aucun resultat connu.
                if not status.is_final:
                    results.append(TreeResult())
                    continue
                previous = model.is_previous(row, reader.index)
                meta = model.result_source(row.node.nodeid, reader.index)
                saved = model._retained.get(row.node.nodeid, {}).get(reader.index, {})
                seconds = saved.get('duration') if previous else model._durations.get(row.node.nodeid, {}).get(reader.index)
                reason = saved.get('reason', '') if previous else model._not_run.get((row.node.nodeid, reader.index), '')
                results.append(TreeResult(status, str(meta.get('run_id') or ''), str(meta.get('at') or ''),
                    str(meta.get('config') or ''), previous, seconds if valid_duration(seconds) else None, str(reason)))
        rows.append(TreeExportRow(row.node.name, row.node.kind.value, len(parents), ' / '.join(path),
                                  row.node.nodeid, tuple(results), row.node.collection_error))
        for child in row.children:
            visit(child, path)
    for root in model._roots:
        visit(root)
    return TreeSnapshot(window.workspace.path, tuple(readers), tuple(rows),
                        datetime.now().astimezone().isoformat(timespec='seconds'))


class TreeResultsExporter(QObject):
    busy_changed = Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.worker = None
        self.confirmation = None
        self.origin = None

    def available(self, window):
        return bool(self.worker is None and window.workspace and window.model._by_nodeid
                    and not window.service.busy and window._stress_worker is None
                    and not window._collecting and not window.profile_tree_button.isChecked()
                    and not (window.run_tabs and window.run_tabs.is_locked(window)))

    def export(self, window):
        if not self.available(window):
            return
        destination, _ = QFileDialog.getSaveFileName(window, 'Export all tree results to Excel',
            f'pytest_tree_results_{datetime.now():%Y%m%d_%H%M%S}.xlsx', 'Excel workbook (*.xlsx)')
        if not destination:
            return
        if not self.available(window):
            window.status_label.setText('Wait for collection or execution to finish, then export again.')
            return
        if not destination.lower().endswith('.xlsx'):
            destination += '.xlsx'
            if Path(destination).exists() and QMessageBox.question(window, 'Update existing workbook?',
                    f'A workbook already exists at:\n{destination}\n'
                    'Update it and keep its analysis notes? Older workbook formats require a new file.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        self.start(window, destination)

    def update(self, window):
        if not self.available(window):
            return
        destination, _ = QFileDialog.getOpenFileName(window, 'Update Excel analysis', '', 'Excel workbook (*.xlsx)')
        if destination and self.available(window):
            self.start(window, destination)

    def start(self, window, destination):
        # Capturer sur le fil UI avant tout travail disque. Le thread reste
        # rattache a l'hote : fermer l'onglet ne detruit pas son export.
        snapshot = snapshot_tree(window)
        worker = TreeResultsExportWorker(Path(destination), snapshot, window.history.entries(), self.host)
        self.worker = worker
        self.origin = ref(window)
        self.busy_changed.emit()
        window.status_label.setText('Exporting tree results to Excel…')
        worker.finished.connect(self.finished)
        worker.start()

    def finished(self):
        worker = self.worker
        ok, message = worker.result
        self.worker = None
        self.busy_changed.emit()
        origin = self.origin() if self.origin else None
        self.origin = None
        if origin is not None and isValid(origin) and origin.status_label.text() == 'Exporting tree results to Excel…':
            origin.status_label.setText('Tree results exported to Excel' if ok else 'Tree results export failed')
        closing = getattr(self.host, '_close_after_tree_export', False)
        if not closing:
            if ok:
                self.offer_open(worker.destination, worker.counts)
            else:
                QMessageBox.critical(self.host, 'Export failed', message)
        worker.deleteLater()

    def offer_open(self, path, counts):
        if self.confirmation is not None:
            self.confirmation.close()
        dialog = QMessageBox(self.host)
        dialog.setWindowTitle('Export complete')
        dialog.setIcon(QMessageBox.Information)
        dialog.setTextFormat(Qt.PlainText)
        dialog.setText(f'{counts[0]} tests exported · {counts[1]} with reader differences\n{path}')
        open_button = dialog.addButton('Open Excel', QMessageBox.ActionRole)
        dialog.addButton(QMessageBox.Close)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self.confirmation = dialog
        def clicked(button):
            if button is open_button and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                QMessageBox.warning(self.host, 'Unable to open Excel',
                    f'The workbook was saved. Open it manually with a spreadsheet application:\n{path}')
        dialog.buttonClicked.connect(clicked)
        dialog.finished.connect(lambda *_: setattr(self, 'confirmation', None))
        dialog.open()
