"""Icones vectorielles, via qtawesome. Aucun emoji dans l'interface.

Un emoji change de dessin d'une machine a l'autre, ignore la couleur du theme
et ne s'aligne pas sur la grille. Une icone vectorielle prend la teinte qu'on
lui donne et reste identique partout.

Toutes les icones passent par ce module : le jeu reste coherent, et un rendu
degrade (qtawesome absent) est gere en un seul endroit.
"""

from __future__ import annotations

from functools import lru_cache

from PyQt5.QtGui import QIcon

from runner.domain.models import Kind, Status
from runner.ui import tokens as t

try:  # pragma: no cover - depend de l'installation
    import qtawesome
except ImportError:  # pragma: no cover
    qtawesome = None

# Un seul jeu (Material Design Icons) : melanger des familles se voit tout de
# suite, les epaisseurs de trait ne s'accordent pas.
STATUS_GLYPHS: dict[Status, str] = {
    Status.PASSED: "mdi.check-circle",
    Status.FAILED: "mdi.close-circle",
    Status.SKIPPED: "mdi.minus-circle",
    Status.ERROR: "mdi.alert-circle",
    Status.RUNNING: "mdi.loading",
    Status.PENDING: "mdi.circle-small",
}

KIND_GLYPHS: dict[Kind, str] = {
    Kind.FOLDER: "mdi.folder-outline",
    Kind.MODULE: "mdi.language-python",
    Kind.CLASS: "mdi.cube-outline",
    Kind.TEST: "mdi.function-variant",
    Kind.CASE: "mdi.circle-outline",
}


@lru_cache(maxsize=256)
def icon(nom: str, couleur: str = t.TEXT_MUTED) -> QIcon:
    """Icone nommee, teintee. Vide si qtawesome n'est pas disponible.

    Une icone vide laisse l'interface utilisable : rien ne depend d'elle pour
    etre compris, chaque action porte aussi un libelle ou une infobulle.
    """
    if qtawesome is None:  # pragma: no cover
        return QIcon()
    try:
        return qtawesome.icon(nom, color=couleur)
    except Exception:  # pragma: no cover - nom inconnu du jeu installe
        return QIcon()


def status_icon(status: Status) -> QIcon:
    return icon(STATUS_GLYPHS.get(status, "mdi.circle-small"), t.status_color(status))


def kind_icon(kind: Kind) -> QIcon:
    return icon(KIND_GLYPHS.get(kind, "mdi.file-outline"), t.TEXT_FAINT)


def available() -> bool:
    """Vrai si les icones peuvent reellement etre dessinees."""
    return qtawesome is not None
