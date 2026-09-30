"""ATR de la carte sous le selecteur de lecteur, suivi par IsCardPresent.

La surveillance tourne pour de vrai dans un sous-processus Python, contre un
faux `Reader.PyHubreader` pose sur le PYTHONPATH -- meme forme que la vraie
classe. Chaque appel qui touche le lecteur (OpenReader / CloseReader) laisse
une trace dans `journal.txt` : c'est elle qui prouve que l'ATR n'est lu qu'a
l'arrivee d'une carte, et que le lecteur est toujours relache.
"""

import os
import queue
import subprocess
import sys
import textwrap
import threading
import time

import pytest
from PySide6.QtCore import QProcess, QSettings

from runner.domain import reader_discovery
from runner.domain.reader_discovery import ATR_NO_CARD, ATR_OK, ATR_UNAVAILABLE, parse_atr_line
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.reader_selector import ReaderAtrField

CARTE = "OMNIKEY CardMan 3x21 0"
VIDE = "Cosmo11SecuredSLC27G"
ATR_CARTE = "3B8F8001804F0CA000000306"

# Carte presente dans CARTE tant que `retiree` n'existe pas dans le dossier
# courant ; jamais de carte dans VIDE.
HUB_REEL = f'''
import pathlib

def trace(ligne):
    with open("journal.txt", "a") as f:
        f.write(ligne + "\\n")

class pyHubReader:
    def __init__(self, readerName="", logger=None):
        self.readerName = readerName
    def IsCardPresent(self):
        return self.readerName == {CARTE!r} and not pathlib.Path("retiree").exists()
    def OpenReader(self) -> int:
        trace("open " + self.readerName)
        self.connection = 1
        return 0
    def GetATR(self) -> bytes:
        if not hasattr(self, "connection"):
            raise Exception("GetATR: There is no connection")
        if self.readerName == {CARTE!r} and not pathlib.Path("retiree").exists():
            return bytes.fromhex({ATR_CARTE!r})
        raise Exception("Failed to get ATR. Error code: 2148532236")
    def CloseReader(self, free_library=False) -> None:
        trace("close " + self.readerName)
'''


def _faux_hub(tmp_path, corps=HUB_REEL):
    paquet = tmp_path / "fakehub" / "Reader"
    paquet.mkdir(parents=True, exist_ok=True)
    (paquet / "__init__.py").write_text("")
    (paquet / "PyHubreader.py").write_text(textwrap.dedent(corps))
    return str(tmp_path / "fakehub")


def _journal(tmp_path):
    chemin = tmp_path / "journal.txt"
    return chemin.read_text().splitlines() if chemin.exists() else []


class _Moniteur:
    """PROBE_MONITOR lance comme le ferait l'interface : stdin garde ouvert."""

    def __init__(self, tmp_path, monkeypatch, lecteur=CARTE, corps=HUB_REEL):
        monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, corps))
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-c", reader_discovery.PROBE_MONITOR, lecteur, "0.05"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=tmp_path, env=reader_discovery.discovery_environment())
        self.lignes = queue.Queue()
        threading.Thread(target=self._lire, daemon=True).start()

    def _lire(self):
        for ligne in self.proc.stdout:
            evenement = parse_atr_line(ligne.strip())
            if evenement:
                self.lignes.put(evenement)

    def suivant(self, delai=10):
        return self.lignes.get(timeout=delai)

    def rien_pendant(self, secondes):
        try:
            evenement = self.lignes.get(timeout=secondes)
        except queue.Empty:
            return True
        raise AssertionError(f"evenement inattendu : {evenement}")

    def fermer(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(5)


@pytest.fixture
def moniteur(tmp_path, monkeypatch):
    lances = []

    def lancer(**kwargs):
        m = _Moniteur(tmp_path, monkeypatch, **kwargs)
        lances.append(m)
        return m

    yield lancer
    for m in lances:
        m.fermer()


# ------------------------------------------------------------------ sonde


def test_a_card_is_read_once_as_compact_hex_and_released(moniteur, tmp_path):
    m = moniteur()
    assert m.suivant()[:2] == (ATR_OK, ATR_CARTE)
    # La carte reste : IsCardPresent tourne, mais l'ATR n'est plus relu.
    assert m.rien_pendant(0.6)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]


def test_removal_is_shown_without_reading_and_insertion_reads_again(moniteur, tmp_path):
    m = moniteur()
    assert m.suivant()[0] == ATR_OK

    (tmp_path / "retiree").write_text("")
    etat, _, detail, _ = m.suivant()
    assert (etat, detail) == (ATR_NO_CARD, "No card detected in the reader.")
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]

    (tmp_path / "retiree").unlink()
    assert m.suivant()[:2] == (ATR_OK, ATR_CARTE)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"] * 2


def test_an_empty_reader_is_never_opened(moniteur, tmp_path):
    m = moniteur(lecteur=VIDE)
    assert m.suivant()[0] == ATR_NO_CARD
    assert m.rien_pendant(0.3)
    assert _journal(tmp_path) == []


