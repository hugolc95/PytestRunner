"""Ce qu'on sait de ce qui est pointe dans l'arbre. Deux fiches, deux questions.

Sur un TEST : « celui-la, qu'est-ce qui s'est passe ? ». La console contient
la reponse, mais melangee a des centaines de lignes de verdicts que l'arbre
affiche deja, et sans lien visible avec le test qu'on vient de cliquer. Ici le
lien est explicite : un test selectionne, une trace par lecteur qui a echoue,
et rien d'autre.

Sur un REGROUPEMENT -- dossier, fichier, test parametre : « ce lot, ca donne
quoi ? ». Une barre par lecteur pour la proportion, les compteurs pour les
nombres, et la liste de ce qui est rouge dedans. Un regroupement n'etait lie a
rien : la fiche gardait le test precedent a l'ecran, et l'on croyait lire le
dossier qu'on venait de cliquer.
"""

from __future__ import annotations

from html import escape

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner.domain.ansi import strip_ansi
from runner.domain.campaign import CampaignDefinition
from runner.domain.failures import Failure, classify_line
from runner.domain.models import Reader, Status
from runner.ui import theme
from runner.ui import tokens as t
from runner.ui.campaign_results import CampaignResultsView
from runner.ui.widgets import (
    EmptyState,
    ReaderBadge,
    ReaderResult,
    StatusRibbon,
)

# Nature de ligne -> teinte. La table vit ici et pas dans le domaine : c'est
# une decision de theme, elle change avec la palette, pas avec pytest.
# Calculee A CHAQUE APPEL : figee au niveau du module, elle aurait garde les
# couleurs du theme charge a l'import.
def _teinte(nature: str) -> str:
    table = {
        "exception": t.status_color(Status.FAILED),
        "code": t.TEXT,
        "frame": t.ACCENT,
        "section": t.TEXT_FAINT,
        "text": t.TEXT_MUTED,
    }
    return table.get(nature, t.TEXT_MUTED)


