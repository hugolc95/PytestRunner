# Pytest Runner GUI

## Profils : groupes colorés et paramètres explicites — v1.5.0

Dans **Execution Profiles**, sélectionner un test puis **YAML parameters…**
(ou double-cliquer sur le test) ouvre une fenêtre dédiée. Chaque paramètre
propose **Profile value** ou **Custom value**, avec la valeur du profil comme
référence. **Apply** valide les modifications pour cette occurrence uniquement ;
**Cancel** les abandonne. **Reset all to profile values** rétablit les valeurs
du profil. Le fichier YAML d’origine reste intact.

Sélectionner plusieurs tests avec Ctrl ou Maj puis **Create group…** permet
de donner au groupe un nom, une couleur et une courte description. Si les tests
ne sont pas adjacents, le dialogue annonce leur rassemblement à la première
position sélectionnée ; leur ordre relatif est conservé. Un groupe peut être
modifié, déplacé, dupliqué ou dissocié sans perdre les paramètres des tests.

Les groupes peuvent contenir des **sous-groupes** : sélectionner des tests
dans un groupe puis **Create group…**, ou utiliser l’icône **Create subgroup**
sur le groupe sélectionné. Les dossiers et sous-dossiers de tests restent
dépliables à l’intérieur de cette hiérarchie. Les descriptions reprennent la
couleur de leur groupe, dans l’éditeur comme dans **Run Tests**.

**YAML parameters…** fonctionne aussi sur un groupe. La configuration suit
l’ordre **profil → groupes parents → sous-groupe → test**. On peut ainsi
dupliquer une suite T0 puis passer le YAML du groupe copié en T1 ; les deux
copies gardent des paramètres indépendants. Une option permet de remplacer
les exceptions des sous-groupes et des tests pour les seuls paramètres
personnalisés dans cette fenêtre.

Un glisser-déposer vers un autre groupe demande confirmation avant de déplacer
les tests. Le dialogue montre le groupe de départ, la destination et les
changements de paramètres effectifs. **Cancel** conserve la séquence intacte ;
réordonner les tests à l’intérieur du même groupe ne demande pas de confirmation.

**Annuler / rétablir.** Les flèches de la barre de séquence, **Ctrl+Z** et
**Ctrl+Y** permettent d’annuler ou de rétablir les ajouts, suppressions,
déplacements, regroupements et paramètres YAML validés. L’historique garde
les 50 dernières actions du profil en cours, y compris après une sauvegarde ;
changer de profil démarre un nouvel historique. Annuler une action ne modifie
pas le fichier déjà sauvegardé. Les champs de texte gardent leur annulation
habituelle pendant la saisie.

**Voir le YAML effectif.** Sélectionner un test puis l’icône d’aperçu, ou
**View effective YAML…** dans son menu clic droit, affiche les valeurs finales
et leur origine : profil, groupe, sous-groupe ou test. Un deuxième onglet
permet de lire et copier le YAML complet. Le choix du lecteur reprend ceux
sélectionnés dans **Run Tests** ; sans lecteur choisi, son affectation est
explicitement indiquée comme restant à faire au lancement.

**Exceptions visibles.** Un triangle discret et une infobulle signalent les
paramètres qui diffèrent de ceux hérités du groupe, par exemple un test T0
dans une suite T1. Les groupes récapitulent le nombre de tests concernés.
Ces indicateurs sont aussi présents dans l’arbre d’exécution.

Le menu clic droit rassemble les paramètres YAML, l’aperçu effectif, les
groupes, la duplication, la suppression et **Move to…**. Ce déplacement permet
de choisir la destination et de voir les changements avant de confirmer,
sans devoir utiliser le glisser-déposer.

**Copier / coller.** Dans la séquence, **Ctrl+C** copie les éléments sélectionnés
(groupes, sous-groupes, dossiers, modules, classes, tests et cas paramétrés).
Un parent sélectionné avec ses enfants n’est copié qu’une fois. La copie fige
la sélection et conserve les occurrences répétées, la hiérarchie, les couleurs,
descriptions et paramètres YAML explicites. Modifier ensuite l’original ne
change pas le contenu du presse-papiers.

