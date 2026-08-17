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

# Variante evidee, pour les lignes de REGROUPEMENT. Un dossier ne porte pas de
# resultat : il montre le pire de ce qu'il contient. Le meme pictogramme plein
# que sur une feuille laissait croire a un verdict propre a cette ligne.
STATUS_GLYPHS_GROUP: dict[Status, str] = {
    Status.PASSED: "mdi.check-circle-outline",
    Status.FAILED: "mdi.close-circle-outline",
    Status.SKIPPED: "mdi.minus-circle-outline",
    Status.ERROR: "mdi.alert-circle-outline",
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


def icon(nom: str, couleur: str = "") -> QIcon:
    """Icone nommee, teintee. Vide si qtawesome n'est pas disponible.

    Une icone vide laisse l'interface utilisable : rien ne depend d'elle pour
    etre compris, chaque action porte aussi un libelle ou une infobulle.

    La couleur est resolue AVANT le cache. En argument par defaut elle serait
    figee a l'import ; laissee vide jusqu'a l'interieur, elle donnerait une
    clef de cache identique dans les deux themes -- et la bascule rendrait
    l'icone de l'ancien.
    """
    return _icon(nom, couleur or t.TEXT_MUTED)


@lru_cache(maxsize=512)
def _icon(nom: str, couleur: str) -> QIcon:
    if qtawesome is None:  # pragma: no cover
        return QIcon()
    try:
        return qtawesome.icon(nom, color=couleur)
    except Exception:  # pragma: no cover - nom inconnu du jeu installe
        return QIcon()


def status_icon(status: Status, group: bool = False) -> QIcon:
    """Icone d'un statut. `group` donne la variante evidee des regroupements."""
    table = STATUS_GLYPHS_GROUP if group else STATUS_GLYPHS
    couleur = t.status_color(status)
    if group:
        # Un agregat ne doit pas peser autant qu'un resultat : meme teinte,
        # moins d'encre. La couleur est COMPOSEE en opaque, pas exprimee en
        # `rgba()` : cette forme est valide en QSS mais pas comme QColor, et
        # qtawesome retombait alors sur du noir -- soit, sur le fond sombre de
        # l'arbre, un anneau invisible. Les dossiers semblaient ne rien
        # recevoir de leurs enfants alors que le calcul etait juste.
        couleur = t.blend(couleur, t.BG_SURFACE, 0.75)
    return icon(table.get(status, "mdi.circle-small"), couleur)


def kind_icon(kind: Kind) -> QIcon:
    return icon(KIND_GLYPHS.get(kind, "mdi.file-outline"), t.TEXT_FAINT)


def available() -> bool:
    """Vrai si les icones peuvent reellement etre dessinees."""
    return qtawesome is not None
