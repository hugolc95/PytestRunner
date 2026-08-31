"""Choisir combien de fois rejouer un test.

Une petite boite plutot qu'un menu deroulant classique : le nombre exact
importe (ce n'est pas un choix parmi quelques valeurs figees), mais les
raccourcis les plus courants restent a portee d'un clic.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from runner.ui import tokens as t

PRESETS = (5, 10, 20, 50)


class RunNTimesDialog(QDialog):
    def __init__(self, defaut: int = 20, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run how many times?")

        self.compte = QSpinBox()
        self.compte.setRange(1, 1000)
        self.compte.setValue(defaut)
        self.compte.setSuffix(" times")

        raccourcis = QHBoxLayout()
        raccourcis.setSpacing(t.SPACE_2)
        self._boutons_preset: list[QPushButton] = []
        for valeur in PRESETS:
            bouton = QPushButton(str(valeur))
            bouton.setObjectName("Chip")
            bouton.setCheckable(True)
            bouton.setChecked(valeur == defaut)
            bouton.clicked.connect(lambda _=False, v=valeur: self._choisir_preset(v))
            raccourcis.addWidget(bouton)
            self._boutons_preset.append(bouton)
        self.compte.valueChanged.connect(self._sur_changement_manuel)

        run_button = QPushButton("Run")
        run_button.setObjectName("Run")
        run_button.setDefault(True)
        run_button.clicked.connect(self.accept)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("Ghost")
        cancel_button.clicked.connect(self.reject)

        boutons = QHBoxLayout()
        boutons.addStretch(1)
        boutons.addWidget(cancel_button)
        boutons.addWidget(run_button)

        colonne = QVBoxLayout(self)
        colonne.setSpacing(t.SPACE_3)
        colonne.addWidget(self.compte)
        colonne.addLayout(raccourcis)
        colonne.addStretch(1)
        colonne.addLayout(boutons)

    def _choisir_preset(self, valeur: int) -> None:
        self.compte.setValue(valeur)

    def _sur_changement_manuel(self, valeur: int) -> None:
        # Les puces ne restent allumees que si la valeur y correspond
        # encore : sinon un "20" reste coche apres avoir tape "7" a la main.
        for bouton in self._boutons_preset:
            bouton.setChecked(int(bouton.text()) == valeur)

    def count(self) -> int:
        return self.compte.value()
