# Mise a jour des campagnes - branche d'evaluation

Branche : `codex/campaign-update-review`. Pas de livraison sur main.

## Parcours courant

Apres une collecte reussie, Run Tests et Execution Profiles affichent les
changements de la campagne. **Review changes...** montre un resume, puis
**Update campaign** applique la mise a jour en une fois. Aucun choix par
test n'est obligatoire. **Show changes** deploie la liste en lecture seule ;
**Advanced choices...** garde les remplacements individuels pour les cas rares.

Les references dont seuls les prefixes de chemin ont change sont reconnues
si le chemin relatif, la classe, la fonction et le parametre correspondent
sans ambiguite. Un meme nom de fichier dans plusieurs suites ne suffit pas.
Les nouvelles references conservent leurs identites, cases cochees et YAML.
Les dossiers suivis et leurs exclusions suivent aussi le changement de racine.

Les nouveaux tests des blocs suivis sont proposes ensemble. Les anciens cas
parametres sans exception YAML sont renouveles a partir des cas actuellement
collectes. Les cas ambigus et ceux qui portent une configuration propre sont
gardes par defaut ; le transfert de leur YAML reste un choix avance explicite.
Une option globale permet de retirer les tests qui n'ont pas pu etre retrouves.
Le resume indique le nombre de tests et les configurations qui seraient retires.

Si aucun test de la campagne n'est retrouve, le dialogue explique qu'il faut
verifier le projet et la collecte. Il propose **Collect again**, sans proposer
de supprimer toute la campagne. Un echec ou une collecte incomplete ne produit
aucune proposition de retrait. Un autre projet exige un changement explicite.

Les tests introuvables restent visibles et inspectables dans Run Tests, avec
un avertissement. Ils ne sont pas coches pour l'execution, meme avec Select all
ou les commandes de relance d'un groupe. Les tests disponibles peuvent tourner.
Le choix de selection sous-jacent est conserve pour les tests retrouves ensuite.

## Contenu de la campagne

**Contents...** propose deux choix :

- **Keep only the tests I selected** : conserver la selection precise ;
- **Include new tests from these folders or files** : afficher les dossiers
  et fichiers a suivre, avec le nombre de tests actuellement trouves.

La liste n'est visible que dans le second mode. Les nouveaux tests peuvent
heriter des reglages du groupe ; les blocs T0 et T1 restent independants.
**Save campaign** sauvegarde les reglages et le brouillon de campagne courant
en une fois, sans bouton Follow ni seconde validation dans l'editeur.
Les exclusions volontaires existantes restent conservees. **Advanced...**
donne acces a leur restauration, aux chemins precis et aux sous-dossiers.

## Conservation et annulation

La mise a jour conserve l'ordre personnalise, les groupes, descriptions,
couleurs, repetitions, YAML, branches ouvertes et selections. Les traces et
durees des occurrences inchangees sont retrouvees par identite stable. Un
nouveau cas ne recupere pas le verdict d'un autre cas. L'historique reste fixe.
La sauvegarde remplace le fichier de facon atomique.

**Undo update** restaure la campagne precedente pendant la session, sans
ecraser des edits ulterieurs. Une campagne active ou en file peut etre
inspectee ; sa mise a jour attend la fin du run. Dupliquer ou copier une source
complete cree une source independante ; une copie partielle reste fixe.

Les anciens formats restent lus. Les profils sauvegardes avec les nouvelles
identites et sources utilisent le format portable v4, non lu par les anciennes
versions de Pytest Runner. La detection suit les collectes reussies ; elle ne
surveille pas le disque en permanence et n'applique rien sans validation.

## Verification de la simplification UX

Tests cibles : domaine, dialogues, 38 references deplacees, ambiguite entre
deux suites, conservation des exclusions et du YAML, absence de choix par
test, suppression globale facultative, selection/relance et sauvegarde unique.
Pas de suite complete.

Parcours dans l'application avec les quatre modules d'installation, reglages
et historique isoles : collecte reelle de 38 tests, campagne provenant d'une
autre racine de collecte, correction des 38 references en une validation,
YAML conserve, 38 cases cochees retrouvees, sauvegarde du contenu en une fois,
puis execution d'un seul test pour verifier le lancement sans relancer toute
la campagne. Cas sans correspondance verifie en clair et sombre.

Captures : `/workspace/campaign-ux-captures/`.
