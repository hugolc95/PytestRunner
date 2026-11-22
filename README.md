# Pytest Runner GUI

## Guide d'utilisation et passe de stabilité — v1.8.0

**Help**, juste au-dessus de **Settings** dans le menu de gauche, ouvre le
guide d'utilisation complet dans le navigateur. **F1** l'ouvre directement
sur la rubrique de la page affichée. Le guide est en anglais, comme
l'interface, et couvre en 30 rubriques : premiers pas, Run Tests, sélection,
lecteurs et ATR, onglets et file d'attente, résultats, Detail / Source /
Output / Logs, profils d'exécution, YAML, Python Environment, History,
comparaison, rapports HTML, Settings, Console, thèmes, raccourcis clavier,
dépannage, FAQ et glossaire.

- C'est un site moderne d'un seul fichier, qui fonctionne hors ligne : menu
  latéral, sommaire de page, étapes numérotées, encadrés, thème clair ou
  sombre.
- **Search the guide** (ou **Ctrl+K**) trouve instantanément les rubriques
  et surligne les mots recherchés.
- Le bouton d'impression produit tout le guide en PDF ; le fichier se
  partage aussi tel quel par mail.
- **Support and data locations** affiche la version, le Python des tests et
  les dossiers de l'historique et des réglages de ce poste ; **Copy support
  information** les copie pour un signalement.

Corrections de stabilité :

- Basculer entre **All tests** et **Profiles** pouvait fermer brutalement
  l'application : la liste des profils laissait derrière elle des objets
  Qt détruits que PySide croyait encore valides. C'était la cause des
  plantages aléatoires de la CI.
- Un Python lent à démarrer (premier lancement, antivirus, disque réseau)
  n'est plus déclaré **Python interpreter not usable** pour toute la
  session : la vérification est retentée une fois avec un délai doublé, et
  un délai dépassé n'est jamais mémorisé.
- Fermer une fenêtre ne produit plus d'erreurs parasites dans la console :
  les filtres d'événements ignorent les objets déjà détruits.

- Dans **Execution Profiles → Test sequence**, **Ctrl+Z** pouvait ne rien
  faire : deux commandes d'annulation se disputaient le raccourci.
- Un test devenu paramétré depuis la collecte, ou un fichier / dossier
  relancé depuis History, n'est plus marqué **Not run** alors que tous ses
  cas ont été exécutés, ce qui faisait échouer le run.
- Dans **History**, un groupe dont une partie seulement des tests a tourné
  affiche de nouveau **Not all tests run**, et un test non exécuté sa raison.
- Les lecteurs de la carte **Execution** retrouvent la hauteur des autres
  contrôles (32 px).
- En demi-écran, l'onglet **Logs** ne déborde plus de la barre
  **Detail / Source / Output / Logs** quand on change d'onglet.

La suite de tests de l'application repasse entièrement au vert : les tests
restés sur d'anciens comportements ont été alignés sur ceux en vigueur
(statut **Not run**, garde du workspace collecté, descriptions élidées).

## Lecteurs en vraies couleurs et compteurs lisibles — v1.7.14

Chaque lecteur a de nouveau une couleur franche, choisie pour ne jamais
ressembler à un verdict du thème affiché. En thème sombre : bleu ciel, rose,
vert citron, turquoise et orange ; en sombre daltonien : bleu, violet, vert,
or et corail. Un lecteur qui a réussi ne s'affiche plus dans la couleur d'un
échec. En thèmes clairs, les badges des lecteurs sont pleins, avec le nom en
blanc, dans l'arbre, les contrôles **Execution** et les onglets de sortie :
ils se lisent comme une étiquette et non comme un verdict.

Les cinq compteurs **Passed**, **Failed**, **Skipped**, **Error** et
**Not run** restent toujours visibles. En grande fenêtre, ils passent sur deux
rangées, chacun sur une seule ligne et en texte plus grand ; en fenêtre plus
petite, ils restent sur une rangée.

Pendant **Run N times** ou **Run until it fails**, le bandeau **Repeat**
signale aussi une collecte incomplète, par exemple « Collection incomplete ·
2 files not collected ».

## Onglets et progression stables — v1.7.13

