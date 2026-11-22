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
- Plantages natifs PySide (corrigés en 1.8.0, ne pas les réintroduire) :
  - jamais `combo.model().item(i)` : l'enveloppe `QStandardItem` survit à
    `combo.clear()`, et un objet alloué ensuite à la même adresse (un
    `QEvent`, un modèle) est pris pour elle → segfault. Passer par
    `setItemData` / `model().flags(...)` (voir `_refresh_profile_picker`) ;
  - jamais `layout.itemAt(i)` dans l'application pour retrouver un widget
    ou un sous-layout : même piège avec `QWidgetItem` quand le widget est
    retiré ou reparenté. Garder une référence (`navigation_utilities`) ;
    dans les tests, `qt_helpers.widgets_du_layout` ;
  - un `eventFilter` ou un `event()` Python reçoit encore des événements
    pendant la destruction de la fenêtre : le décorer avec
    `qt_safety.tolerate_destruction` ;
  - `conftest.py` détruit les fenêtres d'un test à la fin de CE test
    (`DeferredDelete` + `gc.collect()`), après avoir attendu leurs threads.
  Un segfault restant se diagnostique avec `python -X faulthandler` et, sous
  Linux, `gdb -batch -ex run -ex bt --args python -m pytest …`.

## Guide d'utilisation

- Texte : `runner/ui/help_content.py` (rubriques en anglais, fragments HTML).
  Mise en page : `runner/ui/help_site.py`, site hors ligne d'un seul
  fichier, réécrit puis ouvert dans le navigateur par Help et F1 sur la
  rubrique de la page affichée (`CONTEXT_TOPICS`). Aucune ressource réseau.
- Une page ou un libellé de l'interface qui change : mettre la rubrique à
  jour. `test_help_page.py` vérifie les liens, la génération du site et que
  chaque libellé cité en gras existe encore dans `runner/ui` (une simple mise
  en valeur s'ajoute à `EMPHASE`).

## Livrer

Suivre le skill **release** : `codex/<sujet>`, version, README en français,
commit « …; release X.Y.Z », `main` avancé sans commit de merge, tag annoté,
push. La CI ne construit pas `main`.
