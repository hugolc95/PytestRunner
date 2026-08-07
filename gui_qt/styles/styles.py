# gui_qt/styles/styles.py
#
# Deux themes complets, clair et sombre. Les fonctions publiques
# (app_stylesheet, tree_style, console_style, les boutons...) gardent leur
# signature : elles lisent simplement la palette active, que set_theme() change.
#
# Changer de theme a chaud demande de reappliquer les feuilles de style posees
# widget par widget. C'est le role de restyle() cote fenetres.

LIGHT = {
    "name": "light",

    "primary": "#1976d2",
    "neutral": "#616161",
    "success": "#2e7d32",
    "danger": "#c62828",

    "background": "#f3f5f8",
    "surface": "#ffffff",
    "border": "#e0e4e9",
    "text": "#20262e",
    "text_muted": "#6b7480",
    "hover": "#eef2f6",
    "scrollbar": "#c7ccd3",
    "scrollbar_hover": "#a7aeb7",

    "tree_bg": "#ffffff",
    "tree_border": "#ccc",
    "tree_hover": "#f0f4f8",
    "tree_selected": "#e3f2fd",
    "tree_selected_text": "#000000",
    "checkbox_bg": "#ffffff",
    "checkbox_border": "#9e9e9e",
    "checkbox_checked": "#607d8b",
    "checkbox_partial": "#b0bec5",
    "branch_arrow": "#5c6773",
    "branch_arrow_hover": "#1976d2",

    "console_bg": "#ffffff",
    "console_text": "#1f2328",
    "console_border": "#e0e4e9",

    "toolbar_bg": "#e9ecef",
    "toolbar_border": "#ced4da",
    "toolbar_hover": "#dee2e6",
    "toolbar_checked": "#90caf9",

    "disabled_bg": "#c9ced5",
    "disabled_text": "#8b939d",

    # Statuts : texte de l'arbre et icones.
    "status": {
        "PASSED": "#2e7d32",
        "FAILED": "#c62828",
        "SKIPPED": "#ef6c00",
        "ERROR": "#6a1b9a",
    },
    # Cartes de resume : (couleur a zero, couleur au maximum).
    "cards": {
        "PASSED": ("#d7f5dd", "#4caf50"),
        "FAILED": ("#fbd5d5", "#e53935"),
        "SKIPPED": ("#fde8c8", "#fb8c00"),
        "ERROR": ("#ecd9f5", "#8e24aa"),
    },
    "card_text": "#222222",
    "card_active_border": "#333333",

    # Police des zones de code et de sortie : l'alignement des colonnes de
    # pytest n'a de sens qu'en chasse fixe.
    "mono_font": "Consolas, 'DejaVu Sans Mono', 'Courier New', monospace",
    "gutter_bg": "#f6f8fa",
    "gutter_text": "#8c959f",
    # Numero de la ligne courante : couleur dediee, la teinte principale de
    # l'application passe juste sous le seuil de lisibilite sur ce fond.
    "gutter_current": "#0b57b8",
    "current_line": "#d2e3f7",

    # Coloration du code Python (teintes proches de celles d'un IDE clair).
    "syntax": {
        "keyword": "#0033b3",
        "builtin": "#0033b3",
        "string": "#a31515",
        "docstring": "#8a8a3a",
        "comment": "#3d8a3d",
        "number": "#098658",
        "decorator": "#7a5c1e",
        "function": "#795e26",
        "classname": "#267f99",
        "self": "#8250df",
    },
    # Coloration de la sortie pytest et des logs.
    "output": {
        "passed": "#1a7f37",
        "failed": "#c62828",
        "skipped": "#bf5b00",
        "error": "#7b1fa2",
        "separator": "#6b7480",
        "nodeid": "#0969da",
        "percent": "#8c959f",
        "traceback": "#c62828",
        "info": "#0969da",
        "warning": "#bf5b00",
        "timestamp": "#8c959f",
    },
}