**Ctrl+V** colle après la sélection, ou à la fin du profil sans sélection.
**Paste into this group** / **Ctrl+Maj+V** colle à l’intérieur du groupe choisi.
Les groupes collés reçoivent leurs propres identifiants : modifier une copie
ne modifie pas l’original. Si les valeurs héritées changent à destination, un
aperçu demande confirmation ; les tests absents du workspace sont également
signalés avant de coller. Le collage peut être annulé avec **Ctrl+Z**.

Un contour bleu pointillé et un message dans l’en-tête signalent la copie.
Les éléments collés sont sélectionnés et marqués en vert pendant six secondes.
Ces repères n’ajoutent aucun bandeau à l’arbre. Les commandes sont aussi dans
le menu clic droit. Dans les champs de texte, Ctrl+C / Ctrl+V gardent leur
fonctionnement habituel ; vers une autre application, la copie fournit les
identifiants pytest sous forme de texte.

Les liens d’erreur utilisent la touche Ctrl du clic courant : un clic simple
ne part plus vers l’éditeur externe à cause d’un ancien état clavier resté
actif dans Qt. Le clic simple et Ctrl+clic gardent leurs comportements respectifs.

Les groupes colorés apparaissent aussi dans l’arbre **Run Tests**, avec leurs
descriptions en ligne et en infobulle. Ils sont conservés dans les profils
sauvegardés, exportés et récupérés depuis l’historique. Les profils antérieurs
restent lisibles ; les profils contenant ces nouveaux groupes nécessitent
Pytest Runner 1.5.0 ou une version ultérieure.

## Profils : retour des groupes — v1.4.8

La **Test sequence** retrouve un arbre compact avec des groupes de dossiers,
modules, classes et cas paramétrés, repliés au départ. **Add tests / groups**
permet d’ajouter un test seul ou un groupe complet ; **Add selected again**
répète le dernier ajout sans devoir tout recocher.

Un groupe se déplie pour retrouver ses tests. **Duplicate**, **Remove**, les
flèches et le glisser-déposer agissent sur le groupe ou sur le test choisi.
Sélectionner à la fois un groupe et un de ses tests ne traite pas ce test deux
fois. L’ordre d’exécution, les doublons volontaires et les paramètres YAML
propres à chaque occurrence suivent tous ces déplacements et restent conservés
dans les profils sauvegardés ou exportés.

Les lignes ne sont plus de grandes cartes individuelles. Sélectionner un test
ouvre ses paramètres YAML ; déplier un groupe n’ouvre pas les paramètres de
tous ses tests. Les commandes de dépliage et repliage restent dans la barre
de la séquence.

## Fiabilité — v1.4.7

**Menu de l’en-tête de l’arbre.** Le sous-menu **Duration shows** (clic droit
sur l’en-tête) s’affiche de nouveau correctement : il était détruit avant même
l’ouverture du menu.

**Grandes suites plus fluides.** Pendant un run, un dossier de l’arbre n’est
redessiné que lorsque son statut affiché change, et non plus à chaque
résultat d’un de ses tests.

**Runs lancés depuis un environnement pytest parallèle.** Le pytest lancé par
l’application n’hérite plus des variables de pytest-xdist de son parent :
verdicts et durées arrivent toujours.

**Tests de l’application.** Lancer la suite de tests de Pytest Runner ne
modifie plus les préférences de l’utilisateur (workspaces récents, thème,
interpréteur…) : chaque test travaille dans des réglages temporaires. Une CI
lance cette suite sur `main` et sur les branches de travail, et construit
l’exécutable à chaque mise à jour de `main`.

## Logs lisibles et sélection du texte — v1.4.6

Les timestamps en début de ligne sont masqués dans les logs affichés par
l’interface. Les niveaux INFO/ERROR et les dates présentes dans les messages
restent visibles ; les fichiers originaux conservent leur contenu complet.
Le bouton de copie des logs copie le texte affiché, sans les timestamps.

