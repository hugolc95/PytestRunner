from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QAbstractItemView,
    QHeaderView,
)

from core.run_history import RunHistoryManager
from gui_qt.styles.styles import neutral_button


COLUMNS = ["Test", "Vu", "Echoue", "Taux d'echec"]


class FlakyTestsDialog(QDialog):
    def __init__(self, history_manager: RunHistoryManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tests instables (flaky)")
        self.resize(900, 500)

        self.history_manager = history_manager

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Tests dont le resultat varie d'un run a l'autre (parfois passe, parfois echoue), "
            "sur les 50 runs les plus recents de l'historique."
        ))

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for col in range(len(COLUMNS)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        layout.addWidget(self.table)

        button_bar = QHBoxLayout()
        self.btn_refresh = QPushButton("Rafraichir")
        self.btn_refresh.setStyleSheet(neutral_button())
        self.btn_refresh.clicked.connect(self.reload_entries)
        button_bar.addStretch()
        button_bar.addWidget(self.btn_refresh)
        layout.addLayout(button_bar)

        self.reload_entries()

    def reload_entries(self):
        rows = self.history_manager.compute_flaky_tests()
        self.table.setRowCount(len(rows))

        for row, data in enumerate(rows):
            values = [
                data["nodeid"],
                str(data["seen"]),
                str(data["failed"]),
                f"{data['flaky_ratio'] * 100:.0f}%",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

        self.table.resizeColumnsToContents()
