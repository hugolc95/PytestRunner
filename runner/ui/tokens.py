"""Jetons de design : couleurs, espacements, rayons, typo.

Une seule source pour toute l'apparence. Un ecart de 3 px ou un gris invente
au fil de l'eau se voient immediatement quand tout le reste sort d'ici.
"""

from __future__ import annotations

from runner.domain.models import Status

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
SPACE_8 = 32

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10
RADIUS_PILL = 999

FONT_UI = '"Segoe UI", "Inter", system-ui, sans-serif'
FONT_MONO = '"Cascadia Mono", "JetBrains Mono", Consolas, "DejaVu Sans Mono", monospace'

TEXT_XS = 11
TEXT_SM = 12
TEXT_MD = 13
TEXT_LG = 15

CONTROL_SM = 28
CONTROL_MD = 32
CONTROL_LG = 36
ICON_BUTTON = 32

# Dark theme: charcoal/slate rather than near-black. This keeps the night-mode
# contrast while making large surfaces less harsh and easier to distinguish.
DARK: dict = {
    "BG_APP": "#171a21",
    "BG_SURFACE": "#20242d",
    "BG_RAISED": "#292e38",
    "BG_HOVER": "#343b47",
    "BG_INPUT": "#14171d",
    "BORDER": "#303744",
    "BORDER_STRONG": "#46505f",
    "TEXT": "#e4e7ec",
    "TEXT_MUTED": "#9aa3b2",
    "TEXT_FAINT": "#687383",
    "ACCENT": "#4c8dff",
    "ACCENT_HOVER": "#5f9bff",
    "ACCENT_PRESSED": "#3f7ae6",
    "ACCENT_SOFT": "#253451",
    "ON_ACCENT": "#06101f",
    "RUN": "#2f9150",
    "RUN_HOVER": "#37a75d",
    "RUN_PRESSED": "#277b43",
    "ON_RUN": "#06120a",
    "STATUS_COLORS": {
        Status.PASSED: "#4fae63", Status.FAILED: "#ef5f57",
        Status.SKIPPED: "#b98a3f", Status.ERROR: "#a97fd0",
        Status.RUNNING: "#4c8dff", Status.PENDING: "#596372",
    },
    "READER_COLORS": ("#4c8dff", "#39c5bb", "#e0a33e", "#c98bdb", "#7ec87e"),
    "ANSI_COLORS": {
        "black": "#687383", "red": "#ef5f57", "green": "#4fae63",
        "yellow": "#d8a13c", "blue": "#4c8dff", "magenta": "#c98bdb",
        "cyan": "#39c5bb", "white": "#e4e7ec",
    },
    "ANSI_BRIGHT": {
        "black": "#8791a1", "red": "#ff8078", "green": "#71c983",
        "yellow": "#f0bd5c", "magenta": "#dda6ea", "blue": "#7aabff",
        "cyan": "#5adbd1", "white": "#ffffff",
    },
    "SYNTAX": {
        "keyword": "#c792ea", "builtin": "#82aaff", "string": "#c3e88d",
        "docstring": "#8798aa", "comment": "#687383", "number": "#f78c6c",
        "decorator": "#ffcb6b", "function": "#82aaff", "classname": "#ffcb6b",
        "self": "#f07178",
    },
    "GUTTER_BG": "#171a21",
    "GUTTER_TEXT": "#596372",
    "GUTTER_CURRENT": "#9aa3b2",
    "CURRENT_LINE": "#252b36",
}

LIGHT: dict = {
    "BG_APP": "#eef1f6", "BG_SURFACE": "#ffffff", "BG_RAISED": "#ffffff",
    "BG_HOVER": "#e3e9f1", "BG_INPUT": "#ffffff",
    "BORDER": "#d8dee7", "BORDER_STRONG": "#b3bdca",
    "TEXT": "#1b2230", "TEXT_MUTED": "#5b6675", "TEXT_FAINT": "#8a94a3",
    "ACCENT": "#1f6feb", "ACCENT_HOVER": "#2f7ff5", "ACCENT_PRESSED": "#1859c4",
    "ACCENT_SOFT": "#dbe8fd", "ON_ACCENT": "#ffffff",
    "RUN": "#2e7d32", "RUN_HOVER": "#358c3a", "RUN_PRESSED": "#256628", "ON_RUN": "#ffffff",
    "STATUS_COLORS": {
        Status.PASSED: "#2e7d32", Status.FAILED: "#c62828", Status.SKIPPED: "#a1651a",
        Status.ERROR: "#7b3fa0", Status.RUNNING: "#1f6feb", Status.PENDING: "#a8b1bd",
    },
    "READER_COLORS": ("#1f6feb", "#0f8b80", "#a1651a", "#7b3fa0", "#2e7d32"),
    "ANSI_COLORS": {
        "black": "#3a4250", "red": "#c62828", "green": "#2e7d32", "yellow": "#8a6100",
        "blue": "#1f6feb", "magenta": "#7b3fa0", "cyan": "#0f7a80", "white": "#5b6675",
    },
    "ANSI_BRIGHT": {
        "black": "#5b6675", "red": "#e04343", "green": "#3d9942", "yellow": "#a87a10",
        "magenta": "#9a55c4", "blue": "#3a86f5", "cyan": "#1596a0", "white": "#1b2230",
    },
    "SYNTAX": {
        "keyword": "#0033b3", "builtin": "#0f7a80", "string": "#067d17", "docstring": "#6a7b8a",
        "comment": "#8a94a3", "number": "#1750eb", "decorator": "#9e6b00", "function": "#795e26",
        "classname": "#267f99", "self": "#8250df",
    },
    "GUTTER_BG": "#eef1f6", "GUTTER_TEXT": "#a3adba", "GUTTER_CURRENT": "#5b6675",
    "CURRENT_LINE": "#eaf1fb",
}

_THEMES = {"dark": DARK, "light": LIGHT}
_ACTIF = "dark"


def set_theme(nom: str) -> None:
    global _ACTIF
    _ACTIF = nom if nom in _THEMES else "dark"
    globals().update(_THEMES[_ACTIF])


def current_theme() -> str:
    return _ACTIF


def is_dark() -> bool:
    return _ACTIF == "dark"


set_theme("dark")


def syntax_color(role: str) -> str:
    return SYNTAX.get(role, TEXT)


def reader_color(index: int) -> str:
    return READER_COLORS[index % len(READER_COLORS)]


def ansi_color(nom: str | None, vive: bool = False) -> str | None:
    if not nom:
        return None
    if nom.startswith("#"):
        return nom
    table = ANSI_BRIGHT if vive else ANSI_COLORS
    return table.get(nom)


def rgba(couleur: str, opacite: float) -> str:
    c = couleur.lstrip("#")
    r, v, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {v}, {b}, {opacite:.2f})"


def blend(couleur: str, fond: str, opacite: float) -> str:
    def canaux(valeur: str) -> tuple[int, int, int]:
        c = valeur.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    avant, arriere = canaux(couleur), canaux(fond)
    melange = (round(a * opacite + b * (1 - opacite)) for a, b in zip(avant, arriere))
    return "#" + "".join(f"{v:02x}" for v in melange)


def status_color(status: Status) -> str:
    return STATUS_COLORS.get(status, TEXT_MUTED)
