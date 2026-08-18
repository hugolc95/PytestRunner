# Campagnes automatiques dans l'interface principale

Une campagne n'est plus un mode ou une fenetre separee. L'utilisateur charge
son workspace, coche ses tests et utilise toujours **Run tests**.

Quand un fichier `campaign.yml` couvre les tests selectionnes, Pytest Runner :

1. affiche un badge discret `CAMPAIGN` sur la Test Suite concernee ;
2. execute automatiquement chaque setup et son batch pytest dans l'ordre YAML ;
3. conserve le pire verdict dans le tree si le meme test est rejoue ;
4. ajoute les filtres `All / Configuration A / Configuration B` dans Detail,
   Output et Logs, uniquement pour ce run ;
5. fige les logs apres chaque configuration afin que la suivante ne les
   ecrase pas dans l'interface.

Les tests qui ne sont couverts par aucune campagne gardent exactement le
fonctionnement pytest habituel. Une selection mixte commence par ces tests,
puis execute les campagnes detectees.

## Pourquoi

Certaines suites ne sont valides qu'avec la sequence decrite par leur YAML.
Les lancer directement les unes apres les autres donnerait des resultats faux.
La contrainte reste donc dans le moteur, sans ajouter un nouveau geste dans
l'interface.

## Principe

Une campagne permet de lancer une suite sous plusieurs configurations.

Exemple :

1. script de config A
2. tests pytest associes
3. script de config B
4. les memes tests ou d'autres tests

## Exemple fourni

Le fichier `campaign.example.yml` utilise des nodeids de faux environnement de type :

```yaml
testSuite1/test_api.py::test_login[admin]
```

Deux scripts de configuration bidon sont fournis :

- `scripts/campaign_config_a.py`
- `scripts/campaign_config_b.py`

Ils creent simplement un fichier `campaign_active_config.txt` avec `CONFIG_A` ou `CONFIG_B`.

## Format supporte

```yaml
name: My campaign
workspace: .

scenarios:
  - name: Config A
    setup: scripts/campaign_config_a.py
    tests:
      - testSuite1/test_api.py::test_login[admin]
      - nodeid: testSuite1/test_api.py::test_login[user]
        repeat: 2

  - name: Config B
    setup: scripts/campaign_config_b.py
    tests:
      - testSuite1/test_api.py::test_login[admin]
      - nodeid: testSuite1/test_api.py::test_login[user]
        repeat: 2
```

`setup` peut etre :

- un script Python : `scripts/campaign_config_a.py`
- une commande : `python scripts/setup.py --target dev`
- un nodeid pytest : `testSuite1/test_setup.py::test_apply_config`

## Exécution groupée par configuration

Le mode Campaign lance maintenant **un seul processus pytest par scénario/configuration**.

Ordre d'exécution :

1. setup/config du scénario
2. un seul `pytest` contenant tous les tests sélectionnés du scénario
3. scénario suivant

Exemple logique :

```bash
python scripts/campaign_config_a.py
python -m pytest testSuite1/test_api.py::test_login[admin] testSuite1/test_api.py::test_login[user] testSuite1/test_math.py::test_compute[case_1] --keep-duplicates --import-mode=importlib --tb=no -v

python scripts/campaign_config_b.py
python -m pytest testSuite1/test_api.py::test_login[admin] testSuite1/test_api.py::test_login[user] testSuite1/test_math.py::test_compute[case_1] --keep-duplicates --import-mode=importlib --tb=no -v
```

Ça évite de relancer pytest pour chaque test et donne un résultat pytest global par config.

## Imports stables / PYTHONPATH forcé

Le mode Campaign force maintenant le `PYTHONPATH` pour tous les subprocess :

- setup lancé comme script Python
- setup lancé comme test pytest
- batch pytest des tests du scénario

Le workspace résolu est toujours ajouté automatiquement au `PYTHONPATH`.
Tu peux ajouter d'autres dossiers avec `pythonpath:`.

Pour une architecture comme :

```text
test/
└─ TSu/
   └─ TestSuite1/
      ├─ Define/
      ├─ Campaign/
      │  └─ campaign.yml
      ├─ Tests/
      └─ conftest.py
```

utilise :

```yaml
workspace: ../../..

pythonpath:
  - .
  - TSu/TestSuite1
```

Cela permet de garder les deux styles d'import existants :

```python
from TSu.TestSuite1.Define import *
from conftest import *
```

Les chemins `setup:` et `tests:` restent relatifs au workspace :

```yaml
setup: TSu/TestSuite1/Define/test_config_a.py::test_apply_config_a

tests:
  - TSu/TestSuite1/Tests/test_xxx.py::test_something[param]
```

Si `setup:` contient `::` ou pointe vers un fichier `test_*.py`, il est lancé avec pytest.
Sinon, un `.py` classique est lancé comme script Python.
