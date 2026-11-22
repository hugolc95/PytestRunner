"""Resolution et test de l'interpreteur Python qui execute les tests.

L'interface et les tests vivent dans deux processus distincts : l'interface ne
fait que lancer pytest en sous-processus et lire sa sortie, elle n'importe
jamais le code teste. Rien n'oblige donc les deux a partager le meme Python --
et c'est precisement ce qui permet de piloter, depuis une interface 32 bits,
des tests qui chargent des DLL natives 64 bits.

Piege a eviter absolument, une fois l'interface empaquetee par PyInstaller :
`sys.executable` pointe alors vers l'exe de l'INTERFACE, pas vers un Python.
L'utiliser comme interpreteur des tests relance une copie de l'interface au
lieu de pytest -- une nouvelle fenetre s'ouvre, sans le moindre arbre puisque
aucune collecte n'a jamais eu lieu, et rien ne dit pourquoi. `default()` evite
ce piege en cherchant un vrai Python sur le PATH quand l'application est figee.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass


def is_frozen() -> bool:
    """Vrai si l'application tourne empaquetee par PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def subprocess_flags() -> int:
    """Flags Popen qui evitent une console noire derriere l'interface fenetree."""
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def default() -> str:
    """Interpreteur utilise quand rien n'est configure.

    En mode normal, c'est le Python qui execute l'interface. En mode fige, ce
    Python n'existe pas : on cherche un vrai interpreteur sur le PATH, et on
    rend une chaine vide si aucun n'est trouve -- l'appelant doit alors
    demander a l'utilisateur de le configurer, jamais relancer l'exe sur
    lui-meme.
    """
    if not is_frozen():
        return sys.executable
    for nom in ("python", "python3", "py"):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    return ""


@dataclass(frozen=True)
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

    @property
    def usable(self) -> bool:
        return self.ok and self.bits in (32, 64) and bool(self.version and self.pytest_version)

    def summary(self) -> str:
        """Resume en une ligne, affiche sous le champ de saisie."""
        if self.error:
            return self.error
        morceaux = [f"Python {self.version} ({self.bits} bits)"]
        morceaux.append(f"pytest {self.pytest_version}" if self.pytest_version
                        else "pytest MISSING")
        morceaux.append("pytest-xdist present" if self.has_xdist
                        else "pytest-xdist missing")
        return " · ".join(morceaux)


class InterpreterUnavailable(RuntimeError):
    """Echec avant toute collecte : ne pas le presenter comme un test casse."""

    def __init__(self, info: InterpreterInfo):
        self.info = info
        super().__init__(f'Python interpreter not usable\n{info.path}\n{info.summary()}')


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

# Un probe lance un vrai processus Python et y importe pytest : plusieurs
# centaines de millisecondes, voire une a deux secondes sous Windows avec un
# antivirus. Le payer a chaque lancement de tests gelerait l'interface.
_CACHE: dict[tuple, InterpreterInfo] = {}


def _cache_key(path: str) -> tuple:
    try:
        stat = os.stat(path)
        return (path, stat.st_mtime, stat.st_size)
    except (OSError, ValueError):
        return (path, None, None)


def cached_probe(path: str) -> InterpreterInfo | None:
    """Resultat deja connu, ou None si cet interpreteur n'a jamais ete teste.

    Permet au thread de l'interface de repondre sans jamais lancer de
    processus."""
    if not path:
        return None
    return _CACHE.get(_cache_key(str(path).strip()))


def forget_probe(path: str | None = None) -> None:
    """Oublie un resultat mis en cache (ou tous si `path` est None)."""
    if path is None:
        _CACHE.clear()
    else:
        _CACHE.pop(_cache_key(str(path).strip()), None)


def probe(path: str, timeout: float = 15.0, use_cache: bool = True) -> InterpreterInfo:
    """Interroge un interpreteur : version, architecture, pytest disponible.

    Lance un processus : a n'appeler que depuis un thread de travail, jamais
    depuis le thread de l'interface.
    """
    if not path or not str(path).strip():
        return InterpreterInfo(path=path, error="No interpreter configured.")

    path = str(path).strip()
    cle = _cache_key(path)
    if use_cache and cle in _CACHE:
        return _CACHE[cle]

    info = _run_probe(path, timeout)
    if _timed_out(info):
        # Premier lancement d'un Python "froid" (antivirus, disque reseau,
        # poste charge) : une seconde chance, plus longue, avant de le
        # declarer inutilisable.
        info = _run_probe(path, timeout * 2)
    # Un delai depasse n'est jamais memorise : mis en cache, il declarait
    # l'interpreteur inutilisable pour toute la session alors qu'il
    # repondait normalement l'instant d'apres.
    if not _timed_out(info):
        _CACHE[cle] = info
    return info


_NO_RESPONSE = "No response from the interpreter"


def _timed_out(info: InterpreterInfo) -> bool:
    return bool(info.error) and info.error.startswith(_NO_RESPONSE)


def _run_probe(path: str, timeout: float) -> InterpreterInfo:
    if is_frozen() and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(sys.executable)):
        return InterpreterInfo(path=path, error='This is Pytest Runner, not a Python interpreter.')
    try:
        process = subprocess.run(
            [path, "-c", _PROBE_CODE], capture_output=True, text=True,
            timeout=timeout, creationflags=subprocess_flags(),
        )
    except FileNotFoundError:
        return InterpreterInfo(path=path, error=f"Interpreter not found: {path}")
    except PermissionError:
        return InterpreterInfo(path=path, error=f"Interpreter not executable: {path}")
    except subprocess.TimeoutExpired:
        return InterpreterInfo(path=path, error=f"{_NO_RESPONSE}: {path}")
    except (OSError, ValueError, UnicodeError) as exc:
        return InterpreterInfo(path=path, error=f"Could not start {path}: {exc}")

    lignes = process.stdout.splitlines()
    if process.returncode != 0 or len(lignes) < 2:
        detail = (process.stderr or process.stdout or "").strip()
        return InterpreterInfo(path=path,
                               error=detail or f"{path} is not a working Python.")

    version = lignes[0].strip()
    try:
        bits = int(lignes[1].strip())
    except ValueError:
        bits = 0
    pytest_version = lignes[2].strip() if len(lignes) > 2 else ""
    has_xdist = len(lignes) > 3 and lignes[3].strip() == "yes"

    return InterpreterInfo(path=path, version=version, bits=bits,
                           pytest_version=pytest_version, has_xdist=has_xdist)
