"""Resultats d'une campagne : une carte par configuration, setup puis tests.

Prototype visuel, pas encore la version definitive : le statut du setup
ci-dessous est DEVINE (tous ses tests en ERROR => setup en cause), en
attendant que `PhaseReport.setup_ok` soit transmis jusqu'ici. Le vrai cablage
suit une fois la direction confirmee -- voir `_etat_setup`.

Un meme test peut tourner dans plusieurs configurations avec des verdicts
differents. Le fusionner en un seul statut -- comme le fait l'arbre, au pire
des cas -- cache justement ce qu'on cherche a voir ici : chaque carte reste le
groupe d'UNE SEULE configuration, jamais fusionnee avec une autre.

Setup et tests sont dessines comme deux etapes reliees plutot que deux listes
separees : c'est dans cet ordre qu'ils se sont vraiment executes, et un setup
en echec explique a lui seul pourquoi ses tests n'ont jamais tourne.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from runner.domain.campaign import CampaignDefinition, CampaignScenario
from runner.domain.models import Reader, Status, worst
from runner.ui import icons, theme
from runner.ui import tokens as t


def _libelle_test(nodeid: str) -> str:
    """La partie du nodeid qui identifie le test, sans le chemin du fichier."""
    return nodeid.split("::", 1)[-1].replace("::", " › ") if "::" in nodeid else nodeid


def _pastille(texte: str, couleur: str) -> QLabel:
    etiquette = QLabel(texte)
    etiquette.setStyleSheet(theme.pill_style(couleur))
    return etiquette


def _etat_test(status: Status | None) -> tuple[str, str, str]:
    """(couleur, glyphe, texte) d'un test -- None si jamais lance."""
    if status is None:
        return t.TEXT_FAINT, "", "NOT RUN"
    if status is Status.PASSED:
        return t.status_color(status), "mdi.check", status.label
    if status in (Status.FAILED,):
        return t.status_color(status), "mdi.close", status.label
    if status is Status.ERROR:
        # Le setup de sa configuration a echoue : ce n'est pas le test qui a
        # casse, il n'a simplement jamais tourne. Une couleur a part -- ni le
        # rouge d'un vrai echec, ni le gris d'un « pas encore » -- pour ne pas
        # laisser croire a l'un ou l'autre.
        return t.status_color(status), "", "SKIPPED"
    return t.status_color(status), "", status.label


def _etat_setup(scenario: CampaignScenario,
                resultats_scenario: dict) -> tuple[str, str, str]:
    """Estimation du statut du setup -- PLACEHOLDER visuel.

    En attendant que `PhaseReport.setup_ok` soit transmis jusqu'ici, la seule
    chose que cette maquette sait deviner : si tous les tests de la
    configuration sont en ERROR, c'est que rien n'a pu tourner derriere le
    setup. Une configuration deja passee au moins une fois pour un test
    n'a donc pas pu echouer a ce point.
    """
    tous = [statut for statuts in resultats_scenario.values()
            for statut in statuts.values()]
    if not tous:
        return t.TEXT_FAINT, "", "NOT RUN"
    if all(statut is Status.ERROR for statut in tous):
        return t.status_color(Status.FAILED), "mdi.close", "FAILED"
    return t.status_color(Status.PASSED), "mdi.check", "PASSED"


def _a_un_probleme(scenario: CampaignScenario, resultats_scenario: dict) -> bool:
    _, _, texte_setup = _etat_setup(scenario, resultats_scenario)
    if texte_setup == "FAILED":
        return True
    return any(statut is Status.FAILED
              for statuts in resultats_scenario.values()
              for statut in statuts.values())


class _StepDot(QLabel):
    """Le petit rond d'une etape, avec ou sans glyphe."""

    def __init__(self, couleur: str, glyphe: str = "", parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"border-radius: 9px; border: 2px solid {couleur}; background: transparent;")
        if glyphe:
            self.setPixmap(icons.icon(glyphe, couleur).pixmap(9, 9))


def _construire_etape(contenu: QWidget, couleur: str, glyphe: str,
                      dernier: bool) -> QWidget:
    """Une etape : sa pastille et son trait de liaison, a cote de son contenu."""
    hote = QWidget()
    ligne = QHBoxLayout(hote)
    ligne.setContentsMargins(0, 0, 0, 0)
    ligne.setSpacing(t.SPACE_3)

    rail = QWidget()
    rail.setFixedWidth(18)
    rail_colonne = QVBoxLayout(rail)
    rail_colonne.setContentsMargins(0, 2, 0, 0)
    rail_colonne.setSpacing(0)
    rail_colonne.addWidget(_StepDot(couleur, glyphe))
    if dernier:
        rail_colonne.addStretch(1)
    else:
        trait = QFrame()
        trait.setFixedWidth(2)
        trait.setStyleSheet(f"background-color: {t.BORDER_STRONG};")
        rail_colonne.addWidget(trait, 1)

    ligne.addWidget(rail)
    ligne.addWidget(contenu, 1)
    return hote


