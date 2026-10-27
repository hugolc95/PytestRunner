---
name: run-app
description: Lance Pytest Runner (PySide6) isolé des réglages de l'utilisateur, le pilote (collecte, run, pause, pages, thèmes) et rapporte captures, chronos et erreurs ; peut filmer la vraie fenêtre Windows pour les défauts visuels qui ne durent qu'une image. À utiliser pour vérifier une modification de l'interface dans la vraie application (pas seulement dans les tests), avant une release, ou pour reproduire un défaut visuel signalé.
---

# Lancer et vérifier Pytest Runner

Les tests unitaires ne suffisent pas ici : au démarrage, `clean_ui`,
`end_run_feedback`, `main_ux` et `runtime_polish` remplacent des méthodes de
`MainWindow` et de `ReaderRun`. Un changement de signature passe les tests du
domaine mais casse l'application réelle. Toute modification de `runner/ui`,
`runner/services` ou du protocole pytest (`reader_isolation`, `parsing`) se
vérifie avec ce skill.

## Le script

`.claude/skills/run-app/scripts/drive.py`, toujours avec `C:\Python312\python.exe`
(le seul Python qui a PySide6 ; `.venv` est l'ancien PyQt5 32 bits).

Il reproduit le démarrage de `python -m runner`, modules d'installation compris,
et isole tout : réglages (`QSettings`, sinon écrits dans le registre de
l'utilisateur), profils, tests désactivés et historique vont dans un dossier
temporaire. Ne jamais lancer l'application à la main avec un `QSettings` non
isolé pour « tester vite ».

```bash
# Vérification courante, sans fenêtre (≈ 15 s)
C:/Python312/python.exe .claude/skills/run-app/scripts/drive.py --workspace testSuite1 --out <scratchpad>/run-app

# Avant une release : toutes les pages et les trois thèmes
C:/Python312/python.exe .claude/skills/run-app/scripts/drive.py --workspace testSuite1 --out <dossier> --pages --themes

# Pause / reprise avec lecteurs, vraie fenêtre filmée, à la taille de l'utilisateur
C:/Python312/python.exe .claude/skills/run-app/scripts/drive.py --workspace <ws avec lecteurs> --out <dossier> --mode real --record --pause --size 930x990
```

Options : `--no-run` (collecte seule), `--pause`, `--pages`, `--themes`,
`--font-size N` (taille de texte des préférences), `--size LxH`,
`--time-scale` (accélère `demo_queue_workspace`, 0.15 par défaut),
`--timeout`.

Workspaces du dépôt :
- `testSuite1` : 38 tests, succès / échecs / skip / erreur, paramétrés.
- `demo_queue_workspace` : longs tests réguliers, pour Pause, Stop et la file.
- `demo_workspace` : **sans `pytest.ini`**, ses nodeids partent de la racine du
  dépôt et les runs échouent (« file or directory not found ») ; à éviter.
- Pour des lecteurs sans matériel : copier `demo_queue_workspace` dans le
  scratchpad et y écrire un `config.yaml` avec `Reader :` et `Readers :`.

## Lire le résultat

Le script écrit `report.txt` dans `--out` et le rejoue sur la sortie :
statut après collecte et après run, chronos, captures, boîtes de dialogue
fermées automatiquement, messages Qt, erreurs. Il sort en code 1 s'il y a
des erreurs ou un délai dépassé.

- Regarder les captures (`NN_nom.png`) avec Read, en particulier `finished`
  et la zone modifiée. En mode `offscreen`, les polices viennent de
  `C:/Windows/Fonts` : le rendu est fidèle.
- « This plugin does not support raise() / propagateSizeHints() » en
  `offscreen` est sans importance.
- Une erreur `TypeError ... unexpected keyword argument` dans un fil de run
  signale presque toujours un module d'installation, ou un faux `ReaderRun`
  de test, resté sur l'ancienne signature.

## Défauts visuels transitoires

Un bouton qui « bouge puis revient » ne se voit pas sur une capture prise
après coup : il faut filmer. `--mode real --record` garde chaque image qui
change (~25 ms). Puis :

```bash
C:/Python312/python.exe .claude/skills/run-app/scripts/contact_sheet.py --frames <dossier> --crop x,y,largeur,hauteur
```

donne des planches légendées de la zone, une ligne par état visible distinct.
Chercher l'image intermédiaire (deux boutons empilés, un contrôle décalé).
Prévenir l'utilisateur avant le mode `real` : une fenêtre s'ouvre sur son
écran pendant quelques secondes et il ne doit pas cliquer dedans.

Si le défaut n'apparaît que chez l'utilisateur, filmer SA fenêtre pendant
qu'il clique : même principe, en cherchant la fenêtre par son titre
(`Pytest Runner …`) avec `EnumWindows`, et en le prévenant de garder la
fenêtre au premier plan.