Les onglets de run conservent une largeur fixe de 180 px, indépendamment
du nom, de l’état et des compteurs. Si la place manque, les flèches de
défilement permettent de parcourir les onglets.

Le compteur Results reste au format **X / X** pendant le run : une mise
à jour intermédiaire en pourcentage a été supprimée. Le total tient compte
du run ou du profil actif ; les tests Not run ne comptent pas comme exécutés.

## Badges colorés et diagnostics de crash — v1.7.12

Les lecteurs retrouvent des couleurs distinctes : bleu, turquoise, ambre,
mauve et vert. Leur couleur reste cohérente entre les contrôles Execution,
les badges de l’arbre, les détails, les onglets de sortie et les logs, y
compris dans la fenêtre de comparaison. Les badges ont un fond léger et un
contour coloré ; un lecteur décoché conserve une teinte reconnaissable.
Les thèmes clairs utilisent des nuances plus sombres pour garder les noms
lisibles. Les couleurs des verdicts restent inchangées.

Le style encadré des compteurs Results est conservé, avec des icônes plus
grandes : 20 px dans le bandeau compact et 24 px ailleurs.

Les crashs natifs de pytest sont rattachés au test en cours, avec leur code
Windows et les traces disponibles. Les tests demandés mais non exécutés sont
marqués **Not run**, sans être confondus avec un succès, un échec ou un Skip.
Leur raison reste consultable dans les détails, History et les rapports.

Validation ciblée : palettes, contrastes, badges, comparaison des logs,
thèmes et diagnostics de crash. L’exécutable Windows est reconstruit pour
cette version.

## Petites fenêtres sans chevauchement et répétitions nommées — v1.7.11

À 800 px de large, quand les cartes Environment, Execution et Results
s'empilent, la fenêtre ne descend plus sous la hauteur qu'elles demandent :
le bouton **Run tests**, **Stop** et le chemin du workspace restent entiers au
lieu de se chevaucher. Elle retrouve sa hauteur minimale de 560 px dès que les
cartes ont de nouveau la place d'être côte à côte. Le chemin, **Browse…**, **Collect** et **Run name** tiennent alors
sur une seule ligne, et le titre **RESULTS** reste lisible.

Quand l'arbre devient étroit, la colonne **Duration** s'efface d'elle-même
pour laisser la place aux noms de tests, puis revient quand la place revient.
Votre choix d'afficher ou non Duration n'est pas modifié.

Dans **History**, une série **Run N times** ou **Run until it fails** apparaît
avec l'origine **REPEAT** et un nom lisible, par exemple
« Run N times · test_login · 20× », au lieu d'un ancien run d'origine
inconnue nommé par son identifiant. Les noms trop longs se terminent par « … »
et restent complets au survol.

Corrections de M5 et du nouveau constat de l'audit de suivi 1.7.10.

## Couleurs des lecteurs et verdicts distinctes — v1.7.10

En thèmes daltoniens, **Passed** devient turquoise ; les cases cochées et les
boutons d'action restent bleus. Les échecs, tests ignorés et erreurs gardent
leurs couleurs propres, avec un contraste renforcé en thème sombre.

Dans les quatre thèmes, les lecteurs utilisent désormais des bleus et des
gris bleutés : leurs noms ne reprennent plus les couleurs des verdicts. Cette
identité reste cohérente entre les en-têtes du tree, les contrôles lecteurs,
les détails, les onglets de sortie et la fenêtre de comparaison des logs.
Les noms et les icônes restent disponibles pour reconnaître chaque élément.

Les différences de logs utilisent une couleur distincte de **Skipped** dans
les palettes daltoniennes. Les libellés de lecteurs conservent un contraste
d'au moins 4,5:1 sur leur fond, y compris lorsqu'ils sont sélectionnés.

Correction **M7** de l'audit 1.7.1. Validation : 58 tests ciblés et un run réel
de 20 exécutions sur cinq lecteurs, avec les quatre verdicts et les quatre thèmes.

## Comparaison des logs dans une fenêtre indépendante — v1.7.9

Dans **Logs**, **Compare…** ouvre une fenêtre indépendante, déplaçable et
redimensionnable, par exemple sur un autre écran. L'arbre et la consultation
d'un seul log restent disponibles dans la fenêtre principale.

