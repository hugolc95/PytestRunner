# Rapport HTML d'analyse IN Groupe

## Correctifs v1.6.1

Le tableau YAML montre les valeurs effectives, y compris false, zero et les
collections vides. Les origines et les configurations completes restent
disponibles dans des sections depliables. Les durees absentes des snapshots
sont recuperees depuis les timings pytest archives uniquement si le lien
occurrence/lecteur/tentative est non ambigu. Un resultat Not run ne reprend
pas le temps d'une autre execution. Les temps manquants restent explicites.

Les selections et changements d'onglet ne reconstruisent plus l'arbre.
La console et les longues listes de membres sont chargees a la demande.
Un controle Chromium local sur 1 500 occurrences synthetiques mesure des
gestionnaires de clic de 0,4 a 3,2 ms apres correction, contre 193 a 484 ms
avant ; ces mesures ne prejugent pas des performances sur chaque poste.

Apres export, une confirmation propose d'ouvrir le HTML dans le navigateur
par defaut. L'export reste sauvegarde si l'ouverture systeme echoue.

Verification de ces correctifs : 32 tests cibles passes, parcours d'export
avec les quatre modules d'installation dans l'application, puis controles
Chromium hors ligne en clair/sombre aux largeurs 320, 390, 736 et 1440 px.
La suite complete n'a pas ete relancee, a la demande de l'utilisateur.

## Fonctionnement du rapport

Depuis History, le menu Export propose **Export complete HTML report…** pour
les lecteurs du lancement selectionne. Les exports individuels restent dans
les sous-menus lecteurs. Le rapport se genere dans un thread : l'interface
reste utilisable et une fermeture attend la fin de l'ecriture.

Le fichier est autonome : CSS, JavaScript, logo officiel et pictogrammes de
l'interface sont embarques. Les groupes et sous-groupes viennent du profil
capture au lancement ; la construction conserve l'ordre, les doublons, les
cas parametres, les repetitions, les descriptions et les couleurs, comme
l'arbre Run. Un bilan de groupe porte sur tous ses descendants.

Chaque resultat appartient a une occurrence, un lecteur et une tentative.
Le rapport donne les traces enregistrees, les logs disponibles, la duree et
le YAML effectif, avec l'origine des parametres. Il distingue Not run et
Unknown : l'absence d'un verdict n'est jamais assimilee a une reussite.
Les compteurs des anciens historiques restent identifies comme des totaux
archives lorsqu'ils ne permettent pas de reconstruire les details.

Les nouveaux runs ont un fichier .analysis.json annexe, reference dans
l'index de l'historique. Le thread d'archivage ecrit d'abord les metadonnees
legeres, puis les donnees d'analyse et les sorties. Les donnees portent sur
le lancement reel, y compris une selection partielle du profil. Les chemins
des logs sont lus dans ce thread ; leur texte reste ensuite disponible dans
le rapport meme si le dossier source a disparu. Un fichier partage entre
occurrences est signale. Save complete logs reste respecte.

Les donnees manquantes d'un ancien run sont marquees explicitement. Le
rapport n'invente ni versions d'environnement, ni ATR pour les lecteurs non
observes, ni resultat d'une ancienne repetition, ni trace a partir d'un nom
ambigu. Les commandes sont les vrais argv transmis au processus pytest.
La configuration provient de la capture du lancement, pas du workspace
actuel. Les YAML repetes sont dedupliques dans le document.

Le texte externe est echappe dans la vue statique et dans les donnees JSON
embarquees ; les valeurs ne deviennent jamais du HTML executable. Une vue
statique reste consultable sans JavaScript et sert a l'impression.

Verification : tests du domaine et de History, parcours avec les quatre
modules d'installation, run reel pytest sur deux lecteurs simules avec
repetitions/relances, puis export depuis History. Le document est teste dans
Chromium hors ligne, avec le workspace d'origine indisponible, en clair et
sombre aux largeurs 320, 390, 736 et 1440 px. Aucun acces reseau n'est requis.
Les controles Windows/materiel restent a realiser sur le poste utilisateur.

Resultats de verification de cette branche : 17 tests cibles du rapport et
62 tests History passent. Le parcours reel d'export et la verification
navigateur hors ligne sont valides. Le controle de demarrage de l'application
produit 18 captures sans erreur applicative ni message Qt.

La suite complete initiale a produit 1 619 reussites et 11 echecs : un ordre
de menu a ete corrige, deux tests de collecte ont observe leur modele avant
le traitement du signal Qt, un archivage a depasse le delai du test et sept
workers Qt ont plante nativement en parallele. Les modules History profile,
large suite, profile logs, markers et theme repassent en serie. La comparaison
avec main en serie passe sur les quatre premiers modules. Les verifications
generales suivantes ont ete arretees a la demande de l'utilisateur ; la
suite complete n'est donc pas declaree verte.
