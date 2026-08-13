"""Reglages pytest lus dans la configuration du workspace.

Un workspace decrit comment ses tests doivent tourner : quel Python, quels
chemins ajouter au PYTHONPATH, quel mode d'import. Ces reglages etaient soit
codes en dur, soit cherches dans le seul `config.yml`, ce qui les rendait
invisibles pour un projet dont la configuration porte un autre nom.

Ce module centralise leur lecture : memes candidats que le bouton "Ouvrir la
configuration", meme tolerance aux sections imbriquees.
"""

from __future__ import annotations

import os
from pathlib import Path

# Noms reconnus en priorite. Le reste des YAML de la racine est examine ensuite,
# par ordre alphabetique.
STANDARD_CONFIG_NAMES = ("config.yaml", "config.yml")

INTERPRETER_KEYS = ("python_executable", "python", "interpreter")
IMPORT_MODE_KEYS = ("import_mode", "importmode")
PYTHONPATH_KEYS = ("pythonpath", "python_path", "extra_paths", "sys_path")

# Valeurs acceptees par pytest. Une valeur inconnue est ignoree plutot que
# transmise : pytest refuserait de demarrer et l'utilisateur verrait une erreur
# d'usage a la place de ses tests.
IMPORT_MODES = ("prepend", "append", "importlib")


def normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def discover_config_files(workspace: str | None) -> list[Path]:
    """Fichiers YAML de la racine du workspace, les noms standards en tete."""
    if not workspace:
        return []

    root = Path(workspace)
    if not root.is_dir():
        return []

    fichiers: list[Path] = []
    for name in STANDARD_CONFIG_NAMES:
        chemin = root / name
        if chemin.is_file():
            fichiers.append(chemin)

    try:
        autres = [
            p for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in (".yml", ".yaml")
            and p.name not in STANDARD_CONFIG_NAMES
        ]
    except OSError:
        autres = []

    fichiers.extend(sorted(autres, key=lambda p: p.name.lower()))
    return fichiers


def load_config(path: Path) -> dict:
    try:
        import yaml  # type: ignore

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def find_setting(data: dict, keys: tuple[str, ...]):
    """Premiere valeur non vide portee par l'une de ces cles.

    Le niveau courant est examine en entier avant de descendre : un reglage
    pose a la racine du fichier prime sur celui que declarerait une section.
    """
    if not isinstance(data, dict):
        return None

    for key, value in data.items():
        if normalize_key(key) in keys and value not in (None, "", [], {}):
            return value

    for value in data.values():
        if isinstance(value, dict):
            trouve = find_setting(value, keys)
            if trouve is not None:
                return trouve
    return None


def setting_for(workspace: str | None, keys: tuple[str, ...],
                config_path: str | None = None):
    """Reglage lu dans la configuration du workspace, ou None.

    `config_path` est le fichier que l'utilisateur a designe ; il est consulte
    en premier.
    """
    candidats: list[Path] = []
    if config_path:
        chemin = Path(config_path)
        if chemin.is_file():
            candidats.append(chemin)
    candidats.extend(discover_config_files(workspace))

    for chemin in candidats:
        trouve = find_setting(load_config(chemin), keys)
        if trouve is not None:
            return trouve
    return None


def config_file_declaring(workspace: str | None, keys: tuple[str, ...],
                          config_path: str | None = None) -> Path | None:
    """Fichier de configuration qui porte l'une de ces cles, ou None.

    Sert quand il faut ECRIRE dans la configuration : encore faut-il savoir
    laquelle. Le fichier designe par l'utilisateur est examine en premier.
    """
    candidats: list[Path] = []
    if config_path:
        chemin = Path(config_path)
        if chemin.is_file():
            candidats.append(chemin)
    candidats.extend(discover_config_files(workspace))

    for chemin in candidats:
        if find_setting(load_config(chemin), keys) is not None:
            return chemin
    return None


# ------------------------------------------------------------------ mode d'import

def import_mode_for(workspace: str | None, config_path: str | None = None) -> str:
    """Mode d'import pytest voulu par ce workspace, ou "" pour son defaut.

    Retourner "" est le cas normal : on laisse alors pytest choisir, comme le
    font la ligne de commande et VS Code. `prepend`, le defaut de pytest, insere
    le dossier du fichier de test en tete de sys.path, ce dont dependent les
    suites qui importent un module voisin (`import imports_MaTestSuite`) depuis
    leur conftest.
    """
    valeur = setting_for(workspace, IMPORT_MODE_KEYS, config_path)
    if valeur is None:
        return ""

    mode = str(valeur).strip().lower()
    return mode if mode in IMPORT_MODES else ""


def import_mode_args(workspace: str | None, config_path: str | None = None) -> list[str]:
    """Arguments pytest pour le mode d'import, vides si rien n'est configure."""
    mode = import_mode_for(workspace, config_path)
    return [f"--import-mode={mode}"] if mode else []


