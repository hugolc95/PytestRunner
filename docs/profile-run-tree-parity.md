# Arbre d’exécution des profils : comparaison avec All tests

Branche de travail : `codex/profile-run-tree`, basée sur le correctif des détails
immédiats `7b31dcb` (v1.5.2). L’éditeur Execution Profiles et le format portable
des profils ne changent pas.

| Comportement | Écart constaté avant | Comportement aligné |
| --- | --- | --- |
| Classes uniques | Niveau Class toujours présent | Même fonction `collapse_single_class` que All tests ; les classes multiples restent distinctes. |
| Dossiers, fichiers, cas paramétrés | Certaines chaînes étaient supprimées dans les groupes nommés | Même hiérarchie utile, sans fusionner les occurrences non contiguës. |
| Répétition unique | Ligne Repetition 1/1 systématique | Aucun niveau supplémentaire ; les répétitions multiples restent identifiées. |
| Noms des tests | Préfixe numérique systématique | Même nom que dans All tests ; l’occurrence reste identifiable au survol et dans Detail. |
| Sélection | Aucune case ; boutons de sélection désactivés | Cases par occurrence, états partiels des groupes, Tout cocher / Tout décocher et sélection des divergences. Les reprises ne sont pas des occurrences sélectionnables supplémentaires. |
| Durées | Colonne absente | Colonne Duration, durées par lecteur, total des groupes, modes slowest/fastest/average/spread/lecteur spécifique. |
| En-tête | Réglages absents | Même menu Duration et remise à zéro des largeurs ; largeurs mémorisées séparément par vue et identité de colonne. |
| Ligne en cours | Présentation différente sur les noms | Branche et feuille en cours signalées, sans perdre l’indicateur si l’autre lecteur continue. |
| Clic dossier/fichier/fonction paramétrée | Pas de fiche de groupe exploitable | Bilan par lecteur, durée cumulée, erreurs et liens vers les occurrences exactes ; source du fichier disponible. |
| Menu clic droit | Ancien menu réduit aux résultats précédents | Run only this, Run until it fails, Run N times, copie du nodeid, copie de trace, source, activation et résultats précédents. Un seul menu est ouvert. |
| Re-run failed | Risque de relance classique sans YAML propre à l’occurrence | Relance des occurrences encore en échec après leur dernière reprise, avec leurs paramètres de profil. |
| Recherche | Noms disponibles, traces seulement après le rapport final, sans liste d’extraits | Navigation des noms et erreurs, liste des erreurs correspondantes, traces en direct incluses, distinction des occurrences répétées. |
| Clavier | Ctrl+1/2/3/4 ciblait le panneau classique | Detail, Source, Output et Logs suivent la vue active ; navigation des lignes et cases conservée. |
| Compteur d’onglet | Total du profil, même après une sélection partielle | Nombre d’occurrences effectivement cochées. |
| Sauvegarde/duplication d’onglet | Sélection de profil non mémorisée | Sélection conservée dans la session et à la duplication ; anciennes sessions compatibles. |
| Source et détails | Risque de se baser sur un nom visuel simplifié | Le nodeid complet, classe et paramètres compris, reste l’identité de la source et des traces. |

## Différences nécessaires aux profils

- L’ordre défini dans le profil, les doublons, les groupes colorés, descriptions,
  paramètres hérités et personnalisés sont conservés.
- Chaque répétition et reprise garde ses propres résultats et durées ; les anciennes
  tentatives ne sont pas remplacées par le dernier verdict du même nodeid.
- Un lancement partiel ou ciblé utilise un nouvel onglet, avec une copie des
  occurrences et de leurs paramètres effectifs. Le profil, ses cases cochées et
  ses résultats d’origine restent disponibles.
- La source du profil reste consultable ; l’édition des fichiers se fait dans
  All tests. Les paramètres du profil continuent de se modifier dans son éditeur.
- Les markers de collecte restent propres à All tests : ils ne réécrivent pas
  silencieusement la séquence d’un profil.

## Vérifications

`runner/tests/test_profile_run_tree_parity.py` couvre la structure, les classes
multiples, les cas paramétrés, l’ordre et les doublons, les répétitions, les
lecteurs à indices non contigus, les durées, les cases, les reprises, les fiches
de groupe, le menu de l’en-tête, la sélection indépendante, la recherche d’erreurs
en direct, le menu contextuel, les raccourcis et la restauration de session.

Un lancement pytest réel de trois occurrences du même test vérifie que seules
les première et troisième, cochées, reçoivent respectivement les YAML 10 et 30.
La seconde, réglée à 20, ne tourne pas. Le profil d’origine reste intact.
Les captures de l’application avec ses modules de production vérifient aussi
ce scénario sur deux lecteurs simulés, en clair et en sombre.

### Résultat de validation

- 18 tests de parité passent, dont le lancement pytest réel, les raccourcis,
  le menu contextuel et le retour de sélection du lecteur depuis chaque panneau.
- La suite complète a produit 1 523 réussites et quatre échecs. Les deux
  régressions détectées (initialisation héritée du modèle et retour du lecteur)
  sont corrigées ; les trois modules concernés passent ensuite leurs 31 tests.
- Les deux autres échecs de sélection dans l’éditeur de groupes sont également
  présents dans le rapport de la version de départ. Les 12 tests de ce module
  repassent isolément. La suite complète n’a pas été relancée après les correctifs.
- Captures réelles Qt en mode offscreen et lecteurs simulés : pas de validation
  matérielle des lecteurs ni de validation Windows sur cette session.
- Contrôle de publication v1.5.3 : les 18 tests de parité et les 11 tests des
  détails en direct passent de nouveau. Le parcours de toutes les pages et
  des trois thèmes ne produit aucune erreur applicative, boîte d'erreur ou
  message Qt. Le parcours des profils sur deux lecteurs simulés vérifie
  également les détails de groupe et les YAML 10/30 de la sélection partielle.