def test_a_present_card_whose_atr_cannot_be_read_is_no_card_and_released(moniteur, tmp_path):
    corps = HUB_REEL.replace("return self.readerName == ", "return True or self.readerName == ")
    m = moniteur(lecteur=VIDE, corps=corps)
    etat, _, detail, _ = m.suivant()
    assert etat == ATR_NO_CARD and "Failed to get ATR" in detail
    assert _journal(tmp_path) == [f"open {VIDE}", f"close {VIDE}"]


def test_an_empty_atr_means_no_card(moniteur):
    corps = HUB_REEL.replace(f"return bytes.fromhex({ATR_CARTE!r})", 'return b""')
    m = moniteur(corps=corps)
    assert m.suivant()[0] == ATR_NO_CARD


def test_a_failing_iscardpresent_reads_once_and_stops(moniteur, tmp_path):
    """Sans detection possible, une lecture quand meme -- puis plus rien :
    il reste le bouton, jamais une boucle de lectures."""
    corps = HUB_REEL.replace(
        f"        return self.readerName == {CARTE!r} and not pathlib.Path(\"retiree\").exists()",
        "        raise Exception(\"IsCardPresent failed. Error code: 1\")")
    m = moniteur(corps=corps)
    etat, atr, _, remarque = m.suivant()
    assert (etat, atr) == (ATR_OK, ATR_CARTE)
    assert "IsCardPresent failed" in remarque
    assert m.proc.wait(10) == 0
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]


def test_an_unusable_pyhubreader_is_unavailable(moniteur):
    m = moniteur(corps="raise ImportError('DLL load failed')")
    etat, _, detail, _ = m.suivant()
    assert etat == ATR_UNAVAILABLE and "DLL load failed" in detail
    assert m.proc.wait(10) == 0


def test_closing_stdin_stops_the_monitor(moniteur):
    """L'interface fermee ou plantee ferme ce stdin : le processus ne doit
    pas continuer seul a interroger le lecteur."""
    m = moniteur()
    m.suivant()
    m.proc.stdin.close()
    assert m.proc.wait(10) == 0


def test_the_reader_name_is_passed_as_data_not_code(moniteur, tmp_path):
    nom = "x'); import os; os._exit(3) #"
    m = moniteur(lecteur=nom)
    assert m.suivant()[0] == ATR_NO_CARD
    assert m.proc.poll() is None


def test_unrelated_lines_are_ignored():
    assert parse_atr_line("Traceback (most recent call last):") is None
    assert parse_atr_line("HUBATR_JSON:{not json") is None
    assert parse_atr_line('HUBATR_JSON:{"state": "weird"}') is None


# ------------------------------------------------------------------ fenetre


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    QSettings(ORG, APP).clear()
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path))
    monkeypatch.setattr(ReaderAtrField, "INTERVALLE_S", 0.05)
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_effective_interpreter", lambda: sys.executable)
    yield window
    window.reader_atr.release()
    window.close()


def _charger(window, tmp_path, yaml):
    (tmp_path / "config.yml").write_text(yaml, encoding="utf-8")
    window.workspace = Workspace.load(str(tmp_path))
    window._update_actions()


def _pret(fenetre, qtbot, tmp_path, lecteur=CARTE, etat=ATR_OK):
    _charger(fenetre, tmp_path, f"Reader: {lecteur}\n")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == etat, timeout=15000)


def _arrete(champ):
    return champ._process.state() == QProcess.NotRunning


def test_the_field_shows_the_atr_of_the_configured_reader(fenetre, qtbot, tmp_path):
    _pret(fenetre, qtbot, tmp_path)
    assert fenetre.reader_atr.text() == ATR_CARTE
    assert ATR_CARTE in fenetre.reader_atr.toolTip()


def test_a_reader_without_card_shows_no_card_in_reader(fenetre, qtbot, tmp_path):
    _pret(fenetre, qtbot, tmp_path, lecteur=VIDE, etat=ATR_NO_CARD)
    assert fenetre.reader_atr.text() == ReaderAtrField.NO_CARD
    assert fenetre.reader_atr.property("state") == ATR_NO_CARD


def test_the_field_follows_the_reader_control_visibility(fenetre, tmp_path):
    _charger(fenetre, tmp_path, "Component: PQC\n")
    assert not fenetre.reader_controls.isVisibleTo(fenetre)


def test_the_card_is_followed_but_its_atr_read_only_on_arrival(fenetre, qtbot, tmp_path):
    _pret(fenetre, qtbot, tmp_path)
    qtbot.wait(400)  # plusieurs verifications IsCardPresent
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]

    (tmp_path / "retiree").write_text("")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)
    (tmp_path / "retiree").unlink()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_OK, timeout=15000)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"] * 2


