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

import time
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from runner.domain.ansi import strip_ansi
from runner.domain.failures import Failure, classify_line, failure_for, index_failures
from runner.domain.models import Reader, Status
from runner.domain.stress import MODE_UNTIL_FAIL, StressAttempt, StressSummary
from runner.ui import icons, theme
from runner.ui import tokens as t
from runner.ui.widgets import (
    EmptyState,
    ReaderBadge,
    ReaderResult,
    RecentRunsSparkline,
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

    open_output = Signal()
    test_chosen = Signal(str)   # un echec clique dans la fiche de groupe

    PAGE_VIDE, PAGE_TEST, PAGE_GROUPE, PAGE_STRESS = 0, 1, 2, 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodeid = ""
        self._texte_brut = ""
        # Ce qu'il faut pour refaire le rendu a l'identique : le HTML de la
        # trace porte des couleurs resolues au moment ou il a ete construit, et
        # ne suit donc pas un changement de theme.
        self._dernier: tuple | None = None
        self._dernier_groupe: tuple | None = None
        self._dernier_stress: tuple | None = None
        self._tentatives_ratees: list[StressAttempt] = []
        # Texte exact de la case Duration, et une pastille de tendance par
        # lecteur -- lus par les tests, plutot que de deviner le duree dans
        # la disposition du dernier widget d'une rangee.
        self._duree_visible = ""
        self._sparklines: dict[int, RecentRunsSparkline] = {}

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
        self.stack.addWidget(self._build_stress())

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

        # L'identifiant complet, copiable d'un geste : le retrouver ailleurs
        # (un ticket, un message) ne devrait pas obliger a rouvrir le menu
        # contextuel de l'arbre pour "Copy nodeid".
        ligne_nodeid = QHBoxLayout()
        ligne_nodeid.setContentsMargins(0, 0, 0, 0)
        ligne_nodeid.setSpacing(t.SPACE_1)

        self.nodeid_label = QLabel()
        self.nodeid_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nodeid_label.setStyleSheet(
            f"font-family: {t.FONT_MONO}; font-size: {t.TEXT_XS}px;"
            f" color: {t.TEXT_FAINT}; background: transparent;")

        self.copy_nodeid_button = QPushButton()
        self.copy_nodeid_button.setObjectName("IconSm")
        self.copy_nodeid_button.setIcon(icons.icon("mdi.content-copy", t.TEXT_FAINT))
        self.copy_nodeid_button.setToolTip("Copy the full test id")
        self.copy_nodeid_button.clicked.connect(self._copier_nodeid)

        ligne_nodeid.addWidget(self.nodeid_label, 1)
        ligne_nodeid.addWidget(self.copy_nodeid_button)
        colonne.addLayout(ligne_nodeid)

        # Les markers, seulement s'il y en a : une rangee vide qui reserve sa
        # hauteur en permanence decalerait tout le reste sans rien dire.
        self.markers_row = QWidget()
        self._markers_layout = QHBoxLayout(self.markers_row)
        self._markers_layout.setContentsMargins(0, 0, 0, 0)
        self._markers_layout.setSpacing(t.SPACE_1)
        colonne.addWidget(self.markers_row)

        self.results_row = QWidget()
        self._results_layout = QHBoxLayout(self.results_row)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(t.SPACE_2)
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

    # ------------------------------------------------------------ fiche stress

    def _build_stress(self) -> QWidget:
        """Fiche de "Run until it fails" / "Run N times" : une serie de
        tentatives sur UN SEUL test, pas un lot -- d'ou un ruban unique et
        une trace choisie parmi les tentatives en echec, pas par lecteur."""
        contenu = QWidget()
        colonne = QVBoxLayout(contenu)
        colonne.setContentsMargins(0, t.SPACE_2, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        self.stress_path = QLabel()
        self.stress_path.setObjectName("Faint")
        self.stress_name = QLabel()
        self.stress_name.setObjectName("Title")
        self.stress_name.setWordWrap(True)
        self.stress_sub = QLabel()
        self.stress_sub.setObjectName("Muted")

        colonne.addWidget(self.stress_path)
        colonne.addWidget(self.stress_name)
        colonne.addWidget(self.stress_sub)

        self.stress_ribbon = StatusRibbon()
        colonne.addWidget(self.stress_ribbon)

        self.stress_counters = QLabel()
        self.stress_counters.setTextFormat(Qt.RichText)
        self.stress_counters.setStyleSheet(
            f"font-size: {t.TEXT_SM}px; background: transparent;")
        colonne.addWidget(self.stress_counters)

        self.stress_note = QLabel()
        self.stress_note.setObjectName("Muted")
        self.stress_note.setWordWrap(True)
        colonne.addWidget(self.stress_note)

        self.stress_failures_title = QLabel()
        self.stress_failures_title.setObjectName("Muted")
        self.stress_failures_title.setVisible(False)
        colonne.addWidget(self.stress_failures_title)

        self.stress_failures = QListWidget()
        self.stress_failures.setObjectName("Failures")
        self.stress_failures.setVisible(False)
        self.stress_failures.itemClicked.connect(self._sur_tentative_ratee)
        colonne.addWidget(self.stress_failures)

        self.stress_body = QTextEdit()
        self.stress_body.setReadOnly(True)
        self.stress_body.setLineWrapMode(QTextEdit.NoWrap)
        colonne.addWidget(self.stress_body, 1)
        return contenu

    def show_stress_running(self, nodeid: str, mode: str, cap: int,
                            ran: int, passed: int, failed_attempts: int) -> None:
        """Etat en cours : pas encore de trace a montrer, juste l'avancement."""
        self._dernier_stress = None
        self._tentatives_ratees = []
        self._nodeid = ""
        self.stack.setCurrentIndex(self.PAGE_STRESS)
        self._remplir_entete_stress(nodeid)

        if mode == MODE_UNTIL_FAIL:
            self.stress_sub.setText(f"Stress run in progress — attempt {ran + 1} of {cap}")
        else:
            self.stress_sub.setText(f"Run N times — run {ran + 1} of {cap} under way")

        self.stress_ribbon.set_counts({
            Status.PASSED: passed, Status.FAILED: failed_attempts,
            Status.PENDING: max(0, cap - ran),
        })
        morceaux = [f"<b>{ran}</b> of {cap}",
                   f'<span style="color:{t.status_color(Status.PASSED)}">'
                   f"<b>{passed}</b> passed</span>"]
        if failed_attempts:
            morceaux.append(f'<span style="color:{t.status_color(Status.FAILED)}">'
                            f"<b>{failed_attempts}</b> failed</span>")
        self.stress_counters.setText("&nbsp;&nbsp;&nbsp;".join(morceaux))
        self.stress_note.setText(
            "Stops automatically on the first failure." if mode == MODE_UNTIL_FAIL
            else "Runs all the way through — it doesn't stop on a failure.")
        self.stress_failures_title.setVisible(False)
        self.stress_failures.setVisible(False)
        self.stress_body.clear()

    def show_stress_done(self, nodeid: str, resume: StressSummary) -> None:
        """Bilan final : le ruban se fige, et chaque tentative en echec peut
        etre choisie pour voir SA trace precise."""
        self._dernier_stress = (nodeid, resume)
        self._tentatives_ratees = list(resume.failed_attempts)
        self._nodeid = ""
        self.stack.setCurrentIndex(self.PAGE_STRESS)
        self._remplir_entete_stress(nodeid)

        echecs = len(resume.failed_attempts)
        if resume.cancelled:
            self.stress_sub.setText(f"Stopped by you — {resume.ran} of {resume.cap} runs done")
        elif resume.mode == MODE_UNTIL_FAIL and echecs:
            derniere = resume.failed_attempts[-1]
            self.stress_sub.setText(
                f"Attempt {derniere.number} of {derniere.number} — the one that broke it")
        elif resume.mode == MODE_UNTIL_FAIL:
            self.stress_sub.setText(f"Never failed in {resume.ran} attempts")
        else:
            taux = round(100 * resume.passed / resume.ran) if resume.ran else 0
            self.stress_sub.setText(f"{resume.ran} of {resume.cap} runs complete — {taux}% pass rate")

        self.stress_ribbon.set_counts({
            Status.PASSED: resume.passed, Status.FAILED: echecs,
            Status.PENDING: max(0, resume.cap - resume.ran),
        })
        morceaux = [f"<b>{resume.ran}</b> runs",
                   f'<span style="color:{t.status_color(Status.PASSED)}">'
                   f"<b>{resume.passed}</b> passed</span>"]
        if echecs:
            morceaux.append(f'<span style="color:{t.status_color(Status.FAILED)}">'
                            f"<b>{echecs}</b> failed</span>")
        self.stress_counters.setText("&nbsp;&nbsp;&nbsp;".join(morceaux))
        self.stress_note.setText("")

        if echecs:
            self.stress_failures_title.setText(
                f"Failed attempt{'s' if echecs > 1 else ''}")
            self.stress_failures_title.setVisible(True)
            self.stress_failures.setVisible(True)
            self._remplir_tentatives_ratees(nodeid)
            # La plus recente est celle qu'on regarde une fois sur deux.
            self.stress_failures.setCurrentRow(self.stress_failures.count() - 1)
            self._afficher_trace_tentative(nodeid, self._tentatives_ratees[-1])
        else:
            self.stress_failures_title.setVisible(False)
            self.stress_failures.setVisible(False)
            self.stress_body.clear()

    def _remplir_entete_stress(self, nodeid: str) -> None:
        chemin, _, reste = nodeid.partition("::")
        self.stress_path.setText(chemin)
        self.stress_name.setText(reste.replace("::", " › ") or chemin)

    def _remplir_tentatives_ratees(self, nodeid: str) -> None:
        self.stress_failures.clear()
        for tentative in self._tentatives_ratees:
            item = QListWidgetItem(f"Attempt {tentative.number}")
            item.setData(Qt.UserRole, tentative.number)
            item.setForeground(QColor(t.status_color(Status.FAILED)))
            self.stress_failures.addItem(item)

    def _sur_tentative_ratee(self, item) -> None:
        numero = item.data(Qt.UserRole)
        tentative = next((tv for tv in self._tentatives_ratees if tv.number == numero), None)
        if tentative is not None and self._dernier_stress is not None:
            self._afficher_trace_tentative(self._dernier_stress[0], tentative)

    def _afficher_trace_tentative(self, nodeid: str, tentative: StressAttempt) -> None:
        echec = failure_for(index_failures(tentative.output), nodeid)
        bloc = self._html_bloc(Reader("", 0), tentative.status, echec)
        self.stress_body.setHtml(f'<body style="background:transparent;">{bloc}</body>')

    def show_group(self, path: str, name: str, readers: tuple[Reader, ...],
                   counts: dict, failures: list,
                   durations: dict[int, float | None] | None = None) -> None:
        """Fiche d'un dossier, d'un fichier ou d'un test parametre.

        `counts` donne, par index de lecteur, le nombre de tests par statut.
        `failures` liste des couples (nodeid, index du lecteur). `durations`
        est la somme des tentatives connues sous ce noeud, par lecteur.
        """
        self._dernier_groupe = (path, name, readers, counts, failures, durations)
        self._nodeid = ""
        self.stack.setCurrentIndex(self.PAGE_GROUPE)

        self.group_path.setText(path)
        # La racine n'a pas d'ancetre : l'etiquette vide prendrait quand meme
        # sa hauteur et decalerait le titre sans rien dire.
        self.group_path.setVisible(bool(path))
        self.group_name.setText(name)

        total = sum(sum(c.values()) for c in counts.values()) or 0
        tests = total // max(1, len(readers) or 1)
        texte = (f"{tests} test{'s' if tests > 1 else ''}"
                + (f" × {len(readers)} readers" if len(readers) > 1 else ""))
        duree = self._texte_duree(readers or (Reader("", 0),), durations or {})
        if duree:
            texte += f"   ·   {duree}"
        self.group_total.setText(texte)
        self._remplir_rubans(readers, counts)
        self._remplir_echecs(readers, failures)

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
        self._dernier_stress = None
        self._tentatives_ratees = []
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
        elif self.stack.currentIndex() == self.PAGE_STRESS:
            if self._dernier_stress is not None:
                self.show_stress_done(*self._dernier_stress)
        elif self._dernier is not None:
            self.show_test(*self._dernier)

    def nodeid(self) -> str:
        return self._nodeid

    def show_test(self, nodeid: str, readers: tuple[Reader, ...],
                  statuses: dict[int, Status],
                  failures: dict[int, Failure | None],
                  durations: dict[int, float | None] | None = None,
                  markers: tuple[str, ...] = (),
                  recent_runs: dict[int, list[bool]] | None = None,
                  last_seen: float | None = None) -> None:
        """Affiche un test. `statuses` et `failures` sont indexes par lecteur.

        `recent_runs` est la mini-tendance de ce nodeid, par lecteur, du plus
        ancien au plus recent -- absent des lecteurs sans historique connu.
        """
        if not nodeid:
            self.clear()
            return

        self._nodeid = nodeid
        self._dernier = (nodeid, readers, statuses, failures, durations,
                        markers, recent_runs, last_seen)
        self.stack.setCurrentWidget(self.stack.widget(1))

        chemin, _, reste = nodeid.partition("::")
        self.path_label.setText(chemin)
        self.name_label.setText(reste.replace("::", " › ") or chemin)
        self.nodeid_label.setText(nodeid)

        self._remplir_markers(markers)
        self._remplir_resultats(readers, statuses, durations or {}, recent_runs or {})
        self._remplir_corps(readers, statuses, failures, last_seen, recent_runs or {})

    def _copier_nodeid(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self._nodeid:
            QApplication.clipboard().setText(self._nodeid)

    def _remplir_markers(self, markers: tuple[str, ...]) -> None:
        while self._markers_layout.count():
            element = self._markers_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        for nom in markers:
            chip = QLabel(nom)
            chip.setStyleSheet(theme.pill_style(t.TEXT_MUTED))
            self._markers_layout.addWidget(chip)
        self._markers_layout.addStretch(1)
        self.markers_row.setVisible(bool(markers))

    def _stat_cell(self, legende: str, valeur: QWidget) -> QWidget:
        """Case etiquetee du bandeau de stats : une legende discrete au-dessus
        d'une valeur qui, elle, doit se voir du premier coup d'oeil -- la
        duree d'un test se perdait avant dans une simple etiquette grise en
        bout de rangee."""
        cellule = QFrame()
        cellule.setStyleSheet(
            f"background-color: {t.BG_RAISED}; border: 1px solid {t.BORDER};"
            f"border-radius: {t.RADIUS_MD}px;")
        colonne = QVBoxLayout(cellule)
        colonne.setContentsMargins(t.SPACE_2, t.SPACE_1, t.SPACE_2, t.SPACE_1)
        colonne.setSpacing(2)

        libelle = QLabel(legende.upper())
        libelle.setObjectName("StatCellLabel")
        colonne.addWidget(libelle)
        colonne.addWidget(valeur)
        return cellule

    def _texte_duree(self, cibles, durations: dict[int, float | None]) -> str:
        """Duree connue de chaque lecteur, telle que pytest l'a chronometree.

        Silencieux la ou elle manque : un test trop rapide pour figurer dans
        le releve de pytest (`--durations-min`) n'a simplement rien a montrer,
        plutot qu'un faux "0.00s".
        """
        morceaux = []
        plusieurs = len(cibles) > 1
        for lecteur in cibles:
            valeur = durations.get(lecteur.index)
            if valeur is None:
                continue
            prefixe = f"{lecteur.short_name}: " if lecteur.name and plusieurs else ""
            morceaux.append(f"{prefixe}{valeur:.2f}s")
        return "   ".join(morceaux)

    def _remplir_resultats(self, readers, statuses: dict[int, Status],
                           durations: dict[int, float | None],
                           recent_runs: dict[int, list[bool]]) -> None:
        while self._results_layout.count():
            element = self._results_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                # `hide()` tout de suite : retire du layout, un widget garde
                # sa derniere position et reste peint par-dessus les
                # nouvelles cases tant que `deleteLater()` n'a pas ete traite.
                widget.hide()
                widget.deleteLater()
        self._sparklines = {}

        cibles = readers or (Reader("", 0),)
        plusieurs = len(cibles) > 1
        for lecteur in cibles:
            statut = statuses.get(lecteur.index, Status.PENDING)
            legende = lecteur.short_name if lecteur.name else "Status"
            valeur = ReaderResult("", lecteur.index, statut)
            self._results_layout.addWidget(self._stat_cell(legende, valeur))

        self._duree_visible = self._texte_duree(cibles, durations)
        if self._duree_visible:
            duree_label = QLabel(self._duree_visible)
            duree_label.setObjectName("StatCellValue")
            self._results_layout.addWidget(self._stat_cell("Duration", duree_label))

        for lecteur in cibles:
            runs = recent_runs.get(lecteur.index, [])
            if not runs:
                continue
            sparkline = RecentRunsSparkline()
            sparkline.set_runs(runs)
            self._sparklines[lecteur.index] = sparkline
            legende = f"{lecteur.short_name} history" if plusieurs and lecteur.name else "Last runs"
            self._results_layout.addWidget(self._stat_cell(legende, sparkline))

        self._results_layout.addStretch(1)

    def _remplir_corps(self, readers, statuses: dict[int, Status],
                       failures: dict[int, Failure | None],
                       last_seen: float | None = None,
                       recent_runs: dict[int, list[bool]] | None = None) -> None:
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
            blocs.append(self._html_sans_echec(cibles, statuses, last_seen, recent_runs or {}))

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

    def _html_sans_echec(self, cibles, statuses: dict[int, Status],
                         last_seen: float | None = None,
                         recent_runs: dict[int, list[bool]] | None = None) -> str:
        vus = [statuses.get(l.index, Status.PENDING) for l in cibles]
        if all(s is Status.PENDING for s in vus):
            return self._html_note("This test has not run yet.")
        if all(s is Status.SKIPPED for s in vus):
            return self._html_note("Skipped everywhere in the last run.")

        # Le vide d'un test qui passe etait le coeur du reproche : une seule
        # phrase grise, perdue dans un grand cadre vide, ne disait rien de
        # plus qu'un point vert deja visible dans l'arbre. La carte ci-dessous
        # y ajoute au moins la derniere execution, et si l'historique le sait,
        # a quel point ce verdict tient d'un run a l'autre.
        pluriel = "every reader" if len(cibles) > 1 else "the last run"
        sous_ligne = ""
        if last_seen is not None:
            sous_ligne = f"Last run: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen))}"

        runs = [ok for liste in (recent_runs or {}).values() for ok in liste]
        echecs = sum(1 for ok in runs if not ok)
        if runs and echecs:
            fragment = f"flaky {echecs} time{'s' if echecs > 1 else ''} in the last {len(runs)} runs"
            sous_ligne = f"{sous_ligne} · {fragment}" if sous_ligne else fragment[0].upper() + fragment[1:]

        sous_html = ""
        if sous_ligne:
            sous_html = (f'<p style="margin:{t.SPACE_1}px 0 0 0; color:{t.TEXT_MUTED};'
                        f' font-size:{t.TEXT_SM}px;">{escape(sous_ligne)}</p>')

        return (
            f'<div style="border:1px dashed {t.BORDER_STRONG};'
            f' border-radius:{t.RADIUS_MD}px;'
            f' padding:{t.SPACE_3}px {t.SPACE_4}px; margin-top:{t.SPACE_1}px;">'
            f'<p style="margin:0; color:{t.status_color(Status.PASSED)};'
            f' font-size:{t.TEXT_MD}px; font-weight:600;">'
            f"Passed on {pluriel}.</p>{sous_html}</div>")

    def _copier(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self._texte_brut:
            QApplication.clipboard().setText(self._texte_brut)
