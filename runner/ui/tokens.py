"""Jetons de design : couleurs, espacements, rayons, typo.

Une seule source pour toute l'apparence. Un ecart de 3 px ou un gris invente
au fil de l'eau se voient immediatement quand tout le reste sort d'ici.
"""

from __future__ import annotations

from runner.domain.models import Status

# --------------------------------------------------------------- espacements
# Grille de 4 px. Rien dans l'interface ne doit utiliser une autre valeur.
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
SPACE_8 = 32

# ------------------------------------------------------------------- rayons
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10
RADIUS_PILL = 999

# --------------------------------------------------------------------- typo
FONT_UI = '"Segoe UI", "Inter", system-ui, sans-serif'
FONT_MONO = '"Cascadia Mono", "JetBrains Mono", Consolas, "DejaVu Sans Mono", monospace'

TEXT_XS = 11
TEXT_SM = 12
TEXT_MD = 13
TEXT_LG = 15

# ------------------------------------------------------------------ hauteurs
# Trois hauteurs seulement : un controle en fait forcement partie.
CONTROL_SM = 26
CONTROL_MD = 32
CONTROL_LG = 38

# ----------------------------------------------------------------- couleurs
# Theme sombre unique. Les fonds vont du plus profond (l'application) au plus
# clair (ce qui est pose dessus) : la profondeur seule suffit a hierarchiser,
# sans multiplier les bordures.
BG_APP = "#131519"
BG_SURFACE = "#191c22"
BG_RAISED = "#20242c"
BG_HOVER = "#272c35"
BG_INPUT = "#0f1115"

BORDER = "#2a2f39"
BORDER_STRONG = "#3a4150"

TEXT = "#e4e7ec"
TEXT_MUTED = "#8b94a3"
TEXT_FAINT = "#5d6675"

# UNE couleur d'accent, et une seule. Elle marque l'action principale et la
# selection. Tout ce qui n'est pas une action principale reste gris.
ACCENT = "#4c8dff"
ACCENT_HOVER = "#5f9bff"
ACCENT_PRESSED = "#3f7ae6"
ACCENT_SOFT = "#1d2a44"

# Les statuts ne sont pas des accents : ce sont des donnees. Ils n'apparaissent
# que sur des pastilles et des icones, jamais sur un bouton.
STATUS_COLORS: dict[Status, str] = {
    Status.PASSED: "#3fb950",
    Status.FAILED: "#f85149",
    Status.SKIPPED: "#d29922",
    Status.ERROR: "#bc8cff",
    Status.RUNNING: "#4c8dff",
    Status.PENDING: "#5d6675",
}

# Couleur par lecteur, pour relier une colonne, un onglet et une console.
# Volontairement desaturees : elles reperent, elles n'attirent pas.
READER_COLORS = ("#4c8dff", "#39c5bb", "#e0a33e", "#c98bdb", "#7ec87e")


def reader_color(index: int) -> str:
    return READER_COLORS[index % len(READER_COLORS)]


def status_color(status: Status) -> str:
    return STATUS_COLORS.get(status, TEXT_MUTED)
