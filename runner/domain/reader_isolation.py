"""Donner a chaque processus pytest SON lecteur, sans toucher au code de test.

Plusieurs lecteurs testes en parallele partagent un seul fichier de
configuration. Y ecrire le lecteur du moment est donc exclu : le deuxieme
processus ecraserait ce que le premier vient d'y mettre.

Remplacer la fonction du workspace qui lit le lecteur ne convient pas non plus.
Elle fait souvent plus que relire une cle -- elle prefixe, valide, formate --
et tout ce traitement disparaitrait avec elle.

La solution retenue ne touche a rien de tout cela : elle rend le FICHIER
virtuellement different pour un processus, avec la cle deja a la bonne valeur.
La fonction du workspace s'execute normalement, lit "son" fichier, et applique
tout ce qu'elle fait d'habitude. Rien n'est ecrit sur disque, donc les autres
processus ne voient rien.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

PLUGIN_MODULE = "runner_reader_isolation"

ENV_READER = "PYTESTRUNNER_READER"
ENV_CONFIG = "PYTESTRUNNER_READER_CONFIG"

# Le plugin tourne seul dans le processus pytest, sans acces a ce paquet : il
# doit etre autonome.
_SOURCE = '''\
"""Genere automatiquement. Recree et supprime a chaque lancement."""
import builtins
import io
import os
import pathlib
import re
import sys

import pytest

_READER = os.environ.get("PYTESTRUNNER_READER", "")
_CONFIG = os.environ.get("PYTESTRUNNER_READER_CONFIG", "")

_LIGNE = re.compile(
    r"^(?P<indent>[ \\t]*)(?P<cle>[A-Za-z_][\\w \\-]*?)(?P<sep>[ \\t]*:[ \\t]*)"
    r"(?P<valeur>[^\\n#]*)(?P<fin>#.*)?$"
)
_CLES = ("reader", "lecteur")
_A_CITER = set(":#{}[],&*?|<>=!%@`\\"'\\\\")

_texte = None
_cible = None
_erreur = ""

# Canal machine lisible par Pytest Runner. Les lignes humaines de pytest ne
# sont pas une API : leur forme varie avec la couleur, xdist et les plugins du
# workspace. Ce prefixe reste volontairement simple et reserve.
_OUTCOME_PREFIX = "PYTESTRUNNER_OUTCOME"
_OUTCOMES = {}
_RANK = {"PASSED": 0, "SKIPPED": 1, "FAILED": 2, "ERROR": 3}


def _citer(valeur):
    valeur = str(valeur)
    if not valeur:
        return \'""\'
    if any(c in _A_CITER for c in valeur) or valeur != valeur.strip():
        return \'"\' + valeur.replace("\\\\", "\\\\\\\\").replace(\'"\', \'\\\\"\') + \'"\'
    return valeur


def _reecrire(brut, lecteur):
    """Le fichier avec la cle Reader la MOINS indentee changee.

    L'edition est faite a la ligne, pas en reserialisant le YAML : un
    yaml.safe_dump reordonnerait les cles et effacerait les commentaires.
    """
    meilleure = None
    for numero, ligne in enumerate(brut.splitlines()):
        m = _LIGNE.match(ligne)
        if m is None:
            continue
        cle = m.group("cle").strip().lower().replace("-", "_").replace(" ", "_")
        if cle not in _CLES:
            continue
        indent = len(m.group("indent").expandtabs(4))
        if meilleure is None or indent < meilleure[1]:
            meilleure = (numero, indent)

    if meilleure is None:
        return None

    numero = meilleure[0]
    lignes = brut.splitlines(keepends=True)
    m = _LIGNE.match(lignes[numero].rstrip("\\r\\n"))
    fin = "\\r\\n" if lignes[numero].endswith("\\r\\n") else (
        "\\n" if lignes[numero].endswith("\\n") else "")
    commentaire = (" " + m.group("fin").strip()) if m.group("fin") else ""
    lignes[numero] = (m.group("indent") + m.group("cle") + m.group("sep")
                      + _citer(lecteur) + commentaire + fin)
    return "".join(lignes)


def _preparer():
    global _texte, _cible, _erreur
    if not _READER or not _CONFIG:
        return
    try:
        with open(_CONFIG, "r", encoding="utf-8", newline="") as f:
            brut = f.read()
    except OSError as exc:
        _erreur = "cannot read %r: %s" % (_CONFIG, exc)
        return
    modifie = _reecrire(brut, _READER)
    if modifie is None:
        _erreur = "no Reader key found in %r" % _CONFIG
        return
    _texte = modifie
    _cible = os.path.normcase(os.path.abspath(_CONFIG))


def _vise(chemin):
    if _texte is None:
        return False
    try:
        return os.path.normcase(os.path.abspath(os.fspath(chemin))) == _cible
    except Exception:
        return False


_open = builtins.open
_read_text = pathlib.Path.read_text
_read_bytes = pathlib.Path.read_bytes


def _open_virtuel(fichier, mode="r", *args, **kwargs):
    # Seule la LECTURE est detournee : une ecriture doit atteindre le vrai
    # fichier, sous peine de perdre silencieusement ce qu'elle enregistre.
    if "r" in mode and "+" not in mode and _vise(fichier):
        return io.BytesIO(_texte.encode("utf-8")) if "b" in mode else io.StringIO(_texte)
    return _open(fichier, mode, *args, **kwargs)


def _read_text_virtuel(self, *args, **kwargs):
    return _texte if _vise(self) else _read_text(self, *args, **kwargs)


def _read_bytes_virtuel(self, *args, **kwargs):
    return _texte.encode("utf-8") if _vise(self) else _read_bytes(self, *args, **kwargs)


_preparer()
if _texte is not None:
    # Des l'import du plugin, et non dans un hook : la fonction du workspace
    # peut etre appelee des la collecte -- au chargement d'un conftest, dans
    # une fixture de session -- avant que le moindre hook ne se declenche.
    builtins.open = _open_virtuel
    pathlib.Path.read_text = _read_text_virtuel
    pathlib.Path.read_bytes = _read_bytes_virtuel


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if _erreur:
        raise RuntimeError(
            "Could not pin reader %r: %s.\\n"
            "Continuing would have run every reader against the same value "
            "with nothing to signal it." % (_READER, _erreur)
        )
    if _READER:
        # Un seul rapport Allure pour tous les lecteurs d'un run : sans ce
        # parametre, deux lecteurs qui jouent le meme test s'y verraient
        # fondus en un seul historique, l'un cachant l'autre derriere un
        # simple "retry". allure-pytest n'est pas toujours installe -- le
        # cas ordinaire, silencieux, ne doit rien y perdre.
        try:
            import allure
            allure.dynamic.parameter("Reader", _READER)
        except Exception:
            pass


def _record_outcome(nodeid, status):
    precedent = _OUTCOMES.get(nodeid)
    if precedent is None or _RANK[status] > _RANK[precedent]:
        _OUTCOMES[nodeid] = status


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report):
    """Retient le verdict final sans dependre du rendu du terminal pytest."""
    if report.when in ("setup", "teardown"):
        if report.failed:
            _record_outcome(report.nodeid, "ERROR")
        elif report.skipped:
            _record_outcome(report.nodeid, "SKIPPED")
        return

    if report.when == "call":
        if report.failed:
            _record_outcome(report.nodeid, "FAILED")
        elif report.skipped:
            _record_outcome(report.nodeid, "SKIPPED")
        elif report.passed:
            _record_outcome(report.nodeid, "PASSED")


@pytest.hookimpl(trylast=True)
def pytest_runtest_logfinish(nodeid, location):
    """Emet exactement un verdict apres setup, call et teardown."""
    status = _OUTCOMES.pop(nodeid, None)
    # Avec xdist, seul le controleur doit ecrire dans le pipe de l'application.
    # Ecrire dans stdout depuis un worker pourrait perturber son transport.
    if status is not None and "PYTEST_XDIST_WORKER" not in os.environ:
        # sys.__stdout__ contourne la capture pytest, tout en restant branche
        # sur le pipe lu par l'application.
        # Le terminal pytest n'a pas encore toujours termine sa propre ligne.
        # Le saut initial garantit que le protocole commence au premier
        # caractere d'une nouvelle ligne et reste donc reconnaissable.
        sys.__stdout__.write("\\n%s\t%s\t%s\\n" % (_OUTCOME_PREFIX, status, nodeid))
        sys.__stdout__.flush()
'''


@contextmanager
def reader_plugin(config_path: str):
    """Fournit (arguments pytest, dossier a mettre dans PYTHONPATH).

    Le plugin est toujours charge car il transporte aussi les verdicts dans un
    format stable. Sans configuration, seule la virtualisation du Reader reste
    inactive.
    """
    dossier = tempfile.mkdtemp(prefix="runner_reader_")
    try:
        (Path(dossier) / f"{PLUGIN_MODULE}.py").write_text(_SOURCE, encoding="utf-8")
        yield ["-p", PLUGIN_MODULE], dossier
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
