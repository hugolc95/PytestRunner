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

## 1.1.2 — ouverture depuis History

Le bouton Logs utilise le chemin du YAML archivé, puis le chemin enregistré
dans l'historique en repli. Les nouveaux runs conservent dès leur lancement
le véritable dossier des logs, même si le YAML ou le workspace change ensuite.
Les chemins qui désignent déjà le dossier `Run_NNNN` ou le dossier daté sont
également reconnus.

Sous Windows, l'ouverture utilise l'API native de l'explorateur, avec Qt en
repli. Une confirmation affiche le dossier demandé. Un échec affiche un
bandeau dans History, avec les chemins recherchés et des détails copiables.
Le bandeau est masqué en usage normal et ne change pas de page.

Validation : 180 tests ciblés passent, notamment sur la recherche des dossiers,
les archives, les logs des profils et le clic sur le bouton. L'appel Windows
et son repli sont simulés dans les tests ; aucune ouverture de fenêtre Windows
réelle n'a été vérifiée dans l'environnement Linux.
