"""Feuille de style unique de l'application.

Tout le style vit ici. Aucun `setStyleSheet` disperse dans les widgets : une
couleur posee a la main quelque part echappe au theme et finit par jurer.
Les rares exceptions (couleur propre a un lecteur, calculee) passent par une
fonction de ce module.
"""

from __future__ import annotations

from runner.domain.models import Status
from runner.ui import glyphs
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
/* Cette regle globale accorde `WA_StyledBackground` a TOUT QWidget -- y
   compris un simple QLabel qui ne demande qu'une couleur de texte. Sans ce
   `border: none`, le moteur de feuilles de style de Qt peut lui dessiner
   quand meme un contour par defaut. Ligne de defense de base ; certains
   labels, trop imbriques dans la mise en page (une carte, dans une rangee,
   dans un panneau, dans la fenetre), avaient besoin d'aller plus loin --
   voir les regles `QLabel#StatCellLabel` / `#ReaderVerdict_*` / `#StatusLive`
   plus bas, posees par nom d'objet plutot que par `setStyleSheet()` direct. */
QLabel {{
    border: none;
}}
QToolTip {{
    background-color: {t.BG_RAISED};
    color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SPACE_1}px {t.SPACE_2}px;
}}

/* -------------------------------------------------------------- surfaces */
QFrame#Navigation {{
    background-color: {t.BG_SURFACE};
    border: none;
    border-right: 1px solid {t.BORDER};
}}
QLabel#NavigationTitle {{
    color: {t.TEXT};
    font-size: {t.TEXT_LG}px;
    font-weight: 700;
}}
QPushButton#NavigationItem {{
    background-color: transparent;
    border: none;
    color: {t.TEXT_MUTED};
    min-height: {t.CONTROL_LG}px;
    padding: 0 {t.SPACE_3}px;
    text-align: left;
}}
QPushButton#NavigationItem:hover {{
    background-color: {t.BG_HOVER};
    color: {t.TEXT};
}}
QPushButton#NavigationItem:checked {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
    color: {t.ACCENT};
}}
QLabel#PageTitle {{
    color: {t.TEXT};
    font-size: {t.TEXT_LG + 5}px;
    font-weight: 700;
}}
QFrame#InterpreterAlert {{
    background-color: {t.rgba(t.status_color(Status.FAILED), 0.10)};
    border: 1px solid {t.status_color(Status.FAILED)};
    border-radius: {t.RADIUS_MD}px;
}}
QFrame#InterpreterAlert QLabel {{
    color: {t.status_color(Status.FAILED)};
    background: transparent;
}}
QFrame#ConfigSection {{
    background-color: {t.BG_SURFACE};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_LG}px;
}}
QLabel#ConfigSectionTitle {{
    color: {t.TEXT};
    font-size: {t.TEXT_LG}px;
    font-weight: 700;
}}
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
/* Trois niveaux, et trois seulement. Auparavant tout etait la meme boite grise
   et rien ne disait laquelle comptait :
     Primary   -- l'action du moment, remplie, unique a l'ecran
     Secondary -- la voie normale, contour discret  (defaut)
     Ghost     -- utilitaire, sans chrome tant qu'on ne le survole pas        */
QPushButton {{
    background-color: {t.BG_RAISED};
    color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_MD}px;
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_MD}px;
    font-size: {t.TEXT_SM}px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {t.BG_HOVER}; border-color: {t.TEXT_FAINT}; }}
QPushButton:pressed {{ background-color: {t.BG_SURFACE}; }}
QPushButton:disabled {{
    color: {t.TEXT_FAINT};
    background-color: transparent;
    border-color: {t.BORDER};
}}
QPushButton:checked {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
    border-color: {t.ACCENT};
    color: {t.ACCENT};
}}

QPushButton#Primary {{
    background-color: {t.ACCENT};
    color: {t.ON_ACCENT};
    border: 1px solid {t.ACCENT};
    font-weight: 600;
    padding: 0 {t.SPACE_4}px;
}}
QPushButton#Primary:hover {{
    background-color: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER};
}}
QPushButton#Primary:pressed {{
    background-color: {t.ACCENT_PRESSED}; border-color: {t.ACCENT_PRESSED};
}}
QPushButton#Primary:disabled {{
    background-color: transparent; color: {t.TEXT_FAINT}; border-color: {t.BORDER};
}}