La comparaison suit le test sélectionné dans ce run. Décochez **Follow selected
test** pour la figer ; **Load selected test** permet de charger explicitement
un autre test. Les campagnes affichent aussi la répétition et l'étape pour
identifier chaque appel d'un même test.

Chaque lecteur garde sa recherche et son ouverture de fichier. La navigation
entre différences, le retour à la ligne commun et les dispositions côte à côte
ou empilées restent disponibles. **Ctrl+Shift+D** ouvre ou retrouve cette fenêtre ;
**Ctrl+W** la ferme. Sa taille et sa position sont mémorisées.

Révision de **M6**, validée avec 40 tests ciblés et dans l'application réelle :
trois lecteurs, sélection et comparaison figée, raccourcis, fermeture/réouverture,
arrêt de l'application et thèmes clair/sombre.

## Comparaison des logs sans écraser l'arbre — v1.7.8

**Compare** conserve la largeur de l'arbre et de sa recherche. Sur un panneau
étroit, les logs s'empilent automatiquement ; sur un panneau large, ils sont
côte à côte. Le menu de disposition permet aussi de choisir **Automatic**,
**Side by side** ou **Stacked**. Une disposition côte à côte trop large défile
localement, sans déplacer le séparateur principal.

**Comparing N readers** indique clairement le mode actif, y compris après un
changement de test. Le bouton commun de retour à la ligne s'applique à tous
les logs ; changer ce réglage dans une console l'applique aussi aux autres.
Chaque lecteur garde sa recherche, ses erreurs, sa copie et son ouverture
externe. Les flèches de recherche apparaissent lorsqu'une recherche est saisie,
pour garder un champ lisible au repos.

Correction **M6** de l'audit 1.7.1. Validation : 30 tests ciblés et vérifications
dans l'application réelle avec trois lecteurs, recherches, changement de test,
dispositions automatique/manuelles et thèmes clair/sombre.

## Interface utilisable en petite fenêtre — v1.7.7

La fenêtre peut être réduite à 800 × 560 et utilisée en demi-écran à 960 px.
La navigation passe en icônes sur petite fenêtre sans écraser votre préférence
pour les grandes fenêtres. Le résumé des résultats devient une ligne compacte,
avec les mêmes compteurs et filtres, pour laisser davantage de place à l'arbre.

**Detail / Source / Output / Logs** restent accessibles : les onglets réduisent
leurs marges, puis utilisent leurs icônes si le panneau est très étroit.
Les noms de run longs affichent des points de suspension et leur texte complet
au survol. Les en-têtes de History et Execution Profiles se réorganisent sur
petite largeur ; les options des profils restent accessibles par défilement
sur les écrans moins hauts.

Correction **M5** de l'audit 1.7.1. Vérifications ciblées et captures réelles
aux formats 1280 × 720, 960 × 900, 930 × 990 et 800 × 600.

## Compteurs de répétitions cohérents — v1.7.6

Les actions **Run N times** et **Run until it fails** affichent un bilan dédié :
répétitions terminées, lecteurs, exécutions et verdicts. La progression avance
après chaque lecteur. Les cartes **Results · Previous run** conservent le
résumé du run précédent, sans mélanger ses chiffres avec ceux des répétitions.
Une répétition interrompue entre deux lecteurs ne compte pas comme terminée.
Le bilan reste visible après l'arrêt et disparaît au prochain run normal.

Correction du point **M4** de l'audit 1.7.1. Vérification par 27 tests ciblés
et dans l'application réelle : plusieurs lecteurs, échecs, annulation et arrêt
au premier échec.

## Environnement Python vérifié avant enregistrement — v1.7.5

Dans **Python Environment**, **Save** devient disponible seulement après
validation de Python et de pytest. Modifier le chemin invalide immédiatement
la vérification précédente. Une dernière vérification est effectuée avant
l'enregistrement, en arrière-plan pour garder l'interface réactive.

