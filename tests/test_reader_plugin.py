"""Retrouver la fonction lecteur quand elle vit dans un conftest.py.

Le nom qu'un conftest.py recoit dans sys.modules depend de la structure du
workspace (rootdir, presence d'un __init__.py, plusieurs conftest.py
imbriques) et n'est pas previsible depuis l'exterieur. Ces tests verifient
l'algorithme de recherche directement, sans passer par un vrai subprocess
pytest : plus rapide, et ils isolent precisement ce qui peut se tromper.
"""

import sys
import types

import pytest

from core.reader_plugin import _PLUGIN_SOURCE


def _charger_plugin(monkeypatch, reader="R1", cible="getConfigReader"):
    """Execute le code du plugin genere comme un module Python normal.

    Les variables _READER/_CIBLE du plugin sont lues depuis l'environnement au
    chargement : on le fixe donc avant d'executer le code, exactement comme le
    ferait le vrai subprocess pytest.
    """
    monkeypatch.setenv("PYTESTRUNNER_READER", reader)
    monkeypatch.setenv("PYTESTRUNNER_READER_GETTER", cible)

    module = types.ModuleType("plugin_pytestrunner_sous_test")
    exec(compile(_PLUGIN_SOURCE, "<plugin genere>", "exec"), module.__dict__)
    return module


def _faux_module(monkeypatch, nom_sys_modules, fichier, **attributs):
    """Enregistre un faux module dans sys.modules, pour simuler un conftest.py
    charge sous un nom que l'exterieur ne devine pas."""
    module = types.ModuleType(nom_sys_modules)
    module.__file__ = fichier
    for cle, valeur in attributs.items():
        setattr(module, cle, valeur)
    monkeypatch.setitem(sys.modules, nom_sys_modules, module)
    return module


# --------------------------------------------------- juste le nom de fonction

def test_a_bare_name_is_found_in_a_module_that_looks_like_a_conftest(monkeypatch):
    """Le cas de l'utilisateur : getConfigReader vit dans un conftest.py, dont
    le nom reel dans sys.modules n'est pas "conftest.getConfigReader"."""
    def getConfigReader():
        return "original"

    _faux_module(monkeypatch, "un_nom_totalement_impredictible",
                "/workspace/Test/conftest.py", getConfigReader=getConfigReader)

    plugin = _charger_plugin(monkeypatch, cible="getConfigReader")
    original, raison = plugin._trouver_original("getConfigReader")

    assert original is getConfigReader
    assert raison == ""


def test_a_bare_name_ignores_unrelated_modules_with_the_same_attribute(monkeypatch):
    """Ne pas se laisser distraire par un attribut de meme nom ailleurs qu'un
    conftest.py -- une coincidence de nom ne doit pas remplacer la mauvaise
    fonction."""
    def autre_fonction():
        return "sans rapport"

    def la_bonne():
        return "conftest"

    _faux_module(monkeypatch, "un_module_quelconque", "/ws/utils.py",
                getConfigReader=autre_fonction)
    _faux_module(monkeypatch, "conftest", "/ws/conftest.py",
                getConfigReader=la_bonne)

    plugin = _charger_plugin(monkeypatch, cible="getConfigReader")
    original, raison = plugin._trouver_original("getConfigReader")

    assert original is la_bonne


def test_a_bare_name_absent_everywhere_is_reported(monkeypatch):
    plugin = _charger_plugin(monkeypatch, cible="getConfigReader")
    original, raison = plugin._trouver_original("getConfigReader")

    assert original is None
    assert "getConfigReader" in raison


# ---------------------------------------------------------- forme "module.fonction"

def test_a_dotted_name_is_imported_directly_when_possible(monkeypatch):
    def getConfigReader():
        return "x"

    _faux_module(monkeypatch, "conftest", "/ws/conftest.py",
                getConfigReader=getConfigReader)
    monkeypatch.setattr(
        "importlib.import_module",
        lambda nom: sys.modules[nom] if nom in sys.modules else (_ for _ in ()).throw(
            ModuleNotFoundError(nom)))

    plugin = _charger_plugin(monkeypatch, cible="conftest.getConfigReader")
    original, raison = plugin._trouver_original("conftest.getConfigReader")

    assert original is getConfigReader


def test_a_dotted_name_falls_back_to_a_module_with_a_matching_file(monkeypatch):
    """Le module donne ne correspond a aucun module directement importable
    (chemin relatif au workspace, package que Python ne connait pas...) : on
    cherche alors un module deja charge dont le nom se termine pareil.

    Le nom utilise ("outils_lecteur") est choisi pour ne coincider avec aucun
    module deja charge par CE projet de tests -- sans quoi le test verifierait
    accidentellement une collision de cet environnement-ci plutot que le
    mecanisme de repli lui-meme.
    """
    import importlib

    def getConfigReader():
        return "y"

    _faux_module(monkeypatch, "TSu.JC_API.Int.outils_lecteur",
                "/ws/TSu/JC_API/Int/outils_lecteur.py",
                getConfigReader=getConfigReader)

    def import_module_qui_echoue(nom):
        raise ModuleNotFoundError(nom)

    monkeypatch.setattr(importlib, "import_module", import_module_qui_echoue)

    plugin = _charger_plugin(monkeypatch, cible="outils_lecteur.getConfigReader")
    original, raison = plugin._trouver_original("outils_lecteur.getConfigReader")

    assert original is getConfigReader


def test_a_dotted_name_whose_module_is_missing_is_reported(monkeypatch):
    monkeypatch.delitem(sys.modules, "module_qui_nexiste_pas", raising=False)
    plugin = _charger_plugin(monkeypatch, cible="module_qui_nexiste_pas.getReader")
    original, raison = plugin._trouver_original("module_qui_nexiste_pas.getReader")

    assert original is None
    assert "introuvable" in raison


def test_a_dotted_name_with_the_wrong_attribute_is_reported(monkeypatch):
    _faux_module(monkeypatch, "conftest", "/ws/conftest.py", autre_chose=lambda: None)
    plugin = _charger_plugin(monkeypatch, cible="conftest.getConfigReader")
    original, raison = plugin._trouver_original("conftest.getConfigReader")

    assert original is None
    assert "getConfigReader" in raison


# --------------------------------------------------------------- bout en bout

def test_applying_replaces_every_reference_to_the_found_function(monkeypatch):
    """Le remplacement doit suivre jusque dans le module de test qui a fait
    `from conftest import getConfigReader`, exactement comme pour la forme
    module.fonction deja couverte ailleurs."""
    def getConfigReader():
        return "jamais utilise si le remplacement marche"

    conftest = _faux_module(monkeypatch, "conftest", "/ws/conftest.py",
                            getConfigReader=getConfigReader)
    test_module = _faux_module(monkeypatch, "test_x", "/ws/test_x.py",
                               getConfigReader=getConfigReader)

    plugin = _charger_plugin(monkeypatch, reader="Lecteur B", cible="getConfigReader")
    plugin._appliquer()

    assert plugin._erreur == ""
    assert conftest.getConfigReader() == "Lecteur B"
    assert test_module.getConfigReader() == "Lecteur B"
