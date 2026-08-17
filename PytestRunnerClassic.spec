# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour l'ANCIENNE interface (main_qt.py + gui_qt/).

Meme principe que la recette courante : l'exe ne contient que l'interface,
pytest reste du cote de l'interpreteur des tests.

Cette interface reste construite tant que la nouvelle n'a pas fait ses
preuves a l'usage. Elle porte un nom distinct pour que les deux dossiers
puissent cohabiter dans dist/ sans que l'un ecrase l'autre.

Build :
    build_exe.bat classic
Resultat :
    dist/PytestRunnerClassic/PytestRunnerClassic.exe
"""

import sys

sys.path.insert(0, SPECPATH)  # noqa: F821 - injecte par PyInstaller

from build_common import EXCLUDES, EXCLUDES_CLASSIC

a = Analysis(
    ["main_qt.py"],
    pathex=[],
    binaries=[],
    # config.yaml n'est PAS embarque : il est lu dans le workspace de
    # l'utilisateur, pas a cote de l'exe.
    datas=[],
    hiddenimports=["yaml"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES + EXCLUDES_CLASSIC,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PytestRunnerClassic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    name="PytestRunnerClassic",
)
