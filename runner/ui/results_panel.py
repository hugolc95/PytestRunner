"""Panneau de droite : la fiche d'un test, la sortie brute, les logs.

L'ordre des onglets est un choix, pas un hasard. Mesure faite sur un run reel
de 160 tests dont 44 en echec, la console produit 292 lignes :

    160  verdicts       -> deja dans l'arbre, une colonne par lecteur
      9  bannieres      -> jamais lues
      2  vides
    121  traces d'echec <- la SEULE chose qu'on ne trouve nulle part ailleurs

Le seul apport propre de la console represente 41 % de ses lignes, et c'est
justement ce qu'elle rend le plus difficile a trouver : il faut passer neuf
lignes avant la premiere trace, puis chercher la bonne parmi quarante-quatre.

D'ou la disposition : `Detail` d'abord, qui repond a la question posee (ce test
la, pourquoi), et la console juste derriere, entiere et copiable, pour tout ce
que la fiche ne peut pas deviner.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QSplitter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from runner.domain import failures as failures_mod
from runner.domain import log_compare, logs
from runner.domain.models import Outcome, PhaseReport, Reader, ReaderReport, RunRequest, Status
from runner.domain.source import path_of as source_path
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.console_view import ConsoleView
from runner.ui.detail_panel import DetailPanel
from runner.ui.source_panel import SourcePanel
from runner.ui.external_log import open_in_notepad_plus_plus

ONGLET_DETAIL = 0
ONGLET_SOURCE = 1
ONGLET_OUTPUT = 2
ONGLET_LOGS = 3


class ReaderViews(QWidget):
    """Une console par lecteur : une seule visible, ou toutes.

    Sert deux fois -- la sortie pytest et les logs -- avec un sens de
    comparaison different. Les sorties defilent, on les empile pour garder la
    largeur ; les logs se comparent ligne a ligne, on les met cote a cote.
    """

    reader_selected = pyqtSignal(int)
    open_file_requested = pyqtSignal(int)

    def __init__(self, orientation=Qt.Vertical, sync_scroll: bool = False,
                 show_lens: bool = True, highlight_differences: bool = False,
                 external_open: bool = False,
                 parent=None):
        super().__init__(parent)
        self._sync = sync_scroll
        self._show_lens = show_lens
        self._highlight_differences = highlight_differences
        self._external_open = external_open
        self._defile = False
        self._readers: tuple[Reader, ...] = ()
        self._difference_groups: list[tuple[frozenset[int], ...]] = []
        self._difference_index = -1

        self.views: list[ConsoleView] = []
        self.headers: list[QLabel] = []
        self._tab_labels: list[QLabel] = []
        self._paths: list[Path | None] = []

        self.tabs = QTabBar()
        self.tabs.setObjectName("ReaderTabs")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)

        self.compare = QPushButton()
        self.compare.setObjectName("IconSm")
        self.compare.setIcon(icons.icon("mdi.view-split-vertical", t.TEXT_MUTED))
        self.compare.setCheckable(True)
        self.compare.setToolTip(
            "Compare reader logs and highlight meaningful differences"
            if highlight_differences else
            "Compare every reader  (Ctrl+Shift+D)")
        self.compare.setVisible(False)
        self.compare.toggled.connect(self._on_compare_toggled)

        # Pas de bouton d'ouverture ici : il en faut UN PAR CONSOLE, pose dans
        # la barre de chaque vue a cote de son bouton de copie (voir
        # `_add_view`). Un bouton unique en tete portait sur l'onglet courant,
        # notion qui n'existe plus des qu'on compare : les deux logs sont a
        # l'ecran, et rien ne disait lequel des deux allait s'ouvrir.
        self.open_buttons: list[QPushButton] = []

        # La navigation n'a de sens que lorsque la comparaison semantique est
        # active. Elle reste donc entierement absente de la barre le reste du
        # temps, au lieu d'ajouter deux boutons inertes a l'interface.
        self.previous_difference = QPushButton()
        self.previous_difference.setObjectName("IconSm")
        self.previous_difference.setIcon(
            icons.icon("mdi.chevron-up", t.TEXT_MUTED))
        self.previous_difference.setToolTip(
            "Previous meaningful difference  (Shift+F7)")
        self.previous_difference.clicked.connect(
            lambda: self.navigate_difference(-1))

        self.difference_counter = QLabel("0 / 0")
        self.difference_counter.setObjectName("Faint")
        self.difference_counter.setAlignment(Qt.AlignCenter)
        self.difference_counter.setMinimumWidth(48)

        self.next_difference = QPushButton()
        self.next_difference.setObjectName("IconSm")
        self.next_difference.setIcon(
            icons.icon("mdi.chevron-down", t.TEXT_MUTED))
        self.next_difference.setToolTip("Next meaningful difference  (F7)")
        self.next_difference.clicked.connect(
            lambda: self.navigate_difference(1))

        self.difference_navigation = QWidget()
        navigation = QHBoxLayout(self.difference_navigation)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(t.SPACE_1)
        navigation.addWidget(self.previous_difference)
        navigation.addWidget(self.difference_counter)
        navigation.addWidget(self.next_difference)
        self.difference_navigation.setVisible(False)

        self._next_shortcut = QShortcut(QKeySequence("F7"), self)
        self._next_shortcut.activated.connect(
            lambda: self.navigate_difference(1))
        self._previous_shortcut = QShortcut(QKeySequence("Shift+F7"), self)
        self._previous_shortcut.activated.connect(
            lambda: self.navigate_difference(-1))

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.setSpacing(t.SPACE_1)
        barre.addWidget(self.tabs, 1)
        barre.addWidget(self.difference_navigation)
        barre.addWidget(self.compare)

        self.split = QSplitter(orientation)
        self.split.setChildrenCollapsible(False)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addLayout(barre)
        colonne.addWidget(self.split, 1)

        self._add_view()

    # ------------------------------------------------------------- structure

    def _add_view(self) -> ConsoleView:
        vue = ConsoleView(show_lens=self._show_lens)

        entete = QLabel()
        entete.setVisible(False)
        entete.setObjectName("Faint")

        boite = QWidget()
        col = QVBoxLayout(boite)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(t.SPACE_1)
        col.addWidget(entete)
        col.addWidget(vue, 1)

        self.views.append(vue)
        self.headers.append(entete)
        self._paths.append(None)
        self.split.addWidget(boite)

        if self._external_open:
            index = len(self.views) - 1
            vue.add_tool(self._make_open_button(index))
            vue.view.setContextMenuPolicy(Qt.CustomContextMenu)
            vue.view.customContextMenuRequested.connect(
                lambda position, i=index, v=vue.view:
                self._show_external_context_menu(i, v, position)
            )

        if self._sync:
            for sens in ("verticalScrollBar", "horizontalScrollBar"):
                getattr(vue, sens)().valueChanged.connect(
                    lambda valeur, s=sens, v=vue: self._propager(s, v, valeur))
        return vue

    def _make_open_button(self, index: int) -> QPushButton:
        """Le bouton « Open log » de la console numero `index`.

        Desactive tant que ce lecteur n'a pas de fichier a ouvrir : grise, il
        dit que ce log n'existe pas encore, la ou un bouton actif qui ne fait
        rien laisserait croire que Notepad++ a echoue.
        """
        bouton = QPushButton()
        bouton.setObjectName("IconSm")
        bouton.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        bouton.setToolTip("Open this log")
        bouton.setEnabled(False)
        bouton.clicked.connect(lambda: self._request_external_open(index))
        self.open_buttons.append(bouton)
        return bouton

    def _propager(self, sens: str, source, valeur: int) -> None:
        """Fait suivre les autres vues : cote a cote, chacune ne montre qu'une
        fraction de la largeur, et sans cela comparer deux valeurs demanderait
        de faire defiler chaque colonne separement."""
        if self._defile:
            return
        self._defile = True
        try:
            for vue in self.views:
                if vue is not source:
                    barre = getattr(vue, sens)()
                    if barre.value() != valeur:
                        barre.setValue(valeur)
        finally:
            self._defile = False

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        self._readers = tuple(readers)
        multi = len(self._readers) > 1

        while len(self.views) < max(1, len(self._readers)):
            self._add_view()

        if self._external_open:
            self._paths = [None] * len(self.views)
            self._update_external_buttons()

        self.tabs.blockSignals(True)
        for libelle in self._tab_labels:
            libelle.deleteLater()
        self._tab_labels.clear()
        while self.tabs.count():
            self.tabs.removeTab(0)
        for lecteur in (self._readers if multi else ()):
            # Le texte natif d'un onglet herite de la couleur globale du QSS.
            # Un libelle dedie permet de garder la couleur du lecteur, meme au
            # survol et dans l'onglet selectionne.
            position = self.tabs.addTab("")
            # Un point discret porte la couleur comme dans une legende : plus
            # lisible et plus moderne qu'un grand rectangle teinte.
            libelle = QLabel(f"●  {lecteur.short_name}")
            libelle.setAlignment(Qt.AlignCenter)
            libelle.setAttribute(Qt.WA_TransparentForMouseEvents)
            libelle.setProperty("readerIndex", lecteur.index)
            self.tabs.setTabButton(position, QTabBar.LeftSide, libelle)
            self._tab_labels.append(libelle)
            self.tabs.setTabToolTip(position, lecteur.name)
        self.tabs.blockSignals(False)

        for position, entete in enumerate(self.headers):
            if position < len(self._readers):
                lecteur = self._readers[position]
                entete.setText(lecteur.short_name)
                entete.setToolTip(lecteur.name)
            else:
                entete.clear()

        self.tabs.setVisible(multi)
        self.compare.setVisible(multi)
        self.difference_navigation.setVisible(
            multi and self.compare.isChecked()
            and self._highlight_differences)
        self._restyle_reader_names()
        self._apply_layout()

    def _apply_layout(self) -> None:
        nombre = max(1, len(self._readers))
        comparer = self.compare.isChecked()
        courant = max(0, self.tabs.currentIndex())

        for position, vue in enumerate(self.views):
            boite = vue.parentWidget()
            visible = position < nombre and (comparer or nombre == 1 or position == courant)
            boite.setVisible(visible)
            self.headers[position].setVisible(visible and comparer and nombre > 1)

    def _on_compare_toggled(self, checked: bool) -> None:
        self.difference_navigation.setVisible(
            checked and self._highlight_differences)
        self._apply_layout()
        self._update_difference_highlights(reveal=checked)

    def _on_tab(self, index: int) -> None:
        self._apply_layout()
        self._restyle_reader_names()
        self.reader_selected.emit(index)

    def select_silently(self, index: int) -> None:
        """Change d'onglet sans reemettre : evite que deux panneaux qui se
        suivent ne se renvoient leur choix indefiniment."""
        if 0 <= index < self.tabs.count() and index != self.tabs.currentIndex():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
            self._apply_layout()
            self._restyle_reader_names()

    def path_at(self, index: int) -> Path | None:
        if not 0 <= index < len(self._paths):
            return None
        path = self._paths[index]
        return path if path is not None and path.is_file() else None

    def _update_external_buttons(self) -> None:
        """Chaque bouton suit SON log, pas l'onglet courant.

        Cote a cote, un lecteur peut avoir son fichier quand l'autre ne l'a pas
        encore : les deux boutons doivent alors dire deux choses differentes.
        """
        for index, bouton in enumerate(self.open_buttons):
            bouton.setEnabled(self.path_at(index) is not None)

    def _request_external_open(self, index: int) -> None:
        if self.path_at(index) is not None:
            self.open_file_requested.emit(index)

    def _show_external_context_menu(self, index: int, view, position) -> None:
        menu = view.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction("Open log")
        action.setEnabled(self.path_at(index) is not None)
        action.triggered.connect(lambda: self._request_external_open(index))
        menu.exec_(view.mapToGlobal(position))

    def toggle_compare(self) -> None:
        if self.compare.isVisible():
            self.compare.setChecked(not self.compare.isChecked())

    def navigate_difference(self, direction: int) -> None:
        """Va a l'ecart suivant ou precedent, avec retour en boucle."""
        if not self.compare.isChecked() or not self._difference_groups:
            return
        courant = self._difference_index
        if courant < 0:
            courant = 0 if direction < 0 else -1
        self._show_difference((courant + direction)
                              % len(self._difference_groups))

    # ---------------------------------------------------------------- contenu

    def append(self, index: int, texte: str) -> None:
        if 0 <= index < len(self.views):
            self.views[index].append(texte)

    def set_text(self, index: int, texte: str, entete: str = "",
                 chemin: str = "") -> None:
        if 0 <= index < len(self.views):
            self.views[index].set_text(texte)
            self.headers[index].setText(entete)
            self._paths[index] = Path(chemin) if chemin else None
            # Le chemin en infobulle plutot qu'en clair : deux logs se
            # ressemblent beaucoup et savoir DUQUEL on parle est la premiere
            # chose qu'on verifie, mais l'afficher en entier mangerait la
            # largeur de la console.
            self.headers[index].setToolTip(chemin)
            self._update_external_buttons()
            self._update_difference_highlights()

    def _update_difference_highlights(self, reveal: bool = False) -> None:
        """Compare les logs et colore seulement les ecarts significatifs."""
        active = (self._highlight_differences and self.compare.isChecked()
                  and len(self._readers) > 1)
        if not active:
            self._difference_groups.clear()
            self._difference_index = -1
            self._refresh_difference_navigation()
            for view in self.views:
                view.highlight_lines()
            return

        count = len(self._readers)
        texts = [self.views[index].text() for index in range(count)]
        ignored = [reader.name for reader in self._readers]
        ignored.extend(reader.short_name for reader in self._readers)
        differences = log_compare.compare_logs(texts, ignored)
        self._build_difference_groups(differences)

        for index, view in enumerate(self.views):
            if index < count:
                view.highlight_lines(differences.changed[index],
                                     differences.errors[index])
            else:
                view.highlight_lines()

        if reveal and self._difference_groups:
            # A l'ouverture, une erreur explicite est plus utile que le tout
            # premier ecart. La navigation conserve ensuite l'ordre du log.
            priority = next((position for position, groups in
                             enumerate(self._difference_groups)
                             if any(group & errors for group, errors in
                                    zip(groups, differences.errors))), 0)
            self._show_difference(priority)

    @staticmethod
    def _contiguous_groups(indices: frozenset[int]) -> list[frozenset[int]]:
        """Regroupe des lignes voisines en une seule difference navigable."""
        groups: list[set[int]] = []
        for index in sorted(indices):
            if not groups or index > max(groups[-1]) + 1:
                groups.append({index})
            else:
                groups[-1].add(index)
        return [frozenset(group) for group in groups]

    def _build_difference_groups(self, differences) -> None:
        """Aligne les blocs differents de chaque lecteur par leur ordre."""
        by_reader = [self._contiguous_groups(indices)
                     for indices in differences.changed]
        count = max((len(groups) for groups in by_reader), default=0)
        self._difference_groups = [
            tuple(groups[position] if position < len(groups) else frozenset()
                  for groups in by_reader)
            for position in range(count)
        ]
        if self._difference_index >= count:
            self._difference_index = count - 1
        self._refresh_difference_navigation()

    def _show_difference(self, position: int) -> None:
        """Centre chaque console sur son bloc correspondant."""
        if not 0 <= position < len(self._difference_groups):
            return
        self._difference_index = position
        self._defile = True
        try:
            for view, group in zip(self.views, self._difference_groups[position]):
                if group:
                    view.reveal_line(min(group))
        finally:
            self._defile = False
        self._refresh_difference_navigation()

    def _refresh_difference_navigation(self) -> None:
        count = len(self._difference_groups)
        enabled = count > 0
        self.previous_difference.setEnabled(enabled)
        self.next_difference.setEnabled(enabled)
        shown = self._difference_index + 1 if enabled else 0
        self.difference_counter.setText(f"{shown} / {count}")

    def _restyle_reader_names(self) -> None:
        courant = self.tabs.currentIndex()
        for position, (lecteur, libelle) in enumerate(
                zip(self._readers, self._tab_labels)):
            couleur = t.reader_color(lecteur.index)
            libelle.setStyleSheet(
                f"color: {couleur}; background: transparent;"
                f"font-size: {t.TEXT_XS}px;"
                f"font-weight: {700 if position == courant else 600};"
                f"padding: 0 {t.SPACE_1}px;")

        for position, entete in enumerate(self.headers):
            if position >= len(self._readers):
                entete.setStyleSheet("")
                continue
            couleur = t.reader_color(self._readers[position].index)
            entete.setStyleSheet(
                f"color: {couleur};"
                f"background-color: {t.rgba(couleur, 0.07)};"
                f"border: none; border-left: 3px solid {couleur};"
                f"border-radius: {t.RADIUS_SM}px;"
                f"font-size: {t.TEXT_XS}px; font-weight: 600;"
                f"padding: {t.SPACE_1}px {t.SPACE_2}px;")

    def restyle(self) -> None:
        for vue in self.views:
            vue.restyle()
        self.compare.setIcon(icons.icon("mdi.view-split-vertical", t.TEXT_MUTED))
        for bouton in self.open_buttons:
            bouton.setIcon(icons.icon("mdi.open-in-new", t.TEXT_MUTED))
        self.previous_difference.setIcon(
            icons.icon("mdi.chevron-up", t.TEXT_MUTED))
        self.next_difference.setIcon(
            icons.icon("mdi.chevron-down", t.TEXT_MUTED))
        self._restyle_reader_names()
        self._update_difference_highlights()

    def clear(self) -> None:
        for vue in self.views:
            vue.clear()
        if self._external_open:
            self._paths = [None] * len(self.views)
            self._update_external_buttons()
        # Le contenu disparait, pas l'identite des colonnes. En comparaison,
        # un en-tete vide au debut d'un run rendrait les consoles impossibles
        # a attribuer jusqu'au premier rapport complet.
        for position, entete in enumerate(self.headers):
            if position < len(self._readers):
                lecteur = self._readers[position]
                entete.setText(lecteur.short_name)
                entete.setToolTip(lecteur.name)
            else:
                entete.clear()
        self._update_difference_highlights()


