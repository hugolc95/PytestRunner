# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour l'interface Pytest Runner.

Construit l'interface courante (runner/). L'ancienne (main_qt.py + gui_qt/)
reste dans le depot et se lance par `python main_qt.py` ; pour en rebuilder
l'exe a l'identique :
    git checkout v1.0-classic && build_exe.bat

L'exe ne contient QUE l'interface. Il n'embarque ni pytest, ni les dependances
des tests : ceux-ci sont lances dans un processus separe, avec l'interpreteur
Python configure dans le menu Configuration. C'est ce qui permet de distribuer
une interface unique quel que soit l'environnement Python des tests (32 ou
64 bits, venv projet, etc.).

Build :
    pyinstaller --clean --noconfirm PytestRunner.spec
Resultat :
    dist/PytestRunner/PytestRunner.exe   (mode dossier, demarrage instantane)
"""

# Modules lourds ou inutiles a l'interface. QtWebEngine pese a lui seul plusieurs
# centaines de Mo ; pytest et ses dependances vivent cote interpreteur des tests.
EXCLUDES = [
    "PyQt5.QtWebEngine",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebKit",
    "PyQt5.QtWebKitWidgets",
    "PyQt5.QtBluetooth",
    "PyQt5.QtDesigner",
    "PyQt5.QtHelp",
    "PyQt5.QtLocation",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNfc",
    "PyQt5.QtOpenGL",
    "PyQt5.QtPositioning",
    "PyQt5.QtQml",
    "PyQt5.QtQuick",
    "PyQt5.QtQuick3D",
    "PyQt5.QtQuickWidgets",
    "PyQt5.QtSensors",
    "PyQt5.QtSerialPort",
    "PyQt5.QtSql",
    "PyQt5.QtTest",
    "PyQt5.QtTextToSpeech",
    "PyQt5.QtWebChannel",
    "PyQt5.QtWebSockets",
    "PyQt5.QtXmlPatterns",
    "pytest",
    "_pytest",
    "xdist",
    "execnet",
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
]


# qtawesome porte ses pictogrammes dans des fichiers de police. Sans eux,
# l'interface se lance mais toutes les icones sont vides : le module gere ce
# cas sans planter, ce qui rend la panne d'autant plus discrete.
from PyInstaller.utils.hooks import collect_data_files

QTAWESOME_DATA = collect_data_files("qtawesome")


a = Analysis(
    ["main_runner.py"],
    pathex=[],
    binaries=[],
    # config.yaml n'est PAS embarque : il est lu dans le workspace de
    # l'utilisateur, pas a cote de l'exe.
    datas=QTAWESOME_DATA,
    hiddenimports=["yaml", "qtawesome"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
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
    # sous-processus pytest sont eux aussi lances sans console (subprocess_flags).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
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
