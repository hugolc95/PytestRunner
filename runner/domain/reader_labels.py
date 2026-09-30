"""Texte court des badges de lecteur, en tete des colonnes de statut."""

from __future__ import annotations

_MOTS_GENERIQUES = ("reader", "lecteur")


def badge_labels(names) -> list[str]:
    """Le plus court texte qui distingue chaque lecteur des autres.

    Un seul lecteur : son nom entier, il n'y a rien a distinguer. Sinon on
    retire les mots de tete communs a tous les noms ("OnmikeyCardman 3x21
    Reader") et le mot final generique ("Reader"). Reste un numero -- le cas
    des lecteurs d'un meme modele -- il est garde tel quel ; sinon les 4
    premiers caracteres, allonges tant que deux badges se ressembleraient.
    """
    noms = [str(n or "").strip() for n in names]
    if len(noms) <= 1:
        return noms

    mots = [n.split() or [""] for n in noms]
    debut = 0
    while all(len(m) > debut + 1 and m[debut] == mots[0][debut] for m in mots):
        debut += 1

    restes = []
    for m in mots:
        reste = m[debut:]
        if len(reste) > 1 and reste[-1].lower() in _MOTS_GENERIQUES:
            reste = reste[:-1]
        restes.append(reste)
    compacts = ["".join(c for c in "".join(r) if c.isalnum()).upper() for r in restes]

    libelles = []
    for i, reste in enumerate(restes):
        if len(reste) == 1 and reste[0].isdigit() and len(reste[0]) <= 3:
            libelles.append(reste[0])
            continue
        plat = compacts[i]
        if not plat:
            libelles.append(str(i + 1))
            continue
        longueur = min(4, len(plat))
        while longueur < len(plat) and any(
                j != i and compacts[j][:longueur] == plat[:longueur]
                for j in range(len(compacts))):
            longueur += 1
        libelles.append(plat[:longueur])

    # Deux noms identiques : la position les departage.
    return [f"{l}{i + 1}" if libelles.count(l) > 1 else l for i, l in enumerate(libelles)]
