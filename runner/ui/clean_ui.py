"""Small visual refinements for the main runner interface.

Keep the result summary and live run status flat: both already sit inside a
larger panel/status bar, so drawing another box around them creates a nested
"box in a box" effect on Windows.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from runner.domain.models import Status
from runner.ui import tokens as t


def install() -> None:
    """Install the flat variants before the main window is created."""
    from runner.ui.detail_panel import DetailPanel
    from runner.ui.main_window import MainWindow

    def flat_stat_cell(self, legende: str, valeur: QWidget) -> QWidget:
        cellule = QWidget()
        colonne = QVBoxLayout(cellule)
        colonne.setContentsMargins(t.SPACE_2, t.SPACE_1, t.SPACE_2, t.SPACE_1)
        colonne.setSpacing(2)

        from PyQt5.QtWidgets import QLabel
        libelle = QLabel(legende.upper())
        libelle.setObjectName("StatCellLabel")
        colonne.addWidget(libelle)
        colonne.addWidget(valeur)
        return cellule

    def flat_status_live(self, texte: str) -> None:
        couleur = t.status_color(Status.RUNNING)
        self.status_label.setObjectName("StatusLive")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(texte)
        self.live_dot.set_color(couleur)
        self.live_dot.start()
        # No extra background/border here: the status bar already provides
        # the visual container and the live dot + blue text carry the state.
        self.live_chip.setStyleSheet("")

    DetailPanel._stat_cell = flat_stat_cell
    MainWindow._set_status_live = flat_status_live