**Ctrl+A** dans un panneau Logs ou Output sélectionne son texte, sans modifier
la sélection des tests. Dans le champ de recherche d’un log, il sélectionne
uniquement le texte de recherche.

## Tous les lecteurs dans Run tests — v1.4.5

La liste du lecteur principal (**Run tests → Execution**) montre maintenant
tous les lecteurs HubReader détectés, comme dans la configuration YAML. La
recherche des lecteurs partait pendant la collecte des tests, alors que la
liste est désactivée à ce moment-là : elle abandonnait sans réessayer, et la
liste ne montrait que les lecteurs déjà écrits dans le fichier de
configuration. Elle reprend maintenant dès que la liste redevient utilisable.
Ouvrir la liste relance aussi la recherche, comme **Refresh available
readers** dans la configuration : un lecteur branché entre-temps y apparaît.

## Colonnes de résultat collées à droite — v1.4.4

Les colonnes des lecteurs (et Duration quand elle est affichée) restent
collées au bord droit de l’arbre : masquer Duration ou n’avoir que peu de
lecteurs ne laisse plus de vide à droite. La colonne **Test** prend toute la
place restante, dans l’arbre des tests comme dans celui des profils. Quand le
panneau rétrécit, c’est toujours elle qui cède la place. Les colonnes des
lecteurs et Duration se règlent à la souris et restent retenues ; la colonne
Test suit.

## Durée avec plusieurs lecteurs — v1.4.3

**Ce que montre la colonne Duration.** Avec deux lecteurs ou plus, clic droit
sur les en-têtes de colonnes (ou menu **…**) → **Duration shows** :
le lecteur le plus lent (par défaut), le plus rapide, la moyenne, l’écart
entre le plus lent et le plus rapide (**Spread**), ou un lecteur précis. Le
titre de la colonne indique le mode (« Fastest », « Spread », « Duration · A »…).
Le choix est enregistré et vaut pour tous les runs ouverts.

**Écarts en couleur.** En mode **Spread**, la colonne affiche « Δ 1.50s » et
un écart notable (plus de 30 % de la durée du plus lent, et au moins 0,1 s)
ressort en ambre : on repère d’un coup d’œil le lecteur anormalement lent.

**Totaux justes et survols corrigés.** Un dossier ou un fichier se calcule à
partir du total réel de chaque lecteur : en mode par défaut, c’est le total du
lecteur le plus lent, et non plus la somme des pires cas de chaque test, qui
ne correspondait à la durée d’aucun lecteur. Le survol d’un groupe donne le
total de chaque lecteur et l’écart ; celui d’un test, la durée de chaque
lecteur et l’écart.

## Colonnes de l’arbre réglables — v1.4.2

**Colonne Duration affichable ou non.** Clic droit sur les en-têtes de
colonnes de l’arbre, ou menu **…** de la barre de l’arbre : **Show Duration
column**. Le choix est enregistré et vaut pour tous les runs ouverts ; on le
retrouve dans **Settings → Tree & details → Duration column**.

**Largeurs retenues.** Une largeur réglée à la souris (colonne Test, colonne
d’un lecteur, Duration) est retenue pour cette colonne : elle tient après une
nouvelle collecte, un changement de lecteurs — la largeur suit le lecteur même
s’il change de position — et un redémarrage. Seuls les réglages faits à la
souris sont retenus, pas les ajustements automatiques. **Reset column widths**
(même menus) revient aux largeurs calculées. La colonne Duration est
maintenant assez large pour une durée de plusieurs minutes (« 1 min 20.5s »).

## Test supprimé et onglet conservé — v1.4.1

**Test supprimé depuis la collecte.** Lancer un test qui n’existe plus dans le
workspace (supprimé ou renommé sans relancer **Collect**) affiche maintenant
la fenêtre **Execution error** avec le message de pytest, au lieu de finir
sans rien dire sur « All tests passed ». La barre d’état indique
« Execution completed with errors ». Pytest refuse alors toute la commande,
même les tests encore valides de la sélection : le message invite à cliquer
**Collect** pour rafraîchir l’arbre avant de relancer.