Les erreurs restent rouges en thème clair et sombre. Un Python inexistant
ou sans pytest est signalé comme **Python interpreter not usable**, plutôt
que comme une erreur de collecte. Le réglage global est vérifié séparément
de l'interpréteur imposé par le YAML du workspace. Changer de Python pendant
une collecte relance celle-ci avec le nouvel environnement.

L'infobulle de **Collect** indique désormais le bon raccourci : **Ctrl+R**.
Corrections des points **M2 et M3** de l'audit 1.7.1.

## Verdict de collecte et workspace fiables — v1.7.4

Un run dont certains fichiers n'ont pas pu être collectés affiche désormais
**Incomplete** en orange, même si tous les tests exécutés réussissent. Le
bouton **files not collected** donne accès aux erreurs. Cet avertissement
reste présent dans l'historique et les rapports HTML, y compris pour les
profils, les nouveaux onglets et les exécutions répétées. Les compteurs
continuent de représenter uniquement les tests réellement exécutés.

Un chemin invalide remet le champ sur le workspace réellement chargé. Les
tests de l'ancien projet ne peuvent pas être lancés lorsque le champ désigne
un nouveau dossier encore non collecté, y compris par raccourci ou clic
droit. La bannière d'erreur disparaît après une collecte réussie.

Corrections des points **C2 et M1** de l'audit 1.7.1.

## Historique stable après une relance — v1.7.3

L'utilisation des filtres et de la recherche dans **History**, suivie d'un
**Re-run** et d'un retour dans l'historique pendant l'exécution, ne provoque
plus la fermeture de l'application. Les cartes des runs restent disponibles
lors des changements de filtre, du défilement et des mises à jour de la liste.

Correction du point **C1** de l'audit 1.7.1, vérifiée sur le parcours complet
dans l'application réelle et par des tests de non-régression ciblés.

## Sauvegarde des résultats accélérée — v1.7.2

Après l'exécution, les cases du tree redeviennent modifiables immédiatement :
vous pouvez préparer et lancer la sélection suivante pendant la sauvegarde.
La file d'attente continue également sans attendre l'archivage. Un indicateur
discret en bas de la fenêtre signale les sauvegardes encore en cours.

L'enregistrement des grandes suites recherche les logs une seule fois par run,
au lieu de reparcourir les dossiers pour chaque test et chaque lecteur. Les
résultats terminés restent indépendants des nouvelles sélections ; les runs,
leurs paramètres et leurs logs sont conservés séparément dans l'historique.
Les logs de cas comme `[0]` et `[10]` ne sont plus confondus lors de l'archivage.

L'export HTML d'un run encore en cours de sauvegarde demande d'attendre la fin
de son enregistrement pour produire un rapport complet. Les autres runs
restent exportables.

## Sélections de cas paramétrés conservées — v1.7.1

Dans **Add tests / groups**, un cas choisi individuellement reste une
sélection précise lorsque le test reçoit de nouveaux paramètres. Choisir
explicitement une fonction, un fichier ou un dossier complet permet toujours
de suivre ses futurs cas et tests.

Copier, coller, dupliquer un cas ou enregistrer **Contents…** n’active plus
implicitement le suivi de toute sa fonction. **Add selected again** respecte
aussi ce choix après un double-clic. Supprimer un test conserve le suivi
des autres tests du groupe et ses exclusions.

Pour un ancien cas déjà enregistré comme fonction suivie : sélectionner ce
cas, ouvrir **Contents…**, choisir **Keep selected cases**, puis sauvegarder.
[Détails et vérifications](docs/explicit-parameter-selection.md).

## Mise à jour des campagnes simplifiée — v1.7.0

Dans **Run Tests** et **Execution Profiles**, une collecte réussie propose
une mise à jour globale de la campagne, sans décision obligatoire par test.
**Contents…** distingue la sélection fixe du suivi des nouveaux tests d’un
dossier. Les choix avancés restent disponibles pour les remplacements ambigus.

Un test simple devenu paramétré est remplacé par ses cas à **chaque appel**
dans la campagne, y compris dans les anciens profils. L’ordre, les groupes
et les réglages YAML de chaque appel sont conservés. Les nouveaux cas sont
ensuite proposés pour chacun de ces appels ; une sélection explicite de cas
précis reste fixe. La fenêtre montre directement les changements et le total
avant/après, sans changer de taille quand on affiche les chemins complets.

