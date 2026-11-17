# Selection precise de cas parametres — v1.7.1

Correction preparee sur `codex/preserve-explicit-parameter-selection`, depuis
la version 1.7.0, puis livree sur main dans la version 1.7.1.
Les campagnes de campagnes ne sont pas modifiees.

## Reproduction et causes

Six tests de reproduction echouaient sur le code initial :

- Avec un seul cas collecte, cocher sa feuille faisait croire que son dossier
  ou sa fonction avait ete choisi en entier.
- Cocher tous les cas individuellement etait egalement assimile au choix
  d'une branche complete.
- Dupliquer ou copier une seule feuille pouvait copier la regle de suivi de
  toute la fonction, lorsque cette regle n'avait qu'un seul cas membre.
- Enregistrer Contents dans une campagne mixte pouvait activer le suivi des
  autres selections fixes sans action explicite sur leurs lignes.
- Un fichier suivi pouvait proposer de nouveau le cas fixe deja ajoute, ses
  anciens voisins non selectionnes et les nouveaux parametres.

L'investigation a aussi trouve que supprimer une feuille pouvait retirer
les regles de suivi de tout son groupe : la metadata d'appartenance etait
confondue avec un groupe explicitement supprime. Copier une feuille pouvait
emporter un groupe vide voisin pour la meme raison.

## Comportement corrige

Le selecteur distingue maintenant la branche cochee volontairement des
parents coches automatiquement par propagation. Un clic sur un cas, meme
s'il est seul ou si tous les cas sont coches un a un, garde une selection
precise. Le suivi futur reste propose pour une fonction, un fichier ou un
dossier choisi explicitement. La preference de suivi est conservee lorsqu'on
change de selection et pour Add selected again.

Les copies et duplications de cas individuels restent fixes ; celles de
fonctions ou groupes complets conservent leur suivi independant. Un ancien
contenu de presse-papiers marque comme cas individuel n'active plus de suivi
implicite au collage.
Un double-clic sur un cas suivi de Add selected again ne reprend plus la
regle d'une fonction ajoutee precedemment.

Contents conserve les lignes fixes decochees quand d'autres sources sont
suivies. Le fichier suivi ne rajoute pas les voisins d'une fonction dont un
cas a ete ajoute comme selection fixe dans le meme groupe. Les autres tests
et les appels complets de fonction continuent a recevoir leurs ajouts.

La suppression d'un cas preserve le suivi des autres tests. Les exclusions
empechent le fichier de reintegrer ensuite toute la famille du cas retire.
Undo restaure la selection et les regles precedentes.

## Verification

Tests cibles : `test_campaign_explicit_cases.py`, `test_campaign_hmac_update.py`,
`test_campaign_sync_ui.py`, `test_profile_clipboard.py`,
`test_profile_context_add.py`, `test_campaign_review_complete.py`.
Aucune suite complete lancee.

Parcours reel avec les quatre modules d'installation, donnees utilisateur
isolees et clic natif sur la case du selecteur :

1. Collecter SHA256, SHA384 et SHA512.
2. Ajouter seulement SHA256 dans un groupe contenant deja un fichier suivi.
3. Enregistrer Contents sans modifier le suivi des selections fixes.
4. Ajouter SHA224 au fichier et collecter a nouveau : aucun autre cas HMAC
   n'est propose pour cette selection, qui reste SHA256 seul.
5. Executer la campagne : le test voisin et SHA256 passent ; les autres cas
   HMAC ne sont pas lances.
6. Choisir une fonction complete et ajouter un cinquieme cas : la mise a jour
   4 → 5 reste disponible et fonctionne.

Captures et journal : `/workspace/explicit-case-captures/`.

## Campagnes deja enregistrees

Les anciens fichiers qui declarent deja une fonction suivie ne permettent
pas de savoir si cette intention etait volontaire ou due a l'ancien
selecteur. Aucune regle existante n'est effacee par supposition. Pour figer
un tel cas, le selectionner dans l'editeur, ouvrir Contents, choisir
Keep selected cases et sauvegarder. Les selections deja fixes sont protegees
sans cette intervention.
