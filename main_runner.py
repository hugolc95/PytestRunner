"""Point d'entree de l'application empaquetee PySide6 x64.

PyInstaller a besoin d'un script, pas d'un module.  La couche de compatibilite
est installee avant le moindre import de l'interface afin que tous les modules
existants continuent de fonctionner pendant la migration PyQt5 -> PySide6.
"""

import sys

from qt_compat import install_pyqt5_compat

install_pyqt5_compat()

from runner.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
