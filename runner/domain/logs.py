"""Retrouver le fichier .log qu'un test vient de produire.

Le conftest d'un workspace ecrit un .log par test. C'est souvent la seule
trace de ce que la carte a reellement repondu -- la sortie pytest, elle, ne
montre que le verdict. Relier un test a son log est donc la moitie du travail
de diagnostic.

Rien n'est normalise dans la facon d'ecrire ces fichiers. Certains conftest
tiennent un manifeste qui fait le lien ; la plupart se contentent de poser des
fichiers dans une arborescence horodatee, en assainissant le nodeid a leur
facon. Ce module gere les deux, et donne son ordre de priorite : le manifeste
d'abord parce qu'il est exact, la recherche ensuite parce qu'elle marche
partout.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFESTE = "last_run_index.json"

# Extensions considerees comme des logs. Les conftest ne sont pas d'accord.
SUFFIXES = (".log", ".txt")

# Plafond de fichiers examines DANS UN dossier de run. Un plafond global
# laisserait des mois d'historique consommer le budget avant meme d'atteindre
# le run du jour, et le log cherche ne serait jamais vu.
MAX_FICHIERS = 4000

# Dossiers de run explores, du plus recent au plus ancien.
MAX_DOSSIERS_RUN = 12

# Le dossier horodate n'est pas toujours un enfant direct de la racine : il est
# souvent range sous un dossier de projet.
MAX_PROFONDEUR = 3
MAX_DOSSIERS_VISITES = 500

# Un dossier de run porte une date : 20260810_112653, 2026-08-10_11-26-53,
# 2026-08-10T11:26:53... Le nom est plus fiable que son mtime : sous Windows,
# deux dossiers crees dans le meme run peuvent avoir exactement le meme mtime.
_DATE = re.compile(
    r"(?P<annee>\d{4})[-_.]?(?P<mois>\d{2})[-_.]?(?P<jour>\d{2})"
    r"(?:[T _.-]?(?P<heure>\d{2})[-_.:]?(?P<minute>\d{2})"
    r"[-_.:]?(?P<seconde>\d{2}))?"
)

# Prime au fichier dont le nom se TERMINE par l'identifiant du parametre. Elle
# doit l'emporter sur tout comptage de morceaux : c'est le seul moyen de
# distinguer `[...HashAlg==SHA512]` de `[...HashAlg==SHA512_256]`, dont le
# premier est un prefixe du second.
PRIME_PARAMETRE = 100


def cle(valeur: str) -> str:
    """Reduit une chaine a ses caracteres alphanumeriques, en minuscules.

    Les conftest assainissent les nodeids chacun a leur facon : `cas-1`,
    `cas_1` et `cas.1` doivent tous se reconnaitre dans un nom de fichier.
    """
    return "".join(c for c in str(valeur).lower() if c.isalnum())


def nodeid_tokens(nodeid: str) -> list[str]:
    """Morceaux identifiants d'un nodeid, du fichier au parametre.

    `a/b/test_x.py::TestC::test_f[cas-1]` donne
    `['test_x', 'TestC', 'test_f', 'cas-1']`.
    """
    nodeid = str(nodeid).replace("\\", "/").strip()
    chemin, _, reste = nodeid.partition("::")

    morceaux = [Path(chemin).stem] if chemin else []
    for partie in reste.split("::"):
        if not partie:
            continue
        base, _, parametre = partie.partition("[")
        if base:
            morceaux.append(base)
        if parametre:
            morceaux.append(parametre.rstrip("]"))
    return morceaux


def _obligatoires(nodeid: str, morceaux: list[str]) -> list[str]:
    """Morceaux qui doivent apparaitre pour qu'un fichier soit retenu.

    Le nom de la fonction ne suffit pas : normalise, `test_pso` se retrouve
    dans `test_PSO_CDS_RSA`, donc tout log du meme fichier passerait. On exige
    donc aussi l'identifiant du parametre, bien plus discriminant.
    """
    if str(nodeid).strip().endswith("]") and len(morceaux) >= 2:
        exiges = [cle(morceaux[-2]), cle(morceaux[-1])]
    else:
        exiges = [cle(morceaux[-1])] if morceaux else []
    return [t for t in exiges if t]


def _date_de(chemin: Path) -> float:
    try:
        return chemin.stat().st_mtime
    except OSError:
        return 0.0


def _ordre_run(chemin: Path) -> tuple[int, float]:
    """Horodate du nom, puis mtime seulement pour departager.

    Trier uniquement sur le mtime rendait l'ordre aleatoire sous Windows quand
    sa precision fusionnait deux creations proches. Or le conftest donne deja
    l'ordre exact dans le nom du dossier.
    """
    trouve = _DATE.search(chemin.name)
    if trouve is None:
        return 0, _date_de(chemin)
    morceaux = [
        trouve.group("annee"), trouve.group("mois"), trouve.group("jour"),
        trouve.group("heure") or "00", trouve.group("minute") or "00",
        trouve.group("seconde") or "00",
    ]
    return int("".join(morceaux)), _date_de(chemin)


def _sous_dossiers(chemin: Path) -> list[Path]:
    try:
        return [p for p in chemin.iterdir() if p.is_dir()]
    except OSError:
        return []


def _porte_le_composant(chemin: Path, attendu: str) -> bool:
    """Vrai si un DOSSIER du chemin porte exactement ce nom (normalise).

    La comparaison porte sur les composants, pas sur le chemin entier : le
    lecteur `Reader` se retrouverait sinon dans `.../Cosmo11Secured Reader/...`
    et chaque lecteur dont le nom est contenu dans un autre emprunterait son
    log.
    """
    return any(cle(part) == attendu for part in chemin.parts)


def run_directories(log_root: Path) -> list[Path]:
    """Dossiers de run sous la racine, du plus recent au plus ancien.

    Les conftest horodatent le dossier de chaque run et y recreent
    l'arborescence des tests. Le log cherche est presque toujours dans le plus
    recent : commencer par la evite de parcourir tout l'historique, et surtout
    evite de repondre avec le log d'un run precedent.

    Le dossier horodate n'est pas forcement un enfant direct de la racine. On
    descend donc jusqu'a `MAX_PROFONDEUR` en s'arretant des qu'un nom porte une
    date, ce qui evite de plonger dans l'arborescence des tests recreee en
    dessous.
    """
    horodates: list[Path] = []
    a_explorer: list[tuple[Path, int]] = [(log_root, 0)]
    visites = 0

    while a_explorer and visites < MAX_DOSSIERS_VISITES:
        dossier, profondeur = a_explorer.pop(0)
        for enfant in _sous_dossiers(dossier):
            visites += 1
            if _DATE.search(enfant.name):
                horodates.append(enfant)
            elif profondeur + 1 < MAX_PROFONDEUR:
                a_explorer.append((enfant, profondeur + 1))

    if not horodates:
        # Conftest qui ne date pas ses dossiers : on retombe sur les enfants
        # directs, qui restent une decoupe plus fine que la racine entiere.
        horodates = _sous_dossiers(log_root)

    horodates.sort(key=_ordre_run, reverse=True)
    return horodates[:MAX_DOSSIERS_RUN]


def from_manifest(log_root: Path, nodeid: str) -> Path | None:
    """Chemin donne par `<log_root>/last_run_index.json`, s'il y en a un.

    Le rapprochement est souple : le nodeid de l'arbre peut porter un prefixe
    de dossier que la clef du manifeste n'a pas, selon le rootdir de pytest.
    """
    manifeste = Path(log_root) / MANIFESTE
    if not manifeste.is_file():
        return None

    try:
        table = json.loads(manifeste.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(table, dict):
        return None

    def normaliser(valeur: str) -> str:
        return str(valeur).replace("\\", "/").strip()

    vise = normaliser(nodeid)
    chemin = table.get(nodeid) or table.get(vise)
    if not chemin:
        for clef, valeur in table.items():
            connu = normaliser(clef)
            if connu == vise or connu.endswith(vise) or vise.endswith(connu):
                chemin = valeur
                break

    if chemin and Path(chemin).is_file():
        return Path(chemin)
    return None


def _meilleur_sous(zone: Path, exiges: list[str], cherches: list[str],
                   parametre: str = "", lecteur: str = "") -> Path | None:
    """Meilleur fichier de log sous ce dossier, ou None.

    Le rapprochement porte sur le chemin RELATIF au dossier de run, pas sur le
    seul nom de fichier : le conftest y recree l'arborescence des tests, donc
    une partie de l'identite du test est portee par les dossiers
    (`.../TestSuiteCDS/test_PSO_CDS_RSA/[cas].log`). Ne regarder que le nom
    ferait manquer tous ces logs.

    Un morceau reconnu dans le nom du fichier compte double : a dossier egal,
    `[cas-25].log` est un meilleur candidat que le `setup.log` voisin.
    """
    meilleur: tuple[int, float, Path] | None = None
    examines = 0

    for fichier in zone.rglob("*"):
        if examines >= MAX_FICHIERS:
            break
        if fichier.suffix.lower() not in SUFFIXES or not fichier.is_file():
            continue
        examines += 1

        if lecteur and not _porte_le_composant(fichier, lecteur):
            continue

        try:
            relatif = fichier.relative_to(zone)
        except ValueError:
            relatif = fichier

        chemin = cle(str(relatif))
        if any(t not in chemin for t in exiges):
            continue

        nom = cle(fichier.stem)
        score = sum(1 for t in cherches if t in chemin)
        score += sum(1 for t in cherches if t in nom)
        if parametre and (nom.endswith(parametre) or chemin.endswith(parametre)):
            score += PRIME_PARAMETRE

        candidat = (score, _date_de(fichier), fichier)
        if meilleur is None or candidat[:2] > meilleur[:2]:
            meilleur = candidat

    return meilleur[2] if meilleur else None


def by_search(log_root: Path, nodeid: str, reader: str = "") -> Path | None:
    """Cherche le .log dans l'arborescence, sans manifeste.

    C'est le cas de la plupart des workspaces, dont le conftest se contente
    d'ecrire des fichiers. On examine les dossiers de run du plus recent au
    plus ancien et on s'arrete au premier qui contient le test : c'est le
    resultat qui vient d'etre produit. La racine elle-meme passe en dernier,
    pour les conftest qui n'horodatent pas.
    """
    racine = Path(log_root)
    if not racine.is_dir():
        return None

    morceaux = nodeid_tokens(nodeid)
    exiges = _obligatoires(nodeid, morceaux)
    if not exiges:
        return None

    # Le conftest range souvent ses logs par lecteur : exiger ce dossier est ce
    # qui permet d'ouvrir cote a cote le log du meme test vu par deux lecteurs.
    cle_lecteur = cle(reader) if reader else ""
    cherches = [c for c in (cle(t) for t in morceaux) if c]

    # L'identifiant du parametre termine le nom du fichier quand le conftest le
    # nomme d'apres le nodeid : s'en servir departage les cas dont l'un est le
    # prefixe de l'autre.
    parametre = cle(morceaux[-1]) if str(nodeid).strip().endswith("]") else ""

    for zone in run_directories(racine) + [racine]:
        trouve = _meilleur_sous(zone, exiges, cherches, parametre, cle_lecteur)
        if trouve is not None:
            return trouve
    return None


def find_test_log(log_root: Path, nodeid: str, reader: str = "") -> Path | None:
    """Fichier .log du dernier run pour ce test, ou None.

    Le manifeste passe en premier quand il existe : il est exact et immediat.
    A defaut on cherche, ce qui fonctionne avec n'importe quel conftest.

    `reader` restreint aux logs de ce lecteur. Le manifeste ne connait qu'un
    log par test : quand il en donne un qui n'est pas celui du lecteur demande,
    on repasse par la recherche plutot que de rendre le log d'un autre lecteur
    sous son nom.
    """
    if not nodeid or log_root is None:
        return None

    depuis_manifeste = from_manifest(Path(log_root), nodeid)
    if depuis_manifeste is not None:
        if not reader or _porte_le_composant(depuis_manifeste, cle(reader)):
            return depuis_manifeste

    return by_search(Path(log_root), nodeid, reader)


def find_logs_for_build(log_root: Path, build_number: int,
                        reader: str = "") -> list[Path]:
    """Retrouve tous les logs d'un build, dans les deux modes d'ecriture.

    Normal : ``date/Run_0042/.../*.log``.
    Incremental : ``date/.../*_B0042_001.log``.
    """
    racine = Path(log_root)
    if not racine.is_dir():
        return []

    build = f"{int(build_number):04d}"
    composant_normal = f"Run_{build}"
    marque_incrementale = f"_B{build}_"
    lecteur = cle(reader) if reader else ""
    trouves: list[Path] = []

    # Les manifestes donnent la reponse sans parcourir les mois precedents.
    for manifeste in racine.glob(f"*/build_{build}*.json"):
        try:
            table = json.loads(manifeste.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for valeur in table.values() if isinstance(table, dict) else ():
            chemin = Path(valeur)
            if (chemin.is_file()
                    and (not lecteur or _porte_le_composant(chemin, lecteur))):
                trouves.append(chemin)

    # Complete toujours par les fichiers. Sous xdist, plusieurs workers peuvent
    # ecrire le manifeste simultanement, mais leurs logs restent tous presents.
    for chemin in racine.rglob("*.log"):
        if (composant_normal not in chemin.parts
                and marque_incrementale not in chemin.name):
            continue
        if lecteur and not _porte_le_composant(chemin, lecteur):
            continue
        trouves.append(chemin)
        if len(trouves) >= MAX_FICHIERS:
            break

    return sorted(set(trouves), key=lambda path: str(path).lower())


def places_searched(log_root: Path) -> list[Path]:
    """Les endroits que `find_test_log` a regardes, dans l'ordre.

    Sert a expliquer une absence. « No log found » laisse penser a une panne de
    l'outil ; montrer ou l'on a cherche fait voir tout de suite que le dossier
    est vide, que le run n'a rien ecrit, ou que LOG_PATH ne pointe pas la ou
    l'on croyait.
    """
    racine = Path(log_root) if log_root is not None else None
    if racine is None or not racine.is_dir():
        return []
    return run_directories(racine) + [racine]
