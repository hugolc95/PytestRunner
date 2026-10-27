"""Reglages communs aux tests de l'interface PySide6."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def donnees_utilisateur_isolees(tmp_path_factory, monkeypatch):
    """Aucun test ne touche aux reglages, profils ni a l'historique reels.

    `QSettings(ORG, APP)` ecrit dans le registre de l'utilisateur : une
    vingtaine de tests l'effacaient (`.clear()`) pour partir d'un etat propre,
    et chaque lancement de la suite remettait ses preferences a zero. Ici,
    toute construction par organisation/application -- dans l'appli comme
    dans les tests -- va dans un fichier INI propre a ce test. La forme
    explicite `QSettings(fichier, IniFormat)` reste intacte : des tests s'en
    servent pour simuler un redemarrage.
    """
    from PySide6 import QtCore
    from PySide6.QtCore import QStandardPaths

    original = getattr(QtCore.QSettings, "_original_class", QtCore.QSettings)
    dossier = tmp_path_factory.mktemp("donnees")
    ini = str(dossier / "settings.ini")

    class SettingsIsoles(original):
        _original_class = original

        def __init__(self, *args, **kwargs):
            par_fichier = len(args) >= 2 and isinstance(args[1], original.Format)
            if par_fichier:
                super().__init__(*args, **kwargs)
            else:
                super().__init__(ini, original.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", SettingsIsoles)
    # Modules de l'appli ET modules de test qui ont importe la classe a leur
    # chargement : `from PySide6.QtCore import QSettings` en tete de fichier
    # garde sinon l'originale. Un module importe PENDANT un test precedent a
    # garde la classe isolee de ce test-la (son fichier) : elle aussi est
    # remplacee, sinon les reglages fuient d'un test a l'autre.
    for nom, module in list(sys.modules.items()):
        if module is None or nom.startswith(("PySide6", "shiboken")):
            continue
        actuelle = getattr(module, "QSettings", None)
        if actuelle is original or getattr(actuelle, "_original_class", None) is original:
            monkeypatch.setattr(module, "QSettings", SettingsIsoles)
    QStandardPaths.setTestModeEnabled(True)
    import runner.domain.history as history
    monkeypatch.setattr(history, "dossier",
                        lambda: (dossier / "history").mkdir(exist_ok=True) or dossier / "history")


@pytest.fixture
def isolated_run_state(tmp_path, monkeypatch):
    """Keep profile integration tests away from real sessions and run copies."""
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr("runner.ui.main_window.QSettings", lambda *_: settings)
    monkeypatch.setattr("runner.domain.history.dossier", lambda: tmp_path / "history")


@pytest.fixture(autouse=True)
def sans_widget_orphelin():
    """Detruit les widgets sans parent qu'un test laisse derriere lui."""
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    avant = set(application.topLevelWidgets()) if application is not None else set()

    yield

    application = QApplication.instance()
    if application is None:
        return

    for widget in application.topLevelWidgets():
        if widget in avant:
            continue
        widget.close()
        widget.deleteLater()

    application.processEvents()
