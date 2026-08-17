"""Icones de case a cocher, generees a la volee selon la palette.

Une feuille de style Qt ne sait pas DESSINER une coche : `background-color`
donne un carre plein, sans le signe qui distingue "coche" de "simplement
colore". La seule facon d'avoir une vraie coche reste une image.

Embarquer des .svg dans le depot obligerait a en maintenir un jeu par theme
(clair, sombre) et par etat (coche, partiel). On les ecrit donc a la demande
dans un dossier temporaire, avec la couleur de la palette courante : un
changement de theme regenere simplement les fichiers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Un seul dossier pour toute la session : les fichiers sont reecrits a chaque
# changement de theme, jamais accumules.
_DOSSIER: Path | None = None


def _dossier() -> Path:
    global _DOSSIER
    if _DOSSIER is None:
        _DOSSIER = Path(tempfile.mkdtemp(prefix="pytestrunner_icons_"))
    return _DOSSIER


def _ecrire(nom: str, svg: str) -> str:
    """Ecrit le SVG et retourne son chemin, en slashs (exige par Qt sous Windows)."""
    chemin = _dossier() / nom
    try:
        chemin.write_text(svg, encoding="utf-8")
    except OSError:
        return ""
    return chemin.as_posix()


def _coche(couleur: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 14 14">'
        f'<path d="M3.2 7.3 L5.9 10 L10.8 4.4" fill="none" stroke="{couleur}" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def _tiret(couleur: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 14 14">'
        f'<path d="M3.8 7 L10.2 7" fill="none" stroke="{couleur}" '
        'stroke-width="1.7" stroke-linecap="round"/>'
        '</svg>'
    )


def _chevron(couleur: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 12 12">'
        f'<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="{couleur}" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def chevron_icon(couleur: str) -> str:
    """Chevron du menu deroulant d'un QComboBox, ou "" si l'ecriture echoue.

    Une image, et non un triangle en bordures CSS : Qt ne rend pas le
    `border-*: solid transparent` d'un sous-controle comme un navigateur, et la
    fleche apparaissait comme un simple tiret.
    """
    return _ecrire("chevron.svg", _chevron(couleur))


def checkbox_icons(couleur_coche: str) -> dict:
    """Chemins des icones coche/partiel, dessinees dans cette couleur.

    Retourne un dictionnaire vide si l'ecriture echoue : l'appelant retombe
    alors sur un style sans image, moins joli mais fonctionnel.
    """
    checked = _ecrire("check.svg", _coche(couleur_coche))
    partial = _ecrire("partial.svg", _tiret(couleur_coche))
    if not checked or not partial:
        return {}
    return {"checked": checked, "partial": partial}