# ------------------------------------------------------------------- readers

READERS_KEYS = ("readers", "reader_list", "lecteurs")
READER_KEYS = ("reader", "lecteur")
READER_ENV_KEYS = ("reader_env", "reader_env_var", "reader_variable")

# Variable d'environnement portant le lecteur d'un run. Le workspace ne peut pas
# le recevoir autrement : deux processus lances en meme temps partagent le meme
# config.yml, donc y ecrire le lecteur du moment est impossible. Les tests lisent
# donc cette variable, avec repli sur la cle Reader du fichier.
DEFAULT_READER_ENV = "PYTESTRUNNER_READER"

READER_MODE_KEYS = ("reader_mode", "readers_mode", "mode_lecteurs")

# Deux facons d'enchainer plusieurs lecteurs.
#
# `sequential` les joue l'un apres l'autre, en ecrivant chacun dans la cle
# `Reader` du fichier de configuration avant son run. C'est le seul mode qui ne
# demande RIEN au code de test : celui-ci continue de lire un lecteur unique,
# comme il l'a toujours fait. Filet de securite quand aucun autre moyen n'est
# declare de distinguer les lecteurs entre processus simultanes.
#
# `parallel` lance tout en meme temps. Le lecteur ne peut alors pas passer par
# le fichier, que tous les processus partagent : il passe par un plugin injecte
# qui remplace la fonction du workspace, designee par `reader_getter` :
#     reader_getter: config_getters.getConfigReader
# Cette fonction vit souvent dans un conftest.py, dont le nom de module reel
# depend de la structure du workspace et n'est pas toujours previsible ; le nom
# seul suffit alors (voir core/reader_plugin.py) :
#     reader_getter: getConfigReader
# C'est un choix SANS DANGER des que cette cle est presente (le plugin echoue
# bruyamment plutot que de laisser tous les lecteurs lire la meme valeur), donc
# c'est le mode retenu automatiquement quand elle est declaree. `reader_mode`
# permet de forcer l'un ou l'autre explicitement, y compris pour revenir au
# sequentiel malgre un reader_getter present.
READER_MODES = ("sequential", "parallel")
DEFAULT_READER_MODE = "sequential"

READER_GETTER_KEYS = ("reader_getter", "reader_function", "getter_reader")


def reader_getter_for(workspace: str | None, config_path: str | None = None) -> str:
    """Fonction du workspace qui donne le lecteur.

    Sous la forme `module.fonction`, ou juste `fonction` quand elle vit dans un
    conftest.py (voir core/reader_plugin.py pour la recherche que ce deuxieme
    cas declenche). Declaree, elle permet le mode parallele sans modifier le
    code de test : un plugin injecte la remplace le temps du run. Absente, le
    lecteur ne passe que par la variable d'environnement, que le workspace doit
    alors lire lui-meme.
    """
    valeur = setting_for(workspace, READER_GETTER_KEYS, config_path)
    return str(valeur).strip() if valeur is not None else ""


def reader_mode_for(workspace: str | None, config_path: str | None = None) -> str:
    """Comment enchainer les lecteurs : l'un apres l'autre, ou tous a la fois.

    Sans reglage explicite, le parallele est choisi des qu'un reader_getter est
    declare -- c'est alors sans risque -- et le sequentiel sinon, puisque c'est
    le seul mode qui ne demande rien au code de test.
    """
    valeur = setting_for(workspace, READER_MODE_KEYS, config_path)
    if valeur is not None:
        mode = str(valeur).strip().lower()
        if mode in READER_MODES:
            return mode

    if reader_getter_for(workspace, config_path):
        return "parallel"
    return DEFAULT_READER_MODE


def reader_env_var(workspace: str | None, config_path: str | None = None) -> str:
    """Nom de la variable d'environnement portant le lecteur."""
    valeur = setting_for(workspace, READER_ENV_KEYS, config_path)
    texte = str(valeur).strip() if valeur is not None else ""
    return texte or DEFAULT_READER_ENV


def readers_for(workspace: str | None, config_path: str | None = None) -> list[str]:
    """Lecteurs a tester, le lecteur principal en tete.

    `Reader` est celui que les tests lisent, et il reste le premier. `Readers`
    liste ceux qu'on veut tester EN PLUS : le bouton "+" de la configuration
    ajoute la, sans jamais toucher a `Reader`.
    """
    principal = setting_for(workspace, READER_KEYS, config_path)
    supplement = setting_for(workspace, READERS_KEYS, config_path)

    noms: list[str] = []
    if principal is not None:
        noms.append(str(principal).strip())

    if isinstance(supplement, (list, tuple)):
        noms.extend(str(v).strip() for v in supplement)
    elif supplement is not None:
        noms.append(str(supplement).strip())

    # Un meme lecteur deux fois donnerait deux runs identiques et deux colonnes
    # indiscernables.
    vus: list[str] = []
    for nom in noms:
        if nom and nom not in vus:
            vus.append(nom)
    return vus


