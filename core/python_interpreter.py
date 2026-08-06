"""Resolution de l'interpreteur Python utilise pour collecter et executer les tests.

L'interface et les tests vivent dans deux processus distincts : le GUI ne fait
que lancer pytest en sous-processus et lire sa sortie, il n'importe jamais le
code teste. Rien n'oblige donc les deux a partager le meme Python, et c'est
precisement ce qui permet de piloter depuis une interface 32 bits des tests qui
ont besoin d'un Python 64 bits (par exemple pour charger des DLL natives).

Ordre de priorite applique par resolve_interpreter() :
  1. la cle `python_executable` du config.yml du workspace (specifique au projet)
  2. le reglage global de l'application (QSettings, fourni par l'appelant)
  3. le Python courant

Attention au cas "application figee" (PyInstaller) : sys.executable pointe alors
vers le .exe du GUI, pas vers un Python. L'utiliser relancerait une copie de
l'interface au lieu de pytest, d'ou default_interpreter() qui cherche un vrai
Python sur le PATH dans ce cas.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def is_frozen() -> bool:
    """Vrai si l'application tourne empaquetee par PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def subprocess_flags() -> int:
    """Flags Popen evitant l'ouverture d'une console noire sous Windows.

    Sans ca, chaque appel a pytest fait clignoter une fenetre de console quand le
    GUI est empaquete en application fenetree. La sortie est de toute facon
    capturee par un pipe, donc rien n'est perdu.
    """
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def default_interpreter() -> str:
    """Interpreteur utilise quand rien n'est configure.

    En mode normal c'est le Python qui execute le GUI. En mode fige il n'y a pas
    de Python courant utilisable : on cherche alors un interpreteur sur le PATH,
    et on retourne une chaine vide si aucun n'est trouve (l'appelant affiche
    alors un message demandant de configurer le chemin).
    """
    if not is_frozen():
        return sys.executable

    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return found

    return ""


def _find_config_file(workspace: str) -> Path | None:
    root = Path(workspace)
    for name in ("config.yaml", "config.yml"):
        path = root / name
        if path.is_file():
            return path
    return None


def interpreter_from_config(workspace: str | None) -> str | None:
    """Lit la cle `python_executable` du config.yml du workspace, si presente."""
    if not workspace:
        return None

    config_path = _find_config_file(workspace)
    if config_path is None:
        return None

    try:
        import yaml  # type: ignore

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    value = data.get("python_executable") or data.get("python")
    if not value:
        return None

    value = str(value).strip()
    return value or None


def resolve_interpreter(configured: str | None = None, workspace: str | None = None) -> str:
    """Chemin de l'interpreteur a utiliser, selon l'ordre de priorite du module.

    Un chemin configure est retourne tel quel meme s'il est invalide : l'erreur
    doit remonter a l'utilisateur avec le chemin fautif, pas etre masquee par un
    repli silencieux sur un autre Python qui donnerait des resultats trompeurs.
    """
    from_config = interpreter_from_config(workspace)
    if from_config:
        return from_config

    if configured and str(configured).strip():
        return str(configured).strip()

    return default_interpreter()


def interpreter_source(configured: str | None = None, workspace: str | None = None) -> str:
    """Origine lisible de l'interpreteur resolu, pour l'afficher dans le GUI."""
    if interpreter_from_config(workspace):
        return "config.yml du workspace"
    if configured and str(configured).strip():
        return "reglage de l'application"
    if is_frozen():
        return "Python trouve sur le PATH"
    return "Python courant"


@dataclass
class InterpreterInfo:
    """Ce qu'on sait d'un interpreteur apres l'avoir interroge."""

    path: str
    version: str = ""
    bits: int = 0
    pytest_version: str = ""
    has_xdist: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def summary(self) -> str:
        """Resume en une ligne, affiche sous le champ de saisie du GUI."""
        if self.error:
            return self.error

        parts = [f"Python {self.version} ({self.bits} bits)"]
        if self.pytest_version:
            parts.append(f"pytest {self.pytest_version}")
        else:
            parts.append("pytest ABSENT")
        parts.append("pytest-xdist present" if self.has_xdist else "pytest-xdist absent")
        return " - ".join(parts)


_PROBE_CODE = (
    "import struct, sys\n"
    "print(sys.version.split()[0])\n"
    "print(struct.calcsize('P') * 8)\n"
    "try:\n"
    "    import pytest\n"
    "    print(pytest.__version__)\n"
    "except Exception:\n"
    "    print('')\n"
    "try:\n"
    "    import xdist\n"
    "    print('yes')\n"
    "except Exception:\n"
    "    print('')\n"
)


# Resultats de probe_interpreter() deja obtenus, cles par (chemin, mtime, taille)
# pour qu'une mise a jour de l'interpreteur invalide l'entree automatiquement.
#
# Ce cache existe parce qu'un probe lance un vrai processus Python et y importe
# pytest : plusieurs centaines de millisecondes, voire une a deux secondes sous
# Windows avec un antivirus. Le payer a chaque lancement de tests gelait
# l'interface.
_PROBE_CACHE: dict[tuple, InterpreterInfo] = {}


