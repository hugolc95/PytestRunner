from pathlib import Path

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from gui_qt.config.config_editor import ConfigEditor
from gui_qt.styles.styles import toolbar_button


class ConfigDialog(QDialog):
    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Configuration - {Path(config_path).name}")
        self.resize(780, 600)

        self.editor = ConfigEditor()
        self.editor.load(config_path)

        self.close_button = QPushButton("Fermer")
        self.close_button.setStyleSheet(toolbar_button())
        self.close_button.clicked.connect(self.accept)

        barre = QHBoxLayout()
        barre.addStretch(1)
        barre.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addLayout(barre)
