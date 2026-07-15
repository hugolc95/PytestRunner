import os
import shutil
import time

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QTextEdit,
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
)
from PyQt5.QtCore import Qt

from core.run_history import RunHistoryManager
from core.report_export import export_html_report
from gui_qt.styles.styles import primary_button, neutral_button, danger_button, console_style
from gui_qt.status_icons import status_icon, STATUS_COLORS


COLUMNS = ["Date", "Mode", "Workspace", "Total", "Passed", "Failed", "Skipped", "Error", "Duree (s)"]


class HistoryWindow(QDialog):
    def __init__(self, history_manager: RunHistoryManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historique des executions")
        self.resize(1200, 600)

        self.history_manager = history_manager

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for col in range(len(COLUMNS)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Interactive)
        # La colonne "Workspace" absorbe l'espace restant ; les autres restent
        # redimensionnables a la souris (glisser-deposer sur la bordure d'en-tete).
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.view_output)

        layout.addWidget(QLabel("Double-cliquez sur une ligne pour voir la sortie console du run."))
        layout.addWidget(self.table)

        button_bar = QHBoxLayout()

        self.btn_view = QPushButton("Voir la sortie")
        self.btn_export_html = QPushButton("Exporter en HTML")
        self.btn_export_junit = QPushButton("Exporter JUnit XML")
        self.btn_compare = QPushButton("Comparer 2 runs")
        self.btn_refresh = QPushButton("Rafraichir")
        self.btn_clear = QPushButton("Effacer l'historique")

        self.btn_view.setStyleSheet(neutral_button())
        self.btn_export_html.setStyleSheet(primary_button())
        self.btn_export_junit.setStyleSheet(primary_button())
        self.btn_compare.setStyleSheet(neutral_button())
        self.btn_refresh.setStyleSheet(neutral_button())
        self.btn_clear.setStyleSheet(danger_button())

        self.btn_view.clicked.connect(self.view_output)
        self.btn_export_html.clicked.connect(self.export_html)
        self.btn_export_junit.clicked.connect(self.export_junit)
        self.btn_compare.clicked.connect(self.compare_runs)
        self.btn_refresh.clicked.connect(self.reload_entries)
        self.btn_clear.clicked.connect(self.clear_history)

        button_bar.addWidget(self.btn_view)
        button_bar.addWidget(self.btn_export_html)
        button_bar.addWidget(self.btn_export_junit)
        button_bar.addWidget(self.btn_compare)
        button_bar.addStretch()
        button_bar.addWidget(self.btn_refresh)
        button_bar.addWidget(self.btn_clear)

        layout.addLayout(button_bar)

        self.reload_entries()

    def reload_entries(self):
        entries = self.history_manager.all_entries()
        self.table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("timestamp", 0)))
            mode = "Campaign" if entry.get("source") == "campaign" else "Workspace"
            values = [
                ts,
                mode,
                entry.get("workspace", ""),
                str(entry.get("total", 0)),
                str(entry.get("passed", 0)),
                str(entry.get("failed", 0)),
                str(entry.get("skipped", 0)),
                str(entry.get("error", 0)),
                str(entry.get("duration_seconds", 0)),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, entry)
                self.table.setItem(row, col, item)

        # Dimensionne chaque colonne a son contenu des l'ouverture, pour ne pas
        # avoir a redimensionner manuellement a chaque fois (la colonne
        # "Workspace" reste en Stretch et absorbe l'espace restant).
        self.table.resizeColumnsToContents()

    def _selected_entry(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_entries(self) -> list[dict]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        entries = []
        for row in rows:
            item = self.table.item(row, 0)
            if item:
                entries.append(item.data(Qt.UserRole))
        return entries

    def view_output(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "Info", "Selectionnez d'abord un run dans la liste.")
            return

        output_text = self.history_manager.get_output(entry)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Sortie console - {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.get('timestamp', 0)))}")
        dialog.resize(800, 600)
        v = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(console_style())
        text_edit.setPlainText(output_text or "(sortie non disponible)")

        v.addWidget(text_edit)
        dialog.exec_()

    def export_html(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "Info", "Selectionnez d'abord un run dans la liste.")
            return

        default_name = f"rapport_{entry.get('id', 'run')}.html"
        dest_path, _ = QFileDialog.getSaveFileName(self, "Exporter le rapport HTML", default_name, "Fichiers HTML (*.html)")
        if not dest_path:
            return

        output_text = self.history_manager.get_output(entry)
        try:
            export_html_report(entry, output_text, dest_path)
            QMessageBox.information(self, "Export termine", f"Rapport HTML enregistre :\n{dest_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Echec de l'export HTML :\n{exc}")

    def export_junit(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "Info", "Selectionnez d'abord un run dans la liste.")
            return

        junit_path = entry.get("junit_xml_path", "")
        if not junit_path or not os.path.isfile(junit_path):
            QMessageBox.warning(
                self,
                "Indisponible",
                "Aucun rapport JUnit XML n'a ete conserve pour ce run "
                "(il a peut-etre ete supprime, ou le run est trop ancien).",
            )
            return

        default_name = f"junit_{entry.get('id', 'run')}.xml"
        dest_path, _ = QFileDialog.getSaveFileName(self, "Exporter le rapport JUnit XML", default_name, "Fichiers XML (*.xml)")
        if not dest_path:
            return

        try:
            shutil.copyfile(junit_path, dest_path)
            QMessageBox.information(self, "Export termine", f"Rapport JUnit XML enregistre :\n{dest_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Echec de l'export JUnit XML :\n{exc}")

    def compare_runs(self):
        entries = self._selected_entries()
        if len(entries) != 2:
            QMessageBox.information(
                self,
                "Info",
                "Selectionnez exactement 2 runs (Ctrl+clic ou Maj+clic) pour les comparer.",
            )
            return

        older, newer = sorted(entries, key=lambda entry: entry.get("timestamp", 0))
        failed_older = set(older.get("failed_nodeids") or [])
        failed_newer = set(newer.get("failed_nodeids") or [])

        newly_failed = sorted(failed_newer - failed_older)
        newly_fixed = sorted(failed_older - failed_newer)

        def fmt(entry):
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("timestamp", 0)))

        def summary(entry):
            return f"{entry.get('passed', 0)} passed, {entry.get('failed', 0)} failed, {entry.get('skipped', 0)} skipped"

        dialog = QDialog(self)
        dialog.setWindowTitle("Comparaison de deux runs")
        dialog.resize(700, 550)
        v = QVBoxLayout(dialog)

        header = QLabel(
            f"<b>Reference</b> &nbsp; {fmt(older)} &nbsp; <span style='color:#888'>({summary(older)})</span><br>"
            f"<b>Compare a</b> &nbsp;&nbsp; {fmt(newer)} &nbsp; <span style='color:#888'>({summary(newer)})</span>"
        )
        v.addWidget(header)

        v.addWidget(self._build_diff_section(
            f"Nouveaux echecs ({len(newly_failed)})", newly_failed, "FAILED", "Aucun nouvel echec."
        ))
        v.addWidget(self._build_diff_section(
            f"Tests corriges ({len(newly_fixed)})", newly_fixed, "PASSED", "Aucun test corrige."
        ))

        close_button = QPushButton("Fermer")
        close_button.setStyleSheet(neutral_button())
        close_button.clicked.connect(dialog.accept)
        v.addWidget(close_button)

        dialog.exec_()

    def _build_diff_section(self, title: str, nodeids: list[str], status_key: str, empty_text: str) -> QGroupBox:
        box = QGroupBox(title)
        color = STATUS_COLORS.get(status_key)
        if color:
            box.setStyleSheet(f"QGroupBox {{ font-weight: bold; color: {color.name()}; }}")

        layout = QVBoxLayout(box)

        if not nodeids:
            empty_label = QLabel(empty_text)
            empty_label.setStyleSheet("color: #888; font-weight: normal;")
            layout.addWidget(empty_label)
            return box

        list_widget = QListWidget()
        list_widget.setStyleSheet("font-weight: normal; font-size: 12px;")
        for nodeid in nodeids:
            list_widget.addItem(QListWidgetItem(status_icon(status_key), nodeid))
        list_widget.setMaximumHeight(160)
        layout.addWidget(list_widget)
        return box

    def clear_history(self):
        confirm = QMessageBox.question(
            self,
            "Confirmer",
            "Effacer tout l'historique des executions ? Cette action est irreversible.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self.history_manager.clear()
            self.reload_entries()