def _cache_key(path: str) -> tuple:
    try:
        stat = os.stat(path)
        return (path, stat.st_mtime, stat.st_size)
    except OSError:
        return (path, None, None)


def cached_probe(path: str) -> InterpreterInfo | None:
    """Resultat deja connu pour cet interpreteur, ou None s'il n'a jamais ete teste.

    Permet aux appelants du thread UI de repondre instantanement sans jamais
    lancer de processus.
    """
    if not path:
        return None
    return _PROBE_CACHE.get(_cache_key(str(path).strip()))


def forget_probe(path: str | None = None) -> None:
    """Oublie un resultat mis en cache (ou tous si path est None)."""
    if path is None:
        _PROBE_CACHE.clear()
    else:
        _PROBE_CACHE.pop(_cache_key(str(path).strip()), None)


def probe_interpreter(path: str, timeout: float = 15.0, use_cache: bool = True) -> InterpreterInfo:
    """Interroge un interpreteur : version, architecture, pytest disponible.

    ATTENTION : lance un processus. A n'appeler QUE depuis un thread de travail,
    jamais depuis le thread UI. Le thread UI doit passer par cached_probe().
    """
    if not path or not str(path).strip():
        return InterpreterInfo(path=path, error="Aucun interpreteur configure.")

    path = str(path).strip()

    key = _cache_key(path)

    if use_cache:
        cached = _PROBE_CACHE.get(key)
        if cached is not None:
            return cached

    info = _run_probe(path, timeout)
    _PROBE_CACHE[key] = info
    return info


def _run_probe(path: str, timeout: float) -> InterpreterInfo:
    try:
        process = subprocess.run(
            [path, "-c", _PROBE_CODE],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess_flags(),
        )
    except FileNotFoundError:
        return InterpreterInfo(path=path, error=f"Interpreteur introuvable : {path}")
    except PermissionError:
        return InterpreterInfo(path=path, error=f"Interpreteur non executable : {path}")
    except subprocess.TimeoutExpired:
        return InterpreterInfo(path=path, error=f"Aucune reponse de l'interpreteur : {path}")
    except OSError as exc:
        return InterpreterInfo(path=path, error=f"Interpreteur inutilisable : {path} ({exc})")

    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"code de sortie {process.returncode}"
        return InterpreterInfo(path=path, error=f"Ce n'est pas un interpreteur Python valide : {message}")

    lines = process.stdout.splitlines()
    while len(lines) < 4:
        lines.append("")

    try:
        bits = int(lines[1].strip() or 0)
    except ValueError:
        bits = 0

    return InterpreterInfo(
        path=path,
        version=lines[0].strip(),
        bits=bits,
        pytest_version=lines[2].strip(),
        has_xdist=lines[3].strip() == "yes",
    )


def check_ready_to_run(path: str, parallel: bool = False, cached_only: bool = True) -> str:
    """Retourne un message d'erreur pret a afficher, ou une chaine vide si tout va bien.

    Appele juste avant un run. Par defaut (cached_only), ne lance JAMAIS de
    processus : il ne repond que sur la base d'un probe deja effectue dans un
    thread de travail. C'est indispensable car cette fonction est appelee depuis
    le thread UI, ou un probe synchrone gelait l'interface a chaque lancement.

    Quand rien n'est en cache, on laisse le run partir : collect_tests et les
    workers traduisent deja clairement un interpreteur invalide ou un pytest
    manquant, et un test qui demarre vaut mieux qu'une interface figee.
    """
    if not path:
        return (
            "Aucun interpreteur Python n'est configure pour les tests.\n"
            "Ouvrez le menu Configuration > Interpreteur Python des tests... "
            "et indiquez le chemin de python.exe."
        )

    info = cached_probe(path) if cached_only else probe_interpreter(path)

    if info is None:
        return ""

    if info.error:
        return (
            f"{info.error}\n\n"
            "Corrigez le chemin dans le menu Configuration > Interpreteur Python des tests..."
        )

    if not info.pytest_version:
        return (
            f"pytest n'est pas installe dans l'interpreteur des tests :\n  {path}\n\n"
            "C'est cet interpreteur-la qui doit avoir pytest, pas celui de l'interface.\n"
            f"Installez-le avec :\n  \"{path}\" -m pip install pytest"
        )

    if parallel and not info.has_xdist:
        return (
            f"L'option Parallel necessite pytest-xdist dans l'interpreteur des tests :\n  {path}\n\n"
            f"Installez-le avec :\n  \"{path}\" -m pip install pytest-xdist\n\n"
            "Vous pouvez aussi decocher Parallel pour lancer les tests en sequentiel."
        )

    return ""
