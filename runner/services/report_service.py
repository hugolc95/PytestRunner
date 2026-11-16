"""Generation du rapport portable hors du fil de l'interface."""
from PySide6.QtCore import QThread

from runner.domain.report import write_html


class ReportExportWorker(QThread):
    def __init__(self, entries, destination, parent=None):
        super().__init__(parent)
        self.entries = tuple(entries)
        self.destination = destination
        self.result = (False, 'Report generation did not complete.')

    def run(self):
        try:
            self.result = write_html(self.entries, self.destination)
        except Exception as exc:
            self.result = (False, f'{type(exc).__name__}: {exc}')
