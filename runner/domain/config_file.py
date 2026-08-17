"""Lire et REECRIRE un config.yml sans le defigurer.

Un fichier de configuration de workspace est ecrit a la main. Il porte des
commentaires qui expliquent pourquoi telle valeur est la, un ordre de cles qui
suit la pensee de celui qui l'a ecrit, et parfois des fins de ligne Windows.

Le passer dans un `yaml.safe_dump` rend un fichier equivalent pour une machine
et meconnaissable pour un humain : commentaires effaces, cles reordonnees,
guillemets et indentation refaits, diff sur chaque ligne. L'ancienne interface
faisait exactement cela a chaque enregistrement.

Ici on ecrit A LA LIGNE : seules les lignes dont la valeur a change sont
touchees, le reste du fichier est rendu octet pour octet. C'est la meme
approche que celle deja retenue pour poser le lecteur actif le temps d'un run.
"""

from __future__ import annotations

import re
from pathlib import Path

# Une ligne `Cle: valeur`, en capturant separement l'indentation, la cle, le
# separateur et la valeur (avec un eventuel commentaire de fin de ligne).
_LIGNE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<cle>[A-Za-z_][\w \-]*?)(?P<sep>[ \t]*:[ \t]*)"
    r"(?P<valeur>[^\n#]*)(?P<fin>#.*)?$"
)

# Un element de liste : `  - valeur`.
_ELEMENT = re.compile(r"^(?P<indent>[ \t]*)-[ \t]*(?P<valeur>[^\n#]*)(?P<fin>#.*)?$")

# Caracteres qui obligent a mettre la valeur entre guillemets pour rester du
# YAML valide.
_A_CITER = set(":#{}[],&*?|<>=!%@`\"'\\")


def normaliser(cle: str) -> str:
    return str(cle).strip().lower().replace("-", "_").replace(" ", "_")


def citer(valeur) -> str:
    """Rend la valeur telle qu'elle doit apparaitre dans le fichier."""
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, (int, float)):
        return str(valeur)

    texte = "" if valeur is None else str(valeur)
    if not texte:
        return '""'
    if any(c in _A_CITER for c in texte) or texte != texte.strip():
        return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return texte


def deciter(valeur: str) -> str:
    texte = str(valeur).strip()
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "\"'":
        return texte[1:-1]
    return texte


