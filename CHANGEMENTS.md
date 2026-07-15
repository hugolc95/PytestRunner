# Historique des executions + export de rapports

## Fichiers ajoutes
- `core/run_history.py` : stockage JSON de l'historique des runs (dans `~/.pytest_runner_gui/history/`, jamais dans ton workspace de tests). Chaque run garde aussi un `.log` (sortie console complete) et un `.xml` JUnit natif pytest.
- `core/report_export.py` : generation d'un rapport HTML autonome (aucune dependance ajoutee, juste le module `html` de la stdlib).
- `gui_qt/history_window.py` : fenetre "Historique des executions" (liste des runs, voir la sortie, exporter en HTML ou JUnit XML, effacer l'historique).

## Fichier modifie
- `gui_qt/main_window.py` :
  - `PytestWorker` accepte maintenant un `junit_xml_path` optionnel -> ajoute `--junitxml=...` a la commande pytest (option native, zero dependance).
  - Nouveau menu **"Rapports" > "Historique des executions..."**.
  - A chaque fin de run (bouton "Run Selected Tests" ou "Re-run Failed"), une entree est automatiquement enregistree dans l'historique (compteurs, duree, sortie console, chemin du rapport JUnit).

## Comment integrer
1. Copie ces fichiers dans ton projet en respectant les chemins (ils remplacent/completent l'existant, aucun autre fichier touche).
2. Lance l'appli normalement (`start.bat` ou `python main_qt.py`). Rien a installer, aucun wheel supplementaire requis.
3. Fais tourner des tests -> va dans **Rapports > Historique des executions** pour voir l'entree, consulter la sortie, ou exporter.

## Non touche
- Le dossier `wheels/`, `install_offline.bat`, `requirements*.txt`, `start.bat` : rien n'a change cote packaging/installeur, comme demande.

## Pistes suivantes (si tu veux continuer)
- Corriger le filtre de recherche et le bouton "Failed only" (toujours non connectes).
- Ajouter un raccourci pour re-ouvrir directement le dernier rapport HTML genere.
- Regrouper l'historique par workspace dans la fenetre (onglets ou filtre).
