# Pytest Runner GUI

## Pause et reprise d’un run (version d’essai)

Pendant un run, **Pause** prend la place du bouton Run. Le statut existant
affiche **Pause requested — waiting for the current test to finish** : chaque test déjà démarré
termine son exécution et son nettoyage. Quand tous les lecteurs attendent,
le statut devient **Paused · N tests**, avec une icône pause fixe, et **Resume** reprend au prochain test dans le
même run, sans réexécuter les précédents ni recréer la session pytest.
**Cancel pause** permet d’annuler la demande avant la pause effective.

Les profils conservent leur étape, répétition et tentative. La configuration
et la sélection restent verrouillées, la file d’attente attend, et **Stop**
reste disponible. Le compteur de temps affiché est suspendu pendant la pause.
La reprise nécessite de garder l’application ouverte. Les lancements de
stress conservent leurs commandes habituelles.

## Désactivation des tests (version d’essai)

Dans **Run Tests**, clic droit sur un test → **Deactivate test…**, ou sur un dossier,
un fichier, une classe ou un test paramétré → **Deactivate group…**. La raison est
optionnelle. Pour un cas paramétré, on peut désactiver ce cas seul ou tous les
cas du test, y compris les futurs paramètres. Le symbole ⊘ remplace l’icône du
test, sans ajouter de colonne. Les tests désactivés restent visibles et ne
peuvent plus être cochés.

Un bouton ⊘ dans la barre d’outils de l’arbre apparaît uniquement lorsqu’il
existe des désactivations. Il ouvre **Deactivated tests**, avec le motif, la date,
une case d’activation directe et **Deactivate a test or group…**. L’auteur reste disponible
dans les détails et les infobulles. Les décisions sont enregistrées localement
dans le dossier utilisateur de l’application, par workspace, indépendamment du
YAML et de l’onglet de run ; aucun fichier de test n’est modifié.

Les profils contenant une étape désactivée sont bloqués et les runs en attente
sont revérifiés avant leur démarrage. Les tests désactivés sont exclus avant
exécution, sans créer de faux verdict pytest « skipped ». La désactivation ne
concerne que les lancements depuis cette application. Arrêter les exécutions
du workspace avant d’en changer les désactivations ; la réactivation est
manuelle et n’entraîne pas de nouvelle sélection automatique.
Une règle de groupe couvre aussi les futurs tests de ce groupe. Réactiver le
groupe conserve les désactivations individuelles déjà enregistrées séparément.
Un test ou sous-groupe peut être réactivé seul dans un groupe désactivé : cette
exception est conservée au redémarrage et les autres tests restent désactivés.
La fenêtre présente les membres des groupes avec leur case d’activation. Ses
boutons **Activate all** et **Deactivate all** agissent sur tous les éléments de la
liste, y compris ceux qui viennent d’être réactivés tant que la fenêtre reste ouverte.
Cette fenêtre conserve les niveaux fichier `.py`, classe et test paramétré avant
les cas individuels. Cocher un groupe y réactive tous ses éléments ; une case
avec un tiret indique une activation partielle.

## Navigation dans les erreurs — v1.2.0

Les références fichier/ligne sont cliquables dans **Detail**, l’historique,
**Console** et les détails des erreurs de collection. Un fichier Python du
workspace ouvert s’affiche dans **Source**, à la ligne et à la colonne indiquées.
Le bouton **Back to traceback** retourne à la vue d’origine. Le saut dans un
fichier déjà affiché conserve son édition ; une sauvegarde échouée empêche de
remplacer le fichier en cours.

Les dépendances, fichiers externes et projets historiques qui ne sont plus
chargés s’ouvrent dans un IDE. **Ctrl+clic** force cette ouverture. Le menu du
clic droit propose aussi **Copy file:line** et **Locate file…** pour retrouver
un fichier déplacé sans modifier les anciens résultats.

Dans **Settings → External editor**, choisir **Automatic**, **VS Code** ou
**PyCharm**, et éventuellement renseigner les exécutables. En automatique,
VS Code est essayé avant PyCharm ; un éditeur préféré absent laisse place à
l’autre. Si aucun éditeur n’est trouvé ou qu’un chemin configuré est invalide,
une erreur visible indique comment corriger le réglage.

L’IDE reçoit le projet et le fichier avec sa ligne : ses mécanismes habituels
réutilisent le projet ouvert. VS Code reconnaît aussi les fichiers
`.code-workspace` correspondants, y compris avec plusieurs dossiers.
Les politiques de fenêtres propres à l’IDE restent applicables.
Une référence ambiguë ou provenant d’un autre ordinateur est signalée plutôt
que résolue uniquement par le nom du fichier ; une ligne disparue est signalée
dans Source.

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

L'interface peut être distribuée en application autonome, sans installer Python sur le poste.

**➜ [Télécharger la dernière version](https://github.com/hugolc95/PytestRunner/releases/tag/latest)** (`PytestRunner-windows.zip`)

Ce lien est permanent et pointe toujours vers le dernier build. Chaque push reconstruit l'application sur une machine Windows, y rejoue la suite de tests, vérifie que l'exécutable démarre, puis met la release à jour.

Pour construire soi-même : `build_exe.bat` (nécessite PyQt5, PyYAML et PyInstaller).

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
