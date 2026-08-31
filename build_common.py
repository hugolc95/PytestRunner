"""Reglages PyInstaller partages.

La GUI active est construite avec PySide6/Qt 6 en Python x64. Pytest et toutes
les dependances des tests restent hors de l'exe et sont executes par
l'interpreteur externe configure dans l'application (x86 ou x64).
"""

# Modules lourds ou inutiles a l'interface. QtWebEngine/Quick ne sont pas
# utilises par le Runner. On exclut aussi explicitement PyQt5 : meme s'il est
# installe sur le poste de build, il ne doit jamais etre embarque dans l'exe
# PySide6.
EXCLUDES = [
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtBluetooth",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "pytest",
    "_pytest",
    "xdist",
    "execnet",
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
]

# L'interface active n'embarque pas l'ancienne GUI PyQt5/classic.
EXCLUDES_CLASSIC = ["runner"]
EXCLUDES_RUNNER = ["gui_qt", "main_qt", "main_tk"]
