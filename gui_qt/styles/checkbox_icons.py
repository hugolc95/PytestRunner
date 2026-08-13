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
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        'viewBox="0 0 16 16">'
        f'<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" stroke="{couleur}" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def _tiret(couleur: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        'viewBox="0 0 16 16">'
        f'<path d="M4 8 L12 8" fill="none" stroke="{couleur}" '
        'stroke-width="2.2" stroke-linecap="round"/>'
        '</svg>'
    )


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
