# Démonstration de la file et de la fluidité

Ouvrir ce dossier comme workspace dans PytestRunner. Aucun lecteur de carte,
réseau ni matériel n'est nécessaire. Les durées sont approximatives, hors
démarrage de pytest et archivage. Tous les tests doivent réussir.

1. Sélectionner uniquement **TestRunLong90Seconds** et lancer : environ 90 s.
2. Pendant ce run, cliquer **+ New run**, sélectionner
   **TestQueueOne40Seconds**, puis **Add to queue** : environ 40 s.
3. Créer encore un onglet, sélectionner **TestQueueTwo30Seconds** et l'ajouter
   à la file : environ 30 s.
4. Revenir au premier onglet pour suivre les résultats dans l'arbre. Changer
   d'onglet, chercher un test, lire les logs, détacher et réattacher un onglet.
   Les runs doivent se succéder et garder leurs propres résultats.
5. Facultatif : ajouter **TestOutputStress30Seconds**, qui produit environ
   200 lignes par seconde, pour éprouver la console et les résultats.

Les paramètres d'un même groupe sont de vrais tests distincts : le premier
arbre progresse toutes les 15 s, les suivants toutes les 10 s. Stop permet
d'annuler le run courant ; Pause queue empêche les suivants de démarrer.

Pour valider rapidement le contenu en ligne de commande, la variable
`PYTEST_RUNNER_DEMO_TIME_SCALE=0.01` réduit les attentes à 1 % de leur durée.
Ne pas la définir pour l'essai manuel de fluidité.
