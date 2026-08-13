"""Changement du lecteur actif dans la configuration du workspace.

Les tests d'un workspace lisent UN lecteur, par une fonction du genre
`getConfigReader()` qui va chercher la cle `Reader` du fichier de configuration.
Plusieurs lecteurs a la fois n'y sont pas prevus, et le prevoir demanderait de
modifier le code de test.

L'interface s'en charge donc a leur place : elle ecrit le lecteur voulu dans la
cle `Reader` avant chaque lancement, et remet la valeur d'origine ensuite. Les
lecteurs sont alors joues l'un apres l'autre plutot qu'en meme temps -- deux
processus simultanes se disputeraient ce fichier.

L'ecriture est faite a la LIGNE, pas en relisant/reserialisant le YAML : passer
le fichier dans un yaml.safe_dump reordonnerait les cles, effacerait les
commentaires et reformaterait tout. Ici seule la ligne du lecteur change, le
reste du fichier est rendu octet pour octet.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.workspace_config import READER_KEYS, normalize_key

# Caracteres qui obligent a mettre la valeur entre guillemets pour rester du
# YAML valide.
_A_CITER = set(":#{}[],&*?|<>=!%@`\"'\\")

# Une ligne `Cle: valeur`, en capturant separement l'indentation, la cle, le
# separateur et la valeur (avec un eventuel commentaire de fin de ligne).
_LIGNE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<cle>[A-Za-z_][\w \-]*?)(?P<sep>[ \t]*:[ \t]*)"
    r"(?P<valeur>[^\n#]*)(?P<fin>#.*)?$"
)


def _citer(valeur: str) -> str:
    valeur = str(valeur)
    if not valeur:
        return '""'
    if any(c in _A_CITER for c in valeur) or valeur != valeur.strip():
        return '"' + valeur.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return valeur


def _deciter(valeur: str) -> str:
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        return valeur[1:-1]
    return valeur


def find_reader_line(texte: str) -> int | None:
    """Numero de la ligne portant le lecteur actif, ou None.

    La moins indentee gagne : un `Reader` a la racine du fichier est celui que
    les tests lisent, celui d'une section n'est qu'un reglage de mode.
    """
    meilleure: tuple[int, int] | None = None

    for numero, ligne in enumerate(texte.splitlines()):
        m = _LIGNE_RE.match(ligne)
        if m is None or normalize_key(m.group("cle")) not in READER_KEYS:
            continue
        indent = len(m.group("indent").expandtabs(4))
        if meilleure is None or indent < meilleure[1]:
            meilleure = (numero, indent)

    return meilleure[0] if meilleure else None


def _lire(chemin: Path) -> str | None:
    """Lit le fichier SANS traduire les fins de ligne.

    read_text() convertit les CRLF en LF : le fichier reecrit se retrouverait
    entierement en LF, soit un diff sur chaque ligne d'une configuration
    Windows.
    """
    try:
        with open(chemin, "r", encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def read_active_reader(config_path: str | Path) -> str | None:
    """Lecteur actuellement ecrit dans la configuration, ou None."""
    texte = _lire(Path(config_path))
    if texte is None:
        return None

    numero = find_reader_line(texte)
    if numero is None:
        return None

    m = _LIGNE_RE.match(texte.splitlines()[numero])
    return _deciter(m.group("valeur")) if m else None


def set_active_reader(config_path: str | Path, reader: str) -> str | None:
    """Ecrit ce lecteur dans la configuration. Retourne l'ancienne valeur.

    Retourne None si le fichier n'a pas de cle lecteur : il n'y a alors rien a
    changer, et surtout rien a inventer. L'ecriture passe par un temporaire du
    meme dossier pour ne jamais laisser la configuration a moitie ecrite.
    """
    chemin = Path(config_path)
    texte = _lire(chemin)
    if texte is None:
        return None

    numero = find_reader_line(texte)
    if numero is None:
        return None

    lignes = texte.splitlines(keepends=True)
    m = _LIGNE_RE.match(lignes[numero].rstrip("\r\n"))
    ancienne = _deciter(m.group("valeur"))

    fin_de_ligne = "\r\n" if lignes[numero].endswith("\r\n") else "\n"
    if not lignes[numero].endswith(("\n", "\r")):
        fin_de_ligne = ""

    commentaire = m.group("fin") or ""
    if commentaire:
        commentaire = " " + commentaire.strip()

    lignes[numero] = (
        f"{m.group('indent')}{m.group('cle')}{m.group('sep')}"
        f"{_citer(reader)}{commentaire}{fin_de_ligne}"
    )

    temporaire = chemin.with_name(chemin.name + ".pytestrunner.tmp")
    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lignes))
        temporaire.replace(chemin)
    except OSError:
        try:
            temporaire.unlink()
        except OSError:
            pass
        return None

    return ancienne


class ActiveReader:
    """Ecrit un lecteur le temps d'un run, puis remet celui d'origine.

    La valeur d'origine est aussi deposee a cote du fichier : une coupure de
    courant en plein run laisserait sinon la configuration sur le dernier
    lecteur essaye, sans que personne ne s'en apercoive.
    """

    SUFFIXE = ".pytestrunner-reader-backup"

    def __init__(self, config_path: str | Path | None, reader: str):
        self.config_path = Path(config_path) if config_path else None
        self.reader = reader
        self.previous: str | None = None

    @property
    def marqueur(self) -> Path | None:
        if self.config_path is None:
            return None
        return self.config_path.with_name(self.config_path.name + self.SUFFIXE)

    def __enter__(self) -> "ActiveReader":
        if self.config_path is None or not self.reader:
            return self

        self.previous = set_active_reader(self.config_path, self.reader)
        if self.previous is not None and self.marqueur is not None:
            try:
                self.marqueur.write_text(self.previous, encoding="utf-8")
            except OSError:
                pass
        return self

    def __exit__(self, *exc):
        if self.config_path is None or self.previous is None:
            return False

        set_active_reader(self.config_path, self.previous)
        if self.marqueur is not None:
            try:
                self.marqueur.unlink()
            except OSError:
                pass
        return False


def restore_interrupted_reader(config_path: str | Path | None) -> str | None:
    """Remet le lecteur d'origine si un run precedent a ete interrompu.

    Retourne le lecteur restaure, ou None s'il n'y avait rien a faire.
    """
    if not config_path:
        return None

    chemin = Path(config_path)
    marqueur = chemin.with_name(chemin.name + ActiveReader.SUFFIXE)
    if not marqueur.is_file():
        return None

    try:
        precedent = marqueur.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if precedent:
        set_active_reader(chemin, precedent)
    try:
        marqueur.unlink()
    except OSError:
        pass
    return precedent or None
