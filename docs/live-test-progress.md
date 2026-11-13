# Suivi bleu des tests en cours

Les marqueurs de demarrage utilisent maintenant les memes nodeids que la
collecte. Chaque processus les normalise dans sa propre TestSuite, avant
leur transmission au service et aux deux arbres. Un pytest.ini ou
pyproject.toml imbrique peut changer la racine pytest sans perdre le suivi.
Deux suites ayant les memes noms de fichiers, classes et cas parametres
restent distinguees. Le transport fait partie du plugin du domaine et ne
depend plus de l'installation d'un module visuel.

Pendant le demarrage et la collecte du processus, la branche concernee est
bleue et le statut precise **Preparing**. Dans Profiles, cette presentation
ne remplace pas les verdicts precedents ; seuls les tests effectivement
demarres les remplacent. Le suivi est independant pour chaque lecteur.
L'annulation et la fin d'un lot nettoient la preparation.

Le terminal pytest peut annoncer PASSED avant un teardown long. Le verdict
machine, emis apres setup, call et teardown, devient la reference en direct.
L'indicateur reste donc bleu jusqu'a la fin effective du test. La sortie
humaine reste un secours si un plugin empeche le transport final ; elle est
alors exploitee a la fin du processus. Les marqueurs internes sont exclus des
sorties et rapports archives.

Les titres des groupes respectent maintenant le bleu actif en themes clair
et sombre ; leur description et leur repere de couleur restent conserves.

Verification : tests de transport multisuites homonymes, tests de vrais runs
partiels bloques successivement pendant collecte/setup/call/teardown, avec
pytest.ini, pyproject.toml ou sans configuration, en mode simple et xdist.
Les tests de rendu couvrent les groupes selectionnes, les deux themes et
plusieurs tailles de police. Un parcours de l'application installee avec ses
quatre modules de production et deux lecteurs simules verifie les arbres
classique et Profiles ; les captures sont prises directement dans Qt.

Resultats : 178 tests cibles reussis (transport, execution, pause, details,
relances partielles et rendu). Le parcours applicatif avec deux lecteurs et
xdist ne remonte aucune erreur ; le smoke test des pages et des trois themes
produit aussi 18 captures sans erreur applicative ni message Qt. Les essais
sont realises sous Linux/offscreen, avec Qt 6.8.3 et des lecteurs simules.
