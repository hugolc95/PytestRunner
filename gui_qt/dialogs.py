# gui_qt/dialogs.py
#
# Boite de dialogue d'erreur redimensionnable et defilante.
#
# Motivation : QMessageBox.critical() s'agrandit sans limite pour afficher tout
# son texte, sans barre de defilement. Sur une erreur de collecte pytest (gros
# traceback multi-lignes), la fenetre depasse l'ecran et devient illisible,
# surtout sur des ecrans plus petits. On affiche donc les messages potentiellement
# longs dans un QTextEdit defilant, dans une fenetre bornee a la taille de l'ecran.

import os

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QApplication,
    QMessageBox,
)
from PyQt5.QtCore import Qt

from gui_qt.styles.styles import primary_button, neutral_button
from gui_qt.config.config_loader import find_test_log, resolve_log_root


def show_scrollable_error(parent, title: str, message: str, intro: str | None = None):
    """Affiche un message d'erreur (potentiellement long) dans une fenetre
    redimensionnable et defilante, jamais plus grande que l'ecran."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)

    layout = QVBoxLayout(dialog)

    if intro:
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setLineWrapMode(QTextEdit.NoWrap)
    text_edit.setPlainText(message or "(aucun detail)")
    layout.addWidget(text_edit)

    button_bar = QHBoxLayout()
    copy_button = QPushButton("Copier")
    copy_button.setStyleSheet(neutral_button())
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(message or ""))

    close_button = QPushButton("Fermer")
    close_button.setStyleSheet(primary_button())
    close_button.clicked.connect(dialog.accept)

    button_bar.addWidget(copy_button)
    button_bar.addStretch()
    button_bar.addWidget(close_button)
    layout.addLayout(button_bar)

    # Taille de depart raisonnable, bornee a l'ecran pour ne jamais deborder.
    screen = QApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(820, available.width() - 80)
        height = min(560, available.height() - 80)
        dialog.resize(max(width, 320), max(height, 200))
    else:
        dialog.resize(820, 560)

    dialog.exec_()


def _startfile(parent, path) -> bool:
    """Ouvre un fichier/dossier avec l'application par defaut de Windows.
    Retourne True si l'ouverture a ete tentee, False sinon (plateforme non geree)."""
    try:
        os.startfile(str(path))
        return True
    except AttributeError:
        QMessageBox.information(
            parent,
            "Non supporte",
            f"Ouverture automatique non disponible sur cette plateforme.\nChemin : {path}",
        )
        return False
    except OSError as exc:
        QMessageBox.critical(parent, "Erreur", f"Impossible d'ouvrir :\n{exc}")
        return True


def open_test_log_for(parent, workspace: str, nodeid: str):
    """Ouvre le fichier .log du dernier run pour ce test (via le manifeste ecrit par
    le conftest). A defaut : ouvre le dossier racine des logs s'il existe, sinon
    informe qu'aucun log n'a encore ete produit. Partage entre les onglets Workspace
    et Campaign."""
    log_path = find_test_log(workspace, nodeid)
    if log_path is not None:
        _startfile(parent, log_path)
        return

    log_root = resolve_log_root(workspace)
    if log_root.is_dir():
        QMessageBox.information(
            parent,
            "Log introuvable",
            "Aucun log pour ce test precis dans le dernier run.\n"
            f"Ouverture du dossier des logs :\n{log_root}",
        )
        _startfile(parent, log_root)
    else:
        QMessageBox.information(
            parent,
            "Aucun log",
            "Aucun log n'a encore ete produit pour ce workspace.\n"
            "Lancez d'abord ce test (le conftest cree un .log par test execute).",
        )