def _titre_etape(texte: str) -> QLabel:
    etiquette = QLabel(texte)
    etiquette.setStyleSheet(
        f"font-size: {t.TEXT_XS}px; font-weight: 700; letter-spacing: 0.05em;"
        f" color: {t.TEXT_FAINT}; background: transparent;")
    return etiquette


class _ConfigCard(QFrame):
    """Une configuration : repliable, setup puis tests dans l'ordre ou ils
    tournent vraiment."""

    def __init__(self, scenario: CampaignScenario, resultats_scenario: dict,
                ouvert: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("Surface")
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(0)

        colonne.addWidget(
            self._construire_entete(scenario, resultats_scenario))

        self._corps = self._construire_corps(scenario, resultats_scenario)
        colonne.addWidget(self._corps)

        self.set_expanded(ouvert)

    def _construire_entete(self, scenario: CampaignScenario,
                           resultats_scenario: dict) -> QWidget:
        entete = QWidget()
        entete.setCursor(Qt.PointingHandCursor)
        ligne = QHBoxLayout(entete)
        ligne.setContentsMargins(t.SPACE_3, t.SPACE_2, t.SPACE_3, t.SPACE_2)
        ligne.setSpacing(t.SPACE_2)

        self._chevron = QLabel()
        self._chevron.setFixedWidth(14)
        titre = QLabel(scenario.name)
        titre.setStyleSheet(
            f"font-weight: 600; font-size: {t.TEXT_SM}px; background: transparent;")

        ligne.addWidget(self._chevron)
        ligne.addWidget(titre)
        ligne.addStretch(1)

        couleur_setup, _, texte_setup = _etat_setup(scenario, resultats_scenario)
        ligne.addWidget(_pastille(f"SETUP {texte_setup}", couleur_setup))

        resume = self._resume_tests(scenario, resultats_scenario)
        if resume is not None:
            ligne.addWidget(_pastille(*resume))

        entete.mousePressEvent = lambda _evt: self.set_expanded(
            not self._corps.isVisible())
        return entete

    def _resume_tests(self, scenario: CampaignScenario,
                      resultats_scenario: dict) -> tuple[str, str] | None:
        nodeids = list(dict.fromkeys(test.nodeid for test in scenario.tests))
        statuts = [worst(resultats_scenario[n].values())
                  for n in nodeids if resultats_scenario.get(n)]
        if not statuts:
            return None
        # Un ERROR n'est pas un echec de TEST : c'est le setup qui a coupe le
        # batch avant qu'aucun ne tourne. Le dire avec le meme mot que
        # "FAILED" ferait chercher une trace d'echec qui n'existe pas.
        if all(s is Status.ERROR for s in statuts):
            return (f"{len(statuts)} SKIPPED", t.status_color(Status.ERROR))
        echecs = sum(1 for s in statuts if s is Status.FAILED)
        if echecs:
            return (f"{echecs} FAILED", t.status_color(Status.FAILED))
        return (f"{len(statuts)} PASSED", t.status_color(Status.PASSED))

    def _construire_corps(self, scenario: CampaignScenario,
                          resultats_scenario: dict) -> QWidget:
        corps = QWidget()
        colonne = QVBoxLayout(corps)
        colonne.setContentsMargins(t.SPACE_3, 0, t.SPACE_3, t.SPACE_3)
        colonne.setSpacing(t.SPACE_2)

        couleur_setup, glyphe_setup, texte_setup = _etat_setup(
            scenario, resultats_scenario)
        colonne.addWidget(_construire_etape(
            self._contenu_setup(scenario, couleur_setup, texte_setup),
            couleur_setup, glyphe_setup, dernier=False))

        nb = len(dict.fromkeys(test.nodeid for test in scenario.tests))
        couleur_tests = (t.status_color(Status.ERROR) if texte_setup == "FAILED"
                        else t.ACCENT)
        colonne.addWidget(_construire_etape(
            self._contenu_tests(scenario, resultats_scenario, texte_setup),
            couleur_tests, "", dernier=True))
        return corps

    def _contenu_setup(self, scenario: CampaignScenario, couleur: str,
                       texte: str) -> QWidget:
        bloc = QWidget()
        colonne = QVBoxLayout(bloc)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)
        colonne.addWidget(_titre_etape("SETUP"))

        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(t.SPACE_2)
        commande = scenario.setup if isinstance(scenario.setup, str) else \
            (" ".join(scenario.setup) if scenario.setup else "")
        chemin = QLabel(commande or "No setup for this configuration")
        chemin.setStyleSheet(
            f"font-family: {t.FONT_MONO}; font-size: {t.TEXT_SM}px;"
            f" color: {t.TEXT_MUTED}; background: transparent;")
        ligne.addWidget(chemin, 1)
        ligne.addWidget(_pastille(texte, couleur))
        colonne.addLayout(ligne)
        return bloc

    def _contenu_tests(self, scenario: CampaignScenario,
                       resultats_scenario: dict, texte_setup: str) -> QWidget:
        bloc = QWidget()
        colonne = QVBoxLayout(bloc)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_1)

        nodeids = list(dict.fromkeys(test.nodeid for test in scenario.tests))
        sous_titre = f"TESTS · {len(nodeids)}"
        if texte_setup == "FAILED":
            sous_titre += " · SKIPPED, SETUP FAILED"
        colonne.addWidget(_titre_etape(sous_titre))

        for nodeid in nodeids:
            statuts = resultats_scenario.get(nodeid, {})
            statut = worst(statuts.values()) if statuts else None
            couleur, glyphe, texte = _etat_test(statut)

            ligne = QHBoxLayout()
            ligne.setContentsMargins(0, t.SPACE_1, 0, t.SPACE_1)
            ligne.setSpacing(t.SPACE_2)
            icone = QLabel()
            icone.setFixedSize(14, 14)
            if glyphe:
                icone.setPixmap(icons.icon(glyphe, couleur).pixmap(13, 13))
            nom = QLabel(_libelle_test(nodeid))
            nom.setStyleSheet(
                f"font-size: {t.TEXT_SM}px;"
                f" color: {t.TEXT if statut else t.TEXT_FAINT}; background: transparent;")
            ligne.addWidget(icone)
            ligne.addWidget(nom, 1)
            ligne.addWidget(_pastille(texte, couleur))
            colonne.addLayout(ligne)
        return bloc

    def set_expanded(self, ouvert: bool) -> None:
        self._corps.setVisible(ouvert)
        self._chevron.setPixmap(
            icons.icon("mdi.chevron-down" if ouvert else "mdi.chevron-right",
                      t.TEXT_FAINT).pixmap(13, 13))