/* Lancer : vert plein, comme dans l'ancienne interface. */
QPushButton#Run {{
    background-color: {t.RUN};
    color: {t.ON_RUN};
    border: 1px solid {t.RUN};
    font-weight: 600;
    padding: 0 {t.SPACE_4}px;
}}
QPushButton#Run:hover {{
    background-color: {t.RUN_HOVER}; border-color: {t.RUN_HOVER};
}}
QPushButton#Run:pressed {{
    background-color: {t.RUN_PRESSED}; border-color: {t.RUN_PRESSED};
}}
QPushButton#Run:disabled {{
    background-color: transparent; color: {t.TEXT_FAINT}; border-color: {t.BORDER};
}}

/* Ghost : rien tant qu'on ne le survole pas. Un bouton rare ne doit pas peser
   autant qu'une action courante. */
QPushButton#Ghost {{
    background-color: transparent;
    border-color: transparent;
    color: {t.TEXT_MUTED};
}}
QPushButton#Ghost:hover {{
    background-color: {t.BG_HOVER}; color: {t.TEXT}; border-color: transparent;
}}
QPushButton#Ghost:disabled {{ color: {t.TEXT_FAINT}; background: transparent; }}
/* Un filtre pose derriere un panneau ferme serait invisible : on chercherait
   pourquoi la moitie de l'arbre est decochee. Le bouton le dit. */
QPushButton#Ghost[active="true"] {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
    color: {t.ACCENT};
}}

/* Panneau flottant : il se pose PAR-DESSUS l'arbre, il lui faut donc un fond
   opaque, un contour et de l'ombre portee pour ne pas se confondre avec lui. */
QFrame#Popup {{
    background-color: {t.BG_RAISED};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_LG}px;
}}
QScrollArea#Plain, QScrollArea#Plain > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QWidget#MarkerRow {{ border-radius: {t.RADIUS_SM}px; }}
QWidget#MarkerRow:hover {{ background-color: {t.BG_HOVER}; }}
QCheckBox {{ background: transparent; font-size: {t.TEXT_SM}px; spacing: {t.SPACE_2}px; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_SM}px;
    background-color: {t.BG_INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {t.ACCENT}; }}
QCheckBox::indicator:checked {{
    background-color: {t.ACCENT};
    border-color: {t.ACCENT};
    image: url({glyphs.check(t.ON_ACCENT)});
}}

/* Arreter n'est pas une action colorée : elle ne le devient qu'au survol,
   quand elle est reellement disponible. */
QPushButton#Danger:hover {{
    background-color: {t.rgba(t.status_color(Status.FAILED), 0.12)};
    border-color: {t.status_color(Status.FAILED)};
    color: {t.status_color(Status.FAILED)};
}}

/* Bouton d'icone : carre, pour ne pas pencher dans une rangee. */
QPushButton#Icon {{
    background-color: transparent;
    border-color: transparent;
    padding: 0;
    min-width: {t.ICON_BUTTON}px;
    max-width: {t.ICON_BUTTON}px;
    min-height: {t.ICON_BUTTON}px;
}}
QPushButton#Icon:hover {{ background-color: {t.BG_HOVER}; }}
QPushButton#Icon:checked {{ background-color: {t.rgba(t.ACCENT, 0.16)}; }}

/* Variante courte, pour les rangees d'outils secondaires : dans une meme
   rangee, deux hauteurs differentes se voient tout de suite. */
QPushButton#IconSm {{
    background-color: transparent;
    border-color: transparent;
    padding: 0;
    min-width: {t.CONTROL_SM}px;
    max-width: {t.CONTROL_SM}px;
    min-height: {t.CONTROL_SM}px;
    max-height: {t.CONTROL_SM}px;
}}
QPushButton#IconSm:hover {{ background-color: {t.BG_HOVER}; }}
QPushButton#IconSm:checked {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
}}

/* Selecteur segmente : plusieurs vues d'UNE meme chose, pas plusieurs actions.
   Les segments se touchent et ne partagent qu'un seul trait ; separes, ils
   auraient ete lus comme trois boutons independants. */
