from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel
)
from pathlib import Path
from .config_loader import load_yaml, save_yaml
import yaml

from ..styles.styles import toolbar_button


class ConfigEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.path: Path | None = None

        self.title = QLabel("Project configuration")
        self.editor = QTextEdit()
        self.save_button = QPushButton("Save config")
        self.save_button.setStyleSheet(toolbar_button())

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.editor)
        layout.addWidget(self.save_button)

        self.save_button.clicked.connect(self.save)

    def load(self, path: Path):
        self.path = path
        data = load_yaml(path)
        self.editor.setPlainText(
            yaml.safe_dump(data, sort_keys=False)
        )

    def save(self):
        if not self.path:
            return

        data = yaml.safe_load(self.editor.toPlainText())
        save_yaml(self.path, data)
