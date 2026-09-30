"""ATR de la carte sous le selecteur de lecteur.

La sonde tourne pour de vrai dans un sous-processus Python, contre un faux
`Reader.PyHubreader` pose sur le PYTHONPATH : c'est tout le chemin reel --
lancement, API tolerante, format de l'ATR, analyse de la reponse -- sans
lecteur physique.
"""

import subprocess
import sys
import textwrap

import pytest
from PySide6.QtCore import QProcess, QSettings

from runner.domain import reader_discovery
from runner.domain.reader_discovery import ATR_NO_CARD, ATR_OK, ATR_UNAVAILABLE, parse_atr_output
from runner.domain.workspace import Workspace
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.reader_selector import ReaderAtrField

CARTE = "OMNIKEY CardMan 3x21 0"
VIDE = "Cosmo11SecuredSLC27G"


def _faux_hub(tmp_path, corps):
    paquet = tmp_path / "fakehub" / "Reader"
    paquet.mkdir(parents=True)
    (paquet / "__init__.py").write_text("")
    (paquet / "PyHubreader.py").write_text(textwrap.dedent(corps))
    return str(tmp_path / "fakehub")


# Meme forme que la vraie classe (SmartcardFramework, Reader/PyHubreader.py) :
# lecteur choisi a la construction, OpenReader/GetATR/CloseReader sans
# argument, GetATR qui leve sans connexion ou sans carte. Chaque appel laisse
# une trace dans `journal.txt` pour verifier l'ordre et la liberation.
HUB_REEL = f'''
import pathlib

def trace(ligne):
    with open("journal.txt", "a") as f:
        f.write(ligne + "\\n")

class pyHubReader:
    def __init__(self, readerName="", logger=None):
        self.readerName = readerName
    def OpenReader(self) -> int:
        trace("open " + self.readerName)
        self.connection = 1
        return 0
    def GetATR(self) -> bytes:
        if not hasattr(self, "connection"):
            raise Exception("GetATR: There is no connection")
        if pathlib.Path("retiree").exists():
            raise Exception("Failed to get ATR. Error code: 2148532236")
        if self.readerName == {CARTE!r}:
            return bytes.fromhex("3B8F8001804F0CA000000306")
        raise Exception("Failed to get ATR. Error code: 2148532236")
    def CloseReader(self, free_library=False) -> None:
        trace("close " + self.readerName)
'''


def _sonder(tmp_path, corps, lecteur, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, corps))
    monkeypatch.chdir(tmp_path)
    fini = subprocess.run(
        [sys.executable, "-c", reader_discovery.PROBE_ATR, lecteur],
        capture_output=True, text=True, timeout=30,
        env=reader_discovery.discovery_environment())
    return parse_atr_output(fini.stdout, fini.stderr)


def _journal(tmp_path):
    chemin = tmp_path / "journal.txt"
    return chemin.read_text().splitlines() if chemin.exists() else []


def test_a_card_gives_its_atr_as_compact_hex(tmp_path, monkeypatch):
    etat, atr, _ = _sonder(tmp_path, HUB_REEL, CARTE, monkeypatch)
    assert (etat, atr) == (ATR_OK, "3B8F8001804F0CA000000306")


def test_the_reader_is_opened_then_released(tmp_path, monkeypatch):
    """Les tests ont besoin du lecteur : la connexion ouverte pour lire l'ATR
    doit etre refermee aussitot."""
    _sonder(tmp_path, HUB_REEL, CARTE, monkeypatch)
    assert _journal(tmp_path) == [f"open {CARTE}", f"close {CARTE}"]


def test_a_reader_without_card_says_so_and_is_still_released(tmp_path, monkeypatch):
    etat, atr, detail = _sonder(tmp_path, HUB_REEL, VIDE, monkeypatch)
    assert (etat, atr) == (ATR_NO_CARD, "")
    assert "Failed to get ATR" in detail
    assert _journal(tmp_path) == [f"open {VIDE}", f"close {VIDE}"]


def test_a_reader_that_cannot_be_opened_means_no_card(tmp_path, monkeypatch):
    corps = HUB_REEL.replace(
        "        self.connection = 1\n        return 0",
        "        raise Exception(\"OpenReader failed. Error code: 2148532236\")")
    assert corps != HUB_REEL
    etat, _, detail = _sonder(tmp_path, corps, CARTE, monkeypatch)
    assert etat == ATR_NO_CARD
    assert "OpenReader failed" in detail


def test_an_empty_atr_means_no_card(tmp_path, monkeypatch):
    corps = HUB_REEL.replace('return bytes.fromhex("3B8F8001804F0CA000000306")', 'return b""')
    assert corps != HUB_REEL
    assert _sonder(tmp_path, corps, CARTE, monkeypatch)[0] == ATR_NO_CARD


