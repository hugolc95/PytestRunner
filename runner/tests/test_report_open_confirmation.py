"""Meme confirmation que l'export Excel, avec une URL de fichier locale."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from runner.tests.test_history_window import fenetre, historique


def test_open_report_button_opens_the_saved_html(fenetre, tmp_path, monkeypatch, qtbot):
    path = tmp_path / 'report #1 & protocols.html'
    path.write_text('report')
    opened = []
    monkeypatch.setattr('runner.ui.history_dashboard.QDesktopServices.openUrl', lambda url: opened.append(url) or True)
    fenetre._offer_open_html(path)
    confirmation = fenetre._report_export_confirmation
    assert confirmation.windowTitle() == 'Export complete'
    assert str(path) in confirmation.text()
    assert confirmation.textFormat() == Qt.PlainText
    button = next(button for button in confirmation.buttons() if button.text() == 'Open report')
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: bool(opened))
    assert opened[0].isLocalFile()
    # QUrl rend toujours des '/', y compris sous Windows : comparer des chemins.
    assert Path(opened[0].toLocalFile()) == path.resolve()
    qtbot.waitUntil(lambda: fenetre._report_export_confirmation is None)


def test_close_confirmation_does_not_open_a_browser(fenetre, tmp_path, monkeypatch, qtbot):
    opened = []
    monkeypatch.setattr('runner.ui.history_dashboard.QDesktopServices.openUrl', lambda url: opened.append(url) or True)
    fenetre._offer_open_html(tmp_path / 'report.html')
    confirmation = fenetre._report_export_confirmation
    qtbot.mouseClick(confirmation.button(QMessageBox.Close), Qt.LeftButton)
    qtbot.waitUntil(lambda: fenetre._report_export_confirmation is None)
    assert not opened


def test_open_failure_keeps_the_file_and_shows_its_path(fenetre, tmp_path, monkeypatch, qtbot):
    path = tmp_path / 'report.html'
    path.write_text('report')
    warnings = []
    monkeypatch.setattr('runner.ui.history_dashboard.QDesktopServices.openUrl', lambda _: False)
    monkeypatch.setattr('runner.ui.history_dashboard.QMessageBox.warning', lambda *args: warnings.append(args))
    fenetre._offer_open_html(path)
    confirmation = fenetre._report_export_confirmation
    qtbot.mouseClick(next(button for button in confirmation.buttons() if button.text() == 'Open report'), Qt.LeftButton)
    qtbot.waitUntil(lambda: bool(warnings))
    assert path.read_text() == 'report'
    assert str(path) in warnings[0][-1]
