"""Imposer le lecteur d'un run sans modifier le code de test, ni sa logique.

En mode parallele, plusieurs pytest tournent en meme temps : le lecteur ne peut
pas passer par le fichier de configuration, que tous partagent -- l'ecrire pour
l'un ecraserait ce que l'autre vient d'y mettre.

Premiere approche essayee : remplacer la fonction getConfigReader() du
workspace par une qui retourne directement le lecteur voulu. Elle a un defaut
serieux -- si cette fonction ne se contente pas de relire la cle `Reader` mais
lui ajoute quelque chose (un champ construit, une validation, un formatage...),
ce traitement disparait avec la fonction remplacee. Le lecteur transmis aux
tests n'est alors plus celui que le vrai code aurait produit.

La bonne approche ne touche donc PAS a la fonction : elle rend le FICHIER de
configuration virtuellement different pour ce process, avec la cle `Reader`
deja mise a la bonne valeur, exactement comme le fait le mode sequentiel en
l'ecrivant reellement sur disque -- sauf qu'ici rien n'est ecrit, seule la
lecture du fichier est interceptee en memoire, dans CE process uniquement, donc
sans que les autres lecteurs qui tournent en meme temps ne s'en apercoivent.

getConfigReader() n'est jamais touchee : elle s'execute normalement, lit "son"
fichier de configuration (qui contient deja le bon lecteur du point de vue de
ce process), et applique tout traitement qu'elle fait d'habitude. Aucune
declaration n'est necessaire dans le workspace pour que cela fonctionne : le
fichier concerne est celui-la meme ou `Reader`/`Readers` a ete trouve.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

PLUGIN_MODULE = "pytestrunner_reader"

CONFIG_PATH_ENV = "PYTESTRUNNER_READER_CONFIG_PATH"

_PLUGIN_SOURCE = '''\
"""Genere par PytestRunner. Impose le lecteur de ce run.