DARK = {
    "name": "dark",

    "primary": "#5aa9f8",
    "neutral": "#8b939d",
    "success": "#5cb85f",
    "danger": "#ef5350",

    "background": "#181b20",
    "surface": "#22262d",
    "border": "#343a43",
    "text": "#e4e7ec",
    "text_muted": "#9aa3ae",
    "hover": "#2b3038",
    "scrollbar": "#454c56",
    "scrollbar_hover": "#5a6270",

    "tree_bg": "#1e2229",
    "tree_border": "#343a43",
    "tree_hover": "#2b3038",
    "tree_selected": "#2d4257",
    "tree_selected_text": "#ffffff",
    "checkbox_bg": "#2b3038",
    "checkbox_border": "#6b7480",
    "checkbox_checked": "#5aa9f8",
    "checkbox_partial": "#3f5a74",
    "branch_arrow": "#98a2b0",
    "branch_arrow_hover": "#5aa9f8",

    "console_bg": "#14171b",
    "console_text": "#d4d8de",
    "console_border": "#343a43",

    "toolbar_bg": "#2b3038",
    "toolbar_border": "#3d444e",
    "toolbar_hover": "#353b45",
    "toolbar_checked": "#2f5d8a",

    "disabled_bg": "#2b3038",
    "disabled_text": "#5f6875",

    # Teintes plus claires qu'en mode clair : sur fond sombre, un vert ou un
    # rouge fonce devient illisible.
    "status": {
        "PASSED": "#66bb6a",
        "FAILED": "#ef5350",
        "SKIPPED": "#ffa726",
        "ERROR": "#ba68c8",
    },
    "cards": {
        "PASSED": ("#243027", "#3d7a41"),
        "FAILED": ("#33242a", "#a33b38"),
        "SKIPPED": ("#332c22", "#b3762a"),
        "ERROR": ("#2e2635", "#7a4a94"),
    },
    "card_text": "#e4e7ec",
    "card_active_border": "#8b939d",

    "mono_font": "Consolas, 'DejaVu Sans Mono', 'Courier New', monospace",
    "gutter_bg": "#1a1d23",
    "gutter_text": "#5f6875",
    "gutter_current": "#7cc0ff",
    "current_line": "#36435c",

    "syntax": {
        "keyword": "#c586c0",
        "builtin": "#569cd6",
        "string": "#ce9178",
        "docstring": "#b58a63",
        "comment": "#6a9955",
        "number": "#b5cea8",
        "decorator": "#dcdcaa",
        "function": "#dcdcaa",
        "classname": "#4ec9b0",
        "self": "#569cd6",
    },
    "output": {
        "passed": "#6bbf6e",
        "failed": "#ef5350",
        "skipped": "#ffa726",
        "error": "#ba68c8",
        "separator": "#7f8c9b",
        "nodeid": "#6bb3e8",
        "percent": "#7f8c9b",
        "traceback": "#ef5350",
        "info": "#6bb3e8",
        "warning": "#ffa726",
        "timestamp": "#7f8c9b",
    },
}

_THEMES = {"light": LIGHT, "dark": DARK}
_active = LIGHT


def set_theme(name: str) -> None:
    """Active le theme 'light' ou 'dark'. Un nom inconnu retombe sur 'light'."""
    global _active
    _active = _THEMES.get(str(name).lower(), LIGHT)


def current_theme() -> str:
    return _active["name"]


def is_dark() -> bool:
    return _active is DARK


def palette() -> dict:
    return _active


def status_color(status: str) -> str:
    return _active["status"].get(status, _active["neutral"])


def card_colors(status: str) -> tuple[str, str]:
    return _active["cards"].get(status, (_active["surface"], _active["neutral"]))


def syntax_color(role: str) -> str:
    """Couleur de coloration syntaxique Python pour ce role."""
    return _active["syntax"].get(role, _active["text"])


def output_color(role: str) -> str:
    """Couleur de coloration de la sortie pytest / des logs pour ce role."""
    return _active["output"].get(role, _active["console_text"])


def mono_font() -> str:
    return _active["mono_font"]


def muted_label() -> str:
    return f"color: {_active['text_muted']}; font-size: 12px;"


# ---------- APP-WIDE STYLESHEET ----------
def app_stylesheet() -> str:
    """Feuille de style globale (QApplication.setStyleSheet). Les styles poses
    widget par widget (boutons colores, arbre, console...) restent prioritaires."""
    p = _active
    return f"""
    QMainWindow, QDialog, QWidget {{
        background-color: {p['background']};
        color: {p['text']};
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }}

    QMenuBar {{
        background-color: {p['surface']};
        border-bottom: 1px solid {p['border']};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 4px 10px;
        background: transparent;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {p['hover']};
    }}
    QMenu {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 22px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {p['tree_selected']};
    }}

    QTabWidget::pane {{
        border: 1px solid {p['border']};
        border-radius: 8px;
        background-color: {p['surface']};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {p['text_muted']};
        padding: 8px 22px;
        margin-right: 2px;
        min-width: 90px;
        min-height: 18px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {p['surface']};
        color: {p['primary']};
        border: 1px solid {p['border']};
        border-bottom: 2px solid {p['primary']};
        padding: 8px 22px;
    }}
    QTabBar::tab:hover:!selected {{
        color: {p['text']};
    }}

    QPushButton {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 14px;
        color: {p['text']};
    }}
    QPushButton:hover {{
        background-color: {p['hover']};
    }}
    QPushButton:pressed {{
        background-color: {p['border']};
    }}

    QLineEdit, QComboBox {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 5px 8px;
        color: {p['text']};
        selection-background-color: {p['tree_selected']};
        selection-color: {p['tree_selected_text']};
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {p['primary']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p['surface']};
        color: {p['text']};
        border: 1px solid {p['border']};
        selection-background-color: {p['tree_selected']};
        selection-color: {p['tree_selected_text']};
        outline: none;
    }}

    QGroupBox {{
        border: 1px solid {p['border']};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 14px;
        background-color: {p['surface']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}

    QProgressBar {{
        border: 1px solid {p['border']};
        border-radius: 6px;
        background-color: {p['surface']};
        color: {p['text']};
        text-align: center;
        height: 18px;
    }}
    QProgressBar::chunk {{
        background-color: {p['primary']};
        border-radius: 5px;
    }}

    QHeaderView::section {{
        background-color: {p['surface']};
        border: none;
        border-bottom: 1px solid {p['border']};
        padding: 6px;
        font-weight: 600;
        color: {p['text_muted']};
    }}
    QTableWidget {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        gridline-color: {p['border']};
    }}
    QTableWidget::item:selected {{
        background-color: {p['tree_selected']};
        color: {p['tree_selected_text']};
    }}

    QListWidget {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
    }}

    QCheckBox {{
        spacing: 6px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p['scrollbar']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p['scrollbar_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p['scrollbar']};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p['scrollbar_hover']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    """


