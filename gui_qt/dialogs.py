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

from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QApplication,
    QMessageBox,
    QFileDialog,
    QInputDialog,
)
from PyQt5.QtCore import Qt

from gui_qt.styles.styles import primary_button, neutral_button
from gui_qt.config.config_loader import (
    STANDARD_CONFIG_NAMES,
    discover_config_candidates,
    find_test_log,
    resolve_log_root,
)


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


def resolve_config_to_open(parent, workspace: str, remembered: str | None = None) -> Path | None:
    """Determine quel fichier de configuration ouvrir pour ce workspace.

    Beaucoup de projets n'appellent pas leur configuration `config.yml`. Plutot
    que d'abandonner avec "No config.yaml found", on procede par ordre :

    1. le fichier deja choisi pour ce workspace, s'il existe toujours ;
    2. un nom standard (config.yaml / config.yml) present a la racine ;
    3. l'unique YAML de la racine, s'il n'y en a qu'un ;
    4. sinon on laisse l'utilisateur choisir (liste des YAML trouves, ou
       selecteur de fichiers si la racine n'en contient aucun).

    Retourne None si l'utilisateur annule.
    """
    if remembered:
        remembered_path = Path(remembered)
        if remembered_path.is_file():
            return remembered_path

    candidates = discover_config_candidates(workspace)

    for path in candidates:
        if path.name in STANDARD_CONFIG_NAMES:
            return path

    if len(candidates) == 1:
        return candidates[0]

    if candidates:
        names = [path.name for path in candidates]
        choice, accepted = QInputDialog.getItem(
            parent,
            "Choisir la configuration",
            f"Aucun fichier {STANDARD_CONFIG_NAMES[0]} dans ce workspace.\n"
            "Fichiers YAML trouves a la racine :",
            names,
            0,
            False,
        )
        if not accepted:
            return None
        return Path(workspace) / choice

    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Choisir le fichier de configuration",
        workspace,
        "Fichiers YAML (*.yml *.yaml);;Tous les fichiers (*)",
    )
    return Path(path) if path else None


def open_config_editor(parent, workspace: str, settings=None) -> None:
    """Ouvre l'editeur de configuration pour ce workspace.

    Le fichier retenu est memorise par workspace, pour que les clics suivants
    n'aient plus a demander. Partage entre les onglets Workspace et Campaign.
    """
    from gui_qt.config.config_dialog import ConfigDialog

    key = f"config_file/{workspace}"
    remembered = settings.value(key, "", type=str) if settings is not None else ""

    config_path = resolve_config_to_open(parent, workspace, remembered)
    if config_path is None:
        return

    if settings is not None:
        settings.setValue(key, str(config_path))

    ConfigDialog(config_path, parent).exec_()


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


def remembered_config_path(workspace: str, settings) -> str:
    """Fichier de configuration deja retenu pour ce workspace, ou "".

    C'est lui qui porte LOG_PATH dans les projets dont la configuration ne
    s'appelle pas config.yml.
    """
    if settings is None or not workspace:
        return ""
    return settings.value(f"config_file/{workspace}", "", type=str)


def open_test_log_for(parent, workspace: str, nodeid: str, config_path: str | None = None):
    """Ouvre le fichier .log du dernier run pour ce test (via le manifeste ecrit par
    le conftest). A defaut : ouvre le dossier racine des logs s'il existe, sinon
    informe qu'aucun log n'a encore ete produit. Partage entre les onglets Workspace
    et Campaign."""
    log_path = find_test_log(workspace, nodeid, config_path)
    if log_path is not None:
        _startfile(parent, log_path)
        return

    log_root = resolve_log_root(workspace, config_path)
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