QPushButton#Segment {{
    background-color: transparent;
    border: 1px solid {t.BORDER};
    border-radius: 0;
    color: {t.TEXT_MUTED};
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_SM}px;
    max-height: {t.CONTROL_SM}px;
    font-size: {t.TEXT_XS}px;
    font-weight: 600;
}}
QPushButton#Segment[segment="first"] {{
    border-top-left-radius: {t.RADIUS_MD}px;
    border-bottom-left-radius: {t.RADIUS_MD}px;
}}
QPushButton#Segment[segment="middle"] {{ border-left: none; }}
QPushButton#Segment[segment="last"] {{
    border-left: none;
    border-top-right-radius: {t.RADIUS_MD}px;
    border-bottom-right-radius: {t.RADIUS_MD}px;
}}
QPushButton#Segment:hover {{ background-color: {t.BG_HOVER}; color: {t.TEXT}; }}
QPushButton#Segment:checked {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
    color: {t.ACCENT};
}}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SPACE_1}px;
}}
QToolButton:hover {{ background-color: {t.BG_HOVER}; }}
QToolButton:checked {{ background-color: {t.rgba(t.ACCENT, 0.16)}; }}
QToolButton#HistoryAction {{
    background-color: {t.BG_RAISED};
    color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_MD}px;
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_MD}px;
    font-size: {t.TEXT_SM}px;
    font-weight: 500;
}}
QToolButton#HistoryAction:hover {{
    background-color: {t.BG_HOVER};
    border-color: {t.TEXT_FAINT};
}}

/* ---------------------------------------------------------------- champs */
QLineEdit, QComboBox {{
    background-color: {t.BG_INPUT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: 0 {t.SPACE_2}px;
    min-height: {t.CONTROL_MD}px;
    selection-background-color: {t.ACCENT};
    selection-color: {t.ON_ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {t.ACCENT}; }}
/* Une expression que pytest refuserait : le champ le dit avant qu'on lance. */
QLineEdit[invalid="true"] {{ border-color: {t.status_color(Status.FAILED)}; }}

/* Puce de marker : une etiquette qu'on peut allumer, pas un bouton d'action.
   Ronde et sans relief au repos pour qu'une rangee de dix ne fasse pas
   concurrence au bouton qui lance vraiment les tests. */
QPushButton#Chip {{
    background-color: transparent;
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_PILL}px;
    color: {t.TEXT_MUTED};
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_SM - 4}px;
    max-height: {t.CONTROL_SM - 4}px;
    font-size: {t.TEXT_XS}px;
    font-weight: 600;
}}
QPushButton#Chip:hover {{ background-color: {t.BG_HOVER}; color: {t.TEXT}; }}
QPushButton#Chip:checked {{
    background-color: {t.rgba(t.ACCENT, 0.16)};
    border-color: {t.ACCENT};
    color: {t.ACCENT};
}}
QComboBox::drop-down {{ border: none; width: {t.SPACE_6}px; }}
QComboBox::down-arrow {{
    image: url({glyphs.chevron_down(t.TEXT_MUTED)});
    width: 14px; height: 14px;
}}
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
QTreeView::item:selected {{
    background-color: {t.rgba(t.ACCENT, 0.18)};
    color: {t.TEXT};
}}

/* Une coche dessinee : sans image, Qt rendait un simple caractere sans boite,
   qui n'avait rien a voir avec le reste de l'interface. */
QTreeView::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {t.BORDER_STRONG};
    border-radius: {t.RADIUS_SM}px;
    background-color: {t.BG_INPUT};
}}
QTreeView::indicator:hover {{ border-color: {t.ACCENT}; }}
QTreeView::indicator:checked {{
    background-color: {t.ACCENT};
    border-color: {t.ACCENT};
    image: url({glyphs.check(t.ON_ACCENT)});
}}
QTreeView::indicator:indeterminate {{
    background-color: {t.rgba(t.ACCENT, 0.28)};
    border-color: {t.ACCENT};
    image: url({glyphs.dash(t.ACCENT)});
}}

QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    border-image: none;
    image: url({glyphs.branch_closed(t.TEXT_FAINT)});
}}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    border-image: none;
    image: url({glyphs.branch_open(t.TEXT_FAINT)});
}}

/* La colonne des branches est peinte a part de celle des items. Sans ces deux
   regles, Qt y remet sa couleur de selection systeme et la ligne selectionnee
   commence par un bloc bleu vif etranger au theme.
   La couleur est composee en OPAQUE : sur cette zone precise, Qt ignore le
   canal alpha d'un rgba() et retombe sur son bleu par defaut. */
