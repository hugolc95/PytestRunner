"""Markers pytest : les relever, les compter, et filtrer avec.

Une suite de cartes range ses tests par phase (`perso`, `prepersonnalisation`),
par duree (`slow`) ou par intention (`smoke`, `regression`). C'est un axe de
selection au moins aussi utile que l'arborescence des fichiers, et il n'existait
nulle part dans l'outil.

Deux partis pris.

Les markers sont releves par pytest lui-meme, pas par une lecture du source.
Un `grep @pytest.mark` manquerait tout ce qu'un conftest ajoute dans
`pytest_collection_modifyitems` -- une pratique courante pour marquer d'un coup
toute une famille de tests -- et se tromperait sur les marks poses par une
variable ou une boucle.

Un marker ne LANCE rien. Il coche des cases dans l'arbre, et c'est l'arbre qui
reste le contrat de ce qui va tourner. Passer `-m` a pytest aurait rendu le
nombre de tests inconnu jusqu'a la fin du run : progression, tests restants,
historique et rapport seraient tous devenus des estimations.
"""

from __future__ import annotations

import ast
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

PLUGIN_MODULE = "runner_marker_probe"
ENV_OUT = "PYTESTRUNNER_MARKERS_OUT"

# Marks qui sont des MECANISMES pytest, pas des categories de test. Les
# proposer comme filtre n'aurait aucun sens : `parametrize` est porte par la
# moitie d'une suite, `skipif` decrit une condition, pas une intention.
MECHANISM_MARKERS = frozenset({
    "parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings",
})

# Le plugin tourne seul dans le processus pytest : il doit etre autonome.
# Il ecrit dans un FICHIER et non sur la sortie standard -- un `print` pendant
# la collecte obligerait a lancer pytest avec `-s`, ce qui laisserait aussi
# passer tout ce qu'un conftest bavard imprime, en plein milieu des nodeids.
_SOURCE = '''\
"""Genere automatiquement. Recree et supprime a chaque collecte."""
import os

_SORTIE = os.environ.get("PYTESTRUNNER_MARKERS_OUT", "")


def pytest_collection_modifyitems(config, items):
    if not _SORTIE:
        return

    lignes = []

    # Les markers declares, avec leur description. `getini` les rend tous :
    # ceux de pytest.ini comme ceux ajoutes par un `addinivalue_line` dans un
    # conftest, qu'aucune lecture de fichier ne trouverait.
    try:
        for ligne in config.getini("markers"):
            lignes.append("D\\t" + str(ligne).replace("\\t", " "))
    except Exception:
        pass

    for item in items:
        try:
            noms = sorted({m.name for m in item.iter_markers()})
        except Exception:
            noms = []
        lignes.append("M\\t" + item.nodeid + "\\t" + ",".join(noms))

    try:
        with open(_SORTIE, "w", encoding="utf-8") as f:
            f.write("\\n".join(lignes))
    except OSError:
        # Un relevé de markers rate ne doit pas faire echouer une collecte :
        # l'interface se passera des puces, l'arbre reste utilisable.
        pass
'''


@dataclass(frozen=True)
class Marker:
    """Un marker propose a la selection."""

    name: str
    description: str = ""
    count: int = 0

    @property
    def tooltip(self) -> str:
        tests = f"{self.count} test" + ("s" if self.count > 1 else "")
        return f"{self.description}  ({tests})" if self.description else tests


@contextmanager
def marker_probe():
    """Fournit (arguments pytest, dossier PYTHONPATH, fichier de sortie).

    Le fichier doit survivre au processus pytest le temps d'etre relu, d'ou le
    gestionnaire de contexte.
    """
    dossier = tempfile.mkdtemp(prefix="runner_markers_")
    try:
        (Path(dossier) / f"{PLUGIN_MODULE}.py").write_text(_SOURCE, encoding="utf-8")
        sortie = str(Path(dossier) / "markers.tsv")
        yield ["-p", PLUGIN_MODULE], dossier, sortie
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def read_probe(chemin: str) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Relit le fichier du plugin : (markers par nodeid, descriptions).

    Un fichier absent n'est pas une erreur : la collecte a pu se terminer sans
    que le plugin ne tourne (aucun test collecte, pytest trop ancien). On rend
    deux dictionnaires vides et l'interface masque simplement les puces.
    """
    try:
        brut = Path(chemin).read_text(encoding="utf-8")
    except OSError:
        return {}, {}

    par_nodeid: dict[str, tuple[str, ...]] = {}
    descriptions: dict[str, str] = {}

    for ligne in brut.splitlines():
        genre, _, reste = ligne.partition("\t")
        if genre == "D":
            nom, _, description = reste.partition(":")
            nom = nom.split("(")[0].strip()  # `slow(reason)` -> `slow`
            if nom:
                descriptions[nom] = description.strip()
        elif genre == "M":
            nodeid, _, noms = reste.partition("\t")
            if nodeid:
                par_nodeid[nodeid] = tuple(n for n in noms.split(",") if n)

    return par_nodeid, descriptions


def summarize(par_nodeid: dict[str, tuple[str, ...]],
              descriptions: dict[str, str] | None = None) -> list[Marker]:
    """Markers reellement portes par des tests, du plus frequent au moins.

    Les markers declares mais jamais utilises sont laisses de cote : une puce
    qui ne selectionne rien n'aide personne. Les mecanismes pytest aussi.
    """
    comptes: dict[str, int] = {}
    for noms in par_nodeid.values():
        for nom in noms:
            if nom not in MECHANISM_MARKERS:
                comptes[nom] = comptes.get(nom, 0) + 1

    descriptions = descriptions or {}
    return [
        Marker(nom, descriptions.get(nom, ""), compte)
        # A frequence egale, l'ordre alphabetique : sans ce second critere,
        # les puces changeraient de place d'une collecte a l'autre.
        for nom, compte in sorted(comptes.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


# =========================================================================
# Expressions
# =========================================================================


class ExpressionError(ValueError):
    """Expression que pytest n'accepterait pas non plus."""


