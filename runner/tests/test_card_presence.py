"""Presence de carte par PC/SC, contre une fausse winscard.

Le vrai appel n'existe que sous Windows ; ici on verifie la lecture de l'etat
que Windows renverrait -- presence, compteur d'evenements, lecteur inconnu --
et la gestion du contexte PC/SC.
"""

from runner.domain import card_presence
from runner.domain.card_presence import CardPresence

PRESENT = card_presence.SCARD_STATE_PRESENT
INCONNU = card_presence.SCARD_STATE_UNKNOWN
VIDE = 0x0010
LECTEUR_INCONNU = 0x80100009


class _FausseWinscard:
    def __init__(self, etat=PRESENT, code=0):
        self.etat, self.code = etat, code
        self.ouverts, self.fermes, self.lecteurs = 0, [], []

    def SCardEstablishContext(self, portee, a, b, contexte):
        self.ouverts += 1
        contexte._obj.value = 40 + self.ouverts
        return 0

    def SCardGetStatusChangeW(self, contexte, delai, etats, nombre):
        assert delai == 0, "l'appel ne doit jamais attendre"
        etats._obj.dwEventState = self.etat
        self.lecteurs.append(etats._obj.szReader)
        return self.code

    def SCardReleaseContext(self, contexte):
        self.fermes.append(contexte)
        return 0


def test_a_present_card_gives_its_event_counter():
    lib = _FausseWinscard(etat=PRESENT | (3 << 16))
    assert CardPresence(lib).check("OMNIKEY CardMan 3x21 0") == (True, 3)
    assert lib.lecteurs == ["OMNIKEY CardMan 3x21 0"]


def test_an_empty_reader_is_not_present():
    assert CardPresence(_FausseWinscard(etat=VIDE | (5 << 16))).check("R") == (False, 5)


def test_a_reader_unknown_to_pcsc_gives_nothing():
    assert CardPresence(_FausseWinscard(etat=INCONNU)).check("Cosmo11SecuredSLC27G") is None


def test_an_error_releases_the_context_and_the_next_call_starts_afresh():
    lib = _FausseWinscard(code=LECTEUR_INCONNU)
    presence = CardPresence(lib)
    assert presence.check("R") is None
    assert lib.fermes == [41]
    lib.code, lib.etat = 0, PRESENT
    assert presence.check("R") == (True, 0)
    assert lib.ouverts == 2


def test_the_context_is_reused_between_checks():
    lib = _FausseWinscard()
    presence = CardPresence(lib)
    presence.check("R")
    presence.check("R")
    assert lib.ouverts == 1
    presence.close()
    assert lib.fermes == [41]


def test_outside_windows_nothing_is_known():
    assert CardPresence().check("R") is None
