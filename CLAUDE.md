# Pytest Runner

Application de bureau PySide6 (Qt 6, Python 64 bits) qui collecte et lance des
suites pytest, souvent sur plusieurs lecteurs de cartes à puce (HubReader,
ATR, APDU). L'interface n'importe jamais le code testé : pytest tourne dans un
sous-processus, avec l'interpréteur configuré pour les tests.

## Code

- `runner/` est l'application active : `domain/` (sans Qt), `services/`
  (fils et signaux), `ui/`. `core/`, `gui_qt/`, `tests/` et `main_tk.py` sont
  l'ancienne version PyQt5, à ne pas modifier.
- Écrire comme le code autour : commentaires et docstrings en français, sans
  accents dans le code, qui expliquent le **pourquoi** (souvent un bug réel
  évité) ; libellés de l'interface en anglais.
- **Modules d'installation.** Au démarrage, `runner/ui/clean_ui.py`,
  `end_run_feedback.py`, `main_ux.py` et `runtime_polish.py` remplacent des
  méthodes de `MainWindow`, `TestTreeModel` et `ReaderRun`, avec des
  signatures figées. Changer la signature d'une de ces méthodes oblige à
  mettre à jour le remplaçant (et les faux de test, comme `_FauxRun` dans
  `test_readers.py`). Les tests du domaine ne le voient pas : vérifier dans
  l'application avec le skill **run-app**.
- Le plugin pytest du runner est une chaîne de source dans
  `runner/domain/reader_isolation.py` : y écrire `"\\n"` et non `"\n"`.

## Environnement

- Python de l'application et des tests : `C:\Python312\python.exe` (64 bits,
  PySide6, pytest-qt, xdist). `.venv` est l'ancien PyQt5 32 bits.
- Tests : `QT_QPA_PLATFORM=offscreen` ; `runner/tests` (pas `tests/`).
- `pytest.ini` à la racine cible `testSuite1` (workspace de démonstration),
  pas les tests de l'application.

## Tests : prudence

- La suite complète prend ~10 min. Plusieurs fixtures appellent
  `QSettings(ORG, APP).clear()` et **effacent les vrais réglages de
  l'utilisateur** : demander avant de la lancer, et préférer les fichiers
  ciblés, en série, un par commande avec `timeout`.
- Un nouveau test isole ses réglages (fixture `window` avec un `QSettings`
  INI dans `tmp_path`, `history.dossier` redirigé) et ne touche jamais à
  `QSettings(ORG, APP)`.
- Des tests échouent déjà ou sont instables (parallélisme, plantage natif
  intermittent de `test_profile_header_picker`) : comparer avec
  `git stash` avant de conclure à une régression.

## Livrer

Suivre le skill **release** : `codex/<sujet>`, version, README en français,
commit « …; release X.Y.Z », `main` avancé sans commit de merge, tag annoté,
push. La CI ne construit pas `main`.
