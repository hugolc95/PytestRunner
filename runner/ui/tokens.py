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
# Deux themes. Les noms ci-dessous sont RELIES a la palette active par
# `set_theme()` : tout ce qui lit `tokens.TEXT` au moment de l'appel suit donc
# le changement sans rien faire. Seul ce qui fige une couleur a la
# construction -- une feuille de style posee sur un widget, un format de
# coloration -- doit etre rejoue, d'ou les `restyle()` de l'interface.

# Sombre : les fonds vont du plus profond (l'application) au plus clair (ce qui
# est pose dessus). La profondeur seule suffit a hierarchiser, sans multiplier
# les bordures. Quatre niveaux franchement separes : a neuf points d'ecart les
# surfaces ne se detachaient pas.
DARK: dict = {
    "BG_APP": "#0d0f13",
    "BG_SURFACE": "#161a21",
    "BG_RAISED": "#1f242d",
    "BG_HOVER": "#29303b",
    "BG_INPUT": "#0a0c10",

    "BORDER": "#242a34",
    "BORDER_STRONG": "#39414f",

    "TEXT": "#e4e7ec",
    "TEXT_MUTED": "#8b94a3",
    "TEXT_FAINT": "#5d6675",

    # UNE couleur d'accent, et une seule. Elle marque l'action principale et la
    # selection. Tout ce qui n'est pas une action principale reste gris.
    "ACCENT": "#4c8dff",
    "ACCENT_HOVER": "#5f9bff",
    "ACCENT_PRESSED": "#3f7ae6",
    "ACCENT_SOFT": "#1d2a44",
    # Texte pose SUR l'accent : il doit contraster avec lui, pas avec le fond.
    "ON_ACCENT": "#06101f",

    # Lancer et arreter sont les deux gestes qu'on cherche sans lire. Vert /
    # rouge est la convention de tous les lanceurs de tests, et c'est la seule
    # entorse assumee a la regle de l'accent unique.
    "RUN": "#2f9150",
    "RUN_HOVER": "#37a75d",
    "RUN_PRESSED": "#277b43",
    "ON_RUN": "#06120a",

    # Les statuts ne sont pas des accents : ce sont des donnees. Volontairement
    # inegaux en intensite -- un run vert ne se regarde pas, un echec si.
    "STATUS_COLORS": {
        Status.PASSED: "#4fae63",
        Status.FAILED: "#ef5f57",
        Status.SKIPPED: "#b98a3f",
        Status.ERROR: "#a97fd0",
        Status.RUNNING: "#4c8dff",
        Status.PENDING: "#4a525f",
    },

    # Couleur par lecteur, pour relier une colonne, un onglet et une console.
    # Volontairement desaturees : elles reperent, elles n'attirent pas.
    "READER_COLORS": ("#4c8dff", "#39c5bb", "#e0a33e", "#c98bdb", "#7ec87e"),

    # Les huit couleurs ANSI, retraduites dans le theme. Le rouge d'un terminal
    # (#ff0000) sur un fond presque noir vibre et fatigue ; on garde le SENS de
    # la couleur choisie par le conftest, pas sa valeur brute.
    "ANSI_COLORS": {
        "black": "#5d6675",   # jamais du noir : il disparaitrait sur ce fond
        "red": "#ef5f57",
        "green": "#4fae63",
        "yellow": "#d8a13c",
        "blue": "#4c8dff",
        "magenta": "#c98bdb",
        "cyan": "#39c5bb",
        "white": "#e4e7ec",
    },
    "ANSI_BRIGHT": {
        "black": "#7b8494",
        "red": "#ff8078",
        "green": "#71c983",
        "yellow": "#f0bd5c",
        "magenta": "#dda6ea",
        "blue": "#7aabff",
        "cyan": "#5adbd1",
        "white": "#ffffff",
    },

    # Coloration syntaxique. Une famille froide, posee sur le fond d'entree
    # presque noir : le rouge des chaines des themes clairs y vibre.
    "SYNTAX": {
        "keyword": "#c792ea",
        "builtin": "#82aaff",
        "string": "#c3e88d",
        "docstring": "#788a9c",
        "comment": "#5d6675",
        "number": "#f78c6c",
        "decorator": "#ffcb6b",
        "function": "#82aaff",
        "classname": "#ffcb6b",
        "self": "#f07178",
    },

    "GUTTER_BG": "#0d0f13",
    "GUTTER_TEXT": "#4a525f",
    "GUTTER_CURRENT": "#8b94a3",
    "CURRENT_LINE": "#141922",
}

