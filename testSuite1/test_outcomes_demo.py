"""Tous les verdicts pytest possibles, pour verifier que l'arbre et
l'historique du GUI les distinguent correctement : passed, failed, skipped,
xfailed, xpassed (strict, donc compte comme un echec) et error (leve pendant
le setup d'une fixture, pas pendant le test lui-meme).

Deterministe, sans dependance a campaign_state.txt : contrairement a
test_api.py/test_math.py, le but ici n'est pas une regle metier mais un
verdict fixe et previsible a chaque run.
"""

import sys

import pytest


def test_reussit_normalement(apdu_log):
    apdu_log.logPowerON("3B9F9681B1FE451F070064051E0E6400820218")
    assert 1 + 1 == 2


def test_echoue_normalement():
    """FAILED simple : une assertion fausse, sans marker particulier."""
    assert 1 + 1 == 3


@pytest.mark.skip(reason="Materiel non branche sur ce poste de demo")
def test_toujours_ignore():
    assert False  # jamais execute : le skip intervient avant


@pytest.mark.skipif(1 == 1, reason="Condition demo toujours vraie")
def test_ignore_sous_condition():
    """SKIPPED via une condition evaluee a la collecte, pas un skip brut."""
    assert False  # jamais execute non plus


@pytest.mark.xfail(reason="Bug connu, correctif prevu au prochain sprint")
def test_echec_attendu():
    """XFAIL : echoue reellement, mais l'echec est attendu -- ne doit pas
    compter comme un vrai FAILED dans les totaux."""
    assert False


@pytest.mark.xfail(reason="Marque a tort comme casse : demo du cas XPASS",
                    strict=True)
def test_marque_casse_a_tort():
    """XPASS strict : le test PASSE alors qu'il est marque `xfail(strict=True)`,
    ce que pytest compte comme un echec -- un xfail non tenu a jour est aussi
    trompeur qu'un test rouge ignore."""
    assert True


@pytest.fixture
def lecteur_indisponible():
    raise RuntimeError(
        "Lecteur de carte introuvable (demo : erreur de fixture, pas du test)")
    yield  # jamais atteint


def test_erreur_de_fixture(lecteur_indisponible):
    """ERROR, pas FAILED : l'exception vient du setup de la fixture, avant
    meme que le corps du test ne s'execute."""
    assert True


@pytest.mark.skipif(sys.platform.startswith("win"),
                     reason="Comportement specifique non couvert sous Windows")
def test_ignore_seulement_sous_windows():
    """Skip conditionnel qui depend reellement de l'environnement -- contrairement
    a `test_ignore_sous_condition`, celui-ci peut passer OU etre ignore selon
    la machine qui lance la suite."""
    assert True
