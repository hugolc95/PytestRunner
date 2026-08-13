from pathlib import Path

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QPushButton, QSizeGrip, QVBoxLayout

from gui_qt.config.config_editor import ConfigEditor
from gui_qt.styles.styles import toolbar_button

# La taille choisie est memorisee : une configuration fournie se consulte
# souvent, et redimensionner la fenetre a chaque ouverture serait penible.
GEOMETRY_KEY = "config_dialog_geometry"


class ConfigDialog(QDialog):
    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)

        self.settings = QSettings("MyCompany", "PyTestRunner")

        self.setWindowTitle(f"Configuration - {Path(config_path).name}")
        # Une QDialog n'a par defaut ni bouton d'agrandissement ni bouton de
        # reduction : sur un fichier de configuration fourni, on veut pouvoir
        # la mettre en plein ecran.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(520, 320)

        self.editor = ConfigEditor()
        self.editor.load(config_path)

        self.close_button = QPushButton("Close")
        self.close_button.setStyleSheet(toolbar_button())
        self.close_button.clicked.connect(self.accept)

        barre = QHBoxLayout()
        barre.addStretch(1)
        barre.addWidget(self.close_button)
        barre.addWidget(QSizeGrip(self), 0, Qt.AlignBottom | Qt.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self.editor)
        layout.addLayout(barre)

        self._restore_geometry()

    def _restore_geometry(self):
        sauvegarde = self.settings.value(GEOMETRY_KEY)
        if sauvegarde is not None:
            self.restoreGeometry(sauvegarde)
        else:
            self.resize(820, 620)

    def closeEvent(self, event):
        self.settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)

    def accept(self):
        self.settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        super().accept()

    def reject(self):
        self.settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        super().reject()
