"""Ecriture Excel hors du fil UI ; l'instantane ne contient aucun objet Qt."""
from PySide6.QtCore import QThread

from runner.domain.analysis_workbook import export_analysis_xlsx as export_tree_results_xlsx


class TreeResultsExportWorker(QThread):
    def __init__(self, destination, snapshot, entries=(), parent=None):
        super().__init__(parent)
        self.destination = destination
        self.snapshot = snapshot
        self.entries = tuple(entries)
        self.result = (False, 'Tree export did not complete.')
        self.counts = (0, 0)

    def run(self):
        try:
            self.counts = export_tree_results_xlsx(self.destination, self.snapshot, self.entries)
            self.result = (True, '')
        except Exception as exc:
            self.result = (False, f'{type(exc).__name__}: {exc}')