# Clair : la hierarchie s'inverse. Le fond de l'application est le plus gris,
# les surfaces posees dessus sont blanches. Les couleurs de statut sont
# assombries -- le vert #4fae63 du theme sombre est illisible sur du blanc.
LIGHT: dict = {
    "BG_APP": "#eef1f6",
    "BG_SURFACE": "#ffffff",
    "BG_RAISED": "#ffffff",
    "BG_HOVER": "#e3e9f1",
    "BG_INPUT": "#ffffff",

    "BORDER": "#d8dee7",
    "BORDER_STRONG": "#b3bdca",

    "TEXT": "#1b2230",
    "TEXT_MUTED": "#5b6675",
    "TEXT_FAINT": "#8a94a3",

    "ACCENT": "#1f6feb",
    "ACCENT_HOVER": "#2f7ff5",
    "ACCENT_PRESSED": "#1859c4",
    "ACCENT_SOFT": "#dbe8fd",
    "ON_ACCENT": "#ffffff",

    "RUN": "#2e7d32",
    "RUN_HOVER": "#358c3a",
    "RUN_PRESSED": "#256628",
    "ON_RUN": "#ffffff",

    "STATUS_COLORS": {
        Status.PASSED: "#2e7d32",
        Status.FAILED: "#c62828",
        Status.SKIPPED: "#a1651a",
        Status.ERROR: "#7b3fa0",
        Status.RUNNING: "#1f6feb",
        Status.PENDING: "#a8b1bd",
    },

    "READER_COLORS": ("#1f6feb", "#0f8b80", "#a1651a", "#7b3fa0", "#2e7d32"),

    "ANSI_COLORS": {
        "black": "#3a4250",
        "red": "#c62828",
        "green": "#2e7d32",
        "yellow": "#8a6100",
        "blue": "#1f6feb",
        "magenta": "#7b3fa0",
        "cyan": "#0f7a80",
        "white": "#5b6675",   # jamais du blanc : il disparaitrait sur ce fond
    },
    "ANSI_BRIGHT": {
        "black": "#5b6675",
        "red": "#e04343",
        "green": "#3d9942",
        "yellow": "#a87a10",
        "magenta": "#9a55c4",
        "blue": "#3a86f5",
        "cyan": "#1596a0",
        "white": "#1b2230",
    },

    "SYNTAX": {
        "keyword": "#0033b3",
        "builtin": "#0f7a80",
        "string": "#067d17",
        "docstring": "#6a7b8a",
        "comment": "#8a94a3",
        "number": "#1750eb",
        "decorator": "#9e6b00",
        "function": "#795e26",
        "classname": "#267f99",
        "self": "#8250df",
    },

    "GUTTER_BG": "#eef1f6",
    "GUTTER_TEXT": "#a3adba",
    "GUTTER_CURRENT": "#5b6675",
    "CURRENT_LINE": "#eaf1fb",
}

_THEMES = {"dark": DARK, "light": LIGHT}
_ACTIF = "dark"


def set_theme(nom: str) -> None:
    """Relie les jetons de couleur a la palette demandee.

    Les noms sont rebindes dans le module plutot que lus a travers un objet :
    les cent lectures `tokens.TEXT` deja ecrites continuent de fonctionner, et
    prennent la nouvelle valeur des le prochain appel.
    """
    global _ACTIF
    _ACTIF = nom if nom in _THEMES else "dark"
    globals().update(_THEMES[_ACTIF])


def current_theme() -> str:
    return _ACTIF


def is_dark() -> bool:
    return _ACTIF == "dark"


# Valeurs de depart : sans cet appel, les noms n'existeraient pas encore.
set_theme("dark")


def syntax_color(role: str) -> str:
    return SYNTAX.get(role, TEXT)


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
