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