QTreeView::branch:selected {{
    background-color: {t.blend(t.ACCENT, t.BG_SURFACE, 0.18)};
}}
QTreeView::branch:hover {{ background-color: {t.BG_HOVER}; }}
/* Toutes les listes, et non une regle par nom d'objet : sans regle, Qt
   reprend son bleu systeme pour la ligne selectionnee -- etranger au theme,
   et bien plus vif que tout le reste de la fenetre. La premiere liste ajoutee
   apres coup retombait dans le piege. */
QListWidget {{
    background-color: {t.BG_INPUT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    font-size: {t.TEXT_SM}px;
    outline: none;
}}
QListWidget::item {{
    padding: {t.SPACE_1}px {t.SPACE_2}px;
    border-radius: {t.RADIUS_SM}px;
    color: {t.TEXT};
}}
QListWidget::item:hover {{ background-color: {t.BG_HOVER}; }}
QListWidget::item:selected {{
    background-color: {t.blend(t.ACCENT, t.BG_SURFACE, 0.18)};
    color: {t.TEXT};
}}

/* Les echecs d'un regroupement : sans cadre, ils font partie de la fiche, et
   en chasse fixe parce que ce sont des identifiants de tests. */
QListWidget#Failures {{
    background-color: transparent;
    border: none;
    font-family: {t.FONT_MONO};
}}

/* ---------------------------------------------------------------- tables */
/* L'historique est un tableau, pas un arbre : sans regle a lui, Qt n'y peint
   la selection que sur la cellule cliquee. La ligne entiere doit ressortir --
   c'est elle qu'on selectionne, et par paire pour une comparaison. */
QTableView {{
    background-color: {t.BG_SURFACE};
    alternate-background-color: {t.BG_SURFACE};
    color: {t.TEXT};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
    gridline-color: transparent;
    selection-background-color: {t.blend(t.ACCENT, t.BG_SURFACE, 0.18)};
    selection-color: {t.TEXT};
}}
QTableView::item {{
    padding: {t.SPACE_1}px {t.SPACE_2}px;
    border: none;
}}
QTableView::item:selected {{
    background-color: {t.blend(t.ACCENT, t.BG_SURFACE, 0.18)};
    color: {t.TEXT};
}}
QTableView::item:hover {{ background-color: {t.BG_HOVER}; }}

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

/* Deux niveaux bien distincts : les vues principales sont de vrais boutons
   de navigation ; les lecteurs restent plus compacts, comme un filtre local. */
QTabBar#PrimaryTabs::tab {{
    color: {t.TEXT_MUTED};
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SPACE_2}px {t.SPACE_3}px;
    font-size: {t.TEXT_MD}px;
    font-weight: 600;
}}
QTabBar#PrimaryTabs::tab:hover {{
    color: {t.TEXT};
    background-color: {t.BG_HOVER};
}}
QTabBar#PrimaryTabs::tab:selected {{
    color: {t.TEXT};
    background-color: {t.ACCENT_SOFT};
    border-bottom-color: {t.ACCENT};
    font-weight: 700;
}}

/* History utilise quatre onglets de meme importance. Une largeur minimale
   fixe empeche les libelles Issues / Output / Details de se tasser ou de se
   chevaucher lorsque la fenetre est redimensionnee. */
QTabBar#HistoryTabs::tab {{
    min-width: 92px;
    max-width: 92px;
    min-height: {t.CONTROL_MD}px;
    padding: 0 {t.SPACE_3}px;
    margin-right: {t.SPACE_1}px;
    color: {t.TEXT_MUTED};
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: {t.RADIUS_MD}px;
    font-size: {t.TEXT_SM}px;
    font-weight: 600;
}}
QTabBar#HistoryTabs::tab:hover {{
    color: {t.TEXT};
    background-color: {t.BG_HOVER};
}}
QTabBar#HistoryTabs::tab:selected {{
    color: {t.TEXT};
    background-color: {t.ACCENT_SOFT};
    border-bottom-color: {t.ACCENT};
    font-weight: 700;
}}

QFrame#HistorySummary, QFrame#HistoryAside {{
    background-color: {t.BG_APP};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
}}
QFrame#HistoryReaderCard {{
    background-color: {t.BG_SURFACE};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
}}

QTabBar#ReaderTabs {{
    background-color: {t.BG_APP};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_LG}px;
    padding: {t.SPACE_1}px;
}}
QTabBar#ReaderTabs::tab {{
    background-color: transparent;
    border: none;
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SPACE_1}px {t.SPACE_2}px;
    margin: 0 1px;
    font-size: {t.TEXT_XS}px;
}}
QTabBar#ReaderTabs::tab:hover {{
    background-color: {t.BG_HOVER};
}}
QTabBar#ReaderTabs::tab:selected {{
    background-color: {t.BG_SURFACE};
}}
QStatusBar QLabel {{ background: transparent; }}

