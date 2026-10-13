# Pytest Runner 1.1.1 — logs des profils

Dans la vue Profiles, l'onglet Logs était désactivé et son panneau ne recevait
pas le chemin des logs. Les fichiers existaient sur disque, mais restaient
inaccessibles en cliquant sur une exécution.

L'onglet est réactivé. À la fin de chaque lot pytest, les chemins des fichiers
sont associés à l'occurrence, à la tentative et au lecteur correspondants. Le
YAML réellement lancé fournit le dossier `LOG_PATH`. La recherche est limitée
au build du profil, en mode `Run_NNNN` comme en mode incrémental `_BNNNN_001`.
Les suffixes de répétition `_002`, `_003`, etc. restent reconnus pour les tests
paramétrés aussi.

Après avoir exécuté le profil, cliquer sur une occurrence puis sur **Logs**
affiche sa trace et permet d'ouvrir son fichier avec **Open this log**. Une
occurrence en attente, ou terminée sans fichier, affiche un état vide explicite.
Le fonctionnement de la vue All tests est conservé.

Validation : tests de recherche, répétitions, retries, lecteurs distincts,
chemin du YAML lancé, absence de fichiers et accès depuis le panneau Qt. Un
test lance quatre vrais processus pytest avec le module de journalisation du
workspace et vérifie l'ouverture de `test_GenericPerso.log` puis des trois
fichiers numérotés.