# ---------- BUTTONS ----------
def _base_button() -> str:
    p = _active
    return f"""
    QPushButton {{
        border: none;
        border-radius: 6px;
        padding: 8px 14px;
        font-weight: bold;
        color: white;
    }}
    QPushButton:hover {{
        opacity: 0.85;
    }}
    QPushButton:disabled {{
        background-color: {p['disabled_bg']};
        color: {p['disabled_text']};
    }}
    """


def _colored_button(color: str) -> str:
    return _base_button() + f"""
    QPushButton {{
        background-color: {color};
    }}
    """


def primary_button():
    return _colored_button(_active["primary"])


def neutral_button():
    return _colored_button(_active["neutral"])


def success_button():
    return _colored_button(_active["success"])


def danger_button():
    return _colored_button(_active["danger"])


# ---------- TOOLBAR BUTTON ----------
def toolbar_button():
    p = _active
    return f"""
    QPushButton {{
        background-color: {p['toolbar_bg']};
        border: 1px solid {p['toolbar_border']};
        border-radius: 5px;
        padding: 4px 10px;
        font-size: 12px;
        color: {p['text']};
    }}
    QPushButton:hover {{
        background-color: {p['toolbar_hover']};
    }}
    QPushButton:checked {{
        background-color: {p['toolbar_checked']};
        border: 1px solid {p['primary']};
    }}
    """


def theme_toggle_button() -> str:
    """Bouton discret du selecteur de theme, loge dans la barre de menus."""
    p = _active
    return f"""
    QToolButton {{
        background: transparent;
        border: none;
        border-radius: 5px;
        padding: 2px 8px;
        font-size: 15px;
        color: {p['text']};
    }}
    QToolButton:hover {{
        background-color: {p['hover']};
    }}
    """


# ---------- TREE ----------
def tree_style():
    p = _active
    return f"""
    QTreeView {{
        background-color: {p['tree_bg']};
        color: {p['text']};
        border: 1px solid {p['tree_border']};
        border-radius: 6px;
        font-size: 12px;
    }}

    QTreeView::item {{
        padding: 4px 2px;
    }}

    QTreeView::item:hover {{
        background-color: {p['tree_hover']};
    }}

    QTreeView::item:selected {{
        background-color: {p['tree_selected']};
        color: {p['tree_selected_text']};
    }}

    QTreeView::indicator {{
        width: 16px;
        height: 16px;
    }}

    QTreeView::indicator:unchecked {{
        border: 1px solid {p['checkbox_border']};
        border-radius: 4px;
        background-color: {p['checkbox_bg']};
    }}

    QTreeView::indicator:checked {{
        background-color: {p['checkbox_checked']};
        border: 1px solid {p['checkbox_checked']};
        border-radius: 4px;
    }}

    QTreeView::indicator:indeterminate {{
        background-color: {p['checkbox_partial']};
        border: 1px solid {p['checkbox_checked']};
        border-radius: 4px;
    }}
    """


# ---------- CONSOLE ----------
def console_style():
    p = _active
    return f"""
    QTextEdit, QPlainTextEdit {{
        background-color: {p['console_bg']};
        color: {p['console_text']};
        border: 1px solid {p['console_border']};
        font-family: {p['mono_font']};
        font-size: 12px;
        selection-background-color: {p['tree_selected']};
        /* Sans couleur de texte explicite, Qt garde le blanc de sa palette
           systeme : selectionner du texte dans la console le faisait
           disparaitre sur le bleu tres pale du theme clair (contraste 1,1:1). */
        selection-color: {p['tree_selected_text']};
    }}
    """
