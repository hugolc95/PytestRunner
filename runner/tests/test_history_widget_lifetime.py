"""Les destructions differees de Qt ne doivent pas invalider les cartes filtrees."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


SCENARIO = r'''
import sys
import time
from pathlib import Path
from PySide6 import QtCore
from PySide6.QtCore import QCoreApplication, QEvent, QStandardPaths
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

root = Path(sys.argv[1])
kind = sys.argv[2]
original_settings = QtCore.QSettings
class Settings(original_settings):
    def __init__(self, *args, **kwargs):
        super().__init__(str(root / 'settings.ini'), original_settings.IniFormat)
QtCore.QSettings = Settings
QStandardPaths.setTestModeEnabled(True)
location = QStandardPaths.writableLocation
QStandardPaths.writableLocation = staticmethod(lambda key: str(root / 'app-data')
    if key in (QStandardPaths.AppDataLocation, QStandardPaths.AppLocalDataLocation) else location(key))

from runner.domain.history import History, RunEntry
from runner.ui.history_dashboard import HistoryWindow

app = QApplication([])
history = History(root / 'history')
for number in range(3):
    history.add(RunEntry(str(number), time.time() - number * 60, str(root),
        reader='Reader A', nodeids=('test_x.py::test_a',),
        counts={'FAILED': 1} if number == 1 else {'PASSED': 1},
        failed_nodeids=('test_x.py::test_a',) if number == 1 else ()))
window = HistoryWindow(history)
window.show()

def settle():
    app.processEvents()
    # Une boucle processEvents seule ne livre pas toujours DeferredDelete.
    # Le crash se produisait justement au passage dans la boucle suivante.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert all(isValid(card) for _, card in window._cards), 'A cached card was destroyed by Qt'
    for item, card in window._cards:
        if window.run_list.row(item) >= 0:
            host = window.run_list.itemWidget(item)
            assert host is not None and isValid(host)
            assert host is card or host.isAncestorOf(card)

settle()
for iteration in range(12):
    if kind == 'filters':
        window._set_issue_filter(True)
        settle()
        window.search.setText('test_x')
        settle()
        window.search.setText('no matching run')
        settle()
        window.search.clear()
        settle()
        window._set_issue_filter(False)
    elif kind == 'updates':
        history.rename_run('1', 'Changed ' + str(iteration))
        window.refresh()
    elif kind == 'navigation':
        window._set_issue_filter(True)
        settle()
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index)
            settle()
        window.hide()
        settle()
        window.show()
        window._set_issue_filter(False)
    settle()
    window.hide()
    settle()
    window.show()
    settle()
history.clear()
window.refresh()
settle()
assert window.run_list.count() == 0
window.close()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
print('History lifecycle OK: ' + kind)
'''


@pytest.mark.parametrize('scenario', ['filters', 'updates', 'navigation'])
def test_history_cards_survive_filters_and_deferred_deletion(tmp_path, scenario):
    # Un segfault Qt tuerait toute la suite : ce parcours doit rester dans
    # son propre processus et rapporter aussi la pile native en cas d'echec.
    script = tmp_path / 'history_lifecycle.py'
    script.write_text(SCENARIO, encoding='utf-8')
    repo = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONPATH': str(repo)}
    completed = subprocess.run([sys.executable, '-X', 'faulthandler', str(script),
                                str(tmp_path), scenario], cwd=repo, env=env,
                               capture_output=True, text=True, timeout=40)
    assert completed.returncode == 0, completed.stdout + '\n' + completed.stderr
    assert 'History lifecycle OK' in completed.stdout