# `and`, `or`, `not` et les parentheses de pytest sont exactement ceux de
# Python : on laisse donc Python analyser la syntaxe, et on ne garde de l'arbre
# obtenu que ces quatre formes. Rien d'autre n'est evalue -- ni appel, ni
# attribut, ni comparaison -- l'expression ne peut donc rien executer.
_AUTORISES = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Not,
              ast.And, ast.Or, ast.Name, ast.Load, ast.Constant)


def compile_expression(texte: str) -> Callable[[frozenset[str]], bool]:
    """Transforme `smoke and not slow` en un predicat sur un jeu de markers.

    Leve ExpressionError avec un message affichable tel quel : c'est celui que
    l'utilisateur verra sous le champ, il ne doit pas etre une trace Python.
    """
    texte = (texte or "").strip()
    if not texte:
        raise ExpressionError("Empty expression")

    try:
        arbre = ast.parse(texte, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(_message_syntaxe(texte, exc)) from exc

    for noeud in ast.walk(arbre):
        if not isinstance(noeud, _AUTORISES):
            raise ExpressionError(
                "Only marker names and the words and / or / not are allowed here.")
        if isinstance(noeud, ast.Constant) and not isinstance(noeud.value, bool):
            raise ExpressionError(
                f"{noeud.value!r} is not a marker name.")

    code = compile(arbre, "<markers>", "eval")

    def predicat(markers: frozenset[str]) -> bool:
        return bool(eval(code, {"__builtins__": {}}, _Marqueurs(markers)))

    return predicat


class _Marqueurs(dict):
    """Rend vrai tout nom present, faux tout nom absent.

    Un marker inconnu vaut faux plutot que de lever : c'est le comportement de
    pytest, et cela permet de taper une expression au fur et a mesure sans
    qu'elle passe son temps en erreur.
    """

    def __init__(self, presents: Iterable[str]):
        super().__init__()
        self._presents = frozenset(presents)

    def __missing__(self, cle: str) -> bool:
        return cle in self._presents


def _message_syntaxe(texte: str, exc: SyntaxError) -> str:
    """Message lisible pour les fautes de frappe les plus courantes."""
    if "&&" in texte or "||" in texte:
        return "Use the words and / or, not the symbols && / ||."
    if texte.count("(") != texte.count(")"):
        return "Unbalanced parentheses."
    return "This is not a valid marker expression."


def matches(texte: str, markers: Iterable[str]) -> bool:
    """Raccourci pour un seul test. Leve ExpressionError si l'expression est fausse."""
    return compile_expression(texte)(frozenset(markers))


def union_expression(noms: Iterable[str]) -> str:
    """Expression equivalant a « n'importe lequel de ces markers »."""
    retenus = [n for n in dict.fromkeys(noms) if n]
    return " or ".join(retenus)


def names_of_union(texte: str) -> tuple[str, ...] | None:
    """Les noms d'une expression qui n'est QU'une union, sinon None.

    Sert a rallumer les puces quand le champ contient exactement ce qu'elles
    auraient ecrit. Des que l'expression fait autre chose (`and`, `not`, des
    parentheses), les puces ne peuvent plus la representer et s'eteignent.
    """
    try:
        arbre = ast.parse((texte or "").strip(), mode="eval").body
    except SyntaxError:
        return None

    if isinstance(arbre, ast.Name):
        return (arbre.id,)
    if isinstance(arbre, ast.BoolOp) and isinstance(arbre.op, ast.Or):
        if all(isinstance(v, ast.Name) for v in arbre.values):
            return tuple(v.id for v in arbre.values)
    return None


def selected_nodeids(par_nodeid: dict[str, tuple[str, ...]],
                     predicat: Callable[[frozenset[str]], bool]) -> list[str]:
    """Nodeids retenus par ce predicat, dans l'ordre de la collecte."""
    return [nodeid for nodeid, noms in par_nodeid.items()
            if predicat(frozenset(noms))]


def environment(base: dict | None, sortie: str) -> dict:
    """Environnement du sous-processus, avec le fichier de sortie du plugin."""
    env = dict(base if base is not None else os.environ)
    env[ENV_OUT] = sortie
    return env
