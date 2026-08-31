"""Point d'entree : `python -m runner` (PySide6 / Qt 6)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app_icon import install_application_icon, set_windows_app_user_model_id
from runner.ui.main_window import APP, ORG, WINDOW_TITLE, MainWindow
from runner.ui.theme import app_stylesheet
from runner.ui.clean_ui import install as install_clean_ui
from runner.ui.end_run_feedback import install as install_end_run_feedback
from runner.ui.main_ux import install as install_main_ux
from runner.version import __version__


def main(argv: list[str] | None = None) -> int:
    # Qt 6 gere nativement le High-DPI : les anciens attributs Qt5
    # AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps ne sont plus necessaires.
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

    fenetre = MainWindow()
    fenetre.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