def reader_env(workspace: str | None, reader: str, config_path: str | None = None) -> dict:
    """Environnement du processus pytest pour ce lecteur."""
    env = pytest_env(workspace, config_path)
    if reader:
        env[reader_env_var(workspace, config_path)] = reader
    return env


# ------------------------------------------------------------------ console

CONSOLE_PATH_KEYS = ("console_path_levels", "console_paths", "console_path")
CLASS_DISPLAY_KEYS = ("show_test_class", "show_class", "show_classes")

VRAI = ("true", "vrai", "oui", "yes", "1", "always", "toujours")


def show_test_classes(workspace: str | None, config_path: str | None = None) -> bool:
    """Faut-il garder le niveau de classe a l'affichage ?

    Non par defaut : dans les suites ou chaque fichier n'a qu'une classe, son
    nom reprend celui du fichier et occupe une ligne de l'arbre pour rien.
    L'arbre garde tout de meme ce niveau des qu'un fichier contient plusieurs
    classes, sans quoi deux tests de meme nom se retrouveraient cote a cote.
    """
    valeur = setting_for(workspace, CLASS_DISPLAY_KEYS, config_path)
    if valeur is None:
        return False
    if isinstance(valeur, bool):
        return valeur
    return str(valeur).strip().lower() in VRAI

# Dossiers conserves devant le nom du fichier dans la console. Un seul suffit :
# il porte le nom de la suite, et ce qui precede se repete a chaque ligne.
DEFAULT_CONSOLE_PATH_LEVELS = 1


def console_path_levels(workspace: str | None, config_path: str | None = None) -> int:
    """Nombre de dossiers a garder devant le nom du fichier dans la console.

    `full` (ou -1) desactive le raccourcissement, `0` ne laisse que le nom du
    fichier. Une valeur incomprise retombe sur le defaut plutot que de faire
    disparaitre l'information.
    """
    valeur = setting_for(workspace, CONSOLE_PATH_KEYS, config_path)
    if valeur is None:
        return DEFAULT_CONSOLE_PATH_LEVELS

    if isinstance(valeur, bool):
        return DEFAULT_CONSOLE_PATH_LEVELS
    if isinstance(valeur, int):
        return valeur

    texte = str(valeur).strip().lower()
    if texte in ("full", "complet", "long"):
        return -1
    if texte in ("court", "short"):
        return 0
    try:
        return int(texte)
    except ValueError:
        return DEFAULT_CONSOLE_PATH_LEVELS


# --------------------------------------------------------------------- PYTHONPATH

def looks_absolute(chemin: str) -> bool:
    """Vrai si ce texte designe un chemin absolu, Windows ou POSIX.

    Path.is_absolute() depend de la plateforme : sous Linux, `C:\\Projets\\...`
    passe pour relatif et se retrouve colle derriere le workspace. Les
    configurations sont ecrites sous Windows mais relues par les tests des deux
    cotes, d'ou cette reconnaissance explicite.
    """
    texte = str(chemin).strip()
    if not texte:
        return False
    if texte.startswith(("/", "\\\\")):
        return True
    return len(texte) >= 3 and texte[1] == ":" and texte[2] in "/\\" and texte[0].isalpha()


def pythonpath_for(workspace: str | None, config_path: str | None = None) -> list[str]:
    """Chemins a ajouter au PYTHONPATH des tests, resolus depuis le workspace.

    Equivalent du PYTHONPATH que VS Code compose pour la decouverte des tests :
    c'est par la qu'un framework externe est rendu importable.
    """
    valeur = setting_for(workspace, PYTHONPATH_KEYS, config_path)
    if valeur is None:
        return []

    if isinstance(valeur, (list, tuple)):
        bruts = [str(v) for v in valeur]
    else:
        # Une chaine unique peut contenir plusieurs chemins, comme un PYTHONPATH.
        bruts = str(valeur).split(os.pathsep)

    chemins: list[str] = []
    for brut in bruts:
        brut = brut.strip()
        if not brut:
            continue
        if looks_absolute(brut):
            chemins.append(brut)
        elif workspace:
            chemins.append(str(Path(workspace) / brut))
        else:
            chemins.append(brut)
    return chemins


def pytest_env(workspace: str | None, config_path: str | None = None) -> dict:
    """Environnement du processus pytest, PYTHONPATH complete si besoin.

    Les chemins configures passent devant ceux deja presents : un workspace doit
    pouvoir imposer sa version d'un framework.
    """
    env = dict(os.environ)

    chemins = pythonpath_for(workspace, config_path)
    if not chemins:
        return env

    existant = env.get("PYTHONPATH", "")
    morceaux = chemins + ([existant] if existant else [])
    env["PYTHONPATH"] = os.pathsep.join(morceaux)
    return env