def test_the_refresh_button_reads_the_card_again(fenetre, qtbot, tmp_path):
    _pret(fenetre, qtbot, tmp_path)
    [bouton] = fenetre.reader_atr.actions()
    bouton.trigger()
    qtbot.waitUntil(lambda: len(_journal(tmp_path)) == 4, timeout=15000)
    assert fenetre.reader_atr.state == ATR_OK


def test_nothing_touches_the_reader_during_a_run(fenetre, qtbot, tmp_path, monkeypatch):
    _pret(fenetre, qtbot, tmp_path)
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    fenetre._update_actions()
    qtbot.waitUntil(lambda: _arrete(fenetre.reader_atr), timeout=5000)

    (tmp_path / "retiree").write_text("")  # la carte change pendant le run
    qtbot.wait(300)
    fenetre._update_actions()
    assert _arrete(fenetre.reader_atr)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]

    # Des la fin du run, la surveillance repart et voit le retrait.
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: False))
    fenetre._update_actions()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)


def test_starting_a_run_kills_the_monitor_without_waiting(fenetre, qtbot, tmp_path, monkeypatch):
    """Ni gene pour le run, ni interface figee en attendant la fin."""
    _pret(fenetre, qtbot, tmp_path)
    assert not _arrete(fenetre.reader_atr)
    attentes = []
    monkeypatch.setattr(fenetre.reader_atr._process, "waitForFinished",
                        lambda *a: attentes.append(a) or True)
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    fenetre._update_actions()
    assert attentes == []
    qtbot.waitUntil(lambda: _arrete(fenetre.reader_atr), timeout=5000)
    assert fenetre.reader_atr.state == ATR_OK


def test_a_failing_iscardpresent_leaves_the_button_only(qtbot, tmp_path, monkeypatch):
    corps = HUB_REEL.replace(
        f"        return self.readerName == {CARTE!r} and not pathlib.Path(\"retiree\").exists()",
        "        raise Exception(\"IsCardPresent failed. Error code: 1\")")
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, corps))
    champ = ReaderAtrField()
    qtbot.addWidget(champ)
    champ.set_context(str(tmp_path), sys.executable, CARTE)
    qtbot.waitUntil(lambda: champ.state == ATR_OK and _arrete(champ), timeout=15000)
    assert "Use the refresh button" in champ.toolTip()
    qtbot.wait(300)
    assert _arrete(champ)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]


def test_a_missing_pyhubreader_is_unavailable_and_not_retried(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    champ = ReaderAtrField()
    qtbot.addWidget(champ)
    champ.set_context(str(tmp_path), sys.executable, CARTE)
    qtbot.waitUntil(lambda: champ.state == ATR_UNAVAILABLE and _arrete(champ), timeout=15000)
    assert champ.text() == "ATR unavailable"
    qtbot.wait(300)
    assert _arrete(champ)


def test_closing_the_window_stops_the_monitor(fenetre, qtbot, tmp_path):
    _pret(fenetre, qtbot, tmp_path)
    fenetre.close()
    qtbot.waitUntil(lambda: _arrete(fenetre.reader_atr), timeout=5000)


def test_a_long_atr_shrinks_until_it_fits_entirely(qtbot):
    """Un ATR se lit en entier : faute de place, la police retrecit plutot
    que de couper la fin -- et reprend sa taille des qu'il tient."""
    champ = ReaderAtrField()
    qtbot.addWidget(champ)
    champ.resize(champ.LARGEUR_MAX, 26)
    champ.show()
    long_atr = bytes(range(0x3B, 0x3B + 33)).hex().upper()

    champ._show(ATR_OK, long_atr, "")
    taille = int(champ.styleSheet().removeprefix("font-size: ").removesuffix("px;"))
    assert taille < 12
    assert champ._text_width(taille) + champ._margin() <= champ.width()

    champ._show(ATR_OK, "3B8F8001", "")
    assert champ.styleSheet() == ""


def test_the_dot_is_green_with_a_card_red_without_and_absent_otherwise(qtbot):
    """Pas d'etiquette "ATR" : une pastille devant le texte dit l'etat."""
    from PySide6.QtGui import QColor

    from runner.domain.models import Status
    from runner.ui import tokens as t

    champ = ReaderAtrField()
    qtbot.addWidget(champ)
    champ.resize(400, 24)
    champ.show()

    def pixel_pastille():
        image = champ.grab().toImage()
        x = champ.PADDING + champ.PASTILLE // 2
        return QColor(image.pixel(x, champ.height() // 2))

    def proche(a, b):
        return all(abs(x - y) <= 40 for x, y in zip(a.getRgb()[:3], b.getRgb()[:3]))

    champ._show(ATR_OK, "3B8F8001", "")
    assert champ.dot_color() == QColor(t.status_color(Status.PASSED))
    assert proche(pixel_pastille(), QColor(t.status_color(Status.PASSED)))

    champ._show(ATR_NO_CARD, ReaderAtrField.NO_CARD, "")
    assert champ.dot_color().rgb() == QColor(t.status_color(Status.FAILED)).rgb()

    champ._show("reading", "Reading card…", "")
    assert champ.dot_color() is None
