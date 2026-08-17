"""Lecture et ecriture des fichiers de test, pour l'onglet Source.

Ecrire dans les fichiers de test de quelqu'un demande plus de precautions que
d'afficher du texte. Trois pieges, traites ici :

  - un fichier trop gros est tronque a l'affichage. Le reecrire depuis ce qui
    est montre effacerait tout ce qui n'a pas ete lu : un fichier tronque est
    donc en lecture seule, et le dit ;
  - un fichier qui ne se decode pas en UTF-8 subirait le meme sort ;
  - une ecriture interrompue -- disque plein, verrou antivirus -- laisserait le
    fichier de test a moitie ecrit. On passe par un temporaire du meme dossier,
    remplace ensuite d'un seul coup.

Et un detail qui n'en est pas un : la fin de ligne d'origine est retenue. Sans
cela, la premiere frappe dans un fichier CRLF le convertirait entierement en
LF, et le diff ferait des milliers de lignes pour un caractere change.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# Au-dela, la zone de texte devient lente et le fichier n'est de toute facon
# plus un fichier de test.
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class SourceFile:
    """Un fichier source charge, avec de quoi le reecrire fidelement."""

    path: Path | None = None
    text: str = ""
    newline: str = "\n"
    editable: bool = False
    warning: str = ""

    @property
    def loaded(self) -> bool:
        return self.path is not None


def read_source(path: Path) -> SourceFile:
    """Charge un fichier source. Ne leve jamais : l'erreur revient en warning."""
    try:
        brut = Path(path).read_bytes()
    except OSError as exc:
        return SourceFile(warning=f"Could not read: {exc}")

    tronque = len(brut) > MAX_BYTES
    if tronque:
        brut = brut[:MAX_BYTES]

    try:
        texte = brut.decode("utf-8")
        editable = not tronque
    except UnicodeDecodeError:
        texte = brut.decode("utf-8", errors="replace")
        editable = False

    crlf = texte.count("\r\n")
    newline = "\r\n" if crlf > texte.count("\n") - crlf else "\n"
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")

    if tronque:
        avertissement = (f"Truncated to {MAX_BYTES // 1_000_000} MB — read-only.")
    elif not editable:
        avertissement = "Not valid UTF-8 — read-only."
    else:
        avertissement = ""

    return SourceFile(Path(path), texte, newline, editable, avertissement)


def write_source(path: Path, texte: str, newline: str = "\n") -> str:
    """Reecrit le fichier. Rend un message d'erreur, ou la chaine vide.

    L'ecriture passe par un temporaire du meme dossier, remplace d'un seul
    coup : une coupure en cours de route laisserait sinon un fichier de test a
    moitie ecrit, et la suite ne collecterait plus.
    """
    path = Path(path)
    contenu = texte.replace("\n", newline) if newline != "\n" else texte
    temporaire = path.with_name(path.name + ".pytestrunner.tmp")

    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as f:
            f.write(contenu)
        os.replace(temporaire, path)
    except OSError as exc:
        try:
            temporaire.unlink()
        except OSError:
            pass
        return f"Could not save: {exc}"

    return ""


def path_of(workspace: str, nodeid: str) -> Path | None:
    """Fichier .py d'un nodeid, ou None si ce n'en est pas un.

    Un nodeid porte le chemin avant le premier `::`. Un dossier, ou un
    identifiant sans fichier Python, n'a pas de source a montrer.
    """
    if not workspace or not nodeid:
        return None
    relatif = nodeid.split("::", 1)[0].strip()
    if not relatif.endswith(".py"):
        return None
    return Path(workspace) / relatif


def function_line(texte: str, nodeid: str) -> int:
    """Ligne (base 0) de la definition du test, -1 si introuvable.

    Ouvrir un fichier de deux mille lignes tout en haut oblige a chercher a la
    main le test sur lequel on vient de cliquer.
    """
    fonction = nodeid.split("::")[-1].split("[")[0].strip() if nodeid else ""
    if not fonction or not texte:
        return -1

    # Espaces horizontaux uniquement : `\s` engloberait les sauts de ligne et
    # le motif commencerait a matcher sur les lignes vides qui precedent la
    # definition, placant le curseur trop haut.
    motif = re.compile(
        rf"^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(fonction)}[ \t]*\(",
        re.MULTILINE,
    )
    trouve = motif.search(texte)
    if trouve is None:
        return -1
    return texte.count("\n", 0, trouve.start())
