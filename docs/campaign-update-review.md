# Synchronisation des campagnes - premiere version

Branche de travail : `codex/campaign-update-review`. Pas de changement de
version ni de livraison sur main pour cette premiere evaluation.

## Utilisation

Apres une collecte reussie, Run Tests et Execution Profiles indiquent les
changements des campagnes. La bibliotheque affiche un repere Update/Review.
Une occurrence absente reste visible avec un avertissement : la campagne
peut etre ouverte, puis corrigee avec **Review changes...**.

Dans **Add tests / groups**, l'option **Follow complete folders, files and
parameterized tests** conserve les sources des branches completes. Les
feuilles choisies individuellement restent fixes. Decocher l'option produit
une selection entierement fixe.

Pour une ancienne campagne, **Enable tracking...** ou le clic droit
**Selection tracking / sources...** permet de suivre un dossier, fichier ou
test parametre. Sans selection dans l'editeur, le dialogue prend les
occurrences de toute la campagne ; chaque groupe conserve un suivi distinct.
Les tests actuellement absents de la selection peuvent rester exclus ou
etre proposes dans la prochaine revue. Les sous-dossiers sont optionnels.

La revue distingue les ajouts, les anciens cas parametres introuvables et
les autres occurrences absentes. Chaque absence demande un choix : garder,
retirer, choisir un cas du meme test ou un autre test explicitement collecte.
Le transfert d'un override YAML propre au test est volontaire. Un nouveau
test herite du YAML du groupe. Un cas utilise comme remplacement n'est pas
ajoute une seconde fois dans le meme bloc.

Les ajouts sont inseres pres de leur fonction/fichier, en respectant l'ordre
des occurrences existantes. L'ordre personnalise, les groupes, descriptions,
couleurs, repetitions et YAML sont conserves. Les blocs T0/T1 ne partagent
pas leurs exclusions. Dupliquer ou copier/coller une source complete cree
une source independante ; une copie partielle reste une selection fixe.

**Update and reload** sauvegarde la campagne par remplacement atomique et
recharge les vues qui l'utilisent. Les cases cochees, branches ouvertes,
selection, traces et durees des occurrences inchangees sont retrouvees par
identite stable. Un test remplace ou dont le YAML a change ne recupere pas
le verdict de son ancienne version. **Undo update** restaure la precedente
campagne pendant cette session, sans ecraser des modifications ulterieures.

Les suppressions volontaires et les ajouts refuses deviennent des exclusions
de source. **Restore excluded tests...** permet de les reproposer. Un test
conserve comme indisponible doit etre resolu ou decoche avant une execution
partielle : aucune occurrence absente n'est ignoree silencieusement.

## Limites volontaires de cette premiere version

- Les changements sont detectes apres collecte, pas par surveillance des
  fichiers en continu. La revue est manuelle ; l'option Settings d'application
  automatique des ajouts reste a evaluer apres ce premier retour.
- Un echec ou une collecte partielle ne produit aucune proposition de retrait.
  Un autre workspace demande de rebinder explicitement les sources et, si
  necessaire, leurs chemins. Aucun renommage n'est deduit d'une ressemblance.
- Une campagne en cours ou en file peut etre inspectee, mais sa mise a jour
  attend sa fin. Les edits ordinaires sauvegardes pendant un run ne changent
  pas son instantane ; le rechargement attend la liberation du verrou.
- Les anciens formats restent lisibles. Les identites et sources utilisent
  le format portable v4 ; les anciennes versions de Pytest Runner ne lisent
  pas les nouveaux profils sauvegardes dans ce format.
- La revue n'a pas de bouton de lancement partiel dedie : utiliser les cases
  de Run Tests pour choisir explicitement les occurrences executables.

## Verification

27 tests ajoutes pour la synchronisation et l'interface passent. Les controles
cibles existants couvrent egalement le format des profils, le copier/coller,
le choix des profils et les ajouts au point clique. Pas de suite complete.

Parcours dans l'application avec clean_ui, end_run_feedback, main_ux et
runtime_polish installes, reglages/profils/historique isoles : collecte de
4 tests reels, modification des fichiers Python, nouvelle collecte de
6 tests, revue des changements dans deux groupes T0/T1, campagne de 8 a
12 occurrences, puis execution reussie. Des captures montrent les deux
pages, les sources, la revue et l'arbre recharge. La collecte est aussi
terminee avec Execution Profiles deja ouvert pour verifier son actualisation.

Captures de travail : `/workspace/campaign-sync-captures/`.