Les profils existants restent lisibles. Les profils utilisant le suivi des
sources ou conservant des groupes vides nécessitent la version 1.7.0 ou plus.

Les groupes vides conservent leur présentation et leur YAML ; les brouillons
restent disponibles quand on change de profil. **Undo update** fonctionne aussi
après redémarrage et protège les modifications plus récentes.

Une exécution partielle affiche **Campaign incomplete** dans l’interface,
l’historique et le rapport HTML. Les tests non exécutés restent dans l’arbre
du rapport avec leur motif. [Comportements et vérifications](docs/campaign-update-review.md).

## Rapports HTML plus lisibles et plus fluides — v1.6.1

Dans l'onglet **YAML**, le tableau affiche directement la valeur effective
de chaque paramètre. L'origine des valeurs et les configurations complètes
restent consultables dans des sections dépliables.

Les durées enregistrées sont retrouvées dans les sorties pytest archivées
lorsqu'elles peuvent être associées sans ambiguïté à un test et à sa
tentative. Les durées absentes restent signalées ; les temps partiels sont
identifiés. Les noms longs des lecteurs ne chevauchent plus la colonne
**Duration**, qui reste visible sur téléphone.

Les clics sur les tests, lecteurs et onglets sont plus fluides dans les
grands rapports. Ils conservent l'état de l'arbre ; les longues listes de
groupes sont paginées et la console se charge à son ouverture.

Après un export HTML depuis **History**, une petite fenêtre **Export complete**
propose **Open report** pour ouvrir le fichier dans le navigateur par défaut.

## Rapports HTML d’analyse IN Groupe — v1.6.0

Dans **History → Export → Export complete HTML report…**, un même rapport
réunit tous les lecteurs du lancement. Les exports par lecteur restent
accessibles dans leurs sous-menus. La génération se fait en arrière-plan.

Le rapport reprend l’arbre du profil : groupes, sous-groupes, descriptions,
couleurs, fichiers et cas paramétrés. Les occurrences répétées restent
indépendantes. Sélectionner un groupe montre son bilan ; sélectionner un
résultat ouvre les détails de ce lecteur, les tentatives, les traces, les
logs archivés et le YAML effectif avec l’origine des paramètres.

Le fichier contient le logo IN Groupe et les mêmes pictogrammes que
l’interface. Il reste utilisable hors ligne, sur ordinateur ou téléphone,
sans Pytest Runner ni accès au projet d’origine. Il inclut une vue de
secours sans JavaScript et une présentation d’impression.

Les nouveaux runs conservent leurs données d’analyse dans un fichier annexe
à l’historique : résultats par occurrence/tentative, durées, logs disponibles
et commandes réellement lancées. Les anciens historiques restent exportables ;
les informations absentes sont marquées **Unknown** ou **Not recorded**.
Les traces ambiguës ne sont pas attribuées au hasard à des tests homonymes.

## Suivi bleu des tests en cours — v1.5.5

Dans **Run Tests**, le test actif et ses groupes restent signalés en bleu,
dans **All tests** comme dans **Profiles**, en thèmes clair et sombre.
Le suivi retrouve le bon test lorsque le projet utilise une racine pytest
différente, notamment avec un **pytest.ini** ou **pyproject.toml** imbriqué,
et distingue les tests homonymes de plusieurs suites.

La branche est aussi signalée pendant le démarrage du processus et sa
collecte ; le statut indique alors **Preparing**. Cette préparation conserve
les résultats précédents des profils jusqu'au démarrage effectif du test.
Le bleu reste présent pendant le setup, le test et son nettoyage final,
même si pytest affiche déjà **PASSED** avant la fin du teardown.

Le suivi fonctionne avec plusieurs lecteurs et avec pytest-xdist. Les
titres des groupes respectent leur état actif, tout en conservant la couleur
de leur description et leur repère de groupe.

## Profils : conserver son contexte de travail — v1.5.4

