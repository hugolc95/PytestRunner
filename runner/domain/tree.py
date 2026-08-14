"""Construction de l'arbre des tests a partir des nodeids de pytest."""

from __future__ import annotations

import re

from runner.domain.models import Kind, TestNode

# `test_f[cas-1]` -> ('test_f', 'cas-1')
_PARAMETRE = re.compile(r"^(?P<nom>[^\[]+)\[(?P<cas>.+)\]$")


def _decouper(nodeid: str) -> list[tuple[str, Kind]]:
    """Segments d'un nodeid, avec la nature de chacun.

    `a/b/test_x.py::TestC::test_f[cas]` donne les dossiers `a` et `b`, le
    module `test_x.py`, la classe `TestC`, la fonction `test_f` et le cas
    `cas`.
    """
    chemin, _, reste = nodeid.partition("::")
    segments: list[tuple[str, Kind]] = []

    morceaux = [m for m in chemin.replace("\\", "/").split("/") if m]
    for dossier in morceaux[:-1]:
        segments.append((dossier, Kind.FOLDER))
    if morceaux:
        segments.append((morceaux[-1], Kind.MODULE))

    if not reste:
        return segments

    parties = reste.split("::")
    for partie in parties[:-1]:
        segments.append((partie, Kind.CLASS))

    dernier = parties[-1]
    m = _PARAMETRE.match(dernier)
    if m:
        # La fonction devient un regroupement, chaque cas une feuille : c'est
        # au cas pres qu'un resultat differe d'un lecteur a l'autre.
        segments.append((m.group("nom"), Kind.TEST))
        segments.append((f"[{m.group('cas')}]", Kind.CASE))
    else:
        segments.append((dernier, Kind.TEST))

    return segments


def build_tree(nodeids) -> list[TestNode]:
    """Arbre des tests, dans l'ordre de collecte de pytest.

    L'ordre de pytest est celui du systeme de fichiers : le respecter evite que
    deux collectes successives ne reordonnent l'arbre sous les yeux.
    """
    racines: list[TestNode] = []
    index: dict[tuple, TestNode] = {}

    for nodeid in nodeids:
        segments = _decouper(nodeid)
        if not segments:
            continue

        chemin_cle: tuple = ()
        parent_enfants = racines

        for position, (nom, kind) in enumerate(segments):
            chemin_cle = chemin_cle + (nom,)
            noeud = index.get(chemin_cle)
            if noeud is None:
                noeud = TestNode(name=nom, kind=kind)
                index[chemin_cle] = noeud
                parent_enfants.append(noeud)
            parent_enfants = noeud.children

            if position == len(segments) - 1:
                noeud.nodeid = nodeid

    return racines


def collapse_single_class(racines: list[TestNode]) -> list[TestNode]:
    """Retire les classes uniques, qui n'apportent qu'un niveau a deplier.

    Dans les suites ou chaque fichier n'a qu'une classe, son nom reprend celui
    du fichier : le niveau ne distingue rien et coute un clic a chaque descente.
    Il est garde des qu'un fichier en contient plusieurs, sans quoi deux tests
    homonymes se retrouveraient cote a cote.
    """
    for noeud in racines:
        classes = [e for e in noeud.children if e.kind is Kind.CLASS]
        if noeud.kind is Kind.MODULE and len(classes) == 1 and len(noeud.children) == 1:
            noeud.children = classes[0].children
        collapse_single_class(noeud.children)
    return racines