def test_a_missing_pyhubreader_is_not_mistaken_for_an_empty_reader(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    fini = subprocess.run([sys.executable, "-c", reader_discovery.PROBE_ATR, CARTE],
                          capture_output=True, text=True, timeout=30,
                          env=reader_discovery.discovery_environment())
    etat, _, detail = parse_atr_output(fini.stdout, fini.stderr)
    assert etat == ATR_UNAVAILABLE
    assert "Reader" in detail


def test_unreadable_output_is_unavailable():
    assert parse_atr_output("", "Traceback\nOSError: boom")[0] == ATR_UNAVAILABLE
    assert parse_atr_output("", "")[2] == "No valid response from HubReader."


def test_the_reader_name_is_passed_as_data_not_code(tmp_path, monkeypatch):
    """Un nom de lecteur saisi a la main ne doit jamais s'executer."""
    nom = "x'); import os; os._exit(3) #"
    etat, _, _ = _sonder(tmp_path, HUB_REEL, nom, monkeypatch)
    assert etat == ATR_NO_CARD
    assert _journal(tmp_path) == [f"open {nom}", f"close {nom}"]


# ------------------------------------------------------------------ fenetre


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    QSettings(ORG, APP).clear()
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, HUB_REEL))
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_effective_interpreter", lambda: sys.executable)
    yield window
    window.reader_atr.stop()
    window.close()


def _charger(window, tmp_path, yaml):
    (tmp_path / "config.yml").write_text(yaml, encoding="utf-8")
    window.workspace = Workspace.load(str(tmp_path))
    window._update_actions()


def test_the_field_shows_the_atr_of_the_configured_reader(fenetre, qtbot, tmp_path):
    _charger(fenetre, tmp_path, f"Reader: {CARTE}\n")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_OK, timeout=15000)
    assert fenetre.reader_atr.text() == "3B8F8001804F0CA000000306"
    assert fenetre.reader_atr.text() in fenetre.reader_atr.toolTip()


def test_a_reader_without_card_shows_no_card_in_reader(fenetre, qtbot, tmp_path):
    _charger(fenetre, tmp_path, f"Reader: {VIDE}\n")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)
    assert fenetre.reader_atr.text() == ReaderAtrField.NO_CARD
    assert fenetre.reader_atr.property("state") == ATR_NO_CARD


def test_the_field_follows_the_reader_control_visibility(fenetre, tmp_path):
    _charger(fenetre, tmp_path, "Component: PQC\n")
    assert not fenetre.reader_controls.isVisibleTo(fenetre)


def test_nothing_is_read_while_a_run_holds_the_reader(fenetre, qtbot, tmp_path, monkeypatch):
    """Les tests ont besoin du lecteur pendant le run ; la carte a pu changer
    entre-temps, donc on la relit des qu'il se termine."""
    _charger(fenetre, tmp_path, f"Reader: {CARTE}\n")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_OK, timeout=15000)

    lancements = []
    monkeypatch.setattr(fenetre.reader_atr, "refresh",
                        lambda *a, _r=fenetre.reader_atr.refresh: (lancements.append(1), _r()))
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    fenetre._update_actions()
    # Meme un changement de lecteur en plein run ne doit rien lancer.
    _charger(fenetre, tmp_path, f"Reader: {VIDE}\n")
    assert lancements == []
    assert fenetre.reader_atr._process.state() == QProcess.NotRunning

    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: False))
    fenetre._update_actions()
    assert lancements == [1]
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)


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


# ------------------------------------------- relecture sur changement de carte


class _Carte:
    """Presence simulee, a la place de PC/SC : ce que `CardPresence.check`
    rendrait -- (presente, compteur d'evenements), ou None si inconnue."""

    def __init__(self, presente=True):
        self.presente, self.evenements, self.appels = presente, 0, 0

    def __call__(self, lecteur):
        self.appels += 1
        return self.presente, self.evenements

    def retirer(self, tmp_path):
        self.presente, self.evenements = False, self.evenements + 1
        (tmp_path / "retiree").write_text("")

    def inserer(self, tmp_path):
        self.presente, self.evenements = True, self.evenements + 1
        (tmp_path / "retiree").unlink(missing_ok=True)


def _pret(fenetre, qtbot, tmp_path, carte=None):
    carte = carte or _Carte()
    fenetre.reader_atr.presence = carte
    fenetre.show()
    _charger(fenetre, tmp_path, f"Reader: {CARTE}\n")
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_OK, timeout=15000)
    return carte


def _lectures(champ, monkeypatch):
    lancements = []
    reel = champ.refresh
    monkeypatch.setattr(champ, "refresh", lambda *a, **k: (lancements.append(k), reel(*a, **k)))
    return lancements


def test_nothing_is_read_while_the_card_stays_the_same(fenetre, qtbot, tmp_path, monkeypatch):
    """Le coeur de la demande : plus d'ouverture du lecteur a intervalle
    regulier -- on regarde seulement si la carte a change."""
    carte = _pret(fenetre, qtbot, tmp_path)
    lancements = _lectures(fenetre.reader_atr, monkeypatch)
    for _ in range(5):
        fenetre.reader_atr._tick()
    assert carte.appels >= 5
    assert lancements == []
    assert fenetre.reader_atr._process.state() == QProcess.NotRunning


