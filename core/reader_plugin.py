"""Imposer le lecteur d'un run sans modifier le code de test.

En mode parallele, plusieurs pytest tournent en meme temps : le lecteur ne peut
pas passer par le fichier de configuration, que tous partagent. Il passe par une
variable d'environnement -- encore faut-il que les tests la lisent.

Plutot que de demander une ligne dans `getConfigReader()`, on injecte un plugin
pytest qui remplace cette fonction, le temps du run, par une qui retourne le
lecteur voulu. Le workspace declare simplement laquelle :

    reader_getter: config_getters.getConfigReader

Quand la fonction vit dans un conftest.py -- le cas le plus courant --, son nom
de module reel depend de la facon dont pytest l'a charge (rootdir, presence
d'un __init__.py, plusieurs conftest.py imbriques...) et n'est pas toujours
predictible depuis l'exterieur. Deux ecritures sont donc acceptees :

    reader_getter: conftest.getConfigReader   # nom de module tente tel quel,
                                               # avec repli sur une recherche
    reader_getter: getConfigReader            # juste le nom : cherche dans
                                               # tout module charge qui
                                               # ressemble a un conftest.py

Le remplacement est fait au dernier moment, pas au chargement du plugin : le
conftest du workspace n'est importe (et le module a remplacer disponible)
qu'une fois la collecte terminee.

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
import importlib
import os
import sys

import pytest

_READER = os.environ.get("PYTESTRUNNER_READER", "")
_CIBLE = os.environ.get("PYTESTRUNNER_READER_GETTER", "")

_fait = False
_erreur = ""


def _ressemble_a_conftest(module):
    """Vrai si ce module a des chances d'etre un conftest.py.

    Le nom qu'un conftest.py recoit dans sys.modules depend de la structure du
    workspace (rootdir, __init__.py, plusieurs conftest.py imbriques) : on
    reconnait donc le fichier plutot que d'exiger un nom precis.
    """
    nom = getattr(module, "__name__", "") or ""
    fichier = getattr(module, "__file__", "") or ""
    return nom == "conftest" or nom.endswith(".conftest") \
        or os.path.basename(fichier) == "conftest.py"


def _trouver_original(cible):
    """Retrouve (objet_fonction) designe par `cible`, ou (None, raison_echec).

    `cible` peut etre "module.fonction" (tente tel quel, avec repli sur une
    recherche par nom si l'import direct echoue) ou juste "fonction" (cherche
    dans tout module deja charge qui ressemble a un conftest.py -- c'est le cas
    le plus courant, le nom reel du module conftest n'etant pas previsible).
    """
    module_name, point, attribut = cible.rpartition(".")

    if not point:
        # Pas de module donne : on ne cherche que dans les conftest.py connus.
        candidats = [m for m in sys.modules.values()
                    if m is not None and _ressemble_a_conftest(m) and hasattr(m, attribut)]
        if not candidats:
            return None, (
                "aucun conftest.py charge ne definit %r (verifiez l'orthographe, "
                "et que ce fichier fait bien partie des tests lances)" % attribut
            )
        return getattr(candidats[0], attribut), ""

    module = None
    try:
        module = importlib.import_module(module_name)
    except Exception:
        pass

    if module is None:
        # Repli : le nom donne ne correspond a aucun module importable tel
        # quel (frequent pour un conftest.py, dont le nom reel differe selon
        # la structure du workspace). On cherche un module deja charge dont le
        # nom ou le fichier y correspond.
        court = module_name.rsplit(".", 1)[-1]
        for present in sys.modules.values():
            if present is None:
                continue
            nom_present = getattr(present, "__name__", "") or ""
            fichier = getattr(present, "__file__", "") or ""
            base = os.path.splitext(os.path.basename(fichier))[0] if fichier else ""
            if nom_present == module_name or nom_present.rsplit(".", 1)[-1] == court \
                    or base == court:
                module = present
                break

    if module is None:
        return None, "module %r introuvable parmi ceux deja charges" % module_name
    if not hasattr(module, attribut):
        return None, "le module trouve n'a pas d'attribut %r" % attribut
    return getattr(module, attribut), ""


def _appliquer():
    """Remplace la fonction designee par une qui retourne le lecteur du run."""
    global _fait, _erreur
    if _fait or not _READER or not _CIBLE:
        return
    _fait = True

    try:
        original, raison = _trouver_original(_CIBLE)
        if original is None:
            _erreur = raison
            return

        def _remplacant(*args, **kwargs):
            return _READER

        _remplacant.__wrapped__ = original

        # Remplacer a l'endroit trouve ne suffit pas : un
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
