"""Centre d'aide integre : guide d'utilisation complet, recherche et F1.

L'outil est deploye chez des utilisateurs qui ne connaissent ni pytest ni
l'equipe qui l'a ecrit : l'aide doit etre dans l'application, hors ligne, et
s'ouvrir sur la rubrique de la page affichee (F1). Une documentation dans un
README ou sur un serveur interne n'est lue que par ceux qui savent ou la
chercher.

Le texte est dans ``help_content`` ; ce module ne fait que l'afficher.
"""
from __future__ import annotations

import html
import platform
import re
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QImage, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSplitter, QTextBrowser, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from runner.ui import icons, tokens as t
from runner.ui.help_content import (
    APP_PAGES, CATEGORIES, CONTEXT_TOPICS, SCREENSHOTS, TOPICS, TOPICS_BY_ID, HelpTopic,
)

TOPIC_ROLE = Qt.UserRole + 1
_CAPTURE = re.compile(r"\{shot:([\w-]+)\}")
_SCHEMA_IMAGE = "help-image"
_MARGE_IMAGE = 48


def shot_bytes(name: str) -> bytes | None:
    """Image d'une capture, ou None si elle n'a pas ete generee.

    Lue par importlib.resources : elle suit le paquet, y compris dans
    l'executable PyInstaller (collect_data_files de runner.help_assets).
    """
    try:
        from importlib.resources import files
        return files("runner.help_assets").joinpath(f"{name}.png").read_bytes()
    except (OSError, ModuleNotFoundError):
        return None


