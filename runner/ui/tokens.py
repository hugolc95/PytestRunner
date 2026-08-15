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
# Trois hauteurs, et une rangee n'en melange jamais deux : des boutons de 26 et
# de 32 cote a cote donnent une ligne bancale, meme sans savoir pourquoi.
CONTROL_SM = 28   # rangees d'outils secondaires
CONTROL_MD = 32   # barre de commande, champs
CONTROL_LG = 36   # reserve

ICON_BUTTON = 32  # carre : un bouton d'icone plus large que haut est de travers

# ----------------------------------------------------------------- couleurs
# Theme sombre unique. Les fonds vont du plus profond (l'application) au plus
# clair (ce qui est pose dessus) : la profondeur seule suffit a hierarchiser,
# sans multiplier les bordures.
# Quatre niveaux de profondeur, franchement separes. Dans la version
# precedente le fond de l'application et celui des panneaux etaient a neuf
# points l'un de l'autre : les surfaces ne se detachaient pas, et il fallait
# une bordure partout pour compenser.
BG_APP = "#0d0f13"
BG_SURFACE = "#161a21"
BG_RAISED = "#1f242d"
BG_HOVER = "#29303b"
BG_INPUT = "#0a0c10"

BORDER = "#242a34"
BORDER_STRONG = "#39414f"

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
# Volontairement inegales en intensite : un run vert ne se regarde pas, un
# echec si. Le jaune d'origine etait plus sature que le rouge et attirait
# l'oeil en premier -- exactement l'inverse de ce qu'il faut.
STATUS_COLORS: dict[Status, str] = {
    Status.PASSED: "#4fae63",
    Status.FAILED: "#ef5f57",
    Status.SKIPPED: "#b98a3f",
    Status.ERROR: "#a97fd0",
    Status.RUNNING: "#4c8dff",
    Status.PENDING: "#4a525f",
}

# Couleur par lecteur, pour relier une colonne, un onglet et une console.
# Volontairement desaturees : elles reperent, elles n'attirent pas.
READER_COLORS = ("#4c8dff", "#39c5bb", "#e0a33e", "#c98bdb", "#7ec87e")


# Les huit couleurs ANSI, retraduites dans le theme. Le rouge d'un terminal
# (#ff0000) sur un fond presque noir vibre et fatigue ; on garde le SENS de la
# couleur choisie par le conftest, pas sa valeur brute.
ANSI_COLORS: dict[str, str] = {
    "black": "#5d6675",   # jamais du noir : il disparaitrait sur ce fond
    "red": "#ef5f57",
    "green": "#4fae63",
    "yellow": "#d8a13c",
    "blue": "#4c8dff",
    "magenta": "#c98bdb",
    "cyan": "#39c5bb",
    "white": "#e4e7ec",
}

ANSI_BRIGHT: dict[str, str] = {
    "black": "#7b8494",
    "red": "#ff8078",
    "green": "#71c983",
    "yellow": "#f0bd5c",
    "magenta": "#dda6ea",
    "blue": "#7aabff",
    "cyan": "#5adbd1",
    "white": "#ffffff",
}


def reader_color(index: int) -> str:
    return READER_COLORS[index % len(READER_COLORS)]


def ansi_color(nom: str | None, vive: bool = False) -> str | None:
    """Couleur du theme pour une couleur ANSI, ou None pour la couleur par defaut.

    Les modes 256 couleurs et couleurs vraies donnent deja un `#rrggbb` : on le
    laisse passer tel quel, il a ete choisi explicitement.
    """
    if not nom:
        return None
    if nom.startswith("#"):
        return nom
    table = ANSI_BRIGHT if vive else ANSI_COLORS
    return table.get(nom)


def rgba(couleur: str, opacite: float) -> str:
    """`rgba(r, g, b, a)` a partir d'un `#rrggbb`.

    Qt ne lit PAS le `#rrggbbaa` du web : il l'interprete comme `#aarrggbb`.
    Un fond `#ef5f5722` (rouge a 13 %) devenait ainsi un brun opaque. Toute
    transparence doit passer par ici.
    """
    c = couleur.lstrip("#")
    r, v, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {v}, {b}, {opacite:.2f})"


def blend(couleur: str, fond: str, opacite: float) -> str:
    """`#rrggbb` opaque equivalent a `couleur` posee sur `fond` a cette opacite.

    Certaines zones dessinees par Qt ignorent purement et simplement le canal
    alpha d'un `rgba()` en QSS et retombent sur leur couleur par defaut : la
    colonne des branches d'un QTreeView en fait partie, et sa ligne
    selectionnee redevenait alors d'un bleu systeme sans rapport avec le
    theme. Composer la couleur nous-memes donne le meme rendu, en opaque.
    """
    def canaux(valeur: str) -> tuple[int, int, int]:
        c = valeur.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    avant, arriere = canaux(couleur), canaux(fond)
    melange = (round(a * opacite + b * (1 - opacite)) for a, b in zip(avant, arriere))
    return "#" + "".join(f"{v:02x}" for v in melange)


def status_color(status: Status) -> str:
    return STATUS_COLORS.get(status, TEXT_MUTED)