/* Libelles discrets. Poses par nom d'objet et non widget par widget : une
   couleur ecrite a la main dans un widget echappe au theme, et il faudrait la
   rejouer a chaque bascule. Ici la feuille globale s'en charge seule. */
QLabel#Muted {{
    color: {t.TEXT_MUTED};
    font-size: {t.TEXT_SM}px;
    background: transparent;
}}
QLabel#Faint {{
    color: {t.TEXT_FAINT};
    font-size: {t.TEXT_XS}px;
    background: transparent;
}}
QLabel#Title {{
    color: {t.TEXT};
    font-size: {t.TEXT_LG}px;
    font-weight: 600;
    background: transparent;
}}

/* Case du bandeau de stats (READER A, DURATION, ...) : legende et valeur.
   Meme raison que Muted/Faint/Title ci-dessus -- posees par nom d'objet,
   PAS par un `setStyleSheet()` sur le label lui-meme. Assez imbrique dans
   la mise en page (une carte, dans une rangee, dans un panneau, dans une
   fenetre), un `setStyleSheet()` pose directement sur ces labels faisait
   dessiner a Qt un contour fantome autour de la ligne de mise en page qui
   les contient -- quel que soit le contenu de la feuille posee, meme une
   seule regle de couleur. Une regle globale ne declenche jamais ca.  */
QLabel#StatCellLabel {{
    color: {t.TEXT_FAINT};
    font-size: 10px;
    font-weight: 700;
    background: transparent;
}}
QLabel#StatCellValue {{
    color: {t.TEXT};
    font-size: {t.TEXT_MD}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#ReaderVerdict_passed, QLabel#ReaderVerdict_failed,
QLabel#ReaderVerdict_skipped, QLabel#ReaderVerdict_error,
QLabel#ReaderVerdict_running, QLabel#ReaderVerdict_pending {{
    font-size: {t.TEXT_XS}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#ReaderVerdict_passed {{ color: {t.status_color(Status.PASSED)}; }}
QLabel#ReaderVerdict_failed {{ color: {t.status_color(Status.FAILED)}; }}
QLabel#ReaderVerdict_skipped {{ color: {t.status_color(Status.SKIPPED)}; }}
QLabel#ReaderVerdict_error {{ color: {t.status_color(Status.ERROR)}; }}
QLabel#ReaderVerdict_running {{ color: {t.status_color(Status.RUNNING)}; }}
QLabel#ReaderVerdict_pending {{ color: {t.TEXT_FAINT}; }}
QLabel#StatusLive {{
    color: {t.status_color(Status.RUNNING)};
    font-weight: 600;
    background: transparent;
}}

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
    """Pastille coloree : nom de lecteur, etiquette.

    Passe par une fonction plutot que par le QSS global : la couleur depend
    d'une donnee (le statut, l'index du lecteur), pas du theme seul.
    """
    return (
        f"background-color: {t.rgba(couleur, 0.14) if actif else 'transparent'};"
        f"color: {couleur if actif else t.TEXT_FAINT};"
        f"border: none;"
        f"border-radius: {t.RADIUS_PILL}px;"
        f"padding: {t.SPACE_1}px {t.SPACE_3}px;"
        f"font-size: {t.TEXT_XS}px; font-weight: 600;"
    )


def counter_style(couleur: str, actif: bool, taille: int = t.TEXT_SM) -> str:
    """Compteur de statut : sans boite.

    Quatre pastilles encadrees se disputaient l'attention, dont trois a zero.
    Ici seul le nombre porte la couleur ; a zero, tout s'eteint.
    """
    return (
        "background: transparent; border: none;"
        f"color: {couleur if actif else t.TEXT_FAINT};"
        f"font-size: {taille}px;"
        f"font-weight: {'600' if actif else '400'};"
        f"padding: 0 {t.SPACE_2}px;"
    )


def muted(size: int = t.TEXT_SM) -> str:
    return f"color: {t.TEXT_MUTED}; font-size: {size}px; background: transparent;"


def faint(size: int = t.TEXT_XS) -> str:
    return f"color: {t.TEXT_FAINT}; font-size: {size}px; background: transparent;"