class CampaignResultsView(QWidget):
    """Une carte par configuration de la campagne, setup puis tests.

    Vide tant qu'aucune campagne n'est posee : `set_data(None, ...)` la laisse
    prete, mais sans rien a montrer -- l'appelant decide s'il faut l'afficher.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._campaign: CampaignDefinition | None = None

        self._cartes = QVBoxLayout(self)
        self._cartes.setContentsMargins(0, 0, 0, 0)
        self._cartes.setSpacing(t.SPACE_2)

    def set_data(self, campaign: CampaignDefinition | None,
                results: dict[str, dict[str, dict[int, Status]]],
                readers: tuple[Reader, ...] = ()) -> None:
        """`results` : nom du scenario -> nodeid -> index de lecteur -> statut.

        Un test absent de `results[scenario]` n'a simplement pas encore
        tourne dans cette configuration -- distinct d'un statut PENDING, qui
        impliquerait un run en cours.
        """
        while self._cartes.count():
            element = self._cartes.takeAt(0)
            widget = element.widget()
            if widget is not None:
                # `takeAt` retire le widget du LAYOUT, pas de l'ecran : sans
                # `hide()`, il reste peint a sa derniere position jusqu'a ce
                # que `deleteLater()` s'execute -- au prochain tour de
                # boucle, pas maintenant. Deux `set_data()` rapproches (un
                # clic qui redeclenche la selection courante, par exemple)
                # laissaient alors un fragment de l'ancienne carte flotter
                # sous les nouvelles.
                widget.hide()
                widget.deleteLater()

        self._campaign = campaign
        if campaign is None:
            return

        # Une seule carte ouverte par defaut -- celle qui a un probleme,
        # sinon la premiere. Avec beaucoup de configurations, toutes les
        # ouvrir noierait justement celle qui merite l'attention.
        premiere_a_ouvrir = next(
            (i for i, s in enumerate(campaign.scenarios)
             if _a_un_probleme(s, results.get(s.name, {}))), 0)

        for index, scenario in enumerate(campaign.scenarios):
            self._cartes.addWidget(_ConfigCard(
                scenario, results.get(scenario.name, {}),
                ouvert=(index == premiere_a_ouvrir)))

        self._cartes.addStretch(1)