**Onglet conservé.** Passer d’un test à un autre garde l’onglet ouvert
(**Logs**, **Source**, **Output** ou **Detail**) au lieu de revenir sur
**Detail**. Le réglage **Settings → Tree & details → Tab when selecting
another test** vaut désormais **Last used** ; on peut toujours y imposer un
onglet fixe.

## Collecte partielle, durées et compteurs — v1.4.0

**Fichiers en erreur.** Un fichier de tests que pytest ne peut pas importer
(erreur de syntaxe, import manquant…) ne bloque plus toute la collecte. Les
autres tests restent dans l’arbre et peuvent être lancés. Le fichier en erreur
apparaît à sa place, en couleur d’erreur et sans case à cocher ; son survol
donne l’emplacement et le message. Le sélectionner affiche l’erreur dans
**Detail** et le fichier dans **Source**. La barre d’état indique
« N file(s) could not be collected » et la trace complète est dans
**Console → Errors**. Corriger le fichier puis **Collect** le réintègre.
Un `conftest.py` en erreur, ou un workspace dont aucun fichier n’est valide,
bloque toujours la collecte avec la fenêtre d’erreur habituelle.

**Colonne Duration.** L’arbre affiche la durée de chaque test (setup + call
+ teardown) dès qu’il se termine, sans attendre la fin du run. Avec plusieurs
lecteurs, la valeur est celle du lecteur le plus long ; le survol détaille
chaque lecteur. Un dossier, un fichier ou une classe affiche la somme de ses
tests. Les durées repartent de zéro à chaque nouveau run.

**Compteurs.** Les échecs et les erreurs sont comptés séparément partout :
« 8 failed · 1 error » dans la barre d’état, dans l’onglet du run et dans la
notification de fin, comme dans les pastilles de résultats.

**Affichage stable.** Quand l’arbre rétrécit, la colonne des noms cède la
place : Status et Duration restent visibles, et la largeur choisie revient
quand l’espace le permet. Run et Pause occupent une seule et même case :
lancer, mettre en pause, reprendre ou arrêter ne déplace plus ni le bouton, ni
son icône, ni Stop et Re-run.

## Échap et changement de workspace

**Échap** arrête le run seulement quand le curseur n’est pas dans un champ de
saisie. Dans **Find a test…**, Échap efface la recherche ; dans les autres
champs (chemin du workspace, nom du run, valeurs numériques…), il est ignoré.
Le bouton **Stop** reste disponible à tout moment.

Si la collecte d’un autre workspace échoue, l’arbre se vide : les tests du
workspace précédent ne peuvent plus être lancés dans le nouveau dossier. Si
une nouvelle collecte du même workspace échoue, l’arbre existant est conservé.

## Relances ciblées et lecteur affiché

**Run only this test / Run only this** dans le menu contextuel relance le test
ou le groupe sans changer les cases cochées. Les verdicts des autres tests
et lecteurs restent visibles, même si la conservation entre runs est désactivée
dans Settings. Leurs traces d’échec et durées restent consultables pendant
la session ; les nouveaux résultats remplacent ceux des tests effectivement
réexécutés. La file d’attente conserve ce comportement. History et les compteurs
du run continuent de ne contenir que les exécutions de ce run.

Au lancement, **Logs** et **Output** affichent un lecteur utilisé par ce run.
Si un seul lecteur est lancé, il devient le lecteur affiché et la comparaison
se ferme. Avec plusieurs lecteurs, le lecteur affiché est conservé s’il fait
partie de l’exécution. L’onglet principal et le test sélectionné restent en place.
Les profils conservent également le lecteur affiché entre les étapes.

## Recherche dans les logs

