"""Imposer le lecteur d'un run sans modifier le code de test.

En mode parallele, plusieurs pytest tournent en meme temps : le lecteur ne peut
pas passer par le fichier de configuration, que tous partagent. Il passe par une
variable d'environnement -- encore faut-il que les tests la lisent.

Plutot que de demander une ligne dans `getConfigReader()`, on injecte un plugin
pytest qui remplace cette fonction, le temps du run, par une qui retourne le
lecteur voulu. Le workspace declare simplement laquelle :

    reader_mode: parallel
    reader_getter: config_getters.getConfigReader

Le remplacement est fait au dernier moment, pas au chargement du plugin : le
module a remplacer n'est importable qu'une fois que le conftest du workspace a
complete sys.path, ce qui arrive bien apres.

Si le remplacement echoue, le run s'arrete avec un message. Continuer serait
pire : tous les lecteurs liraient le meme et les resultats se ressembleraient
sans que rien ne le signale.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

PLUGIN_MODULE = "pytestrunner_reader"

GETTER_ENV = "PYTESTRUNNER_READER_GETTER"

_PLUGIN_SOURCE = '''\
"""Genere par PytestRunner. Impose le lecteur de ce run.

Ne pas modifier : ce fichier est recree et supprime a chaque lancement.
"""
import os

import pytest

_READER = os.environ.get("PYTESTRUNNER_READER", "")
_CIBLE = os.environ.get("PYTESTRUNNER_READER_GETTER", "")

_fait = False
_erreur = ""


def _appliquer():
    """Remplace la fonction designee par une qui retourne le lecteur du run."""
    global _fait, _erreur
    if _fait or not _READER or not _CIBLE:
        return
    _fait = True

    module_name, _, attribut = _CIBLE.rpartition(".")
    if not module_name or not attribut:
        _erreur = "reader_getter doit valoir module.fonction"
        return

    try:
        import importlib
        import sys

        module = importlib.import_module(module_name)
        original = getattr(module, attribut)

        def _remplacant(*args, **kwargs):
            return _READER

        _remplacant.__wrapped__ = original

        # Remplacer dans le module qui la definit ne suffit pas : un
        # `from config_getters import getConfigReader` a copie la reference dans
        # le module de test, et c'est cette copie-la qui est appelee. On
        # remplace donc TOUTES les references a cette fonction precise -- pas
        # tout ce qui porte ce nom, mais tout ce qui EST cet objet.
        remplacements = 0
        for present in list(sys.modules.values()):
            if present is None:
                continue
            try:
                noms = list(vars(present))
            except Exception:
                continue
            for nom in noms:
                try:
                    if getattr(present, nom, None) is original:
                        setattr(present, nom, _remplacant)
                        remplacements += 1
                except Exception:
                    continue

        if not remplacements:
            _erreur = "aucune reference a remplacer"
    except Exception as exc:
        _erreur = "%s: %s" % (type(exc).__name__, exc)


def _verifier():
    if _erreur:
        raise RuntimeError(
            "PytestRunner n'a pas pu imposer le lecteur %r : la fonction %r n'a "
            "pas pu etre remplacee (%s).\\n"
            "Sans cela tous les lecteurs liraient le meme et les resultats se "
            "ressembleraient sans que rien ne le signale.\\n"
            "Corrigez la cle reader_getter du fichier de configuration, ou "
            "repassez en reader_mode: sequential." % (_READER, _CIBLE, _erreur)
        )


def pytest_collection_finish(session):
    # Le conftest du workspace a complete sys.path : le module est importable.
    _appliquer()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # tryfirst : le remplacement doit etre en place avant le setup_method de la
    # classe de test, qui est justement l'endroit ou le lecteur est demande.
    _appliquer()
    _verifier()
'''


@contextmanager
def reader_plugin(getter: str):
    """Fournit (arguments pytest, dossier a ajouter au PYTHONPATH).

    Sans `getter`, ne fait rien : le lecteur passe alors par la seule variable
    d'environnement, que le workspace doit lire lui-meme.
    """
    if not getter:
        yield [], ""
        return

    dossier = tempfile.mkdtemp(prefix="pytestrunner_plugin_")
    try:
        (Path(dossier) / f"{PLUGIN_MODULE}.py").write_text(
            _PLUGIN_SOURCE, encoding="utf-8")
        yield ["-p", PLUGIN_MODULE], dossier
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
