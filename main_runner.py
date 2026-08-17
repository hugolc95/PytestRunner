"""Point d'entree de l'application empaquetee.

PyInstaller a besoin d'un script, pas d'un module : ce fichier ne fait que
rendre `python -m runner` lancable sous forme d'exe.
"""

import sys

from runner.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
