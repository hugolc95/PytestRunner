"""Construction de l'arbre des tests a partir des nodeids de pytest."""

from __future__ import annotations

import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class SequenceGroup:
    """One or more sequence steps collapsed under a shared ancestor.

    `name` is the qualified path up to and including that ancestor (a bare
    nodeid when `nodeids` holds a single entry, since there's nothing to
    collapse) ; `kind` says what level it collapsed at -- a parametrized
    function, a class, a module, or a folder -- so the caller can phrase the
    label accordingly ("N parameter cases" vs. "N tests").
    """

    kind: Kind
    name: str
    nodeids: tuple[str, ...]


def _rejoindre(segments: list[tuple[str, Kind]]) -> str:
    """Reassemble a nodeid-like path from `_decouper()`-style segments."""
    texte = ""
    for nom, genre in segments:
        if not texte:
            texte = nom
        elif genre in (Kind.FOLDER, Kind.MODULE):
            texte = f"{texte}/{nom}"
        else:
            texte = f"{texte}::{nom}"
    return texte


def group_hierarchically(nodeids) -> list[SequenceGroup]:
    """Group nodeids under the HIGHEST shared ancestor that exactly, and
    contiguously, accounts for them -- a parametrized function's cases, a
    class's methods, a module's tests, a whole folder's tree, whichever level
    the run actually forms.

    Checking one heavily parametrized test, a whole class, or an entire
    folder can select thousands of nodeids in one click. `checked_nodeids()`
    already returns them in tree order, so building a tree from exactly this
    selection (`build_tree`) and flattening it back reproduces the same
    order -- any subtree's own leaves therefore land on a contiguous slice of
    the input, and collapsing top-down from each root is enough; nothing
    needs to search for a match.

    A run that repeats an earlier nodeid (a deliberate rerun step) is handled
    by splitting the input into duplicate-free runs first: `build_tree()`
    folds a repeated nodeid into a single leaf, so grouping across a repeat
    would silently "complete" a group and lose the repeat -- never
    acceptable for a step placed there on purpose.
    """
    resultat: list[SequenceGroup] = []
    for run in _sans_doublons(nodeids):
        resultat.extend(_grouper_run(run))
    return resultat


def _sans_doublons(nodeids) -> list[list[str]]:
    runs: list[list[str]] = []
    courant: list[str] = []
    vus: set[str] = set()
    for nodeid in nodeids:
        if nodeid in vus:
            runs.append(courant)
            courant, vus = [], set()
        courant.append(nodeid)
        vus.add(nodeid)
    if courant:
        runs.append(courant)
    return runs


def _grouper_run(nodeids: list[str]) -> list[SequenceGroup]:
    if not nodeids:
        return []
    groupes: list[SequenceGroup] = []
    pos = 0
    for racine in build_tree(nodeids):
        resultat = _consommer(racine, nodeids, pos, ())
        if resultat is None:
            # Ne devrait pas arriver sur une sequence bien formee --
            # `build_tree()` y reconstruit alors exactement l'ordre donne,
            # racine par racine (voir `group_hierarchically()`). Mais une
            # sequence enregistree a pu etre reordonnee a la main d'une facon
            # qui casse cette hypothese : `_consommer()` ne rend alors qu'un
            # echec global, sans dire combien de ses enfants avaient deja
            # reussi. Continuer racine par racine a partir d'un `pos`
            # incertain risquerait de sauter ou de dedoubler un nodeid --
            # s'arreter net et rendre le reste tel quel, une ligne par
            # nodeid, est le seul choix qui ne perde jamais rien.
            break
        sous_groupes, pos = resultat
        groupes.extend(sous_groupes)
    groupes.extend(SequenceGroup(Kind.CASE, nodeid, (nodeid,)) for nodeid in nodeids[pos:])
    return groupes


def _descendre(node: TestNode, segments: tuple[tuple[str, Kind], ...]):
    """Suit une chaine a enfant unique jusqu'au noeud le plus specifique
    qu'elle atteint sans jamais se ramifier.

    Un dossier qui ne contient qu'un seul module, lui-meme n'ayant qu'une
    seule classe, ne merite pas d'etre nomme par le dossier : la classe
    couvre exactement la meme selection et le dit mieux. Ca vaut aussi pour
    une fonction parametree seule dans son module -- son compte reste "N
    parameter cases", pas "N tests" une fois remonte au module, ce qui
    perdrait la nuance que c'est LE MEME test rejoue avec des donnees
    differentes.
    """
    while len(node.children) == 1:
        enfant = node.children[0]
        segments = segments + ((enfant.name, enfant.kind),)
        node = enfant
    return node, segments


def _consommer(node: TestNode, nodeids: list[str], pos: int,
              segments_parent: tuple[tuple[str, Kind], ...]):
    segments = segments_parent + ((node.name, node.kind),)
    feuilles = [feuille.nodeid for feuille in node.leaves()]
    n = len(feuilles)
    if nodeids[pos:pos + n] == feuilles:
        if n == 1:
            return [SequenceGroup(node.kind, feuilles[0], tuple(feuilles))], pos + n
        noeud_final, segments_final = _descendre(node, segments)
        nom = _rejoindre(list(segments_final))
        return [SequenceGroup(noeud_final.kind, nom, tuple(feuilles))], pos + n
    if node.is_leaf:
        return None
    groupes: list[SequenceGroup] = []
    courant = pos
    for enfant in node.children:
        resultat = _consommer(enfant, nodeids, courant, segments)
        if resultat is None:
            return None
        sous, courant = resultat
        groupes.extend(sous)
    return groupes, courant


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
