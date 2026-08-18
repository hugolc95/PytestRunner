# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour l'interface COURANTE (runner/).

L'exe ne contient QUE l'interface. Il n'embarque ni pytest, ni les dependances
des tests : ceux-ci sont lances dans un processus separe, avec l'interpreteur
Python configure dans l'application. C'est ce qui permet de distribuer une
interface unique quel que soit l'environnement Python des tests (32 ou 64
bits, venv projet, etc.).

Pour l'ancienne interface, voir PytestRunnerClassic.spec.

Build :
    build_exe.bat                     (ou : pyinstaller --clean --noconfirm PytestRunner.spec)
Resultat :
    dist/PytestRunner/PytestRunner.exe   (mode dossier, demarrage instantane)
"""

import sys

sys.path.insert(0, SPECPATH)  # noqa: F821 - injecte par PyInstaller

from PyInstaller.utils.hooks import collect_data_files

from build_common import EXCLUDES, EXCLUDES_RUNNER

# qtawesome porte ses pictogrammes dans des fichiers de police. Sans eux,
# l'interface se lance mais toutes les icones sont vides : le module gere ce
# cas sans planter, ce qui rend la panne d'autant plus discrete.
QTAWESOME_DATA = collect_data_files("qtawesome")
APP_ICON_DATA = [("assets/pytest_runner.ico", "assets")]


a = Analysis(
    ["main_runner.py"],
    pathex=[],
    binaries=[],
    # config.yaml n'est PAS embarque : il est lu dans le workspace de
    # l'utilisateur, pas a cote de l'exe.
    datas=QTAWESOME_DATA + APP_ICON_DATA,
    hiddenimports=["yaml", "qtawesome"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES + EXCLUDES_RUNNER,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PytestRunner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Application fenetree : pas de console noire derriere l'interface. Les
    # sous-processus pytest sont eux aussi lances sans console.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/pytest_runner.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PytestRunner",
)