def test_removing_then_inserting_the_card_is_followed(fenetre, qtbot, tmp_path):
    carte = _pret(fenetre, qtbot, tmp_path)

    carte.retirer(tmp_path)
    fenetre.reader_atr._tick()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)

    carte.inserer(tmp_path)
    fenetre.reader_atr._tick()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_OK, timeout=15000)


def test_a_card_swapped_between_two_checks_is_read_again(fenetre, qtbot, tmp_path, monkeypatch):
    """Retiree puis remise entre deux verifications : toujours "presente",
    mais le compteur d'evenements de Windows a bouge -- c'est peut-etre une
    autre carte."""
    carte = _pret(fenetre, qtbot, tmp_path)
    lancements = _lectures(fenetre.reader_atr, monkeypatch)
    carte.evenements += 2
    fenetre.reader_atr._tick()
    assert lancements == [{"quiet": True}]


def test_an_automatic_read_does_not_flash_reading_card(fenetre, qtbot, tmp_path):
    carte = _pret(fenetre, qtbot, tmp_path)
    avant = fenetre.reader_atr.text()
    carte.evenements += 2
    fenetre.reader_atr._tick()
    assert fenetre.reader_atr._process.state() != QProcess.NotRunning
    assert fenetre.reader_atr.text() == avant
    qtbot.waitUntil(lambda: fenetre.reader_atr._process.state() == QProcess.NotRunning,
                    timeout=15000)
    assert fenetre.reader_atr.text() == avant


def test_an_unknown_presence_never_reads_on_its_own(fenetre, qtbot, tmp_path, monkeypatch):
    """Lecteur que PC/SC ne connait pas : pas de detection automatique, il
    reste le bouton."""
    _pret(fenetre, qtbot, tmp_path)
    fenetre.reader_atr.presence = lambda lecteur: None
    lancements = _lectures(fenetre.reader_atr, monkeypatch)
    for _ in range(3):
        fenetre.reader_atr._tick()
    assert lancements == []


def test_the_refresh_button_reads_the_card_on_demand(fenetre, qtbot, tmp_path):
    carte = _pret(fenetre, qtbot, tmp_path)
    fenetre.reader_atr.presence = lambda lecteur: None  # pas de detection auto
    (tmp_path / "retiree").write_text("")
    [bouton] = fenetre.reader_atr.actions()
    bouton.trigger()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)


def test_no_automatic_read_while_a_run_holds_the_reader(fenetre, qtbot, tmp_path, monkeypatch):
    carte = _pret(fenetre, qtbot, tmp_path)
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    fenetre._update_actions()
    carte.retirer(tmp_path)
    fenetre.reader_atr._tick()
    assert fenetre.reader_atr._process.state() == QProcess.NotRunning

    # Des la fin du run, la carte est relue : elle a pu changer pendant.
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: False))
    fenetre._update_actions()
    qtbot.waitUntil(lambda: fenetre.reader_atr.state == ATR_NO_CARD, timeout=15000)


def test_starting_a_run_kills_a_read_in_flight_without_waiting(fenetre, qtbot, tmp_path, monkeypatch):
    """Une lecture en vol au moment du lancement ne doit ni gener le run, ni
    figer l'interface en attendant qu'elle se termine."""
    _pret(fenetre, qtbot, tmp_path)
    fenetre.reader_atr.refresh(quiet=True)
    assert fenetre.reader_atr._process.state() != QProcess.NotRunning

    attentes = []
    monkeypatch.setattr(fenetre.reader_atr._process, "waitForFinished",
                        lambda *a: attentes.append(a) or True)
    monkeypatch.setattr(type(fenetre.service), "busy", property(lambda self: True))
    fenetre._update_actions()

    assert attentes == []
    qtbot.waitUntil(lambda: fenetre.reader_atr._process.state() == QProcess.NotRunning,
                    timeout=5000)
    assert fenetre.reader_atr.state == ATR_OK  # le resultat tardif est ignore


def test_no_presence_check_for_a_hidden_field(fenetre, qtbot, tmp_path):
    carte = _pret(fenetre, qtbot, tmp_path)
    fenetre._show_page("history")
    avant = carte.appels
    carte.retirer(tmp_path)
    fenetre.reader_atr._tick()
    assert carte.appels == avant
    assert fenetre.reader_atr._process.state() == QProcess.NotRunning


def test_no_automatic_read_once_pyhubreader_is_unavailable(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    champ = ReaderAtrField()
    qtbot.addWidget(champ)
    carte = _Carte()
    champ.presence = carte
    champ.show()
    champ.set_context(str(tmp_path), sys.executable, CARTE)
    qtbot.waitUntil(lambda: champ.state == ATR_UNAVAILABLE, timeout=15000)
    carte.retirer(tmp_path)
    champ._tick()
    assert champ._process.state() == QProcess.NotRunning
    champ.release()


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
