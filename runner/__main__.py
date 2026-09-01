"""Point d'entree : `python -m runner` (PySide6 / Qt 6)."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app_icon import install_application_icon, set_windows_app_user_model_id
from runner.ui.main_window import APP, ORG, WINDOW_TITLE, MainWindow
from runner.ui.theme import app_stylesheet
from runner.ui.clean_ui import install as install_clean_ui
from runner.ui.end_run_feedback import install as install_end_run_feedback
from runner.ui.main_ux import install as install_main_ux
from runner.ui.runtime_polish import install as install_runtime_polish
from runner.version import __version__


def main(argv: list[str] | None = None) -> int:
    # Qt 6 gere nativement le High-DPI. PassThrough evite cependant le dernier
    # arrondi de facteur d'echelle (125/150/175 % sous Windows) qui peut rendre
    # textes, traits de 1 px et icones legerement moins nets sur certains
    # ecrans. Ce reglage doit etre applique AVANT QApplication.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    set_windows_app_user_model_id()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORG)
    app.setApplicationName(APP)
    app.setApplicationDisplayName(WINDOW_TITLE)
    app.setApplicationVersion(__version__)
    install_application_icon(app)
    app.setStyleSheet(app_stylesheet())

    install_clean_ui()
    install_end_run_feedback()
    install_main_ux()
    install_runtime_polish()

    fenetre = MainWindow()
    fenetre.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