Dans **Logs**, une barre **Find in log…** au-dessus de chaque log permet de
chercher du texte sans masquer les lignes voisines. La recherche ignore la
casse et traite les caractères tels que `[` ou `.` comme du texte. Les
occurrences ont toutes le même fond jaune vif avec du texte noir, en thème
clair comme sombre. Seuls les mots surlignés changent de couleur ; le reste
du log conserve ses couleurs. Le compteur et les flèches permettent de les
parcourir en boucle. **Ctrl+F** depuis le log place le curseur dans ce champ,
**Entrée / F3** passe au résultat suivant, **Maj+Entrée / Maj+F3** au précédent
et **Échap** efface la recherche. Le bouton de suppression du champ fait de même.
La recherche et les deux flèches rouges de navigation entre les erreurs
partagent une seule ligne avec les commandes du log. Si le panneau est étroit,
les commandes secondaires restent accessibles dans **More log actions** (`…`).
Sans recherche active, le compteur indique le nombre de lignes ou la position
de l’erreur ; le survol donne l’information complète.

La recherche fonctionne aussi pour les profils. En comparaison, chaque
lecteur garde sa propre recherche et les différences restent surlignées.
Naviguer dans les résultats suspend le suivi automatique ; le bouton de suivi
permet de revenir à la fin. Le compteur se met à jour quand le contenu change.
Seule la partie affichée d’un fichier très volumineux est recherchée ; le
fichier complet reste accessible par **Open log**.

## Résultats conservés dans l’arbre (version d’essai)

**Settings → Tree & details → Keep previous results in the test tree** permet
de conserver le dernier verdict connu de chaque test et lecteur. Les icônes
du dernier run sont pleines ; celles des résultats précédents sont en contour
et de couleur atténuée. Le survol indique le statut et la date du résultat.
Dans **Detail**, un indicateur discret **Previous** apparaît sur la ligne de
chaque lecteur dont le verdict provient d’un autre run. Son survol donne la
date et la configuration. Ces informations restent dans le contenu de Detail :
les onglets **Detail / Source / Output / Logs** restent alignés avec la barre
d’outils du tree. Le contexte des exécutions de profil se trouve aussi dans
Detail. Les infobulles d’Output et Logs rappellent qu’ils montrent le dernier run.
Les compteurs, la progression et les rapports du run ne comptent que les tests
réellement exécutés pendant ce run.

La petite gomme **Clear tree results** dans la barre de l’arbre efface ces
résultats sans supprimer History ni changer la sélection ou les désactivations.
Les compteurs du dernier run restent affichés. La gomme est inactive pendant
une exécution ou lorsque l’onglet est dans la file d’attente. Cette action est
aussi accessible par clic droit dans l’arbre et par le menu **More tree actions**.

La barre de l’arbre regroupe recherche, markers, désactivations, sélection et
affichage, avec de petits espacements entre les groupes. L’icône **Markers**
se trouve près de la recherche. L’expression active partage la ligne de sélection
sous l’arbre ; son texte complet reste accessible au survol et dans le panneau.
Le filtre n’ajoute aucune ligne au bandeau d’exécution. Il sélectionne les tests
correspondants, comme auparavant ; retirer
le filtre conserve cette sélection. Le bouton et **Ctrl+M** sont verrouillés
pendant l’exécution et la mise en attente. Le bouton des désactivations affiche
leur nombre et disparaît quand il n’y en a aucune.

La préférence est enregistrée avec **Apply settings**. Les résultats sont
conservés localement par workspace et nom de lecteur, entre onglets et après
redémarrage. Lorsque l’option est désactivée, chaque nouveau run remet l’arbre
à zéro, comme auparavant.

## Pause et reprise d’un run (version d’essai)

Pendant un run, **Pause** prend la place du bouton Run. Le statut existant
affiche **Pause requested — waiting for the current test to finish** : chaque test déjà démarré
termine son exécution et son nettoyage. Quand tous les lecteurs attendent,
le statut devient **Paused · N tests**, avec une icône pause fixe, et **Resume** reprend au prochain test dans le
même run, sans réexécuter les précédents ni recréer la session pytest.
**Cancel pause** permet d’annuler la demande avant la pause effective.

