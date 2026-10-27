---
name: release
description: Publie une version de Pytest Runner selon la convention du dépôt — branche codex/<sujet>, incrément de runner/version.py, section française du README, vérification (tests ciblés + run-app), commit « …; release X.Y.Z », avance de main sans commit de merge, tag annoté « Pytest Runner X.Y.Z - … », push et contrôle du tag distant. À utiliser quand l'utilisateur demande de committer / merger / publier / sortir une version, ou après une modification visible prête à livrer.
---

# Publier une version

Toute modification visible livrée sur `main` change `runner/version.py`
(patch par défaut ; mineure pour une vraie fonctionnalité). Ne rien pousser
sans que l'utilisateur l'ait demandé dans ce tour ou un précédent pour ce
travail précis.

## 1. Préparer

1. `git fetch origin` puis `git status -sb`. Travailler sur une branche
   `codex/<sujet-court>` créée depuis `origin/main` à jour. Si `main` a bougé
   pendant le travail, rebaser la branche dessus avant de continuer.
2. Version : lire `runner/version.py`, choisir X.Y.Z, vérifier qu'aucun tag
   `vX.Y.Z` n'existe (`git ls-remote --tags origin`).
3. README : ajouter **en tête** (juste sous `# Pytest Runner GUI`) une section
   `## <Titre> — vX.Y.Z` en français, qui décrit le comportement pour
   l'utilisateur (ce qu'il voit, où cliquer), pas l'implémentation. Les
   sections plus anciennes restent dessous.

## 2. Vérifier

- Tests ciblés des fichiers touchés, **en série**, avec `C:\Python312` et
  `QT_QPA_PLATFORM=offscreen`, un fichier par commande avec une limite
  (`timeout 240`) : un plantage natif ou un blocage ne doit pas emporter le
  reste.
- Ne lancer la suite complète (`runner/tests`, ~10 min) que si l'utilisateur
  l'accepte : plusieurs fixtures effacent ses vrais réglages
  (`QSettings(ORG, APP).clear()`). Le dire avant.
- Distinguer les régressions des échecs déjà présents : relancer un échec
  avec `git stash` pour comparer, et lancer en série ce qui échoue en
  parallèle (`-n`), qui est instable chez nous.
- Si `runner/ui`, `runner/services` ou le protocole pytest ont changé :
  passer par le skill **run-app** (au minimum la vérification courante).

## 3. Committer et publier

Ne committer que les fichiers du travail : jamais `.idea/`, les fichiers
`~$*.xlsx`, `build/`, `dist/`, `logs/` ni les sorties du scratchpad.

Message de commit : un titre en anglais à l'impératif, terminé par
`; release X.Y.Z`, puis un corps qui liste les changements visibles, puis la
ligne d'attribution demandée par l'environnement.

```bash
git add <fichiers du travail>
git commit -F <message>
git switch main
git merge --ff-only codex/<sujet>          # jamais de commit de merge
git tag -a vX.Y.Z -m "Pytest Runner X.Y.Z - <résumé court>"
git push origin codex/<sujet> main vX.Y.Z
```

Si `--ff-only` refuse, `main` a reçu d'autres commits : revenir sur la
branche, la rebaser sur `origin/main`, revérifier, recommencer.

## 4. Contrôler

- `git status -sb` : `main` à égalité avec `origin/main`.
- `git ls-remote --tags origin | grep vX.Y.Z` : le tag est bien distant.
- Signaler les versions publiées sans tag : comparer les
  « release X.Y.Z » de `git log origin/main` aux tags distants et proposer de
  poser les tags manquants.
- Rappeler à l'utilisateur que la CI ne construit pas `main` (seulement
  `pyside6-x64-migration`) : la release « latest » et son `.exe` ne sont pas
  mis à jour par ce push.