def shot_manifest() -> dict:
    import json
    try:
        from importlib.resources import files
        return json.loads(files("runner.help_assets").joinpath("manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return {}


def _figure(name: str, src: str, largeur: int) -> str:
    """La capture, sa legende et la liste numerotee de ses reperes."""
    capture = SCREENSHOTS[name]
    taille = shot_manifest().get(name, {})
    # Sans hauteur explicite, QTextDocument garde la hauteur native de
    # l'image reduite : un grand blanc apparaissait sous la capture.
    hauteur = ""
    if taille.get("width") and taille.get("height"):
        hauteur = f" height='{round(taille['height'] * largeur / taille['width'])}'"
    reperes = "".join(f"<li>{html.escape(texte)}</li>" for _, texte in capture.markers)
    return (f"<p class='figure'><img src='{src}' width='{largeur}'{hauteur} "
            f"alt='{html.escape(capture.caption)}'></p>"
            f"<p class='caption'>{html.escape(capture.caption)}</p>"
            f"<ol class='legend'>{reperes}</ol>")
_BALISE = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")


def _texte_brut(fragment: str) -> str:
    """Texte d'une rubrique, pour la recherche. Une expression reguliere
    suffit : le contenu est ecrit ici, sans HTML piege."""
    texte = html.unescape(_BALISE.sub(" ", fragment))
    return _ESPACES.sub(" ", texte).strip()


def _mots(requete: str) -> list[str]:
    return [mot for mot in requete.casefold().split() if mot]


def support_values(window=None) -> dict[str, str]:
    """Valeurs reelles du poste, affichees dans la rubrique Support.

    Chaque valeur est protegee : une information indisponible ne doit jamais
    empecher d'ouvrir l'aide -- c'est justement quand quelque chose ne marche
    pas qu'on vient la lire.
    """
    from runner.version import __version__

    def sur(fonction, defaut="Unknown"):
        try:
            valeur = fonction()
        except Exception:
            return defaut
        return str(valeur) if valeur not in (None, "") else defaut

    def qt_version():
        import PySide6
        from PySide6.QtCore import qVersion
        return f"Qt {qVersion()} · PySide6 {PySide6.__version__}"

    def history_dir():
        from runner.domain import history
        return history.dossier()

    def interpreter():
        if window is None:
            return ""
        context = window._selected_run_context() if hasattr(window, "_selected_run_context") else window
        return context._effective_interpreter()

    return {
        "version": __version__,
        "python": sur(lambda: f"{platform.python_version()} "
                              f"({platform.architecture()[0]}) · {sys.executable}"),
        "qt": sur(qt_version),
        "os": sur(platform.platform),
        "interpreter": sur(interpreter, "Not configured (default Python)"),
        "history_dir": sur(history_dir),
        "data_dir": sur(lambda: QStandardPaths.writableLocation(
            QStandardPaths.AppDataLocation)),
        "settings_file": sur(lambda: window.settings.fileName() if window is not None else ""),
    }


def support_text(window=None) -> str:
    """Bloc texte a coller dans un signalement."""
    valeurs = support_values(window)
    lignes = (
        ("Pytest Runner", "version"), ("Application Python", "python"),
        ("Qt", "qt"), ("Operating system", "os"),
        ("Test interpreter", "interpreter"), ("History folder", "history_dir"),
        ("Application data", "data_dir"), ("Settings", "settings_file"),
    )
    return "\n".join(f"{libelle}: {valeurs[cle]}" for libelle, cle in lignes)


def _feuille_de_style(imprimable: bool = False) -> str:
    """CSS du sous-ensemble compris par QTextDocument (ni flex ni grid).

    Recalculee a chaque affichage : les couleurs suivent le theme courant.
    L'export imprimable reste clair quel que soit le theme de l'utilisateur.
    """
    if imprimable:
        texte, attenue, accent, bord, doux, fond = (
            "#1b2230", "#5b6675", "#1f6feb", "#d8dee7", "#eef3fb", "#ffffff")
        ambre = "#8a6100"
    else:
        texte, attenue, accent, bord = t.TEXT, t.TEXT_MUTED, t.ACCENT, t.BORDER
        doux, fond = t.ACCENT_SOFT, t.BG_SURFACE
        ambre = t.ANSI_COLORS.get("yellow", t.ACCENT)
    return f"""
body {{ color: {texte}; background-color: {fond}; font-family: {t.FONT_UI}; }}
h1 {{ font-size: x-large; font-weight: 700; margin-bottom: 2px; }}
h2 {{ font-size: large; font-weight: 700; margin-top: 18px; margin-bottom: 6px; color: {texte}; }}
h3 {{ font-weight: 700; margin-top: 14px; margin-bottom: 4px; }}
p, li {{ line-height: 140%; }}
a {{ color: {accent}; text-decoration: none; font-weight: 600; }}
.summary {{ color: {attenue}; margin-bottom: 12px; }}
.crumb {{ color: {attenue}; font-size: small; }}
.center {{ text-align: center; }}
.tip {{ background-color: {doux}; padding: 8px; margin-top: 12px; }}
.note {{ background-color: {doux}; padding: 8px; margin-top: 12px; color: {texte}; }}
.note b {{ color: {ambre}; }}
.kbd {{ font-family: {t.FONT_MONO}; font-weight: 700; background-color: {doux}; color: {texte}; }}
code {{ font-family: {t.FONT_MONO}; color: {accent}; }}
pre {{ font-family: {t.FONT_MONO}; background-color: {doux}; padding: 8px; }}
table {{ border-collapse: collapse; margin-top: 6px; margin-bottom: 6px; }}
th {{ background-color: {doux}; font-weight: 700; text-align: left; border: 1px solid {bord}; }}
td {{ border: 1px solid {bord}; vertical-align: top; }}
.nav {{ color: {attenue}; margin-top: 20px; }}
.figure {{ margin-top: 10px; margin-bottom: 2px; }}
.caption {{ color: {attenue}; font-size: small; margin-top: 0px; }}
.legend li {{ line-height: 130%; }}
"""


def _tableaux(fragment: str) -> str:
    # QTextDocument ignore `padding` sur les cellules : seuls les attributs
    # HTML donnent de l'air au texte des tableaux.
    return fragment.replace(
        "<table>", "<table width='100%' cellspacing='0' cellpadding='6'>")


def _remplir(fragment: str, valeurs: dict[str, str]) -> str:
    """Remplace les marqueurs `{cle}` sans `str.format` : les autres rubriques
    peuvent contenir des accolades sans qu'elles soient interpretees."""
    for cle, valeur in valeurs.items():
        fragment = fragment.replace("{" + cle + "}", html.escape(valeur))
    return fragment


class HelpBrowser(QTextBrowser):
    """Fournit les captures a QTextDocument et signale ses changements de
    largeur, pour que l'image suive la largeur du panneau."""

    resized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images: dict[str, QImage] = {}

    def loadResource(self, kind, url):
        if kind == QTextDocument.ImageResource and url.scheme() == _SCHEMA_IMAGE:
            name = url.path()
            if name not in self._images:
                donnees = shot_bytes(name)
                image = QImage()
                if donnees:
                    image.loadFromData(donnees, "PNG")
                self._images[name] = image
            return self._images[name]
        return super().loadResource(kind, url)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class HelpCenter(QWidget):
    """Liste des rubriques et recherche a gauche, rubrique a droite."""

    topic_changed = Signal(str)

    def __init__(self, window=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.current_topic_id = ""
        self._historique: list[str] = []
        self._position = -1
        self._index = {topic.id: " ".join((
            topic.title, topic.summary, topic.keywords, _texte_brut(topic.body),
        )).casefold() for topic in TOPICS}

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 8, 0, 0)
        racine.setSpacing(0)
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        racine.addWidget(self.splitter)

        # --- Rubriques et recherche -------------------------------------
        gauche = QWidget()
        colonne = QVBoxLayout(gauche)
        colonne.setContentsMargins(0, 0, 8, 0)
        colonne.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the help…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search the help")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._open_first_match)
        colonne.addWidget(self.search)
        self.result_label = QLabel()
        self.result_label.setObjectName("Muted")
        self.result_label.setWordWrap(True)
        colonne.addWidget(self.result_label)
        self.topics = QTreeWidget()
        self.topics.setHeaderHidden(True)
        self.topics.setRootIsDecorated(False)
        self.topics.setIndentation(10)
        self.topics.setAccessibleName("Help topics")
        self.topics.currentItemChanged.connect(self._on_current_item)
        colonne.addWidget(self.topics, 1)
        self._items: dict[str, QTreeWidgetItem] = {}
        self._categories: dict[str, QTreeWidgetItem] = {}
        for categorie in CATEGORIES:
            entete = QTreeWidgetItem([categorie.upper()])
            entete.setFlags(Qt.ItemIsEnabled)
            police = entete.font(0)
            police.setBold(True)
            entete.setFont(0, police)
            self.topics.addTopLevelItem(entete)
            self._categories[categorie] = entete
        for topic in TOPICS:
            item = QTreeWidgetItem([topic.title])
            item.setData(0, TOPIC_ROLE, topic.id)
            item.setToolTip(0, topic.summary)
            self._categories[topic.category].addChild(item)
            self._items[topic.id] = item
        self.topics.expandAll()
        gauche.setMinimumWidth(200)
        self.splitter.addWidget(gauche)

        # --- Rubrique ----------------------------------------------------
        droite = QWidget()
        lecture = QVBoxLayout(droite)
        lecture.setContentsMargins(8, 0, 0, 0)
        lecture.setSpacing(6)
        outils = QHBoxLayout()
        outils.setSpacing(6)
        self.back_button = self._bouton("mdi.arrow-left", "Back", self.back)
        self.forward_button = self._bouton("mdi.arrow-right", "Forward", self.forward)
        self.home_button = self._bouton("mdi.home-outline", "Help home", lambda: self.show_topic("welcome"))
        for bouton in (self.back_button, self.forward_button, self.home_button):
            outils.addWidget(bouton)
        outils.addStretch(1)
        self.status_label = QLabel()
        self.status_label.setObjectName("Muted")
        outils.addWidget(self.status_label)
        self.copy_support_button = QPushButton("Copy support information")
        self.copy_support_button.setToolTip(
            "Copy the version, environment and data folders, to paste in a problem report")
        self.copy_support_button.clicked.connect(self.copy_support_information)
        outils.addWidget(self.copy_support_button)
        self.export_button = QPushButton("Export guide…")
        self.export_button.setToolTip("Save the complete guide as one HTML file, to read, print or share")
        self.export_button.clicked.connect(self.export_guide)
        outils.addWidget(self.export_button)
        lecture.addLayout(outils)
        self.browser = HelpBrowser()
        self._largeur_images = 0
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._fit_images)
        self.browser.resized.connect(self._resize_timer.start)
        self.browser.setObjectName("HelpBrowser")
        # La feuille globale donne une police a chasse fixe aux zones de
        # texte (consoles, logs) : un guide se lit en police d'interface.
        self.browser.setStyleSheet(f"QTextBrowser#HelpBrowser {{ font-family: {t.FONT_UI}; }}")
        # Les liens sont traites ici : `topic:` et `page:` ne sont pas des
        # URL que QTextBrowser saurait charger, et un lien externe doit
        # s'ouvrir dans le navigateur, pas remplacer la rubrique.
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._on_link)
        self.browser.setAccessibleName("Help topic")
        lecture.addWidget(self.browser, 1)
        self.splitter.addWidget(droite)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([250, 750])

        self.restyle()
        self._filter("")
        self.show_topic("welcome")

    # ------------------------------------------------------------------
    def _bouton(self, glyph, infobulle, slot):
        bouton = QPushButton()
        bouton.setObjectName("Icon")
        bouton.setToolTip(infobulle)
        bouton.setAccessibleName(infobulle)
        bouton.setProperty("glyph", glyph)
        bouton.setFixedSize(t.ICON_BUTTON, t.ICON_BUTTON)
        bouton.clicked.connect(slot)
        return bouton

    def restyle(self):
        for bouton in (self.back_button, self.forward_button, self.home_button):
            bouton.setIcon(icons.icon(bouton.property("glyph"), t.TEXT_MUTED))
        self.copy_support_button.setIcon(icons.icon("mdi.content-copy", t.TEXT_MUTED))
        self.export_button.setIcon(icons.icon("mdi.export", t.TEXT_MUTED))
        if self.current_topic_id:
            self._render(self.current_topic_id)

    # ------------------------------------------------------------------
    # Recherche
    # ------------------------------------------------------------------
    def matching_topics(self, requete: str) -> list[str]:
        """Rubriques contenant TOUS les mots, les titres en premier."""
        mots = _mots(requete)
        if not mots:
            return [topic.id for topic in TOPICS]
        trouves = [topic for topic in TOPICS
                   if all(mot in self._index[topic.id] for mot in mots)]
        def rang(topic: HelpTopic):
            titre = topic.title.casefold()
            return (0 if all(mot in titre for mot in mots) else
                    1 if all(mot in topic.keywords.casefold() for mot in mots) else 2)
        return [topic.id for topic in sorted(trouves, key=rang)]

    def _filter(self, texte: str):
        visibles = set(self.matching_topics(texte))
        for topic_id, item in self._items.items():
            item.setHidden(topic_id not in visibles)
        for entete in self._categories.values():
            entete.setHidden(all(entete.child(i).isHidden()
                                 for i in range(entete.childCount())))
        if not _mots(texte):
            self.result_label.setText(f"{len(TOPICS)} topics")
        elif visibles:
            self.result_label.setText(
                f"{len(visibles)} topic{'s' if len(visibles) > 1 else ''} match “{texte.strip()}”")
        else:
            self.result_label.setText(
                f"No topic matches “{texte.strip()}”. Try another word, "
                "or open Troubleshooting.")
        self._highlight()

    def _open_first_match(self):
        trouves = self.matching_topics(self.search.text())
        if trouves:
            self.show_topic(trouves[0])

    def _highlight(self):
        """Surligne les mots recherches dans la rubrique affichee."""
        selections = []
        couleur_fond, couleur_texte = t.search_highlight()
        format_ = QTextCharFormat()
        format_.setBackground(QColor(couleur_fond))
        format_.setForeground(QColor(couleur_texte))
        document = self.browser.document()
        for mot in _mots(self.search.text()):
            curseur = QTextCursor(document)
            while True:
                curseur = document.find(mot, curseur)
                if curseur.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = curseur
                selection.format = format_
                selections.append(selection)
                if len(selections) > 500:
                    break
        self.browser.setExtraSelections(selections)
        if selections:
            premier = QTextCursor(selections[0].cursor)
            premier.clearSelection()
            self.browser.setTextCursor(premier)
            self.browser.ensureCursorVisible()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def topic_for_page(self, page: str) -> str:
        return CONTEXT_TOPICS.get(page, "welcome")

    def show_topic(self, topic_id: str, *, record: bool = True) -> bool:
        if topic_id not in TOPICS_BY_ID:
            return False
        if record and topic_id != self.current_topic_id:
            del self._historique[self._position + 1:]
            self._historique.append(topic_id)
            self._historique = self._historique[-50:]
            self._position = len(self._historique) - 1
        self.current_topic_id = topic_id
        self._render(topic_id)
        item = self._items[topic_id]
        if self.topics.currentItem() is not item:
            self.topics.blockSignals(True)
            self.topics.setCurrentItem(item)
            self.topics.blockSignals(False)
        self._update_navigation()
        self.topic_changed.emit(topic_id)
        return True

    def back(self):
        if self._position > 0:
            self._position -= 1
            self.show_topic(self._historique[self._position], record=False)

    def forward(self):
        if self._position < len(self._historique) - 1:
            self._position += 1
            self.show_topic(self._historique[self._position], record=False)

    def _update_navigation(self):
        self.back_button.setEnabled(self._position > 0)
        self.forward_button.setEnabled(self._position < len(self._historique) - 1)

    def _on_current_item(self, current, _previous=None):
        if current is not None:
            topic_id = current.data(0, TOPIC_ROLE)
            if topic_id:
                self.show_topic(topic_id)

    def _on_link(self, url: QUrl):
        cible = url.toString()
        schema, _, reste = cible.partition(":")
        if schema == "topic":
            self.show_topic(reste)
        elif schema == "page":
            if reste in APP_PAGES and self.window is not None:
                self.window._show_page(reste)
        elif schema in ("http", "https", "mailto", "file"):
            QDesktopServices.openUrl(url)

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------
    def _image_width(self, name: str) -> int:
        native = int(shot_manifest().get(name, {}).get("width") or 900)
        disponible = self.browser.viewport().width() - _MARGE_IMAGE
        return max(200, min(native, disponible)) if disponible > 200 else min(native, 900)

    def _fit_images(self):
        """Re-affiche la rubrique si la largeur des captures doit changer."""
        topic = TOPICS_BY_ID.get(self.current_topic_id)
        if topic is None or not _CAPTURE.search(topic.body):
            return
        largeurs = tuple(self._image_width(n) for n in _CAPTURE.findall(topic.body))
        if largeurs != self._largeur_images:
            barre = self.browser.verticalScrollBar()
            proportion = barre.value() / max(1, barre.maximum())
            self._render(self.current_topic_id, keep_scroll=True)
            barre.setValue(int(proportion * barre.maximum()))

    def _shots_html(self, corps: str, *, exporte: bool) -> str:
        import base64

        def remplace(correspondance):
            name = correspondance.group(1)
            if name not in SCREENSHOTS:
                return ""
            if exporte:
                donnees = shot_bytes(name)
                if not donnees:
                    return ""
                largeur = int(shot_manifest().get(name, {}).get("width") or 900)
                src = "data:image/png;base64," + base64.b64encode(donnees).decode("ascii")
                return _figure(name, src, largeur)
            if shot_bytes(name) is None:
                return ""
            return _figure(name, f"{_SCHEMA_IMAGE}:{name}", self._image_width(name))

        return _CAPTURE.sub(remplace, corps)

    def _topic_html(self, topic: HelpTopic, *, valeurs=None, exporte=False) -> str:
        corps = _tableaux(topic.body)
        if valeurs is not None:
            corps = _remplir(corps, valeurs)
        corps = self._shots_html(corps, exporte=exporte)
        return (f"<p class='crumb'>{html.escape(topic.category)}</p>"
                f"<h1>{html.escape(topic.title)}</h1>"
                f"<p class='summary'>{html.escape(topic.summary)}</p>{corps}")

    def _render(self, topic_id: str, *, keep_scroll: bool = False):
        topic = TOPICS_BY_ID[topic_id]
        valeurs = support_values(self.window) if "{version}" in topic.body else {}
        self._largeur_images = tuple(self._image_width(n) for n in _CAPTURE.findall(topic.body))
        position = [item.id for item in TOPICS].index(topic_id)
        liens = []
        if position > 0:
            precedent = TOPICS[position - 1]
            liens.append(f"← <a href='topic:{precedent.id}'>{html.escape(precedent.title)}</a>")
        if position < len(TOPICS) - 1:
            suivant = TOPICS[position + 1]
            liens.append(f"<a href='topic:{suivant.id}'>{html.escape(suivant.title)}</a> →")
        navigation = f"<hr><p class='nav'>{' &nbsp;·&nbsp; '.join(liens)}</p>" if liens else ""
        self.browser.document().setDefaultStyleSheet(_feuille_de_style())
        self.browser.setHtml(
            f"<html><body>{self._topic_html(topic, valeurs=valeurs)}{navigation}</body></html>")
        if not keep_scroll:
            self.browser.verticalScrollBar().setValue(0)
        self._highlight()

    def guide_html(self) -> str:
        """Le guide complet en un seul fichier, lisible sans l'application."""
        from runner.version import __version__

        sommaire, sections = [], []
        for categorie in CATEGORIES:
            membres = [topic for topic in TOPICS if topic.category == categorie]
            sommaire.append(f"<h3>{html.escape(categorie)}</h3><ul>" + "".join(
                f"<li><a href='#{topic.id}'>{html.escape(topic.title)}</a></li>"
                for topic in membres) + "</ul>")
            for topic in membres:
                sections.append(f"<a name='{topic.id}'></a>{self._topic_html(topic, exporte=True)}<hr>")
        corps = "".join(sections)
        corps = re.sub(r"href=(['\"])topic:([\w-]+)\1", r"href='#\2'", corps)
        # Hors de l'application, un lien vers une page n'a pas de cible : il
        # devient du texte en gras, ce qui garde le nom de la page lisible.
        corps = re.sub(r"<a href=(['\"])page:[\w-]+\1>(.*?)</a>", r"<b>\2</b>", corps, flags=re.S)
        # Les valeurs du poste n'ont pas de sens dans un guide partage.
        corps = re.sub(r"\{(version|python|qt|os|interpreter|history_dir|data_dir|settings_file)\}",
                       "<i>see Help → Support in the application</i>", corps)
        return (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>Pytest Runner {html.escape(__version__)} — User guide</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<style>body{{font-family:{t.FONT_UI};max-width:900px;margin:24px auto;"
            f"padding:0 16px;}}{_feuille_de_style(imprimable=True)}"
            "td,th{padding:6px;} .kbd{padding:0 4px;border-radius:3px;}"
            "img{max-width:100%;height:auto;border:1px solid #d8dee7;border-radius:6px;}"
            "</style></head><body>"
            f"<h1>Pytest Runner {html.escape(__version__)} — User guide</h1>"
            "<h2>Contents</h2>" + "".join(sommaire) + "<hr>" + corps +
            "</body></html>")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def copy_support_information(self):
        QApplication.clipboard().setText(support_text(self.window))
        self.status_label.setText("Support information copied")

    def export_guide(self, path: str = ""):
        if not path:
            depart = str(Path.home() / "Pytest Runner user guide.html")
            path, _ = QFileDialog.getSaveFileName(
                self, "Export the user guide", depart, "HTML files (*.html)")
        if not path:
            return False
        try:
            Path(path).write_text(self.guide_html(), encoding="utf-8")
        except OSError as exc:
            self.status_label.setText(f"Export failed: {exc.strerror or exc}")
            return False
        self.status_label.setText("Guide exported")
        return True

    def search_for(self, texte: str):
        self.search.setText(texte)
        self._open_first_match()
