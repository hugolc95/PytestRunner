"""Reglages partages par les deux recettes PyInstaller.

Les deux interfaces vivent dans le meme depot et excluent les memes modules.
Recopier la liste dans chaque `.spec` la ferait diverger a la premiere
correction : l'une des deux embarquerait QtWebEngine sans que personne ne s'en
apercoive avant de peser le dossier produit.
"""

# Modules lourds ou inutiles aux interfaces. QtWebEngine pese a lui seul
# plusieurs centaines de Mo ; pytest et ses dependances vivent cote
# interpreteur des tests, dans un processus separe.
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

# Chaque interface ignore l'autre. Les deux cohabitent dans le depot mais
# n'ont aucun lien : sans ces exclusions, PyInstaller suivrait un import
# oublie et embarquerait les deux dans le meme exe.
EXCLUDES_CLASSIC = ["runner"]
EXCLUDES_RUNNER = ["gui_qt", "main_tk"]
