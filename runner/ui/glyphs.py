"""Petites formes SVG que le QSS ne sait pas dessiner lui-meme.

Une feuille de style Qt ne trace pas une coche : `background-color` sur un
indicateur donne un carre plein, ou rien ne distingue « coche » de
« partiellement coche ». Il faut une image.

Les fichiers sont ecrits a la demande dans un temporaire, avec la couleur de la
palette : pas de binaire a versionner, et un changement de teinte se regenere.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

_DOSSIER: Path | None = None


def _dossier() -> Path:
    global _DOSSIER
    if _DOSSIER is None:
        _DOSSIER = Path(tempfile.mkdtemp(prefix="runner_glyphs_"))
    return _DOSSIER


def _ecrire(nom: str, svg: str) -> str:
    """Ecrit le SVG et rend son chemin en slashs, seule forme que Qt accepte
    dans une url() sous Windows."""
    chemin = _dossier() / nom
    try:
        chemin.write_text(svg, encoding="utf-8")
    except OSError:
        return ""
    return chemin.as_posix()


def _svg(contenu: str, taille: int = 14) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{taille}" '
        f'height="{taille}" viewBox="0 0 {taille} {taille}">{contenu}</svg>'
    )


def check(couleur: str) -> str:
    trace = (f'<path d="M3.2 7.2 L5.9 10 L10.9 4.3" fill="none" stroke="{couleur}" '
             'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    return _ecrire("check.svg", _svg(trace))


def dash(couleur: str) -> str:
    trace = (f'<path d="M4 7 L10 7" fill="none" stroke="{couleur}" '
             'stroke-width="1.8" stroke-linecap="round"/>')
    return _ecrire("dash.svg", _svg(trace))


def chevron_down(couleur: str) -> str:
    trace = (f'<path d="M3.5 5.5 L7 9 L10.5 5.5" fill="none" stroke="{couleur}" '
             'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>')
    return _ecrire("chevron.svg", _svg(trace))


def branch_closed(couleur: str) -> str:
    trace = (f'<path d="M5.5 3.5 L9 7 L5.5 10.5" fill="none" stroke="{couleur}" '
             'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return _ecrire("branch_closed.svg", _svg(trace))


def branch_open(couleur: str) -> str:
    trace = (f'<path d="M3.5 5.5 L7 9 L10.5 5.5" fill="none" stroke="{couleur}" '
             'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return _ecrire("branch_open.svg", _svg(trace))