Ne pas modifier : ce fichier est recree et supprime a chaque lancement.
"""
import builtins
import io
import os
import pathlib
import re

import pytest

_READER = os.environ.get("PYTESTRUNNER_READER", "")
_CONFIG_PATH = os.environ.get("PYTESTRUNNER_READER_CONFIG_PATH", "")

# Meme regle qu'un `Reader:` a la racine du fichier prime sur celui d'une
# section -- voir core/reader_switch.py, dont cette portion est la copie : le
# plugin genere tourne seul dans un subprocess pytest, sans acces au paquet
# PytestRunner.
_LIGNE_RE = re.compile(
    r"^(?P<indent>[ \\t]*)(?P<cle>[A-Za-z_][\\w \\-]*?)(?P<sep>[ \\t]*:[ \\t]*)"
    r"(?P<valeur>[^\\n#]*)(?P<fin>#.*)?$"
)
_CLES_READER = ("reader", "lecteur")
_A_CITER = set(":#{}[],&*?|<>=!%@`\\"'\\\\")


def _normaliser_cle(cle):
    return str(cle).strip().lower().replace("-", "_").replace(" ", "_")


def _citer(valeur):
    valeur = str(valeur)
    if not valeur:
        return \'""\'
    if any(c in _A_CITER for c in valeur) or valeur != valeur.strip():
        return \'"\' + valeur.replace("\\\\", "\\\\\\\\").replace(\'"\', \'\\\\"\') + \'"\'
    return valeur


def _construire_texte_modifie(brut, nouveau_lecteur):
    """Le texte du fichier, avec la ligne Reader (la moins indentee) changee.

    None si aucune cle reader n'y est trouvee : rien de sur a modifier.
    """
    meilleure = None
    for numero, ligne in enumerate(brut.splitlines()):
        m = _LIGNE_RE.match(ligne)
        if m is None or _normaliser_cle(m.group("cle")) not in _CLES_READER:
            continue
        indent = len(m.group("indent").expandtabs(4))
        if meilleure is None or indent < meilleure[1]:
            meilleure = (numero, indent)

    if meilleure is None:
        return None

    numero = meilleure[0]
    lignes = brut.splitlines(keepends=True)
    m = _LIGNE_RE.match(lignes[numero].rstrip("\\r\\n"))

    fin_de_ligne = "\\r\\n" if lignes[numero].endswith("\\r\\n") \\
        else ("\\n" if lignes[numero].endswith("\\n") else "")
    commentaire = m.group("fin") or ""
    if commentaire:
        commentaire = " " + commentaire.strip()

    lignes[numero] = (
        m.group("indent") + m.group("cle") + m.group("sep")
        + _citer(nouveau_lecteur) + commentaire + fin_de_ligne
    )
    return "".join(lignes)


_texte_virtuel = None
_chemin_normalise = None
_erreur = ""


def _preparer():
    """Lit le vrai fichier une fois, calcule sa version avec le bon lecteur."""
    global _texte_virtuel, _chemin_normalise, _erreur
    if not _READER or not _CONFIG_PATH:
        return
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8", newline="") as f:
            brut = f.read()
    except OSError as exc:
        _erreur = "could not read %r: %s" % (_CONFIG_PATH, exc)
        return

    modifie = _construire_texte_modifie(brut, _READER)
    if modifie is None:
        _erreur = "no Reader key found in %r" % _CONFIG_PATH
        return

    _texte_virtuel = modifie
    _chemin_normalise = os.path.normcase(os.path.abspath(_CONFIG_PATH))


def _est_le_fichier_vise(chemin):
    if _texte_virtuel is None:
        return False
    try:
        return os.path.normcase(os.path.abspath(os.fspath(chemin))) == _chemin_normalise
    except Exception:
        return False


_open_reel = builtins.open


def _open_virtuel(fichier, mode="r", *args, **kwargs):
    # Seule une lecture du fichier vise est interceptee : une ecriture doit
    # continuer d'aller sur le vrai fichier (rare, mais ne jamais la piegeur).
    if "r" in mode and "+" not in mode and _est_le_fichier_vise(fichier):
        if "b" in mode:
            return io.BytesIO(_texte_virtuel.encode("utf-8"))
        return io.StringIO(_texte_virtuel)
    return _open_reel(fichier, mode, *args, **kwargs)


_read_text_reel = pathlib.Path.read_text
_read_bytes_reel = pathlib.Path.read_bytes


def _read_text_virtuel(self, *args, **kwargs):
    if _est_le_fichier_vise(self):
        return _texte_virtuel
    return _read_text_reel(self, *args, **kwargs)


def _read_bytes_virtuel(self, *args, **kwargs):
    if _est_le_fichier_vise(self):
        return _texte_virtuel.encode("utf-8")
    return _read_bytes_reel(self, *args, **kwargs)


_preparer()
if _texte_virtuel is not None:
    # Des l'import du plugin -- le plus tot que pytest permette -- et non dans
    # un hook : getConfigReader() peut etre appelee des le debut de la
    # collecte (conftest.py, fixture de session...), avant que la plupart des
    # hooks ne se declenchent.
    builtins.open = _open_virtuel
    pathlib.Path.read_text = _read_text_virtuel
    pathlib.Path.read_bytes = _read_bytes_virtuel


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if _erreur:
        raise RuntimeError(
            "PytestRunner could not impose the reader %r: %s.\\n"
            "Continuing would have run every reader with the same value, "
            "with nothing to signal it.\\n"
            "Check the configuration file's Reader key, or switch back "
            "to reader_mode: sequential." % (_READER, _erreur)
        )
'''


@contextmanager
def reader_plugin(config_path: str):
    """Fournit (arguments pytest, dossier a ajouter au PYTHONPATH).

    Sans `config_path`, ne fait rien : rien ne permet alors de savoir quel
    fichier rendre virtuellement different, et le lecteur ne passe que par la
    variable d'environnement PYTESTRUNNER_READER (inoffensive si rien ne la lit).
    """
    if not config_path:
        yield [], ""
        return

    dossier = tempfile.mkdtemp(prefix="pytestrunner_plugin_")
    try:
        (Path(dossier) / f"{PLUGIN_MODULE}.py").write_text(
            _PLUGIN_SOURCE, encoding="utf-8")
        yield ["-p", PLUGIN_MODULE], dossier
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