class ResultsPanel(QWidget):
    """Fiche du test, sortie brute et logs, derriere un etat vide au demarrage."""

    reader_selected = pyqtSignal(int)
    test_chosen = pyqtSignal(str)   # relaye la fiche de groupe vers l'arbre

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_root: Path | None = None
        self._readers: tuple[Reader, ...] = ()
        self._sorties: dict[int, str] = {}
        self._index_echecs: dict[tuple[int, str], dict] = {}
        self._phase_reports: dict[int, dict[str, PhaseReport]] = {}
        self._live_phase_statuses: dict[str, dict[int, dict[str, Status]]] = {}
        # phase_id -> (nom de la campagne, nom du scenario). Un identifiant de
        # phase (`campaign_index:phase_index`) ne veut rien dire pour un YAML
        # de campagne, qui ne connait que des NOMS -- c'est par eux que
        # `campaign_results()` retrouve les resultats d'une phase en cours.
        self._live_phase_names: dict[str, tuple[str, str]] = {}
        self._phase_id = ""
        self._nodeid = ""
        self._statuses: dict[int, Status] = {}
        # La campagne actuellement affichee dans Detail, ou None si on regarde
        # autre chose (un test, un dossier ordinaire, rien). Sert a rejouer
        # ses resultats en direct pendant un run, sans rebatir toute la fiche.
        self._group_campaign = None
        self._campaign_refresh = QTimer(self)
        self._campaign_refresh.setSingleShot(True)
        # Coalesce les resultats rapproches : un test par test sur une
        # campagne de 171 tests reconstruirait les cartes 171 fois pour un
        # affichage qui n'a besoin de suivre qu'a l'oeil.
        self._campaign_refresh.setInterval(250)
        self._campaign_refresh.timeout.connect(self._refresh_campaign_group)

        self.detail = DetailPanel()
        self.detail.open_output.connect(self.show_output)
        self.detail.test_chosen.connect(self.test_chosen)

        self.source = SourcePanel()

        self.output = ReaderViews(Qt.Vertical)
        self.logs = ReaderViews(
            Qt.Horizontal, sync_scroll=True, show_lens=False,
            highlight_differences=True, external_open=True)
        self.logs.open_file_requested.connect(self._open_log_in_notepad_plus_plus)

        # Les trois panneaux suivent le meme lecteur : lire le log de l'un en
        # regardant la sortie de l'autre n'a pas de sens.
        self.output.reader_selected.connect(self._on_reader, Qt.UniqueConnection)
        self.logs.reader_selected.connect(self._on_reader, Qt.UniqueConnection)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setObjectName("PrimaryTabs")
        self.tabs.addTab(self.detail,
                         icons.icon("mdi.text-box-search-outline", t.TEXT_MUTED),
                         "Detail")
        self.tabs.addTab(self.source,
                         icons.icon("mdi.file-code-outline", t.TEXT_MUTED),
                         "Source")
        self.tabs.addTab(self.output, icons.icon("mdi.console", t.TEXT_MUTED),
                         "Output")
        self.tabs.addTab(self.logs,
                         icons.icon("mdi.file-document-outline", t.TEXT_MUTED),
                         "Logs")
        self.tabs.setTabToolTip(ONGLET_DETAIL,
                                "What happened to the selected test  (Ctrl+1)")
        self.tabs.setTabToolTip(ONGLET_SOURCE,
                                "The file of the selected test, editable  (Ctrl+2)")
        self.tabs.setTabToolTip(ONGLET_OUTPUT, "Everything pytest wrote  (Ctrl+3)")
        self.tabs.setTabToolTip(ONGLET_LOGS,
                                "The .log files of the selected test  (Ctrl+4)")

        self.phase_label = QLabel("Configuration")
        self.phase_label.setObjectName("Faint")
        self.phase_tabs = QTabBar()
        self.phase_tabs.setObjectName("CampaignTabs")
        self.phase_tabs.setDrawBase(False)
        self.phase_tabs.setExpanding(False)
        self.phase_tabs.setUsesScrollButtons(True)
        self.phase_tabs.currentChanged.connect(self._on_phase)

        self.phase_bar = QWidget()
        phases = QHBoxLayout(self.phase_bar)
        phases.setContentsMargins(t.SPACE_2, 0, t.SPACE_2, 0)
        phases.setSpacing(t.SPACE_2)
        phases.addWidget(self.phase_label)
        phases.addWidget(self.phase_tabs, 1)
        self.phase_bar.setVisible(False)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addWidget(self.phase_bar)
        colonne.addWidget(self.tabs)

    # ------------------------------------------------------------- navigation

    def restyle(self) -> None:
        """Fait redescendre le changement de theme dans tout le panneau."""
        for vues in (self.output, self.logs):
            vues.restyle()
        self.source.restyle()
        for position, glyphe in (
                (ONGLET_DETAIL, "mdi.text-box-search-outline"),
                (ONGLET_SOURCE, "mdi.file-code-outline"),
                (ONGLET_OUTPUT, "mdi.console"),
                (ONGLET_LOGS, "mdi.file-document-outline")):
            self.tabs.setTabIcon(position, icons.icon(glyphe, t.TEXT_MUTED))

    def show_tab(self, position: int) -> None:
        self.tabs.setCurrentIndex(position)

    def show_output(self) -> None:
        self.show_tab(ONGLET_OUTPUT)

    def _on_reader(self, index: int) -> None:
        self.output.select_silently(index)
        self.logs.select_silently(index)
        self.reader_selected.emit(index)

    # ------------------------------------------------------------------- run

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        """Nouvelle collecte : les lecteurs changent, la selection ne vaut plus."""
        self._readers = tuple(readers)
        self._nodeid = ""
        self._statuses = {}
        self._sorties.clear()
        self._index_echecs.clear()
        self._phase_reports.clear()
        self._live_phase_statuses.clear()
        self._live_phase_names.clear()
        self._phase_id = ""
        self._group_campaign = None
        self._campaign_refresh.stop()
        self.phase_bar.setVisible(False)
        self.detail.clear()
        self.source.save()
        self.source.clear()
        self.output.set_readers(readers)
        self.logs.set_readers(readers)

    def begin_run(self, request: RunRequest | None = None) -> None:
        """Vide les vues sans changer d'onglet.

        Basculer d'office sur la console au lancement volait l'ecran a
        l'utilisateur : l'avancement se lit dans l'arbre et dans la barre
        d'etat, la console n'a pas a s'imposer.
        """
        self.output.clear()
        self.logs.clear()
        self._sorties.clear()
        self._index_echecs.clear()
        self._phase_reports.clear()
        self._live_phase_statuses.clear()
        self._live_phase_names.clear()
        self._phase_id = ""
        self.phase_tabs.blockSignals(True)
        while self.phase_tabs.count():
            self.phase_tabs.removeTab(0)
        self.phase_tabs.addTab("All")
        if request is not None:
            for campagne in request.campaigns:
                for phase in campagne.phases:
                    position = self.phase_tabs.addTab(phase.name)
                    self.phase_tabs.setTabData(position, phase.id)
                    self.phase_tabs.setTabToolTip(
                        position, f"{campagne.name} · {phase.name}")
        self.phase_tabs.setCurrentIndex(0)
        self.phase_tabs.blockSignals(False)
        self.phase_bar.setVisible(self.phase_tabs.count() > 1)
        self._refresh_detail()
        # L'etat de campagne vient d'etre efface au-dessus : sans ce rejeu
        # immediat, la fiche garderait les verdicts du run PRECEDENT affiches
        # jusqu'au tout premier resultat du nouveau.
        self._refresh_campaign_group()

    def set_report(self, rapport: ReaderReport) -> None:
        """Range la sortie complete d'un lecteur qui vient de finir.

        Les traces d'echec ne sont extraites qu'a la demande : sur un run de
        plusieurs milliers de lignes, les decouper a chaque fin de lecteur
        couterait pour rien si personne ne clique.
        """
        index = rapport.reader.index
        self._sorties[index] = rapport.output
        self._phase_reports[index] = {phase.id: phase for phase in rapport.phases}
        for cle in [cle for cle in self._index_echecs if cle[0] == index]:
            self._index_echecs.pop(cle, None)
        self._apply_phase_content()
        self._refresh_detail()
        # Immediat et non coalesce : ceci n'arrive qu'une fois par lecteur, pas
        # une fois par test -- rien a gagner a attendre.
        self._refresh_campaign_group()

    def append_output(self, index: int, texte: str) -> None:
        self.output.append(index, texte)

    # ---------------------------------------------------------------- detail

    def show_test(self, nodeid: str, statuses: dict[int, Status],
                  workspace: str = "") -> None:
        """Selectionne un test : sa fiche, sa source, et ses logs."""
        self._nodeid = nodeid
        self._statuses = dict(statuses)
        self._group_campaign = None
        self._refresh_detail()
        self.source.show_file(source_path(workspace, nodeid), nodeid)
        self.show_logs_for(nodeid, self._readers)

    def show_group(self, path: str, name: str, readers, counts: dict,
                   failures: list, source: Path | None = None,
                   jump_nodeid: str = "", campaign=None) -> None:
        """Selectionne un regroupement : son bilan, et sa source s'il en a une.

        Un module a un fichier, un dossier n'en a pas. Laisser celui du test
        precedent quand il n'y en a pas ferait croire qu'il parle de ce qu'on
        vient de cliquer ; le refuser a un module priverait du geste le plus
        courant, cliquer un `.py` pour le lire.

        `campaign` prend le pas sur `source` : la ligne qui porte le badge
        Campaign n'a le plus souvent PAS de fichier .py propre (c'est un
        dossier), et meme quand elle en a un, ce qu'on cherche en cliquant
        cette ligne precise est le YAML qui la gouverne, pas un .py parmi
        d'autres. Detail montre sa structure (les configurations), Source son
        texte -- deux lectures d'une meme chose, pas la meme.

        Les logs, eux, restent vides : ils sont ecrits PAR TEST, et il n'y en
        a aucun qui reponde pour un lot entier.
        """
        self._nodeid = ""
        self._statuses = {}
        self._group_campaign = campaign
        resultats, setup_ok = self.campaign_results(campaign) \
            if campaign is not None else (None, None)
        self.detail.show_group(path, name, tuple(readers), counts, failures,
                               campaign, resultats, setup_ok)
        if campaign is not None:
            self.source.show_file(Path(campaign.path))
        else:
            self.source.show_file(source, jump_nodeid)
        self.logs.clear()

    def campaign_results(self, campaign) -> tuple[dict, dict]:
        """Statut de chaque test de cette campagne, par configuration puis lecteur.

        Cherche par NOM de campagne et de configuration, pas par
        `phase.id` : cet identifiant technique (`campaign_index:phase_index`)
        depend de l'ordre de decouverte du run courant, alors que le YAML ne
        connait que des noms. Une phase deja terminee vit dans
        `_phase_reports` ; une phase encore en cours n'existe que dans
        `_live_phase_statuses`, repere via `_live_phase_names`.

        Rend `(resultats, setup_ok)`. `setup_ok[nom]` vaut le VRAI
        `PhaseReport.setup_ok` (le pire de tous les lecteurs qui ont fini
        cette configuration) une fois qu'au moins un a fini, sinon `None` --
        rien ne permet encore de savoir. L'appelant retombe alors sur les
        seuls statuts de test pour deviner en attendant.
        """
        resultat: dict[str, dict[str, dict[int, Status]]] = {}
        setup_ok: dict[str, bool | None] = {}
        for scenario in campaign.scenarios:
            par_test: dict[str, dict[int, Status]] = {}
            connu: bool | None = None

            for lecteur_index, phases in self._phase_reports.items():
                for phase in phases.values():
                    if phase.campaign == campaign.name and phase.name == scenario.name:
                        for nodeid, statut in phase.statuses.items():
                            par_test.setdefault(nodeid, {})[lecteur_index] = statut
                        connu = phase.setup_ok if connu is None else (connu and phase.setup_ok)

            for phase_id, (nom_campagne, nom_scenario) in self._live_phase_names.items():
                if nom_campagne != campaign.name or nom_scenario != scenario.name:
                    continue
                for lecteur_index, statuts in self._live_phase_statuses.get(
                        phase_id, {}).items():
                    for nodeid, statut in statuts.items():
                        # Une phase deja dans `_phase_reports` est definitive ;
                        # ne pas ecraser son verdict par un residu en direct.
                        par_test.setdefault(nodeid, {}).setdefault(lecteur_index, statut)

            resultat[scenario.name] = par_test
            setup_ok[scenario.name] = connu
        return resultat, setup_ok

    def update_statuses(self, nodeid: str, statuses: dict[int, Status],
                        outcome: Outcome | None = None) -> None:
        """Rafraichit la fiche si elle porte sur ce test, sans toucher aux logs.

        Appele a chaque resultat pendant un run : relire les .log a ce
        rythme-la balayerait le disque des centaines de fois.
        """
        if outcome is not None and outcome.phase_id:
            self._live_phase_statuses.setdefault(outcome.phase_id, {}) \
                .setdefault(outcome.reader_index, {})[nodeid] = outcome.status
            self._live_phase_names[outcome.phase_id] = (
                outcome.campaign, outcome.phase_name)
        if nodeid and nodeid == self._nodeid:
            self._statuses = dict(statuses)
            self._refresh_detail()
        elif self._group_campaign is not None:
            self._campaign_refresh.start()

    def _refresh_campaign_group(self) -> None:
        """Rejoue les resultats de la campagne actuellement affichee.

        Ne touche qu'aux cartes de resultats -- pas au chemin, aux rubans
        (masques pour une campagne) ni a Source : les rouvrir a chaque
        resultat recu rechargerait le YAML depuis le disque en boucle pendant
        un run, et interromprait qui serait en train de l'editer.
        """
        if self._group_campaign is None:
            return
        resultats, setup_ok = self.campaign_results(self._group_campaign)
        self.detail.refresh_campaign_results(resultats, setup_ok)

    def _refresh_detail(self) -> None:
        if not self._nodeid:
            # Rien a faire : soit aucune fiche n'est ouverte, soit un
            # regroupement l'est, et lui n'a pas besoin de la fiche de TEST.
            # Un `clear()` ici effacerait un regroupement pourtant toujours
            # selectionne dans l'arbre -- exactement quand un lecteur finit
            # ou qu'un nouveau run demarre pendant qu'on le regarde.
            return
        statuses = self._statuses_for_phase(self._nodeid)
        cibles = self._readers or (Reader("", 0),)
        echecs = {
            lecteur.index: failures_mod.failure_for(
                self._echecs_de(lecteur.index), self._nodeid)
            for lecteur in cibles
        }
        self.detail.show_test(self._nodeid, self._readers, statuses, echecs)

    def _statuses_for_phase(self, nodeid: str) -> dict[int, Status]:
        if not self._phase_id:
            return dict(self._statuses)
        resultat: dict[int, Status] = {}
        for lecteur in self._readers or (Reader("", 0),):
            phase = self._phase_reports.get(lecteur.index, {}).get(self._phase_id)
            if phase is not None:
                resultat[lecteur.index] = phase.statuses.get(nodeid, Status.PENDING)
            else:
                resultat[lecteur.index] = self._live_phase_statuses \
                    .get(self._phase_id, {}).get(lecteur.index, {}) \
                    .get(nodeid, Status.PENDING)
        return resultat

    def _echecs_de(self, reader_index: int) -> dict:
        cle = (reader_index, self._phase_id)
        index = self._index_echecs.get(cle)
        if index is None:
            sortie = self._sorties.get(reader_index, "")
            if self._phase_id:
                phase = self._phase_reports.get(reader_index, {}).get(self._phase_id)
                sortie = phase.output if phase is not None else ""
            index = failures_mod.index_failures(sortie)
            self._index_echecs[cle] = index
        return index

    def _on_phase(self, index: int) -> None:
        self._phase_id = str(self.phase_tabs.tabData(index) or "")
        self._apply_phase_content()
        self._refresh_detail()
        if self._nodeid:
            self.show_logs_for(self._nodeid, self._readers)

    def _apply_phase_content(self) -> None:
        for lecteur in self._readers or (Reader("", 0),):
            texte = self._sorties.get(lecteur.index, "")
            entete = lecteur.name
            if self._phase_id:
                phase = self._phase_reports.get(lecteur.index, {}).get(self._phase_id)
                texte = phase.output if phase is not None else "Configuration still running…"
                if phase is not None:
                    entete = f"{lecteur.name} · {phase.name}".strip(" ·")
            self.output.set_text(lecteur.index, texte, entete)

    # ------------------------------------------------------------------ logs

    def set_log_root(self, racine: Path | None) -> None:
        self._log_root = racine

    def show_logs_for(self, nodeid: str, readers: tuple[Reader, ...]) -> None:
        """Charge le .log de ce test, un par lecteur."""
        if not nodeid or self._log_root is None:
            return

        cibles = readers or (Reader("", 0),)
        for lecteur in cibles:
            if self._phase_id:
                phase = self._phase_reports.get(lecteur.index, {}).get(self._phase_id)
                if phase is not None:
                    if nodeid in phase.logs:
                        contenu = phase.logs[nodeid]
                        chemin = phase.log_paths.get(nodeid, "")
                    else:
                        contenu = (
                            f"No log was produced for this test during "
                            f"{phase.name}.\n\nThe logs from another configuration "
                            "are intentionally not reused.")
                        chemin = ""
                    self.logs.set_text(
                        lecteur.index, contenu,
                        f"{lecteur.name or 'Run'} · {phase.name}", chemin)
                    continue
            chemin = logs.find_test_log(self._log_root, nodeid, lecteur.name)
            if chemin is None:
                self.logs.set_text(lecteur.index,
                                   self._rien_trouve(lecteur),
                                   lecteur.name or "")
                continue
            try:
                contenu = chemin.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                contenu = f"Could not read {chemin}:\n{exc}"
            # Le chemin en tete : deux logs se ressemblent beaucoup, et savoir
            # DUQUEL on parle est la premiere chose qu'on veut verifier.
            self.logs.set_text(lecteur.index, contenu,
                               lecteur.name or chemin.name, str(chemin))

    def refresh_logs(self) -> None:
        """Recharge les logs du test encore selectionne apres un run."""
        if self._nodeid:
            self.show_logs_for(self._nodeid, self._readers)

    def _open_log_in_notepad_plus_plus(self, reader_index: int) -> None:
        path = self.logs.path_at(reader_index)
        if path is not None:
            open_in_notepad_plus_plus(self, path)

    def _rien_trouve(self, lecteur: Reader) -> str:
        """Dire ou l'on a cherche, et pas seulement qu'on n'a rien trouve.

        « No log found » tout seul se lit comme une panne de l'outil. La liste
        des dossiers examines montre au contraire tout de suite si le dossier
        est vide, si le run n'a rien ecrit, ou si le reglage du chemin des logs
        ne pointe pas la ou l'on croyait.
        """
        ou = logs.places_searched(self._log_root)
        lignes = ["No log found for this test"
                  + (f" on {lecteur.name}." if lecteur.name else ".")]

        if not ou:
            lignes += ["", f"The log folder does not exist yet:",
                       f"    {self._log_root}", "",
                       "It is created by the workspace conftest on the first "
                       "run. Check the log path setting if the run did write "
                       "somewhere else."]
        else:
            lignes += ["", "Looked in, most recent first:"]
            lignes += [f"    {chemin}" for chemin in ou]
        return "\n".join(lignes)
