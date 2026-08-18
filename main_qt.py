import os
import sys

from PyQt5.QtWidgets import QApplication

from app_icon import install_application_icon, set_windows_app_user_model_id
from gui_qt.main_window import MainWindow
from gui_qt.styles.styles import app_stylesheet


if __name__ == "__main__":
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    install_application_icon(app)
    app.setStyleSheet(app_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
