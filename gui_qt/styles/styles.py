# gui_qt/styles/styles.py

# ---------- COLORS ----------
PRIMARY = "#1976d2"
NEUTRAL = "#616161"
SUCCESS = "#2e7d32"
DANGER = "#c62828"

TREE_BG = "#ffffff"
TREE_BORDER = "#ccc"
TREE_HOVER = "#f0f4f8"
TREE_SELECTED = "#e3f2fd"

CONSOLE_BG = "#1e1e1e"
CONSOLE_TEXT = "#dcdcdc"
CONSOLE_BORDER = "#444"

# ---------- APP-WIDE THEME (fond clair moderne, remplace le gris Windows par defaut) ----------
APP_BACKGROUND = "#f3f5f8"
APP_SURFACE = "#ffffff"
APP_BORDER = "#e0e4e9"
APP_TEXT = "#20262e"
APP_TEXT_MUTED = "#6b7480"
APP_HOVER = "#eef2f6"
APP_SCROLLBAR = "#c7ccd3"
APP_SCROLLBAR_HOVER = "#a7aeb7"


# ---------- APP-WIDE STYLESHEET ----------
def app_stylesheet() -> str:
    """Feuille de style globale (QApplication.setStyleSheet), pour un look
    moderne et clair au lieu du gris Windows par defaut. Les styles specifiques
    par widget (boutons colores, arbre, console...) restent prioritaires."""
    return f"""
    QMainWindow, QDialog, QWidget {{
        background-color: {APP_BACKGROUND};
        color: {APP_TEXT};
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }}

    QMenuBar {{
        background-color: {APP_SURFACE};
        border-bottom: 1px solid {APP_BORDER};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 4px 10px;
        background: transparent;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {APP_HOVER};
    }}
    QMenu {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 22px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {TREE_SELECTED};
    }}

    QTabWidget::pane {{
        border: 1px solid {APP_BORDER};
        border-radius: 8px;
        background-color: {APP_SURFACE};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {APP_TEXT_MUTED};
        padding: 8px 22px;
        margin-right: 2px;
        min-width: 90px;
        min-height: 18px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {APP_SURFACE};
        color: {PRIMARY};
        border: 1px solid {APP_BORDER};
        border-bottom: 2px solid {PRIMARY};
        padding: 8px 22px;
    }}
    QTabBar::tab:hover:!selected {{
        color: {APP_TEXT};
    }}

    QPushButton {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
        border-radius: 6px;
        padding: 6px 14px;
        color: {APP_TEXT};
    }}
    QPushButton:hover {{
        background-color: {APP_HOVER};
    }}
    QPushButton:pressed {{
        background-color: {APP_BORDER};
    }}

    QLineEdit, QComboBox {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {TREE_SELECTED};
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {PRIMARY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
        selection-background-color: {TREE_SELECTED};
        outline: none;
    }}

    QGroupBox {{
        border: 1px solid {APP_BORDER};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 14px;
        background-color: {APP_SURFACE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}

    QProgressBar {{
        border: 1px solid {APP_BORDER};
        border-radius: 6px;
        background-color: {APP_SURFACE};
        text-align: center;
        height: 18px;
    }}
    QProgressBar::chunk {{
        background-color: {PRIMARY};
        border-radius: 5px;
    }}

    QHeaderView::section {{
        background-color: {APP_SURFACE};
        border: none;
        border-bottom: 1px solid {APP_BORDER};
        padding: 6px;
        font-weight: 600;
        color: {APP_TEXT_MUTED};
    }}
    QTableWidget {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
        border-radius: 8px;
        gridline-color: {APP_BORDER};
    }}
    QTableWidget::item:selected {{
        background-color: {TREE_SELECTED};
        color: {APP_TEXT};
    }}

    QListWidget {{
        background-color: {APP_SURFACE};
        border: 1px solid {APP_BORDER};
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
        background: {APP_SCROLLBAR};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {APP_SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {APP_SCROLLBAR};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {APP_SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    """


# ---------- BUTTONS ----------
BASE_BUTTON = """
QPushButton {
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
    color: white;
}
QPushButton:hover {
    opacity: 0.85;
}
QPushButton:disabled {
    background-color: #555;
    color: #aaa;
}
"""

def primary_button():
    return BASE_BUTTON + f"""
    QPushButton {{
        background-color: {PRIMARY};
    }}
    """

def neutral_button():
    return BASE_BUTTON + f"""
    QPushButton {{
        background-color: {NEUTRAL};
    }}
    """

def success_button():
    return BASE_BUTTON + f"""
    QPushButton {{
        background-color: {SUCCESS};
    }}
    """

def danger_button():
    return BASE_BUTTON + f"""
    QPushButton {{
        background-color: {DANGER};
    }}
    """


# ---------- TOOLBAR BUTTON ----------
def toolbar_button():
    return f"""
    QPushButton {{
        background-color: #e9ecef;
        border: 1px solid #ced4da;
        border-radius: 5px;
        padding: 4px 10px;
        font-size: 12px;
    }}
    QPushButton:hover {{
        background-color: #dee2e6;
    }}
    QPushButton:checked {{
        background-color: #90caf9;
        border: 1px solid {PRIMARY};
    }}
    """


# ---------- TREE ----------
def tree_style():
    return f"""
    QTreeView {{
        background-color: {TREE_BG};
        border: 1px solid {TREE_BORDER};
        border-radius: 6px;
        font-size: 12px;
    }}

    QTreeView::item {{
        padding: 4px 2px;
    }}

    QTreeView::item:hover {{
        background-color: {TREE_HOVER};
    }}

    QTreeView::item:selected {{
        background-color: {TREE_SELECTED};
        color: #000;
    }}

    QTreeView::indicator {{
        width: 16px;
        height: 16px;
    }}

    QTreeView::indicator:unchecked {{
        border: 1px solid #9e9e9e;
        border-radius: 4px;
        background-color: #ffffff;
    }}

    QTreeView::indicator:checked {{
        background-color: #607d8b;
        border: 1px solid #607d8b;
        border-radius: 4px;
    }}

    QTreeView::indicator:indeterminate {{
        background-color: #b0bec5;
        border: 1px solid #607d8b;
        border-radius: 4px;
    }}
    """


# ---------- CONSOLE ----------
def console_style():
    return f"""
    QTextEdit {{
        background-color: {CONSOLE_BG};
        color: {CONSOLE_TEXT};
        border: 1px solid {CONSOLE_BORDER};
    }}
    """
