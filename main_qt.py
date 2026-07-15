import os
import sys

from PyQt5.QtWidgets import QApplication
from gui_qt.main_window import MainWindow
from gui_qt.styles.styles import app_stylesheet


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(app_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
