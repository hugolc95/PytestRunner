"""Feuille de style unique de l'application.

Tout le style vit ici. Aucun `setStyleSheet` disperse dans les widgets : une
couleur posee a la main quelque part echappe au theme et finit par jurer.
Les rares exceptions (couleur propre a un lecteur, calculee) passent par une
fonction de ce module.
"""

from __future__ import annotations

from runner.domain.models import Status
from runner.ui import tokens as t


def app_stylesheet() -> str:
    """QSS de l'application entiere."""
    return f"""
/* ------------------------------------------------------------------ base */
QWidget {{
    background-color: {t.BG_APP};
    color: {t.TEXT};
    font-family: {t.FONT_UI};
    font-size: {t.TEXT_MD}px;
}}
QToolTip {{
    background-color: {t.BG_RAISED};
    color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SPACE_1}px {t.SPACE_2}px;
}}

/* -------------------------------------------------------------- surfaces */
QFrame#Surface, QWidget#Surface {{
    background-color: {t.BG_SURFACE};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_LG}px;
}}
QFrame#Separator {{
    background-color: {t.BORDER};
    max-height: 1px;
    border: none;
}}

/* ---------------------------------------------------------------- boutons */
/* Bouton par defaut : discret. Ce qui est rare ne doit pas crier. */
QPushButton {{
    background-color: {t.BG_RAISED};
    color: {t.TEXT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_SM}px;
    font-size: {t.TEXT_SM}px;
}}
QPushButton:hover {{ background-color: {t.BG_HOVER}; border-color: {t.BORDER_STRONG}; }}
QPushButton:pressed {{ background-color: {t.BG_SURFACE}; }}
QPushButton:disabled {{ color: {t.TEXT_FAINT}; background-color: {t.BG_SURFACE}; }}
QPushButton:checked {{
    background-color: {t.ACCENT_SOFT};
    border-color: {t.ACCENT};
    color: {t.ACCENT};
}}

/* L'action principale, et elle seule, porte la couleur d'accent. */
QPushButton#Primary {{
    background-color: {t.ACCENT};
    color: #06101f;
    border: none;
    font-weight: 600;
    padding: 0 {t.SPACE_4}px;
    min-height: {t.CONTROL_MD}px;
}}
QPushButton#Primary:hover {{ background-color: {t.ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background-color: {t.ACCENT_PRESSED}; }}
QPushButton#Primary:disabled {{ background-color: {t.BG_RAISED}; color: {t.TEXT_FAINT}; }}

QPushButton#Danger {{ min-height: {t.CONTROL_MD}px; }}
QPushButton#Danger:hover {{
    border-color: {t.status_color(Status.FAILED)};
    color: {t.status_color(Status.FAILED)};
}}

QPushButton#Quiet {{
    background-color: transparent;
    border-color: transparent;
    color: {t.TEXT_MUTED};
}}
QPushButton#Quiet:hover {{ background-color: {t.BG_HOVER}; color: {t.TEXT}; }}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SPACE_1}px;
}}
QToolButton:hover {{ background-color: {t.BG_HOVER}; }}
QToolButton:checked {{ background-color: {t.ACCENT_SOFT}; }}

/* ---------------------------------------------------------------- champs */
QLineEdit, QComboBox {{
    background-color: {t.BG_INPUT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: 0 {t.SPACE_2}px;
    min-height: {t.CONTROL_MD}px;
    selection-background-color: {t.ACCENT};
    selection-color: #06101f;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {t.ACCENT}; }}
QComboBox::drop-down {{ border: none; width: {t.SPACE_6}px; }}
QComboBox QAbstractItemView {{
    background-color: {t.BG_RAISED};
    border: 1px solid {t.BORDER_STRONG};
    selection-background-color: {t.ACCENT_SOFT};
    outline: none;
    padding: {t.SPACE_1}px;
}}

/* ----------------------------------------------------------------- arbre */
QTreeView {{
    background-color: {t.BG_SURFACE};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_LG}px;
    outline: none;
    font-size: {t.TEXT_SM}px;
    show-decoration-selected: 1;
}}
QTreeView::item {{ min-height: {t.CONTROL_SM}px; border: none; padding-left: {t.SPACE_1}px; }}
QTreeView::item:hover {{ background-color: {t.BG_HOVER}; }}
QTreeView::item:selected {{ background-color: {t.ACCENT_SOFT}; color: {t.TEXT}; }}
QHeaderView::section {{
    background-color: {t.BG_APP};
    color: {t.TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {t.BORDER};
    padding: {t.SPACE_2}px {t.SPACE_2}px;
    font-size: {t.TEXT_XS}px;
    font-weight: 600;
}}

/* --------------------------------------------------------------- onglets */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent;
    color: {t.TEXT_MUTED};
    padding: {t.SPACE_2}px {t.SPACE_3}px;
    margin-right: {t.SPACE_1}px;
    border-bottom: 2px solid transparent;
    font-size: {t.TEXT_SM}px;
}}
QTabBar::tab:hover {{ color: {t.TEXT}; }}
QTabBar::tab:selected {{ color: {t.TEXT}; border-bottom-color: {t.ACCENT}; font-weight: 600; }}

/* ---------------------------------------------------------------- textes */
QPlainTextEdit, QTextEdit {{
    background-color: {t.BG_INPUT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    font-family: {t.FONT_MONO};
    font-size: {t.TEXT_SM}px;
    selection-background-color: {t.ACCENT_SOFT};
    selection-color: {t.TEXT};
    padding: {t.SPACE_2}px;
}}

/* ------------------------------------------------------------ progression */
QProgressBar {{
    background-color: {t.BG_RAISED};
    border: none;
    border-radius: {t.RADIUS_PILL}px;
    max-height: {t.SPACE_1}px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {t.ACCENT}; border-radius: {t.RADIUS_PILL}px; }}

/* ------------------------------------------------------------ ascenseurs */
QScrollBar:vertical {{ background: transparent; width: {t.SPACE_3}px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: {t.SPACE_3}px; margin: 0; }}
QScrollBar::handle {{ background: {t.BORDER_STRONG}; border-radius: {t.RADIUS_SM}px; }}
QScrollBar::handle:vertical {{ min-height: {t.SPACE_8}px; margin: {t.SPACE_1}px; }}
QScrollBar::handle:horizontal {{ min-width: {t.SPACE_8}px; margin: {t.SPACE_1}px; }}
QScrollBar::handle:hover {{ background: {t.TEXT_FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---------------------------------------------------------------- divers */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: {t.SPACE_2}px; }}
QSplitter::handle:vertical {{ height: {t.SPACE_2}px; }}
QMenuBar {{ background: {t.BG_APP}; padding: {t.SPACE_1}px {t.SPACE_2}px; }}
QMenuBar::item {{ padding: {t.SPACE_1}px {t.SPACE_2}px; border-radius: {t.RADIUS_SM}px; }}
QMenuBar::item:selected {{ background: {t.BG_HOVER}; }}
QMenu {{
    background: {t.BG_RAISED};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SPACE_1}px;
}}
QMenu::item {{ padding: {t.SPACE_2}px {t.SPACE_4}px; border-radius: {t.RADIUS_SM}px; }}
QMenu::item:selected {{ background: {t.ACCENT_SOFT}; }}
QStatusBar {{ background: {t.BG_APP}; border-top: 1px solid {t.BORDER}; }}
QStatusBar::item {{ border: none; }}
"""


def pill_style(couleur: str, actif: bool = True) -> str:
    """Pastille coloree : compteur de statut, nom de lecteur.

    Passe par une fonction plutot que par le QSS global : la couleur depend
    d'une donnee (le statut, l'index du lecteur), pas du theme seul.
    """
    fond = f"{couleur}22" if actif else "transparent"
    texte = couleur if actif else t.TEXT_FAINT
    return (
        f"background-color: {fond};"
        f"color: {texte};"
        f"border: 1px solid {couleur if actif else t.BORDER};"
        f"border-radius: {t.RADIUS_PILL}px;"
        f"padding: {t.SPACE_1}px {t.SPACE_3}px;"
        f"font-size: {t.TEXT_XS}px; font-weight: 600;"
    )


def muted(size: int = t.TEXT_SM) -> str:
    return f"color: {t.TEXT_MUTED}; font-size: {size}px; background: transparent;"


def faint(size: int = t.TEXT_XS) -> str:
    return f"color: {t.TEXT_FAINT}; font-size: {size}px; background: transparent;"
