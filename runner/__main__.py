"""Point d'entree : `python -m runner`."""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app_icon import install_application_icon, set_windows_app_user_model_id
from runner.ui.main_window import APP, ORG, MainWindow
from runner.ui.theme import app_stylesheet


def main(argv: list[str] | None = None) -> int:
    # A declarer AVANT la QApplication : sur un ecran 4K a 150 %, sans cela
    # l'interface est dessinee en basse resolution puis etiree, et tout est
    # flou.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    set_windows_app_user_model_id()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)
    install_application_icon(app)
    app.setStyleSheet(app_stylesheet())

    fenetre = MainWindow()
    fenetre.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
