"""Point d'entree : `python -m runner`."""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app_icon import install_application_icon, set_windows_app_user_model_id
from runner.ui.main_window import APP, ORG, WINDOW_TITLE, MainWindow
from runner.ui.theme import app_stylesheet
from runner.ui.clean_ui import install as install_clean_ui
from runner.ui.end_run_feedback import install as install_end_run_feedback
from runner.ui.main_ux import install as install_main_ux
from runner.version import __version__


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
    app.setApplicationDisplayName(WINDOW_TITLE)
    app.setApplicationVersion(__version__)
    install_application_icon(app)
    app.setStyleSheet(app_stylesheet())

    # Evite les contours imbriques visibles sous Windows autour des petites
    # cases de resultat et du statut "Running...". Les informations restent
    # identiques, seule la presentation devient plus plate et plus propre.
    install_clean_ui()
    # Le dernier verdict peut preceder de peu la fin reelle du processus pytest.
    # Montrer alors "Finalizing" puis le resultat avant l'archivage rend la fin
    # du run immediate sans annoncer la fin tant que pytest travaille encore.
    install_end_run_feedback()
    # Selection des raffinements UX valides apres essai de la branche dediee.
    # Installe en dernier pour conserver uniquement les choix retenus sur main.
    install_main_ux()

    fenetre = MainWindow()
    fenetre.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