class DetailPanel(QWidget):
    """Ce qu'on sait de ce qui est pointe dans l'arbre.

    Deux fiches, parce qu'on ne pose pas la meme question selon ou l'on
    clique. Sur un test : « celui-la, qu'est-ce qui s'est passe ? ». Sur un
    dossier ou un fichier : « ce lot, ca donne quoi, et qu'est-ce qui est
    rouge dedans ? ».
    """

    open_output = pyqtSignal()
    test_chosen = pyqtSignal(str)   # un echec clique dans la fiche de groupe

    PAGE_VIDE, PAGE_TEST, PAGE_GROUPE = 0, 1, 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodeid = ""
        self._texte_brut = ""
        # Ce qu'il faut pour refaire le rendu a l'identique : le HTML de la
        # trace porte des couleurs resolues au moment ou il a ete construit, et
        # ne suit donc pas un changement de theme.
        self._dernier: tuple | None = None
        self._dernier_groupe: tuple | None = None

        self.empty = EmptyState(
            "mdi.cursor-default-click-outline",
            "Nothing selected",
            "Click a test to see its verdict on every reader — or a folder to "
            "see how the whole thing is doing.",
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self._build_content())
        self.stack.addWidget(self._build_group())

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self.stack)

    # ------------------------------------------------------------- structure

    def _build_content(self) -> QWidget:
        contenu = QWidget()
        colonne = QVBoxLayout(contenu)
        # Un peu d'air sous les onglets : colle a la barre, le chemin se lisait
        # comme un quatrieme onglet.
        colonne.setContentsMargins(0, t.SPACE_2, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        # Le chemin au-dessus, en petit : il situe, il ne se lit pas. Le nom du
        # test en dessous, en grand : c'est lui qu'on cherchait.
        self.path_label = QLabel()
        self.path_label.setObjectName("Faint")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.name_label.setObjectName("Title")

        colonne.addWidget(self.path_label)
        colonne.addWidget(self.name_label)

        self.results_row = QWidget()
        self._results_layout = QHBoxLayout(self.results_row)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(t.SPACE_4)
        colonne.addWidget(self.results_row)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setLineWrapMode(QTextEdit.NoWrap)
        colonne.addWidget(self.body, 1)

        actions = QHBoxLayout()
        actions.setSpacing(t.SPACE_2)
        actions.addStretch(1)

        self.copy_button = QPushButton("Copy traceback")
        self.copy_button.setObjectName("Ghost")
        self.copy_button.clicked.connect(self._copier)

        self.output_button = QPushButton("Open the raw output")
        self.output_button.setObjectName("Ghost")
        self.output_button.clicked.connect(self.open_output)

        actions.addWidget(self.copy_button)
        actions.addWidget(self.output_button)
        colonne.addLayout(actions)
        return contenu

    # --------------------------------------------------- fiche de regroupement

    def _build_group(self) -> QWidget:
        contenu = QWidget()
        colonne = QVBoxLayout(contenu)
        colonne.setContentsMargins(0, t.SPACE_2, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        self.group_path = QLabel()
        self.group_path.setObjectName("Faint")
        self.group_name = QLabel()
        self.group_name.setObjectName("Title")
        self.group_name.setWordWrap(True)
        self.group_total = QLabel()
        self.group_total.setObjectName("Muted")

        colonne.addWidget(self.group_path)
        colonne.addWidget(self.group_name)
        colonne.addWidget(self.group_total)

        # Le resultat de CHAQUE test, par configuration -- pas le bilan agrege
        # que les rubans donnent aux regroupements ordinaires. Un meme test
        # peut tourner plusieurs fois avec des verdicts differents ; les
        # rubans les auraient fondus en un seul (le pire), ce qui est
        # justement ce qu'on cherche a eviter ici. Les deux widgets ne
        # coexistent donc jamais : voir `_remplir_campagne`.
        #
        # Dans un defilement : une vraie campagne compte facilement 5 a 10
        # configurations, chacune pouvant couvrir plus de cent tests des que
        # `tests:` designe un dossier entier. Sans lui, tout depasserait la
        # fenetre sans aucun moyen d'atteindre le reste.
        self.campaign_results_view = CampaignResultsView()
        self._campaign_scroll = QScrollArea()
        self._campaign_scroll.setObjectName("Plain")
        self._campaign_scroll.setWidgetResizable(True)
        self._campaign_scroll.setFrameShape(QFrame.NoFrame)
        self._campaign_scroll.setWidget(self.campaign_results_view)
        colonne.addWidget(self._campaign_scroll, 1)

        # Une barre par lecteur, empilees : c'est en les superposant qu'on voit
        # que l'un est plus rouge que l'autre.
        self.ribbons_host = QWidget()
        self._ribbons = QVBoxLayout(self.ribbons_host)
        self._ribbons.setContentsMargins(0, t.SPACE_2, 0, t.SPACE_2)
        self._ribbons.setSpacing(t.SPACE_3)
        colonne.addWidget(self.ribbons_host)

        self.failures_title = QLabel()
        self.failures_title.setObjectName("Muted")
        colonne.addWidget(self.failures_title)

        self.failures = QListWidget()
        self.failures.setObjectName("Failures")
        self.failures.itemActivated.connect(self._sur_echec)
        self.failures.itemClicked.connect(self._sur_echec)
        colonne.addWidget(self.failures, 1)
        return contenu

    def show_group(self, path: str, name: str, readers: tuple[Reader, ...],
                   counts: dict, failures: list,
                   campaign: CampaignDefinition | None = None,
                   campaign_results: dict | None = None,
                   campaign_setup: dict | None = None) -> None:
        """Fiche d'un dossier, d'un fichier ou d'un test parametre.

        `counts` donne, par index de lecteur, le nombre de tests par statut.
        `failures` liste des couples (nodeid, index du lecteur). `campaign`
        n'est pas None que sur la ligne qui porte le badge -- c'est elle qui
        represente la campagne entiere, pas l'un de ses descendants.
        `campaign_results` : nom du scenario -> nodeid -> index de lecteur ->
        statut, pour montrer le resultat de CHAQUE execution plutot que
        l'agregat que les rubans donneraient. `campaign_setup` : nom du
        scenario -> son `PhaseReport.setup_ok`, ou None tant qu'aucun lecteur
        n'a fini cette configuration.
        """
        self._dernier_groupe = (path, name, readers, counts, failures,
                                campaign, campaign_results, campaign_setup)
        self._nodeid = ""
        self.stack.setCurrentIndex(self.PAGE_GROUPE)

        self.group_path.setText(path)
        # La racine n'a pas d'ancetre : l'etiquette vide prendrait quand meme
        # sa hauteur et decalerait le titre sans rien dire.
        self.group_path.setVisible(bool(path))
        self.group_name.setText(name)

        total = sum(sum(c.values()) for c in counts.values()) or 0
        tests = total // max(1, len(readers) or 1)
        self.group_total.setText(f"{tests} test{'s' if tests > 1 else ''}"
                                 + (f" × {len(readers)} readers" if len(readers) > 1
                                    else ""))
        self._remplir_campagne(campaign, campaign_results or {},
                               campaign_setup or {}, readers)
        self._remplir_rubans(readers, counts)
        self._remplir_echecs(readers, failures)

    def _remplir_campagne(self, campaign: CampaignDefinition | None,
                          resultats: dict, setup_ok: dict,
                          readers: tuple[Reader, ...]) -> None:
        self._campaign_scroll.setVisible(campaign is not None)
        # Les deux vues repondent a la meme question -- « qu'est-ce qui s'est
        # passe ? » -- et se contrediraient affichees ensemble : les rubans
        # fondent plusieurs executions du meme test en un seul statut, ce que
        # la vue Campaign detaille justement.
        self.ribbons_host.setVisible(campaign is None)
        self.failures_title.setVisible(campaign is None)
        self.failures.setVisible(campaign is None)
        self.campaign_results_view.set_data(campaign, resultats, readers, setup_ok)

    def refresh_campaign_results(self, resultats: dict, setup_ok: dict) -> None:
        """Rejoue les cartes de campagne avec des resultats plus recents.

        Appele en direct pendant un run : ne touche qu'aux cartes, pas au
        chemin, au nom ni aux rubans -- ils n'ont pas change et les refaire a
        chaque resultat recu serait du travail perdu. Sans effet si Detail
        montre autre chose que la campagne : naviguer ailleurs pendant le run
        ne doit pas faire revenir la fiche en arriere.
        """
        if self.stack.currentIndex() != self.PAGE_GROUPE or self._dernier_groupe is None:
            return
        path, name, readers, counts, failures, campaign, _, _ = self._dernier_groupe
        if campaign is None:
            return
        self._dernier_groupe = (path, name, readers, counts, failures,
                                campaign, resultats, setup_ok)
        self.campaign_results_view.set_data(campaign, resultats, readers, setup_ok)

    def _remplir_rubans(self, readers, counts: dict) -> None:
        while self._ribbons.count():
            element = self._ribbons.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()

        for lecteur in readers or (Reader("", 0),):
            propres = counts.get(lecteur.index, {})
            bloc = QWidget()
            ligne = QVBoxLayout(bloc)
            ligne.setContentsMargins(0, 0, 0, 0)
            ligne.setSpacing(t.SPACE_1)

            entete = QHBoxLayout()
            entete.setContentsMargins(0, 0, 0, 0)
            if lecteur.name:
                entete.addWidget(ReaderBadge(lecteur.short_name, lecteur.index))
            entete.addStretch(1)
            entete.addWidget(self._chiffres(propres))
            ligne.addLayout(entete)

            ruban = StatusRibbon()
            ruban.set_counts(propres)
            ligne.addWidget(ruban)
            self._ribbons.addWidget(bloc)

    def _chiffres(self, propres: dict) -> QLabel:
        """Les compteurs en clair, a cote de la barre.

        La barre donne la proportion, pas le nombre : « presque tout vert »
        peut cacher deux echecs comme vingt.
        """
        morceaux = []
        for statut in StatusRibbon.ORDRE:
            nombre = propres.get(statut, 0)
            if not nombre:
                continue
            morceaux.append(
                f'<span style="color:{t.status_color(statut)}">{nombre}</span>'
                f' <span style="color:{t.TEXT_FAINT}">{statut.name.lower()}</span>')

        etiquette = QLabel(" &nbsp; ".join(morceaux) or
                           f'<span style="color:{t.TEXT_FAINT}">not run yet</span>')
        etiquette.setTextFormat(Qt.RichText)
        etiquette.setStyleSheet(
            f"font-size: {t.TEXT_SM}px; background: transparent;")
        return etiquette

    def _remplir_echecs(self, readers, failures: list) -> None:
        self.failures.clear()
        noms = {r.index: r.short_name for r in readers}

        if not failures:
            # Rien de rouge : le dire franchement plutot que de laisser une
            # zone vide, qu'on prend pour un affichage qui n'a pas fini.
            self.failures_title.setText("")
            vide = QListWidgetItem("Nothing is failing in here.")
            vide.setFlags(Qt.NoItemFlags)
            self.failures.addItem(vide)
            return

        # Une ligne par TEST, et les lecteurs a cote. Une ligne par couple
        # test-lecteur affichait deux fois le meme nom des qu'un test tombait
        # sur les deux, alors que ce qu'on cherche est la liste de ce qui est
        # casse -- pas le detail des combinaisons.
        par_test: dict[str, list[int]] = {}
        for nodeid, index_lecteur in failures:
            par_test.setdefault(nodeid, []).append(index_lecteur)

        combien = len(par_test)
        self.failures_title.setText(
            f"Failing ({combien} test{'s' if combien > 1 else ''})")

        for nodeid, lecteurs in par_test.items():
            court = nodeid.split("::", 1)[-1].replace("::", " › ")
            suffixe = ""
            if len(readers) > 1:
                suffixe = "   —   " + ", ".join(noms[i] for i in lecteurs)
            item = QListWidgetItem(court + suffixe)
            item.setToolTip(nodeid)
            item.setData(Qt.UserRole, nodeid)
            item.setForeground(QColor(t.status_color(Status.FAILED)))
            self.failures.addItem(item)

    def _sur_echec(self, item) -> None:
        """Cliquer un echec y emmene : c'est le geste suivant, une fois sur
        deux, apres avoir vu la liste."""
        nodeid = item.data(Qt.UserRole)
        if nodeid:
            self.test_chosen.emit(nodeid)

    # ---------------------------------------------------------------- contenu

    def clear(self) -> None:
        self._nodeid = ""
        self._texte_brut = ""
        self._dernier = None
        self._dernier_groupe = None
        self.stack.setCurrentWidget(self.empty)

    def restyle(self) -> None:
        """Refait le rendu avec la palette courante.

        La trace est du HTML fabrique une fois : ses couleurs sont ecrites en
        dur dans le document. Sans ce rejeu, l'exception restait rouge sombre
        sur le fond blanc du theme clair.
        """
        # La fiche affichee est refaite, l'autre attend son tour : elle sera
        # rebatie a son prochain affichage, avec la palette d'alors.
        if self.stack.currentIndex() == self.PAGE_GROUPE:
            if self._dernier_groupe is not None:
                self.show_group(*self._dernier_groupe)
        elif self._dernier is not None:
            self.show_test(*self._dernier)

    def nodeid(self) -> str:
        return self._nodeid

    def show_test(self, nodeid: str, readers: tuple[Reader, ...],
                  statuses: dict[int, Status],
                  failures: dict[int, Failure | None]) -> None:
        """Affiche un test. `statuses` et `failures` sont indexes par lecteur."""
        if not nodeid:
            self.clear()
            return

        self._nodeid = nodeid
        self._dernier = (nodeid, readers, statuses, failures)
        self.stack.setCurrentWidget(self.stack.widget(1))

        chemin, _, reste = nodeid.partition("::")
        self.path_label.setText(chemin)
        self.name_label.setText(reste.replace("::", " › ") or chemin)

        self._remplir_resultats(readers, statuses)
        self._remplir_corps(readers, statuses, failures)

    def _remplir_resultats(self, readers, statuses: dict[int, Status]) -> None:
        while self._results_layout.count():
            element = self._results_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()

        cibles = readers or (Reader("", 0),)
        for lecteur in cibles:
            statut = statuses.get(lecteur.index, Status.PENDING)
            self._results_layout.addWidget(
                ReaderResult(lecteur.short_name, lecteur.index, statut))
        self._results_layout.addStretch(1)

    def _remplir_corps(self, readers, statuses: dict[int, Status],
                       failures: dict[int, Failure | None]) -> None:
        cibles = readers or (Reader("", 0),)
        blocs: list[str] = []
        brut: list[str] = []

        for lecteur in cibles:
            statut = statuses.get(lecteur.index, Status.PENDING)
            if not statut.is_bad:
                continue
            echec = failures.get(lecteur.index)
            blocs.append(self._html_bloc(lecteur, statut, echec))
            entete = f"--- {lecteur.name or 'run'} ---" if len(cibles) > 1 else ""
            brut.append("\n".join(x for x in (entete, echec.body if echec else "") if x))

        if not blocs:
            blocs.append(self._html_sans_echec(cibles, statuses))

        self.body.setHtml(
            f'<body style="background:transparent;">{"".join(blocs)}</body>')
        self._texte_brut = "\n\n".join(x for x in brut if x.strip())
        self.copy_button.setEnabled(bool(self._texte_brut))

    # ------------------------------------------------------------------- html

    def _html_bloc(self, lecteur: Reader, statut: Status,
                   echec: Failure | None) -> str:
        couleur = t.reader_color(lecteur.index)
        titre = ""
        if lecteur.name:
            titre = (
                f'<p style="margin:0 0 2px 0; color:{couleur};'
                f' font-size:{t.TEXT_XS}px; font-weight:700;">'
                f"{escape(lecteur.short_name.upper())}</p>")

        if echec is None:
            # Un run annule, ou un echec que pytest a resume sans trace : le
            # dire vaut mieux qu'un cadre vide qu'on prend pour un bug.
            return titre + self._html_note(
                f"{statut.label} — pytest printed no traceback for this test. "
                "The raw output may say more.")

        avertissement = ""
        if echec.ambiguous:
            avertissement = self._html_note(
                "Another test has the same name in this run; pytest does not "
                "print the file in its traceback headers, so this one may "
                "belong to the other.")

        resume = (
            f'<p style="margin:0 0 {t.SPACE_2}px 0;'
            f' color:{t.status_color(statut)}; font-size:{t.TEXT_MD}px;'
            f' font-weight:600;">{escape(echec.headline)}</p>')

        return titre + resume + avertissement + self._html_trace(echec.body)

    def _html_trace(self, corps: str) -> str:
        lignes = []
        for ligne in corps.splitlines():
            nature = classify_line(ligne)
            teinte = _teinte(nature)
            gras = "font-weight:600;" if nature == "exception" else ""
            nue = escape(strip_ansi(ligne)) or "&nbsp;"
            lignes.append(f'<span style="color:{teinte};{gras}">{nue}</span>')

        return (
            f'<pre style="font-family:{t.FONT_MONO}; font-size:{t.TEXT_SM}px;'
            f' margin:0 0 {t.SPACE_4}px 0;">' + "<br/>".join(lignes) + "</pre>")

    def _html_note(self, texte: str) -> str:
        return (f'<p style="margin:0 0 {t.SPACE_3}px 0; color:{t.TEXT_MUTED};'
                f' font-size:{t.TEXT_SM}px;">{escape(texte)}</p>')

    def _html_sans_echec(self, cibles, statuses: dict[int, Status]) -> str:
        vus = [statuses.get(l.index, Status.PENDING) for l in cibles]
        if all(s is Status.PENDING for s in vus):
            return self._html_note("This test has not run yet.")
        if all(s is Status.SKIPPED for s in vus):
            return self._html_note("Skipped everywhere in the last run.")

        pluriel = "every reader" if len(cibles) > 1 else "the last run"
        return (f'<p style="margin:0; color:{t.status_color(Status.PASSED)};'
                f' font-size:{t.TEXT_MD}px; font-weight:600;">'
                f"Passed on {pluriel}. Nothing to explain.</p>")

    def _copier(self) -> None:
        from PyQt5.QtWidgets import QApplication

        if self._texte_brut:
            QApplication.clipboard().setText(self._texte_brut)
