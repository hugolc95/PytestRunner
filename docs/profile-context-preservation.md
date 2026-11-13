# Profils : conserver le contexte de travail

## Exécution partielle dans Run Tests

Décocher des occurrences puis cliquer sur **Run profile** conserve le profil
complet dans le même onglet. Seules les occurrences cochées sont exécutées,
dans leur ordre, avec leur YAML propre. La sélection reste identique après
l’exécution ; les doublons et répétitions gardent leurs lignes d’origine.

Les occurrences non relancées conservent leurs verdicts, durées, traces,
sorties et chemins de logs. Leur résultat précédent est indiqué dans la ligne
du lecteur de Detail et par le style du verdict dans l’arbre. Les compteurs
du run et l’historique décrivent uniquement les occurrences réellement lancées.
L’historique conserve le sous-ensemble et ses paramètres pour pouvoir le rejouer.

Le résultat d’une occurrence est remplacé lorsqu’elle commence effectivement
sur un lecteur. Les tentatives précédentes de ce lecteur sont réinitialisées ;
les résultats des autres lecteurs restent disponibles. Une occurrence cochée
mais non atteinte conserve son ancien résultat.

Les fiches, traces en direct et sorties des lots sont rattachées aux positions
du profil complet, même pour une sélection non contiguë dans plusieurs répétitions.
La file d’attente fige aussi cette correspondance et les paramètres au lancement.
Les relances ciblées du menu contextuel restent des onglets séparés.

## Édition dans Test sequence

Les branches ouvertes et fermées restent en place après un renommage, un
changement de YAML, une duplication, une suppression, un déplacement par les
flèches ou glisser-déposer, un copier-coller ou une sauvegarde. Les groupes
indépendants contenant les mêmes tests gardent chacun leur état.

Le défilement s’appuie sur la ligne visible en haut, plutôt que sur un numéro
de ligne qui change après une insertion. Une modification de métadonnées
conserve ainsi le point de lecture. Un élément déplacé ou collé est révélé
si nécessaire ; ses branches et les groupes non concernés conservent leur état.

Annuler et rétablir modifient le contenu sans annuler les choix d’ouverture
faits entre-temps. Une branche supprimée puis restaurée retrouve son état.
Les identifiants utilisés sont propres à l’éditeur ; le format des profils
enregistrés et exportés reste inchangé.

La touche **Suppr / Delete**, lorsque Test sequence a le focus, retire la
sélection comme le bouton **Remove** : tests, cas paramétrés, dossiers,
groupes et sous-groupes, y compris plusieurs éléments à la fois. Un parent
sélectionné avec ses enfants est retiré une seule fois. **Ctrl+Z** restaure
les éléments et leur YAML ; **Ctrl+Y** rétablit la suppression. Le menu affiche
le raccourci. Les champs de texte, dialogues de paramètres et la bibliothèque
des profils gardent leur comportement habituel. Maintenir Suppr enfoncée
ne déclenche pas une cascade de suppressions.

## Ajouter au point du clic droit

Le menu de Test sequence propose **Add tests / groups…** sur les groupes,
sous-groupes, dossiers, fichiers, fonctions paramétrées et tests. Le groupe
cliqué reçoit les nouvelles occurrences à la fin de son bloc ; une ligne
de test les reçoit juste après elle. La fenêtre indique le point d’insertion.
Le clic droit reste la référence même si plusieurs lignes sont sélectionnées
et que le focus clavier est sur une autre ligne.

Le bouton **Add tests / groups** utilise aussi la sélection courante.
Sans sélection, ou depuis le menu du fond vide, l’ajout se fait en fin de
profil. Les ajouts successifs, y compris **Add selected again**, avancent
au même point d’insertion et conservent l’ordre choisi.

Les nouveaux tests héritent des paramètres des groupes parents de la
destination, avec des paramètres propres initialement vides. Les paramètres
des tests existants et l’état des autres branches restent conservés.
Les dossiers de source restent déduits des vrais chemins : un fichier issu
d’un autre dossier est placé à cet endroit de la séquence sous son propre
chemin, dans le même groupe nommé. Chaque ajout peut être annulé et rétabli.
Fermer le sélecteur sans ajouter ne modifie pas le profil.

## Vérifications

- `test_profile_partial_context.py` : vrais runs pytest, deux lecteurs,
  doublons avec YAML différents, répétitions, résultats et logs précédents,
  sélection non contiguë, file d’attente et reprise d’un seul lecteur.
- `test_profile_sequence_view.py` : actions d’édition, états indépendants,
  annuler/rétablir, conservation de l’ancrage de défilement et déplacement
  d’un sous-arbre.
- `test_profile_context_add.py` : cible exacte du clic droit, sous-groupes,
  dossiers et lignes de test, ajouts répétés, ordre, héritage YAML, annulation,
  profil vide, fond vide et limite du nombre d’occurrences.
- Vérification dans l’application avec les quatre modules de production,
  données isolées et lecteurs simulés. Les captures proviennent de Qt.

### Résultats

Les 429 tests ciblés de 26 modules passent avec Qt 6.8.3, dont cinq scénarios
de relance partielle et quinze scénarios de stabilité de l’éditeur. Les vrais
Ctrl-clics conservent la sélection multiple ; un focus programmé par une
commande ignore un Ctrl encore tenu et sélectionne seulement sa cible.

La suite complète initiale a produit 1 561 réussites et quatre échecs. Trois
problèmes de sélection ont été corrigés, puis les modules concernés ont été
relancés avec succès. Le test de collecte/détails restant repasse isolément.
La suite complète n’a pas été relancée après ces corrections.

Les essais isolés ont aussi reproduit sur v1.5.3 un plantage natif à l’arrêt
de Python : le presse-papiers offscreen conservait un QMimeData Python jusqu’à
la destruction tardive de QPlatformClipboard. Le banc d’essai libère désormais
ses données de presse-papiers avant l’arrêt de QApplication. Les tests de
l’éditeur et le parcours visuel se terminent alors avec un code de sortie nul.
La vérification matérielle et Windows reste à effectuer sur le poste utilisateur.

Pour l’ajout contextuel : les 14 nouveaux tests et 165 tests de régression de
l’éditeur passent, soit 179 tests ciblés. Le parcours dans l’application réelle
vérifie le menu, la destination affichée, deux ajouts successifs dans un
sous-groupe, l’héritage YAML, la conservation d’un autre groupe fermé et
annuler/rétablir. Aucun problème applicatif n’est relevé ; les messages Qt
concernent uniquement les limites de fenêtres du mode offscreen.

Pour Suppr : 27 tests de stabilité/clavier et 86 tests de régression passent
(113 contrôles ciblés). Les essais au clavier couvrent les tests, cas et
fonctions paramétrés, dossiers, groupes, sélections multiples et parents avec
enfants, puis Ctrl+Z/Ctrl+Y. Les champs de nom/description, un dialogue de
saisie et la bibliothèque des profils conservent leur comportement normal.

Avant publication de v1.5.4, les quatre modules de mise en page, relance
partielle, ajout contextuel et stabilité/clavier repassent : 65 tests réussis
avec Qt 6.8.3. Le parcours de démarrage et des pages dans les trois thèmes
produit 18 captures sans erreur applicative ni message Qt. Les échecs du
projet de démonstration sont intentionnels.
