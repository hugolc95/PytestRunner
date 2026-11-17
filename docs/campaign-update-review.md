# Mise a jour des campagnes — branche d'evaluation

Branche : `codex/campaign-update-review`. Verification le 17 novembre 2026.
Pas de merge, de tag ni de changement de version pour cette evaluation.

## Ce que voit l'utilisateur

Apres une collecte reussie, **Run Tests** et **Execution Profiles** signalent
les changements. **Review changes…** presente un resume au futur : tests a
ajouter, emplacements a mettre a jour, tests a retirer et taille finale.
**Update campaign** applique les changements en une validation, sans choix
obligatoire par test. La liste des changements est visible directement ;
**Full paths** affiche les chemins complets sans redimensionner la fenetre.
Les remplacements manuels et le transfert explicite du YAML restent dans
**Advanced…**.

**Contents…** separe deux comportements : garder une selection fixe, ou
inclure les futurs tests des dossiers/fichiers choisis. La liste des sources
n'apparait que dans le second mode. **Save campaign** sauvegarde le contenu
et le brouillon courant ensemble. Les cases de Run Tests choisissent le
prochain lancement ; elles ne suppriment aucun test de la campagne.

Un ancien appel de fonction sans parametres est remplace par ses nouveaux
cas a chacun de ses emplacements. Chaque appel garde son groupe, son ordre,
son YAML et sa selection. Les futurs cas sont ensuite suivis pour chacun
de ces appels, sans ajouter les autres tests du projet aux anciennes
selections fixes. Les cas precis choisis individuellement restent fixes.

Le survol colore d'un groupe explique son mode, ses emplacements suivis,
ses exclusions et ses valeurs YAML. Un ajout ou changement de chemin est
signale en bleu ; un test introuvable en orange. Les libelles expliquent le
probleme et l'action suivante, sans utiliser uniquement une couleur.

Apres mise a jour, une confirmation verte compacte remplace le grand bandeau
de succes. **Undo update** reste disponible pres des commandes de campagne,
y compris apres redemarrage. Dans un panneau etroit, les actions de sequence
utilisent des libelles courts ou des icones avec infobulles et noms accessibles.

## Verification de chaque cas

| Cas | Comportement attendu et verifie | Preuve ciblee |
| --- | --- | --- |
| Ajout de tests dans un dossier suivi | Ajouts proposes ensemble, reglages du groupe herites, ordre existant conserve | `test_campaign_sync.py`, parcours reel |
| Selection precise | Aucun nouveau test ajoute hors des sources suivies | `test_campaign_sync.py`, `test_campaign_update_ux.py` |
| Nouveaux cas parametres | Renouvellement des cas suivis sans imposer un choix par cas | `test_campaign_update_ux.py` |
| Ancien HMAC devenu parametre | 13 appels remplaces chacun par 3 cas : 273 → 299 tests. Un quatrieme cas ajoute ensuite a chacun : 312 tests. YAML et ordre conserves | `test_campaign_hmac_update.py`, parcours pytest reel |
| Fenetres de mise a jour et de contenu | Liste concise visible directement ; modes et chemins complets ne redimensionnent pas les fenetres. Redimensionnement manuel possible | `test_campaign_hmac_update.py`, captures reelles |
| Exception YAML sur un cas disparu | Cas et YAML conserves par defaut ; transfert vers un remplacement explicite dans Advanced | `test_campaign_update_ux.py`, `test_campaign_sync.py` |
| Racine de collecte differente | Correspondance uniquement si le chemin relatif et le symbole correspondent sans ambiguite ; YAML, identites et exclusions conserves | 38 chemins corriges dans l'application ; `test_campaign_update_ux.py` |
| Fichier renomme/deplace | Suggestions si le symbole correspond ; jamais appliquees automatiquement sur un simple nom | `campaign_sync.compare`, options avancees |
| Nom identique dans deux suites | Aucune correspondance inventee | `test_campaign_update_ux.py` |
| Autre projet, collecte echouee ou incomplete | Aucun retrait propose ; campagne intacte. Si rien ne correspond, **Check project** ouvre le choix d'environnement | `test_campaign_sync.py`, dialogue reel clair/sombre |
| Test introuvable | Visible et inspectable ; Select all et relances ne l'executent pas. Les autres tests peuvent tourner | `test_campaign_update_ux.py` |
| Exclusions volontaires | Conservees, propres a chaque source, restaurables dans Advanced | `test_campaign_sync.py`, parcours reel |
| Groupes T0/T1 et copies | Sources, exclusions, YAML et identites independants ; aucune fusion des doublons | `test_campaign_sync_ui.py`, `test_campaign_sync.py` |
| Groupe/sous-groupe vide | Nom, ordre, couleur, description et YAML gardes ; editable, duplicable, copiable, exportable ; nouveaux tests reintegres au bon endroit | `test_campaign_review_complete.py`, captures 11–13 |
| Insertion avant un groupe vide | Sa position suit les tests qui restent, sans sauter dans l'arbre | `test_campaign_review_complete.py` |
| Mise a jour repetee | Aucun ajout en double apres application ; les tests volontairement exclus restent exclus | `test_campaign_sync.py`, `test_campaign_update_ux.py` |
| Contexte Run Tests | Cases, lecteur, recherche, filtre, branches, selection et ancrage de defilement conserves ; voisin selectionne si le test disparait | `campaign_run_sync.updated`, `test_campaign_sync_ui.py`, `test_campaign_review_complete.py` |
| Resultats precedents | Restaures seulement pour la meme occurrence et la meme configuration ; jamais reutilises pour un nouveau cas | `test_campaign_sync_ui.py` |
| Editeur de campagne | Changer de profil ou rafraichir garde les brouillons non sauvegardes ; les editions usuelles gardent Undo/Redo et le contexte d'arbre | `test_campaign_review_complete.py`, `test_profile_nested_groups.py` |
| Fichier modifie sur disque | Sauvegarde/mise a jour refuse l'ecrasement ; brouillon garde, **Reload saved version** et Save as disponibles | `test_campaign_review_complete.py` |
| Run actif ou en file | Comparaison consultable ; mise a jour verrouillee. L'instantane lance ne change pas ; rechargement de l'affichage differe | `test_campaign_review_complete.py` |
| Annulation durable | Version precedente sauvegardee sur disque. Undo apres recreation du store/editeur ; un edit ulterieur empeche de l'ecraser | `test_campaign_review_complete.py` |
| Campagne partiellement executee | **Campaign incomplete**, compte prevu/execute, tests non coches/introuvables/non termines distingues ; pas de faux succes global | `test_campaign_review_complete.py`, lancement reel d'1 test sur 38 |
| Arret pendant un test | Tentative inachevee marquee Not run, motif explicite, archive de campagne conservee avec indicateur stopped | `test_campaign_review_complete.py` |
| Plusieurs lecteurs/reprises | Couverture par occurrence et lecteur ; la derniere tentative fait foi, sans completer un lecteur avec les resultats d'un autre | `test_campaign_review_complete.py` |
| History | Badge Incomplete/Stopped, perimetre prevu, portion non executee neutre dans la barre ; nouvelles donnees non confondues avec de vieux resultats inconnus | `test_campaign_review_complete.py`, capture 09 |
| Export HTML | Arbre complet fige au lancement, motifs des tests non executes dans Details/Logs/Traceback ; recherche et filtres fonctionnels | `test_html_analysis_report.py`, `test_report_values_timing.py`, navigateur reel |
| Clavier/accessibilite | Enter sur l'action principale, Escape pour fermer ; Ctrl+Z limite a l'arbre pour Undo update, sans prendre le raccourci des champs de texte ; icones avec noms/infobulles | actions Qt et parcours reel |