Dans **Run Tests → Profiles**, décocher des occurrences puis cliquer sur
**Run profile** conserve le profil complet dans le même onglet. Seules les
occurrences cochées sont exécutées, avec leurs YAML propres et dans leur
ordre. Les cases restent cochées après le run. Les tests non relancés gardent
leurs résultats, durées, traces, sorties et chemins de logs ; leurs verdicts
précédents sont identifiés dans l'arbre et sur la ligne du lecteur de Detail.
Les compteurs et l'historique décrivent uniquement l'exécution qui vient
d'être lancée. Les doublons, répétitions et reprises restent indépendants.

Les groupes retrouvent un arbre compact : les dossiers communs tels que
**TSu/RA/Int/FlexiDep/tests** sont masqués à l'intérieur d'un groupe nommé,
en conservant les fichiers et les cas paramétrés utiles. Le titre du groupe
ne chevauche plus la case à cocher ou l'icône ; il reste lisible lorsqu'il
est sélectionné en thème clair. Les colonnes lecteurs se redimensionnent
depuis leurs deux bords et leur largeur reste mémorisée par lecteur.

Dans **Execution Profiles → Test sequence**, les branches ouvertes et fermées
ainsi que le point de défilement sont conservés lors des changements de YAML,
renommages, duplications, suppressions, déplacements, copier-coller et
sauvegardes. Annuler et rétablir conservent aussi les choix d'ouverture faits
entre-temps. Les commandes de focus ne reprennent plus un Ctrl encore tenu ;
les vrais Ctrl-clics gardent la sélection multiple.

Le clic droit propose **Add tests / groups…** au point cliqué. La fenêtre
indique la destination ; les ajouts successifs et **Add selected again**
restent à cet endroit. Le bouton principal utilise également la sélection :
dans le groupe choisi, après la ligne d'un test, ou en fin de profil sans
sélection. Les nouveaux tests héritent du YAML de leurs groupes parents.

**Suppr / Delete** retire les éléments sélectionnés dans Test sequence,
y compris une sélection multiple de tests ou de groupes. **Ctrl+Z** annule
la suppression et **Ctrl+Y** la rétablit. Le menu **Remove** affiche le
raccourci. Les champs de texte et les dialogues de paramètres gardent leur
comportement normal ; maintenir Suppr n'enchaîne pas les suppressions.

## Arbre des profils aligné sur All tests — v1.5.3

Dans **Run Tests → Profiles**, l'arbre reprend la présentation de **All tests** :
dossiers, fichiers, fonctions et cas paramétrés, sans niveau de classe lorsqu'il
est seul dans son fichier. Les classes multiples restent distinctes. Une seule
répétition n'ajoute plus de ligne **Repetition 1/1**, et les noms des tests
n'ont plus de préfixe numérique. L'occurrence reste identifiable au survol
et dans ses détails lorsqu'un test est répété.

Les cases à cocher permettent de sélectionner les occurrences à exécuter.
**Select all**, **Clear selection**, les raccourcis et la sélection des tests
où les lecteurs divergent ciblent l'arbre affiché. La sélection est conservée
dans les sessions et lors de la duplication d'un onglet.

La colonne **Duration**, son menu et les modes de calcul suivent les mêmes
réglages que dans **All tests**. Sélectionner un dossier, un fichier ou une
fonction paramétrée affiche son bilan par lecteur, ses durées et ses erreurs,
avec des liens vers les occurrences concernées. Les traces restent disponibles
pendant que le run continue, comme depuis la version 1.5.2 incluse dans main.

Le clic droit propose la relance ciblée, **Run N times**, **Run until it fails**,
la copie du nodeid ou de la trace, la source et l'activation. **Re-run failed**
relance les occurrences encore en échec après leur dernière reprise. La
recherche dans les erreurs et les raccourcis **Ctrl+1/2/3/4** suivent la vue
profil. La ligne en cours reste signalée tant qu'un lecteur travaille dessus.

Une exécution partielle ou ciblée ouvre un nouvel onglet et conserve l'ordre,
les doublons et les YAML propres aux occurrences sélectionnées. Le profil
et les résultats d'origine restent disponibles. Les groupes colorés,
descriptions, répétitions et reprises restent propres aux profils.

## Détails des tests disponibles pendant le run — v1.5.2