Les profils conservent leur étape, répétition et tentative. La configuration
et la sélection restent verrouillées, la file d’attente attend, et **Stop**
reste disponible. Le compteur de temps affiché est suspendu pendant la pause.
La reprise nécessite de garder l’application ouverte. Les lancements de
stress conservent leurs commandes habituelles.

## Désactivation des tests (version d’essai)

Dans **Run Tests**, clic droit sur un test → **Deactivate test…**, ou sur un dossier,
un fichier, une classe ou un test paramétré → **Deactivate group…**. La raison est
optionnelle. Pour un cas paramétré, on peut désactiver ce cas seul ou tous les
cas du test, y compris les futurs paramètres. Le symbole ⊘ remplace l’icône du
test, sans ajouter de colonne. Les tests désactivés restent visibles et ne
peuvent plus être cochés.

Un bouton ⊘ dans la barre d’outils de l’arbre apparaît uniquement lorsqu’il
existe des désactivations. Il ouvre **Deactivated tests**, avec le motif, la date,
une case d’activation directe et **Deactivate a test or group…**. L’auteur reste disponible
dans les détails et les infobulles. Les décisions sont enregistrées localement
dans le dossier utilisateur de l’application, par workspace, indépendamment du
YAML et de l’onglet de run ; aucun fichier de test n’est modifié.

Les profils contenant une étape désactivée sont bloqués et les runs en attente
sont revérifiés avant leur démarrage. Les tests désactivés sont exclus avant
exécution, sans créer de faux verdict pytest « skipped ». La désactivation ne
concerne que les lancements depuis cette application. Arrêter les exécutions
du workspace avant d’en changer les désactivations ; la réactivation est
manuelle et n’entraîne pas de nouvelle sélection automatique.
Une règle de groupe couvre aussi les futurs tests de ce groupe. Réactiver le
groupe conserve les désactivations individuelles déjà enregistrées séparément.
Un test ou sous-groupe peut être réactivé seul dans un groupe désactivé : cette
exception est conservée au redémarrage et les autres tests restent désactivés.
La fenêtre présente les membres des groupes avec leur case d’activation. Ses
boutons **Activate all** et **Deactivate all** agissent sur tous les éléments de la
liste, y compris ceux qui viennent d’être réactivés tant que la fenêtre reste ouverte.
Cette fenêtre conserve les niveaux fichier `.py`, classe et test paramétré avant
les cas individuels. Cocher un groupe y réactive tous ses éléments ; une case
avec un tiret indique une activation partielle.

## Navigation dans les erreurs — v1.2.0

Les références fichier/ligne sont cliquables dans **Detail**, l’historique,
**Console** et les détails des erreurs de collection. Un fichier Python du
workspace ouvert s’affiche dans **Source**, à la ligne et à la colonne indiquées.
Le bouton **Back to traceback** retourne à la vue d’origine. Le saut dans un
fichier déjà affiché conserve son édition ; une sauvegarde échouée empêche de
remplacer le fichier en cours.

Les dépendances, fichiers externes et projets historiques qui ne sont plus
chargés s’ouvrent dans un IDE. **Ctrl+clic** force cette ouverture. Le menu du
clic droit propose aussi **Copy file:line** et **Locate file…** pour retrouver
un fichier déplacé sans modifier les anciens résultats.

Dans **Settings → External editor**, choisir **Automatic**, **VS Code** ou
**PyCharm**, et éventuellement renseigner les exécutables. En automatique,
VS Code est essayé avant PyCharm ; un éditeur préféré absent laisse place à
l’autre. Si aucun éditeur n’est trouvé ou qu’un chemin configuré est invalide,
une erreur visible indique comment corriger le réglage.

L’IDE reçoit le projet et le fichier avec sa ligne : ses mécanismes habituels
réutilisent le projet ouvert. VS Code reconnaît aussi les fichiers
`.code-workspace` correspondants, y compris avec plusieurs dossiers.
Les politiques de fenêtres propres à l’IDE restent applicables.
Une référence ambiguë ou provenant d’un autre ordinateur est signalée plutôt
que résolue uniquement par le nom du fichier ; une ligne disparue est signalée
dans Source.

