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

## Tests

- Suite complète : `python -m pytest runner/tests -q -n 6` (~6 min). La CI
  (`.github/workflows/ci.yml`) la lance sur main, `codex/**` et les PR.
- `runner/tests/conftest.py` isole automatiquement chaque test : tout
  `QSettings(ORG, APP)` (appli et tests) va dans un INI temporaire,
  `QStandardPaths` est en mode test et `history.dossier` est redirigé. Ne pas
  contourner cette fixture : sans elle, la suite effaçait les vrais réglages
  de l'utilisateur.
- Un test qui attend un sous-processus ou un minuteur attend une condition
  (boucle avec limite, `qtbot.waitUntil`), jamais un délai fixe : la suite
  tourne en parallèle et sous charge.
- Instabilités natives connues (PySide, objets Qt détruits encore référencés) :
  segfault intermittent de `test_profile_header_picker` (bascules rapides
  Tests / Profiles) et `QWidgetItem` à la place d'un modèle dans
  `ExecutionProfilesPage._build_ui`. Comparer avec `git stash` avant de
  conclure à une régression.

## Livrer

Suivre le skill **release** : `codex/<sujet>`, version, README en français,
commit « …; release X.Y.Z », `main` avancé sans commit de merge, tag annoté,
push. La CI ne construit pas `main`.
