"""Fenetre About : version, auteur et environnement de l'application.

L'outil est diffuse largement : la fenetre About dit qui l'a cree et quelle
version tourne, comme tout logiciel professionnel. Elle n'est pas modale :
on la consulte sans bloquer un run en cours.
"""
from __future__ import annotations

import platform

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from runner.version import AUTHOR, AUTHOR_COPYRIGHT, __version__


def _environnement() -> str:
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        qt = f"Qt {qVersion()} · PySide6 {PySide6.__version__}"
    except Exception:  # pragma: no cover - information seulement
        qt = "Qt"
    return f"Python {platform.python_version()} ({platform.architecture()[0]}) · {qt}"


class AboutDialog(QDialog):
    def __init__(self, window=None):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("About Pytest Runner")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(420)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(24, 22, 24, 18)
        racine.setSpacing(14)

        entete = QHBoxLayout()
        entete.setSpacing(16)
        self.logo = QLabel()
        icone = QApplication.instance().windowIcon() if QApplication.instance() else QIcon()
        if icone.isNull():
            from app_icon import APP_ICON_RELATIVE_PATH, resource_path
            icone = QIcon(str(resource_path(APP_ICON_RELATIVE_PATH)))
        if not icone.isNull():
            self.logo.setPixmap(icone.pixmap(64, 64))
        entete.addWidget(self.logo, 0, Qt.AlignTop)
        titres = QVBoxLayout()
        titres.setSpacing(2)
        self.name_label = QLabel("Pytest Runner")
        self.name_label.setObjectName("PageTitle")
        self.version_label = QLabel(f"Version {__version__}")
        self.version_label.setObjectName("Muted")
        titres.addWidget(self.name_label)
        titres.addWidget(self.version_label)
        titres.addStretch(1)
        entete.addLayout(titres, 1)
        racine.addLayout(entete)

        self.description_label = QLabel(
            "Collect, run and analyze pytest suites, including runs on several "
            "smart-card readers at the same time.")
        self.description_label.setWordWrap(True)
        racine.addWidget(self.description_label)

        self.author_label = QLabel(f"Created by <b>{AUTHOR}</b>")
        self.author_label.setTextFormat(Qt.RichText)
        racine.addWidget(self.author_label)
        self.copyright_label = QLabel(AUTHOR_COPYRIGHT)
        self.copyright_label.setObjectName("Muted")
        racine.addWidget(self.copyright_label)
        self.environment_label = QLabel(_environnement())
        self.environment_label.setObjectName("Faint")
        self.environment_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        racine.addWidget(self.environment_label)

        boutons = QDialogButtonBox()
        self.guide_button = QPushButton("Open the user guide")
        self.guide_button.clicked.connect(self._open_guide)
        boutons.addButton(self.guide_button, QDialogButtonBox.ActionRole)
        fermer = boutons.addButton(QDialogButtonBox.Close)
        fermer.clicked.connect(self.close)
        racine.addWidget(boutons)

    def _open_guide(self):
        if self.window_ is not None and hasattr(self.window_, "open_help"):
            self.window_.open_help("about")