Application de bureau **PyQt5** permettant de charger un workspace, découvrir ses tests pytest, sélectionner des tests complets ou un seul cas paramétré, lancer/arrêter l'exécution, consulter les résultats et exécuter des campagnes YAML.

## Deux Python indépendants

L'interface **n'importe jamais** le code testé : elle lance pytest dans un sous-processus et lit sa sortie. L'interface et les tests peuvent donc utiliser deux interpréteurs Python différents.

C'est ce qui permet, par exemple, de piloter depuis une interface 32 bits des tests qui ont besoin d'un Python 64 bits pour charger des DLL natives.

L'interpréteur des tests se règle dans **Configuration > Interpréteur Python des tests...**. Cet interpréteur doit avoir `pytest` installé (et `pytest-xdist` si vous cochez *Parallel*) ; l'interface, elle, n'a besoin que de PyQt5 et PyYAML.

Ordre de priorité, du plus fort au plus faible :

1. la clé `python:` de `campaign.yml` (mode Campaign uniquement) ;
2. la clé `python_executable:` du `config.yaml` du workspace ;
3. le réglage global de l'application ;
4. le Python courant.

Laisser le réglage vide conserve le comportement historique : les tests tournent avec le Python de l'interface.

## Exécutable Windows

L'interface peut être distribuée en application autonome, sans installer Python sur le poste.

**➜ [Télécharger la dernière version](https://github.com/hugolc95/PytestRunner/releases/tag/latest)** (`PytestRunner-windows.zip`)

Ce lien est permanent et pointe toujours vers le dernier build. Chaque push reconstruit l'application sur une machine Windows, y rejoue la suite de tests, vérifie que l'exécutable démarre, puis met la release à jour.

Pour construire soi-même : `build_exe.bat` (nécessite PyQt5, PyYAML et PyInstaller).

Le résultat est le dossier `dist\PytestRunner\` : distribuez-le entier (zippé), pas seulement le `.exe`. L'exécutable ne contient que l'interface — pytest et les dépendances des tests restent du côté de l'interpréteur configuré, il faut donc toujours renseigner celui-ci au premier lancement.

## Installation hors ligne (mode source)

- Windows x86 / 32 bits ;
- CPython **3.13 32 bits** ;
- aucune connexion Internet nécessaire ;
- Python doit déjà être installé sur le poste.

## Démarrage

1. Extraire entièrement l'archive dans un dossier local.
2. Vérifier Python avec `py -0p` : une entrée `-3.13-32` doit être visible.
3. Double-cliquer sur `start.bat`.

Au premier lancement, le script crée `.venv` avec `py -3.13-32`, puis installe les dépendances exclusivement depuis `wheels/` avec `--no-index`.

## Fichiers BAT

- `start.bat` : installe si nécessaire puis lance l'interface ;
- `install_offline.bat` : recrée/installe l'environnement hors ligne ;
- `test_offline.bat` : installe les outils de test hors ligne et exécute la suite automatisée ;
- `diagnostic.bat` : affiche les versions Python et l'architecture détectées.

## Tests paramétrés

Les cas issus de `@pytest.mark.parametrize` sont affichés comme des feuilles distinctes et peuvent être lancés séparément :

```text
testSuite1/test_parametrized_selection.py
└── test_addition_parametree
    ├── [small]
    ├── [medium]
    └── [large]
```

Sélectionner uniquement `[medium]` lance précisément :

```text
testSuite1/test_parametrized_selection.py::test_addition_parametree[medium]
```

## Installation manuelle

```bat
py -3.13-32 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links=wheels -r requirements.txt
.venv\Scripts\python.exe main_qt.py
```

## Vérification

Double-cliquer sur `test_offline.bat`. La suite couvre notamment : découverte, collecte invalide, tests paramétrés sélectionnables individuellement, succès/échec/skip/error, arrêt d'un test long et campagnes YAML.
