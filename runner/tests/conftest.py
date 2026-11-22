"""Reglages communs aux tests de l'interface PySide6."""

from __future__ import annotations

import gc
import sys
import time

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

    from PySide6.QtCore import QProcess, QThread
    for widget in application.topLevelWidgets():
        if widget in avant:
            continue
        widget.close()
        # Une fenetre peut refuser de se fermer tant qu'une sauvegarde
        # d'historique ou une collecte tourne. La detruire quand meme
        # detruirait un QThread actif : abandon natif du processus.
        for thread in widget.findChildren(QThread):
            if thread.isRunning():
                thread.wait(30000)
        # Idem pour un sous-processus (decouverte des lecteurs, ATR) : le
        # tuer et attendre sa fin plutot que de le laisser a la destruction.
        for process in widget.findChildren(QProcess):
            if process.state() != QProcess.NotRunning:
                process.kill()
                process.waitForFinished(5000)
        widget.deleteLater()

    # `processEvents()` n'execute pas les `deleteLater()` : la fenetre d'un
    # test etait detruite au milieu du test SUIVANT, pendant que ses filtres
    # d'evenements tournaient -- segfault natif intermittent, "worker crashed"
    # en CI. Detruire ici, puis ramasser les enveloppes Python orphelines,
    # garde chaque test seul avec ses propres widgets.
    from PySide6.QtCore import QEvent
    application.processEvents()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    application.processEvents()


# Au-dela, une boite modale ouverte pendant un test est consideree oubliee.
DELAI_DIALOGUE_MODAL = 20.0


def _texte_de(modale) -> str:
    """Tout le texte d'une boite : en CI, c'est le seul diagnostic visible.

    Ne leve jamais : une erreur ici empecherait de fermer la boite, et le
    worker resterait bloque.
    """
    morceaux = []
    try:
        from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTextEdit
        morceaux.append(modale.windowTitle())
        for nom in ("text", "informativeText", "detailedText"):
            valeur = getattr(modale, nom, None)
            if callable(valeur) and valeur():
                morceaux.append(valeur())
        for classe in (QLabel, QPlainTextEdit, QTextEdit):
            for enfant in modale.findChildren(classe):
                texte = enfant.toPlainText() if hasattr(enfant, "toPlainText") else enfant.text()
                if texte and texte not in morceaux:
                    morceaux.append(texte)
    except Exception as exc:  # pragma: no cover - diagnostic seulement
        morceaux.append(f"(texte illisible : {exc})")
    return " -- ".join(morceaux)[:1500]


@pytest.fixture(autouse=True)
def sans_dialogue_bloquant(qapp):
    """Ferme une boite modale restee ouverte et fait echouer le test.

    Une collecte ralentie par la charge (suite en parallele) echouait et
    l'application ouvrait sa fenetre d'erreur modale : `exec()` attendait un
    clic qui ne viendrait jamais, et le delai de pytest-timeout ne peut pas
    interrompre une boucle Qt. Le worker restait bloque jusqu'a la limite
    de la CI. Ici, le test echoue avec le titre et le texte de la boite.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    fermees: list[str] = []
    ouvertes: dict[int, float] = {}

    def surveiller():
        try:
            fermer_si_oubliee()
        except Exception:  # pragma: no cover - ne jamais laisser un worker bloque
            modale = QApplication.activeModalWidget()
            if modale is not None:
                modale.close()

    def fermer_si_oubliee():
        modale = QApplication.activeModalWidget()
        if modale is None:
            ouvertes.clear()
            return
        debut = ouvertes.setdefault(id(modale), time.monotonic())
        if time.monotonic() - debut < DELAI_DIALOGUE_MODAL:
            return
        fermees.append(_texte_de(modale))
        ouvertes.pop(id(modale), None)
        if isinstance(modale, QDialog):
            modale.reject()
        else:
            modale.close()

    minuteur = QTimer()
    minuteur.setInterval(500)
    minuteur.timeout.connect(surveiller)
    minuteur.start()
    yield
    minuteur.stop()
    if fermees:
        pytest.fail("Boite de dialogue modale restee ouverte pendant le test : "
                    + " | ".join(fermees), pytrace=False)


@pytest.fixture(autouse=True)
def verifications_python_oubliees():
    """Chaque test repart d'un cache de verification de Python vide.

    Ce cache est global au processus. Un test qui simule un Python en panne
    (sous-processus remplace, delai depasse) y laissait un echec pour
    `sys.executable` ; les tests suivants du meme worker xdist voyaient alors
    "Python interpreter not usable", la collecte refusee et les runs en
    erreur -- au hasard de la repartition des tests entre workers.
    """
    from runner.domain import interpreter

    interpreter.forget_probe()
    yield
    interpreter.forget_probe()
