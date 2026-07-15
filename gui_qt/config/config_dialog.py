from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton
from .config_editor import ConfigEditor
from pathlib import Path

from ..styles.styles import toolbar_button


class ConfigDialog(QDialog):
    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Project configuration")
        self.resize(700, 500)

        self.editor = ConfigEditor()
        self.editor.load(config_path)

        self.close_button = QPushButton("Close")

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(self.close_button)
        self.close_button.setStyleSheet(toolbar_button())

        self.close_button.clicked.connect(self.accept)