def lire_texte(chemin: Path) -> str | None:
    """Lit le fichier SANS traduire les fins de ligne.

    `read_text()` convertit les CRLF en LF : le fichier reecrit se retrouverait
    entierement en LF, soit un diff sur chaque ligne d'une configuration
    Windows.
    """
    try:
        with open(chemin, "r", encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def charger(chemin: Path) -> dict:
    """Contenu du fichier, en dictionnaire. Vide si illisible."""
    try:
        import yaml

        with open(chemin, "r", encoding="utf-8") as f:
            donnees = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return donnees if isinstance(donnees, dict) else {}


def _fin_de_ligne(ligne: str) -> str:
    if ligne.endswith("\r\n"):
        return "\r\n"
    return "\n" if ligne.endswith("\n") else ""


def _fin_dominante(texte: str) -> str:
    """La fin de ligne du fichier, pour les lignes qu'on AJOUTE.

    Ajouter du LF a la fin d'un fichier en CRLF donne un fichier mixte, que
    certains editeurs signalent et que le prochain outil normalisera en entier.
    """
    return "\r\n" if texte.count("\r\n") * 2 >= texte.count("\n") else "\n"


def _emplacements(texte: str) -> dict[str, int]:
    """Numero de ligne de chaque cle de PREMIER niveau.

    Seul le premier niveau est modifiable ici : une cle indentee appartient a
    une section, et deux sections peuvent porter la meme. Les reecrire au
    jugé melangerait les reglages de l'une avec ceux de l'autre.
    """
    trouves: dict[str, int] = {}
    for numero, ligne in enumerate(texte.splitlines()):
        m = _LIGNE.match(ligne)
        if m is None or m.group("indent"):
            continue
        trouves.setdefault(normaliser(m.group("cle")), numero)
    return trouves


def _etendue_liste(lignes: list[str], depart: int) -> int:
    """Derniere ligne du bloc `- element` qui suit la ligne `depart`."""
    fin = depart
    for numero in range(depart + 1, len(lignes)):
        nue = lignes[numero].rstrip("\r\n")
        if not nue.strip():
            continue
        if _ELEMENT.match(nue) and nue.startswith((" ", "\t", "-")):
            fin = numero
            continue
        break
    return fin


def _bloc_liste(cle: str, separateur: str, valeurs, fin: str) -> list[str]:
    lignes = [f"{cle}{separateur.rstrip()}{fin}"]
    lignes += [f"  - {citer(v)}{fin}" for v in valeurs]
    return lignes


def ecrire(chemin: Path, modifications: dict) -> tuple[bool, str]:
    """Applique ces changements au fichier. Rend (succes, message).

    `modifications` est un dictionnaire cle -> nouvelle valeur, les cles etant
    celles du premier niveau, telles qu'elles apparaissent dans le fichier ou
    sous une forme normalisee. Une cle absente du fichier est ajoutee a la fin ;
    une cle presente garde sa place, son indentation et son commentaire.

    L'ecriture passe par un temporaire du meme dossier, remplace d'un bloc :
    une coupure en plein enregistrement ne doit jamais laisser la configuration
    a moitie ecrite -- le workspace deviendrait incollectable.
    """
    chemin = Path(chemin)
    texte = lire_texte(chemin)
    if texte is None:
        texte = ""

    lignes = texte.splitlines(keepends=True)
    fin_par_defaut = _fin_dominante(texte)
    connues = _emplacements(texte)

    # Les remplacements sont prepares puis appliques du BAS vers le HAUT : une
    # liste plus courte ou plus longue decale tout ce qui suit, et les numeros
    # releves ne vaudraient plus rien.
    remplacements: list[tuple[int, int, list[str]]] = []
    ajouts: list[str] = []

    for cle, valeur in modifications.items():
        numero = connues.get(normaliser(cle))
        if numero is None:
            if isinstance(valeur, (list, tuple)):
                ajouts += _bloc_liste(str(cle), ": ", valeur, fin_par_defaut)
            else:
                ajouts.append(f"{cle}: {citer(valeur)}{fin_par_defaut}")
            continue

        m = _LIGNE.match(lignes[numero].rstrip("\r\n"))
        if m is None:
            continue
        fin = _fin_de_ligne(lignes[numero]) or fin_par_defaut

        if isinstance(valeur, (list, tuple)):
            jusqua = _etendue_liste(lignes, numero)
            remplacements.append(
                (numero, jusqua,
                 _bloc_liste(m.group("indent") + m.group("cle"), m.group("sep"),
                             valeur, fin)))
            continue

        commentaire = m.group("fin") or ""
        if commentaire:
            commentaire = " " + commentaire.strip()
        remplacements.append((numero, numero, [
            f"{m.group('indent')}{m.group('cle')}{m.group('sep')}"
            f"{citer(valeur)}{commentaire}{fin}"]))

    for debut, fin_bloc, nouvelles in sorted(remplacements, reverse=True):
        lignes[debut:fin_bloc + 1] = nouvelles

    if ajouts:
        if lignes and not lignes[-1].endswith(("\n", "\r")):
            lignes[-1] += fin_par_defaut
        lignes += ajouts

    temporaire = chemin.with_name(chemin.name + ".pytestrunner.tmp")
    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lignes))
        temporaire.replace(chemin)
    except OSError as exc:
        try:
            temporaire.unlink()
        except OSError:
            pass
        return False, str(exc)

    return True, ""


def ecrire_texte(chemin: Path, texte: str) -> tuple[bool, str]:
    """Remplace le fichier entier par ce texte, atomiquement.

    Utilise par l'onglet YAML, ou l'on edite le fichier tel quel : c'est alors
    le texte de l'utilisateur qui fait foi, commentaires compris.
    """
    chemin = Path(chemin)
    temporaire = chemin.with_name(chemin.name + ".pytestrunner.tmp")
    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as f:
            f.write(texte)
        temporaire.replace(chemin)
    except OSError as exc:
        try:
            temporaire.unlink()
        except OSError:
            pass
        return False, str(exc)
    return True, ""


def valider(texte: str) -> tuple[bool, str]:
    """Le texte est-il un YAML de cles valide ? Rend (valide, message).

    Verifie AVANT d'ecrire : un fichier invalide rend le workspace
    incollectable, et l'erreur apparaitrait alors loin d'ici, sous la forme
    d'une collecte qui echoue sans raison apparente.
    """
    try:
        import yaml

        donnees = yaml.safe_load(texte)
    except Exception as exc:
        premiere = str(exc).strip().splitlines()
        return False, premiere[0] if premiere else "invalid YAML"

    if donnees is None or isinstance(donnees, dict):
        return True, ""
    return False, "the file must be a list of key: value settings"