## Captures reelles

Application lancee avec `clean_ui`, `end_run_feedback`, `main_ux` et
`runtime_polish`, profils/reglages/historique isoles. Collecte pytest reelle
de 38 cas, correction de leurs chemins en une fois, puis execution du cas
17 seul : 1 succes sur 38 prevus, 37 non selectionnes. Export par le vrai
worker HTML puis inspection dans Chromium hors ligne. Aucun lecteur physique
necessaire pour ces essais ; le comportement materiel ATR ne fait pas partie
de cette modification.

Dossier de captures : `/workspace/campaign-complete-captures/`.

Correction HMAC et fenetres : `/workspace/campaign-hmac-captures/`.
Collectes reelles de 21, 23 puis 24 tests ; campagne de 273, 299 puis 312
tests. Trois cas HMAC executes avec leurs positions et leur YAML reels.
`verification.json` contient les compteurs, tailles et erreurs du parcours.

- 01 : avertissement dans Run Tests avant correction.
- 02–03 : Contents en selection fixe puis en suivi de dossiers.
- 04 : correction de 38 chemins, sans formulaire par test.
- 05 : campagne rechargee, cases et YAML conserves.
- 06–07 : aucun test retrouve, action Check project en clair/sombre.
- 08–09 : lancement partiel et historique explicite.
- 10 : confirmation compacte et annulation disponible.
- 11–12 : groupe vide conserve puis rempli a nouveau, exclusion respectee.
- 13 : survol du groupe, suivi et configuration visibles.
- 14–15 : editeur sombre et panneau etroit.
- 16–17 : rapport HTML dans Chromium, clair/sombre.
- `verification.json`, `browser-verification.json` : controles des parcours.

Tests limites aux modules touches et leurs interactions ; aucune suite
complete lancee.

## Compatibilite et limites explicites

Les anciens profils restent lus. Les profils avec suivi/identites utilisent
le format portable v4 ; ceux conservant des groupes vides utilisent v5.
Ces formats necessitent cette branche pour etre ouverts. Un profil exporte
sans ces fonctions garde son format anterieur.

Le suivi reagit aux collectes reussies : il ne surveille pas le disque en
continu et n'applique pas de changement sans validation. Un renommage de
classe/fonction ou une correspondance ambigue exige une selection explicite
dans Advanced. Les archives anciennes ne peuvent pas retrouver des donnees
qui n'ont jamais ete enregistrees. Les brouillons sont conserves lors des
changements de profil pendant la session ; ils doivent etre sauvegardes avant
fermeture. L'annulation durable porte sur la derniere mise a jour, pas sur
une suite illimitee d'editions.
