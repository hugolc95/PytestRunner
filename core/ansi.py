"""Lecture des sequences d'echappement ANSI d'un texte colore.

Beaucoup de conftest colorent leurs traces pour la console : un verdict en
vert, un ecart en rouge. Cette couleur passe par des sequences ANSI
(`ESC[31m ... ESC[0m`) qu'un terminal interprete, mais qu'une zone de texte Qt
affiche telles quelles -- des `[31m` parasites au milieu de chaque ligne, et la
couleur perdue.

Ce module separe le texte de sa mise en forme. La traduction en couleurs
reelles est laissee a l'appelant : le rouge vif d'un terminal est illisible sur
un fond clair, c'est donc a la palette du theme de decider de la teinte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

# Sequence de style (SGR) : `ESC[` puis des parametres, puis `m`.
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# Toute autre sequence d'echappement (deplacement du curseur, effacement...).
# Elle ne porte aucune couleur mais s'afficherait en toutes lettres.
_AUTRES_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Za-z0-9]|\x1b[=>]")

# Indices ANSI des huit couleurs de base, dans leur ordre standard.
COULEURS = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")


@dataclass(frozen=True)
class Style:
    """Mise en forme d'un morceau de texte.

    `couleur` est un nom de COULEURS, ou un `#rrggbb` pour les modes 256
    couleurs et couleurs vraies. None = couleur par defaut de la zone de texte.
    """

    couleur: str | None = None
    vive: bool = False
    gras: bool = False
    italique: bool = False
    souligne: bool = False

    @property
    def neutre(self) -> bool:
        """Vrai si ce style ne demande rien : rien a appliquer."""
        return self == Style()


# Palette 256 couleurs : les 16 premieres sont les couleurs de base, puis un
# cube 6x6x6, puis 24 niveaux de gris.
def _couleur_256(index: int) -> str | None:
    if index < 8:
        return COULEURS[index]
    if index < 16:
        return COULEURS[index - 8]
    if index < 232:
        index -= 16
        niveaux = (0, 95, 135, 175, 215, 255)
        r, v, b = niveaux[index // 36], niveaux[(index // 6) % 6], niveaux[index % 6]
        return f"#{r:02x}{v:02x}{b:02x}"
    if index < 256:
        gris = 8 + (index - 232) * 10
        return f"#{gris:02x}{gris:02x}{gris:02x}"
    return None


def _appliquer(style: Style, parametres: list[int]) -> Style:
    """Style resultant apres ces parametres SGR."""
    i = 0
    while i < len(parametres):
        code = parametres[i]

        if code == 0:
            style = Style()
        elif code == 1:
            style = replace(style, gras=True)
        elif code == 3:
            style = replace(style, italique=True)
        elif code == 4:
            style = replace(style, souligne=True)
        elif code in (22, 21):
            style = replace(style, gras=False)
        elif code == 23:
            style = replace(style, italique=False)
        elif code == 24:
            style = replace(style, souligne=False)
        elif 30 <= code <= 37:
            style = replace(style, couleur=COULEURS[code - 30], vive=False)
        elif 90 <= code <= 97:
            style = replace(style, couleur=COULEURS[code - 90], vive=True)
        elif code == 39:
            style = replace(style, couleur=None, vive=False)
        elif code == 38 and i + 1 < len(parametres):
            # 38;5;N (256 couleurs) ou 38;2;R;G;B (couleur vraie).
            mode = parametres[i + 1]
            if mode == 5 and i + 2 < len(parametres):
                style = replace(style, couleur=_couleur_256(parametres[i + 2]), vive=False)
                i += 2
            elif mode == 2 and i + 4 < len(parametres):
                r, v, b = parametres[i + 2:i + 5]
                style = replace(style, couleur=f"#{r:02x}{v:02x}{b:02x}", vive=False)
                i += 4
        # Les codes de fond (40-49, 100-107) sont ignores : reecrire le fond
        # d'une ligne dans une zone de texte au theme choisi la rendrait
        # illisible des que les deux ne s'accordent pas.
        i += 1
    return style


def contient_ansi(texte: str) -> bool:
    """Vrai si le texte porte au moins une sequence d'echappement."""
    return "\x1b" in (texte or "")


def parse_ansi(texte: str) -> list[tuple[str, Style]]:
    """Decoupe le texte en morceaux (contenu, style), sequences retirees.

    Les morceaux mis bout a bout redonnent le texte debarrasse de toutes ses
    sequences d'echappement -- y compris celles qui ne portent pas de couleur,
    qui s'afficheraient sinon en toutes lettres.
    """
    texte = texte or ""
    if not contient_ansi(texte):
        return [(texte, Style())] if texte else []

    morceaux: list[tuple[str, Style]] = []
    style = Style()
    position = 0

    for m in _SGR_RE.finditer(texte):
        avant = texte[position:m.start()]
        if avant:
            morceaux.append((_AUTRES_RE.sub("", avant), style))
        parametres = [int(p) if p else 0 for p in m.group(1).split(";")]
        style = _appliquer(style, parametres)
        position = m.end()

    reste = texte[position:]
    if reste:
        morceaux.append((_AUTRES_RE.sub("", reste), style))

    return [(contenu, s) for contenu, s in morceaux if contenu]


def strip_ansi(texte: str) -> str:
    """Le texte sans aucune sequence d'echappement."""
    return "".join(contenu for contenu, _ in parse_ansi(texte))
