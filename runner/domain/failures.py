"""Decoupage de la sortie de pytest en blocs d'echec, un par test.

Sur un run reel de 160 tests, la console fait pres de 300 lignes dont 160 ne
sont que des verdicts -- deja lisibles dans l'arbre, colonne par colonne. La
seule chose que la console apporte et qu'on ne trouve nulle part ailleurs,
c'est le contenu des traces d'echec : environ 40 % des lignes, noyees au
milieu du reste et separees du test auquel elles se rapportent.

Ce module retrouve ce lien. Il travaille sur du texte brut, sans Qt et sans
pytest : on peut lui donner une sortie enregistree et verifier ce qu'il en
tire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from runner.domain.ansi import strip_ansi

# `======================== FAILURES ========================`, et la ligne de
# `=` sans titre. Le titre est non gourmand et encadre d'espaces : sans cela un
# titre contenant le separateur (`test_f`, plein de `_`) ne serait pas reconnu.
_BANNIERE = re.compile(r"^={3,}(?:\s+(?P<titre>.+?)\s+={3,})?$")

# `________________________ TestC.test_f[1] ________________________`
_ENTETE = re.compile(r"^_{3,}\s+(?P<titre>.+?)\s+_{3,}$")

# En-tete de la section ERRORS : `ERROR at setup of TestC.test_f`.
_PHASE = re.compile(r"^ERROR at (?P<phase>setup|call|teardown) of\s+(?P<cible>.+)$")

# Sections dont le contenu nous interesse. Toute autre banniere les termine.
_SECTIONS = {"FAILURES": "failure", "ERRORS": "error"}


@dataclass(frozen=True)
class Failure:
    """Le bloc d'echec d'un test, tel que pytest l'a imprime.

    `title` est le titre de l'en-tete (`TestC.test_f[1]`), pas un nodeid :
    pytest n'imprime pas le fichier dans ce titre.
    """

    title: str
    kind: str = "failure"      # "failure" ou "error"
    phase: str = ""            # "", "setup", "call", "teardown"
    body: str = ""
    ambiguous: bool = False    # plusieurs tests portent ce titre

    @property
    def message(self) -> str:
        """La ligne qui dit ce qui a casse, sans son prefixe `E`.

        pytest prefixe d'un `E` les lignes de l'exception. La premiere resume
        la panne ; c'est elle qu'on met en titre plutot que de faire lire toute
        la trace pour la retrouver.
        """
        for ligne in self.body.splitlines():
            nue = strip_ansi(ligne).rstrip()
            if nue == "E" or nue.startswith("E "):
                return nue[1:].strip()
        return ""

    @property
    def headline(self) -> str:
        """Message de l'echec, ou a defaut sa nature."""
        if self.message:
            return self.message
        if self.phase:
            return f"Error during {self.phase}"
        return "Failed without a message"


def section_of(ligne: str) -> str | None:
    """Titre de la banniere que porte cette ligne, `None` si ce n'en est pas une.

    Une ligne de `=` sans titre rend la chaine vide : c'est bien une banniere,
    elle ferme la section en cours, mais elle n'en ouvre aucune.
    """
    m = _BANNIERE.match(strip_ansi(ligne).strip())
    if m is None:
        return None
    return (m.group("titre") or "").strip()


def is_failure_section(titre: str | None) -> bool:
    """Vrai si ce titre de banniere ouvre une section de traces."""
    return titre in _SECTIONS


def title_for_nodeid(nodeid: str) -> str:
    """Titre que pytest imprimera pour ce nodeid.

    `suite/test_a.py::TestC::test_f[1]` donne `TestC.test_f[1]` : pytest laisse
    tomber le fichier et joint le reste par des points.
    """
    if "::" not in nodeid:
        return nodeid
    return nodeid.split("::", 1)[1].replace("::", ".")


def split_failures(sortie: str) -> list[Failure]:
    """Tous les blocs d'echec d'une sortie, dans l'ordre d'impression."""
    blocs: list[Failure] = []
    kind = ""
    titre = ""
    phase = ""
    corps: list[str] = []

    def fermer() -> None:
        nonlocal titre, corps
        if titre:
            blocs.append(Failure(title=titre, kind=kind, phase=phase,
                                 body=_nettoyer(corps)))
        titre, corps = "", []

    for ligne in (sortie or "").splitlines():
        nue = strip_ansi(ligne).rstrip()

        banniere = section_of(nue)
        if banniere is not None:
            fermer()
            kind = _SECTIONS.get(banniere, "")
            phase = ""
            continue

        if not kind:
            continue

        entete = _ENTETE.match(nue.strip())
        if entete is not None:
            fermer()
            brut = entete.group("titre").strip()
            m = _PHASE.match(brut)
            if m is not None:
                phase, titre = m.group("phase"), m.group("cible").strip()
            else:
                phase, titre = "", brut
            continue

        if titre:
            corps.append(ligne.rstrip())

    fermer()
    return blocs


def _nettoyer(lignes: list[str]) -> str:
    """Corps sans ses lignes vides de tete et de queue."""
    debut, fin = 0, len(lignes)
    while debut < fin and not strip_ansi(lignes[debut]).strip():
        debut += 1
    while fin > debut and not strip_ansi(lignes[fin - 1]).strip():
        fin -= 1
    return "\n".join(lignes[debut:fin])


def index_failures(sortie: str) -> dict[str, Failure]:
    """Blocs d'echec indexes par titre, prets a etre interroges par nodeid.

    Deux tests homonymes dans deux fichiers differents produisent le meme
    titre : pytest n'imprime pas de quoi les distinguer. Plutot que de choisir
    en silence, le bloc retenu est marque `ambiguous` -- l'interface peut le
    dire au lieu de faire lire une trace qui n'est peut-etre pas la bonne.
    """
    index: dict[str, Failure] = {}
    for bloc in split_failures(sortie):
        ancien = index.get(bloc.title)
        if ancien is None:
            index[bloc.title] = bloc
        elif ancien.phase != bloc.phase:
            # `ERROR at setup of X` puis `ERROR at teardown of X` : c'est bien
            # le meme test, pas deux tests qui se ressemblent.
            index[bloc.title] = replace(
                ancien, body=f"{ancien.body}\n\n{bloc.body}")
        else:
            index[bloc.title] = replace(ancien, ambiguous=True)
    return index


def failure_for(index: dict[str, Failure], nodeid: str) -> Failure | None:
    """Bloc d'echec de ce nodeid, s'il y en a un."""
    return index.get(title_for_nodeid(nodeid))


# Une trace pytest melange quatre natures de lignes. Les distinguer est ce qui
# rend un pave lisible d'un coup d'oeil : sans cela, la ligne qui dit ce qui a
# casse a exactement le meme poids que le chemin du fichier au-dessus.
_ROLE_CADRE = re.compile(r"^\S+\.py:\d+:")
_ROLE_SECTION = re.compile(r"^-{3,}\s+.+?\s+-{3,}$")


def classify_line(ligne: str) -> str:
    """Nature d'une ligne de trace : exception, code, cadre, section, texte.

    C'est une regle de lecture de la sortie pytest, pas une regle d'affichage :
    la couleur associee a chaque nature appartient au theme.
    """
    nue = strip_ansi(ligne).rstrip()
    depouillee = nue.strip()
    if nue == "E" or nue.startswith("E "):
        return "exception"
    if depouillee.startswith(">"):
        return "code"
    if _ROLE_CADRE.match(depouillee):
        return "frame"
    if _ROLE_SECTION.match(depouillee):
        return "section"
    return "text"