L'onglet **Detail** affiche les traces d'erreur dès leur réception, sans
attendre la fin du run. Les erreurs de **setup**, d'appel du test et de
**teardown**, les motifs de skip et les durées sont disponibles pendant que
les tests suivants continuent de tourner, en exécution classique comme avec
un profil et plusieurs lecteurs.

Dans un profil, chaque occurrence, tentative de reprise et lecteur conserve
ses propres détails. Changer de test puis revenir permet de les consulter
avant la fin du lot. Une relance réussie remplace l'ancienne trace d'échec.
La console reçoit également les traces au fil de l'eau, sous forme lisible.
Les rapports finaux et l'historique conservent les diagnostics sans les dupliquer.

## YAML des profils : édition par test et repères visibles — v1.5.1

Dans **Execution Profiles**, **YAML parameters…** fonctionne sur un test,
un cas individuel, une fonction paramétrée, un dossier, une classe ou un
groupe nommé. Un double-clic sur un test ou une fonction paramétrée ouvre
directement ses paramètres. Pour un ensemble de tests, **Mixed values —
unchanged** indique des réglages différents : seuls les champs modifiés
dans la fenêtre sont appliqués à tous. Les autres valeurs propres à chaque
cas sont conservées. Annuler/rétablir couvre cette modification en une action.

Le menu clic droit sépare **Edit YAML parameters…** (modifier les réglages)
de **View effective YAML…** (consulter les valeurs finales). Dans la fenêtre
d'édition, les colonnes **Use value from** et **Value used** distinguent la
source choisie de la valeur utilisée. Sous une valeur personnalisée, **Without
this customization** indique celle qui serait reprise en supprimant cette
personnalisation ; ce n'est pas une seconde valeur utilisée simultanément.

Dans cette fenêtre, chaque valeur de référence indique sa véritable origine :
**Profile** ou le nom complet du groupe/sous-groupe concerné. **Custom values
only**, à côté de la recherche, permet de retrouver uniquement les paramètres
explicitement personnalisés sur le test ou le groupe en cours. Les valeurs
mixtes restent visibles lorsqu'au moins un test les personnalise. Le filtre
se combine avec la recherche par paramètre ou origine et ne modifie aucune valeur.
Si un champ invalide est masqué par les filtres, un lien permet de le retrouver
directement et de le corriger avant d'appliquer les modifications.

Une petite pastille ambre sur l'icône signale les paramètres explicitement
personnalisés sur ce test ou ce groupe. Les valeurs simplement héritées
n'ajoutent aucun repère permanent. Le survol distingue **Value used** (valeur
utilisée) de **Inherited value** (valeur reprise sans la personnalisation) et
indique le groupe d'origine. Pour un groupe, **Group default** désigne son
réglage par défaut. Une valeur personnalisée identique à l'héritage conserve
sa pastille. Les dossiers repliés détaillent les tests personnalisés au survol.

Le survol présente les paramètres dans des encarts : noms en gras, valeurs
utilisées agrandies, personnalisations en ambre et valeurs provenant des
groupes en bleu. La valeur héritée et son origine restent en retrait sous
chaque réglage. Les couleurs suivent le thème au moment du survol. Les listes
longues sont résumées avec le nombre de paramètres supplémentaires ; le YAML
complet reste accessible dans l'aperçu. Les descriptions accessibles gardent
l'ensemble des informations en texte simple.

Une personnalisation ou un écart d'héritage ne porte plus de triangle d'alerte.
Le triangle est réservé à un problème réel de lecture du YAML : fichier
inaccessible, syntaxe invalide ou racine qui n'est pas un dictionnaire.
Son survol donne le diagnostic ; il disparaît une fois la configuration corrigée.

Les icônes des dossiers, fichiers Python, classes, fonctions et cas reprennent
la couleur du groupe nommé le plus proche. Un sous-groupe utilise sa propre
couleur. Les mêmes couleurs, pastilles et infobulles apparaissent dans **Run
Tests** dès le chargement du profil, puis pendant l'exécution et les reprises.
Les couleurs des résultats par lecteur restent celles de leurs verdicts.
L'infobulle de Run Tests rappelle que l'édition du profil dans **Execution
Profiles** s'applique aux exécutions suivantes.

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
