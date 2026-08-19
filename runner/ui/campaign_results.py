"""Resultats d'une campagne : par configuration, ou en matrice.

Un meme test peut tourner dans plusieurs configurations avec des verdicts
differents. Le fusionner en un seul statut -- comme le fait l'arbre, au pire
des cas -- cache justement ce qu'on cherche a voir ici. Aucune des deux vues
qui suivent ne fusionne deux executions du meme test entre elles :

- Par configuration : chaque scenario reste son propre groupe, avec le detail
  par lecteur -- la lecture la plus complete.
- Matrice : un tableau compact, un test par ligne, une configuration par
  colonne -- la comparaison la plus rapide. Le detail par lecteur y est
  seulement en infobulle : la cellule montre le pire des lecteurs, comme
  partout ailleurs dans l'outil des qu'un statut doit tenir en un seul mot.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from runner.domain.campaign import CampaignDefinition
from runner.domain.models import Reader, Status, worst
from runner.ui import tokens as t

VUE_LISTE, VUE_MATRICE = 0, 1


def _libelle_test(nodeid: str) -> str:
    """La partie du nodeid qui identifie le test, sans le chemin du fichier."""
    return nodeid.split("::", 1)[-1].replace("::", " › ") if "::" in nodeid else nodeid


class CampaignResultsView(QWidget):
    """Les tests d'une campagne, groupes par configuration ou en matrice.

    Vide tant qu'aucune campagne n'est posee : `set_data(None, ...)` la laisse
    prete, mais sans rien a montrer -- l'appelant decide s'il faut l'afficher.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._campaign: CampaignDefinition | None = None
        self._results: dict[str, dict[str, dict[int, Status]]] = {}
        self._readers: tuple[Reader, ...] = ()

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(t.SPACE_2)

        barre = QHBoxLayout()
        barre.setContentsMargins(0, 0, 0, 0)
        barre.addStretch(1)

        # Segmente, comme les lentilles de la console : deux vues d'UNE meme
        # chose, pas deux actions differentes.
        self.list_button = QPushButton("By configuration")
        self.list_button.setObjectName("Segment")
        self.list_button.setProperty("segment", "first")
        self.list_button.setCheckable(True)
        self.list_button.setChecked(True)
        self.list_button.clicked.connect(lambda: self._basculer(VUE_LISTE))

        self.matrix_button = QPushButton("Matrix")
        self.matrix_button.setObjectName("Segment")
        self.matrix_button.setProperty("segment", "last")
        self.matrix_button.setCheckable(True)
        self.matrix_button.clicked.connect(lambda: self._basculer(VUE_MATRICE))

        barre.addWidget(self.list_button)
        barre.addWidget(self.matrix_button)
        colonne.addLayout(barre)

        self.tree = QTreeWidget()
        self.tree.setObjectName("CampaignTree")
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)

        self.table = QTableWidget()
        self.table.setObjectName("CampaignMatrix")
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        # Le nom du test EST l'en-tete de ligne : le masquer laisserait un
        # tableau de statuts sans dire de quel test chacun parle.

        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.table)
        colonne.addWidget(self.stack, 1)

    def _basculer(self, vue: int) -> None:
        self.list_button.setChecked(vue == VUE_LISTE)
        self.matrix_button.setChecked(vue == VUE_MATRICE)
        self.stack.setCurrentIndex(vue)

    # ---------------------------------------------------------------- donnees

    def set_data(self, campaign: CampaignDefinition | None,
                results: dict[str, dict[str, dict[int, Status]]],
                readers: tuple[Reader, ...] = ()) -> None:
        """`results` : nom du scenario -> nodeid -> index de lecteur -> statut.

        Un test absent de `results[scenario]` n'a simplement pas encore
        tourne dans cette configuration -- distinct d'un statut PENDING, qui
        impliquerait un run en cours.
        """
        self._campaign = campaign
        self._results = results
        self._readers = readers or (Reader("", 0),)
        self._remplir_liste()
        self._remplir_matrice()

    def _nom_lecteur(self, index: int) -> str:
        for lecteur in self._readers:
            if lecteur.index == index:
                return lecteur.short_name or f"Reader {index}"
        return f"Reader {index}"

    # -------------------------------------------------------- vue par config

    def _remplir_liste(self) -> None:
        self.tree.clear()
        cibles = self._readers
        entetes = ["Test"] + [lecteur.short_name or "Result" for lecteur in cibles]
        self.tree.setColumnCount(len(entetes))
        self.tree.setHeaderLabels(entetes)
        if self._campaign is None:
            return

        for scenario in self._campaign.scenarios:
            par_test = self._results.get(scenario.name, {})
            racine = QTreeWidgetItem([scenario.name] + [""] * len(cibles))
            police = racine.font(0)
            police.setBold(True)
            racine.setFont(0, police)
            self.tree.addTopLevelItem(racine)

            # `dict.fromkeys` plutot qu'un `set` : garde l'ordre du YAML, que
            # l'utilisateur reconnait.
            for nodeid in dict.fromkeys(test.nodeid for test in scenario.tests):
                statuts = par_test.get(nodeid, {})
                ligne = QTreeWidgetItem([_libelle_test(nodeid)])
                for position, lecteur in enumerate(cibles, start=1):
                    statut = statuts.get(lecteur.index)
                    ligne.setText(position, statut.label if statut else "not run")
                    couleur = t.status_color(statut) if statut else t.TEXT_FAINT
                    ligne.setForeground(position, QColor(couleur))
                racine.addChild(ligne)
            racine.setExpanded(True)

        for colonne in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(colonne)

    # ------------------------------------------------------------ la matrice

    def _remplir_matrice(self) -> None:
        self.table.clear()
        if self._campaign is None:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        scenarios = self._campaign.scenarios
        # Un test unique, dans l'ordre de sa PREMIERE apparition dans le YAML.
        tests: list[str] = []
        for scenario in scenarios:
            for test in scenario.tests:
                if test.nodeid not in tests:
                    tests.append(test.nodeid)

        self.table.setRowCount(len(tests))
        self.table.setColumnCount(len(scenarios))
        self.table.setHorizontalHeaderLabels([s.name for s in scenarios])
        self.table.setVerticalHeaderLabels([_libelle_test(n) for n in tests])

        for ligne, nodeid in enumerate(tests):
            for colonne, scenario in enumerate(scenarios):
                couvre = any(test.nodeid == nodeid for test in scenario.tests)
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                if couvre:
                    statuts = self._results.get(scenario.name, {}).get(nodeid, {})
                    if statuts:
                        pire = worst(statuts.values())
                        item.setText(pire.label)
                        item.setForeground(QColor(t.status_color(pire)))
                        # Une infobulle seulement quand les lecteurs se
                        # contredisent : sinon elle ne ferait que repeter la
                        # cellule.
                        if len(set(statuts.values())) > 1:
                            item.setToolTip(", ".join(
                                f"{self._nom_lecteur(i)}: {s.label}"
                                for i, s in statuts.items()))
                    else:
                        item.setText("not run")
                        item.setForeground(QColor(t.TEXT_FAINT))
                self.table.setItem(ligne, colonne, item)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
