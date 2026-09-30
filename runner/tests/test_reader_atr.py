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


HUB_ARGUMENT = f'''
class pyHubReader:
    def getAtr(self, reader):
        if reader == {CARTE!r}:
            return bytes.fromhex("3B8F8001804F0CA000000306")
        raise RuntimeError("SCARD_E_NO_SMARTCARD")
'''


def _sonder(tmp_path, corps, lecteur, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, corps))
    fini = subprocess.run(
        [sys.executable, "-c", reader_discovery.PROBE_ATR, lecteur],
        capture_output=True, text=True, timeout=30,
        env=reader_discovery.discovery_environment())
    return parse_atr_output(fini.stdout, fini.stderr)


def test_a_card_gives_its_atr_as_compact_hex(tmp_path, monkeypatch):
    etat, atr, _ = _sonder(tmp_path, HUB_ARGUMENT, CARTE, monkeypatch)
    assert (etat, atr) == (ATR_OK, "3B8F8001804F0CA000000306")


def test_a_reader_without_card_says_so(tmp_path, monkeypatch):
    etat, atr, detail = _sonder(tmp_path, HUB_ARGUMENT, VIDE, monkeypatch)
    assert (etat, atr) == (ATR_NO_CARD, "")
    assert "SCARD_E_NO_SMARTCARD" in detail


def test_connect_then_getatr_is_supported_and_released(tmp_path, monkeypatch):
    """L'autre forme d'API : connexion au lecteur, puis getAtr() sans
    argument -- et la connexion doit etre relachee, les tests en ont besoin."""
    corps = '''
    import pathlib
    class pyHubReader:
        def connect(self, reader):
            self.reader = reader
        def getATR(self):
            return "3b8f8001"
        def disconnect(self):
            pathlib.Path("released").write_text(self.reader)
    '''
    monkeypatch.chdir(tmp_path)
    etat, atr, _ = _sonder(tmp_path, corps, CARTE, monkeypatch)
    assert (etat, atr) == (ATR_OK, "3B8F8001")
    assert (tmp_path / "released").read_text() == CARTE


def test_an_empty_atr_means_no_card(tmp_path, monkeypatch):
    corps = '''
    class pyHubReader:
        def getAtr(self, reader):
            return ""
    '''
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
    corps = '''
    class pyHubReader:
        def getAtr(self, reader):
            return reader.encode()
    '''
    nom = "x'); import os; os._exit(3) #"
    etat, atr, _ = _sonder(tmp_path, corps, nom, monkeypatch)
    assert etat == ATR_OK
    assert atr == nom.encode().hex().upper()


# ------------------------------------------------------------------ fenetre


@pytest.fixture
def fenetre(qtbot, tmp_path, monkeypatch):
    QSettings(ORG, APP).clear()
    monkeypatch.setenv("PYTHONPATH", _faux_hub(tmp_path, HUB_ARGUMENT))
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
