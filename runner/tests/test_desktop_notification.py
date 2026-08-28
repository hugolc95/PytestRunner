"""Notification systeme en fin de run.

Le run finit souvent pendant qu'on regarde autre chose : rien d'autre ne le
signale une fois la fenetre hors de vue, d'ou la notification desktop.
"""

from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QSystemTrayIcon

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree
from runner.domain.workspace import Workspace

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
    "suite/perso/test_cert.py::test_chr",
]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    w = MainWindow()
    w.workspace = Workspace.load(str(tmp_path))
    w.model.set_tree(build_tree(NODEIDS))
    w.model.set_readers((Reader("", 0),))
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _messages(monkeypatch, fenetre, disponible=True):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        staticmethod(lambda: disponible))
    appels = []
    monkeypatch.setattr(fenetre._tray, "showMessage",
                        lambda titre, detail, icone: appels.append((titre, detail, icone)))
    return appels


def test_a_finished_run_notifies_with_all_four_counts(fenetre, monkeypatch):
    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    fenetre.model.apply_outcome(NODEIDS[1], Status.FAILED, 0)
    fenetre.model.apply_outcome(NODEIDS[2], Status.SKIPPED, 0)
    appels = _messages(monkeypatch, fenetre)

    fenetre._on_run_finished([])

    assert len(appels) == 1
    titre, detail, icone = appels[0]
    assert "1 passed" in detail
    assert "1 failed" in detail
    assert "1 skipped" in detail
    # Le zero est explicite : une notification qui disparait ne se relit pas,
    # contrairement aux pastilles de la barre d'etat qui s'eteignent a zero.
    assert "0 error" in detail


def test_a_clean_run_uses_the_information_icon(fenetre, monkeypatch):
    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    appels = _messages(monkeypatch, fenetre)

    fenetre._on_run_finished([])

    assert appels[0][2] == QSystemTrayIcon.Information


def test_a_run_with_failures_uses_the_critical_icon(fenetre, monkeypatch):
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    appels = _messages(monkeypatch, fenetre)

    fenetre._on_run_finished([])

    assert appels[0][2] == QSystemTrayIcon.Critical


def test_a_stopped_run_does_not_notify(fenetre, monkeypatch):
    from runner.domain.models import Reader as ReaderModel
    from runner.domain.execution import ReaderReport

    appels = _messages(monkeypatch, fenetre)
    rapport = ReaderReport(reader=ReaderModel("", 0), cancelled=True)

    fenetre._on_run_finished([rapport])

    assert appels == []


def test_nothing_happens_without_a_system_tray(fenetre, monkeypatch):
    fenetre.model.apply_outcome(NODEIDS[0], Status.PASSED, 0)
    appels = _messages(monkeypatch, fenetre, disponible=False)

    fenetre._on_run_finished([])

    assert appels == []
