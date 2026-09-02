"""Dans un sous-dossier expres : verifie que l'arbre groupe correctement par
dossier, puis module, puis classe, quand le workspace n'est pas plat.
"""

import pytest


@pytest.mark.smoke
class TestVerificationPin:
    """Classe dans un sous-dossier, avec son propre marker de classe."""

    def test_pin_correct_est_accepte(self, apdu_log):
        apdu_log.logSendAPDU("0020000008" + "1234".encode().hex().upper(), "9000")
        assert True

    def test_pin_incorrect_est_refuse(self, apdu_log):
        apdu_log.logSendAPDU("0020000008" + "0000".encode().hex().upper(), "63C2")
        assert True

    @pytest.mark.parametrize("tentative", [1, 2, 3])
    def test_compteur_tentatives(self, tentative, apdu_log):
        """Classe + parametrize + marker de module (voir plus bas) en meme
        temps : le cas le plus charge que l'arbre ait a afficher."""
        assert tentative <= 3


class TestBlocageCarte:
    """Deuxieme classe du meme module : verifie que l'arbre ne les confond
    pas et affiche bien deux groupes distincts sous le meme fichier."""

    @pytest.mark.critical
    def test_carte_bloquee_apres_trois_echecs(self, apdu_log):
        apdu_log.logSendAPDU("0020000008" + "0000".encode().hex().upper(), "6983")
        assert True


def test_fonction_hors_classe(apdu_log):
    """Une fonction du meme module, en dehors de toute classe : l'arbre doit
    la montrer a cote des deux classes, pas a l'interieur de l'une d'elles."""
    apdu_log.logReaderInfo("Demo virtual reader")
    assert True
