# Pytest Runner GUI

Application de bureau **PyQt5** permettant de charger un workspace, découvrir ses tests pytest, sélectionner des tests complets ou un seul cas paramétré, lancer/arrêter l'exécution, consulter les résultats et exécuter des campagnes YAML.

## Deux Python indépendants

L'interface **n'importe jamais** le code testé : elle lance pytest dans un sous-processus et lit sa sortie. L'interface et les tests peuvent donc utiliser deux interpréteurs Python différents.

C'est ce qui permet, par exemple, de piloter depuis une interface 32 bits des tests qui ont besoin d'un Python 64 bits pour charger des DLL natives.

L'interpréteur des tests se règle dans **Configuration > Interpréteur Python des tests...**. Cet interpréteur doit avoir `pytest` installé (et `pytest-xdist` si vous cochez *Parallel*) ; l'interface, elle, n'a besoin que de PyQt5 et PyYAML.

Ordre de priorité, du plus fort au plus faible :

1. la clé `python:` de `campaign.yml` (mode Campaign uniquement) ;
2. la clé `python_executable:` du `config.yaml` du workspace ;
3. le réglage global de l'application ;
4. le Python courant.

Laisser le réglage vide conserve le comportement historique : les tests tournent avec le Python de l'interface.

## Exécutable Windows

L'interface peut être distribuée en application autonome, sans installer Python sur le poste :

- **automatiquement** : chaque push déclenche le workflow *Build Windows executable*, qui publie l'application en artefact téléchargeable depuis l'onglet Actions du dépôt ;
- **localement** : `build_exe.bat` (nécessite PyQt5, PyYAML et PyInstaller).

Le résultat est le dossier `dist\PytestRunner\` : distribuez-le entier (zippé), pas seulement le `.exe`. L'exécutable ne contient que l'interface — pytest et les dépendances des tests restent du côté de l'interpréteur configuré, il faut donc toujours renseigner celui-ci au premier lancement.

## Installation hors ligne (mode source)

- Windows x86 / 32 bits ;
- CPython **3.13 32 bits** ;
- aucune connexion Internet nécessaire ;
- Python doit déjà être installé sur le poste.

## Démarrage

1. Extraire entièrement l'archive dans un dossier local.
2. Vérifier Python avec `py -0p` : une entrée `-3.13-32` doit être visible.
3. Double-cliquer sur `start.bat`.

Au premier lancement, le script crée `.venv` avec `py -3.13-32`, puis installe les dépendances exclusivement depuis `wheels/` avec `--no-index`.

## Fichiers BAT

- `start.bat` : installe si nécessaire puis lance l'interface ;
- `install_offline.bat` : recrée/installe l'environnement hors ligne ;
- `test_offline.bat` : installe les outils de test hors ligne et exécute la suite automatisée ;
- `diagnostic.bat` : affiche les versions Python et l'architecture détectées.

## Tests paramétrés

Les cas issus de `@pytest.mark.parametrize` sont affichés comme des feuilles distinctes et peuvent être lancés séparément :

```text
testSuite1/test_parametrized_selection.py
└── test_addition_parametree
    ├── [small]
    ├── [medium]
    └── [large]
```

Sélectionner uniquement `[medium]` lance précisément :

```text
testSuite1/test_parametrized_selection.py::test_addition_parametree[medium]
```

## Installation manuelle

```bat
py -3.13-32 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links=wheels -r requirements.txt
.venv\Scripts\python.exe main_qt.py
```

## Vérification

Double-cliquer sur `test_offline.bat`. La suite couvre notamment : découverte, collecte invalide, tests paramétrés sélectionnables individuellement, succès/échec/skip/error, arrêt d'un test long et campagnes YAML.
