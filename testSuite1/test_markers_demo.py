"""Combinaisons de markers pytest, pour verifier le filtre par marker du GUI.

Chaque test ici est deterministe (aucune dependance a campaign_state.txt) :
le but est de peupler le panneau "Filter by marker" avec des cas varies --
marker seul, plusieurs markers empiles, marker de module, marker de classe,
marker combine a un parametrize -- pas de tester une vraie logique metier.
"""

import pytest


# Un marker pose ici s'applique a TOUS les tests du module, sans annotation
# repetee sur chacun : `demo` doit donc regrouper ce fichier entier des que le
# filtre est active, tests de classe et parametres compris.
pytestmark = pytest.mark.demo


@pytest.mark.smoke
def test_marker_seul(apdu_log):
    """Un seul marker en plus de celui du module : `demo` + `smoke`."""
    apdu_log.logPowerON("3B9F9681B1FE451F070064051E0E6400820218")
    assert True


@pytest.mark.smoke
@pytest.mark.critical
def test_marker_empiles(apdu_log):
    """Plusieurs marqueurs sur le meme test : `demo` + `smoke` + `critical`."""
    apdu_log.logSendAPDU("00A4040007A0000002471001", "9000")
    assert True


@pytest.mark.regression
@pytest.mark.parametrize("valeur", [1, 2, 3])
def test_marker_avec_parametrize(valeur):
    """Marker + parametrize : chaque cas genere doit rester rattache au
    marker du test source, pas seulement a son propre nodeid."""
    assert valeur > 0


@pytest.mark.integration
class TestCampagnePersonnalisation:
    """Un marker pose sur la classe s'applique a chacune de ses methodes :
    les trois tests ci-dessous doivent tous ressortir sous `integration`."""

    def test_selection_applet(self, apdu_log):
        apdu_log.logSendAPDU("00A4040007A0000002471001", "9000")
        assert True

    def test_verification_pin(self, apdu_log):
        apdu_log.logSendAPDU("0020000008" + "1234".encode().hex().upper(), "9000")
        assert True

    @pytest.mark.slow
    def test_cycle_complet(self, apdu_log):
        """Methode qui ajoute son propre marker en plus de celui de la
        classe : doit apparaitre sous `integration` ET sous `slow`."""
        apdu_log.logPowerON("3B9F9681B1FE451F070064051E0E6400820218")
        apdu_log.logSendAPDU("00A4040007A0000002471001", "9000")
        apdu_log.logPowerOFF()
        assert True
