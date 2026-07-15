# Pytest Runner GUI — Python 3.13 32 bits, hors ligne

Application de bureau **PyQt5** permettant de charger un workspace, découvrir ses tests pytest, sélectionner des tests complets ou un seul cas paramétré, lancer/arrêter l'exécution, consulter les résultats et exécuter des campagnes YAML.

## Cible stricte

- Windows x86 / 32 bits ;
- CPython **3.13 32 bits** uniquement ;
- aucune connexion Internet nécessaire ;
- Python doit déjà être installé sur le poste.

Un Python 3.13 64 bits n'est pas utilisé par les scripts de cette édition.

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
