# Pytest Runner 1.1.0 — Settings et Console

Ces pages font partie de l'interface PySide6 lancée par `python main_runner.py`.

## Navigation

Console se trouve après Python Environment dans le menu de gauche. Settings
reste en bas, séparé des pages de travail. Les raccourcis du bas sont, dans
l'ordre : thème, couleurs accessibles, réduction du menu. Quand le menu est
réduit, ils s'alignent verticalement et conservent leurs infobulles.

## Settings

- Interface : thème, taille du texte, marges du bandeau supérieur, ATR dans la
  barre du bas avec son champ sélectionnable et son action de rafraîchissement.
- Tree & details : espacement des lignes, onglet de détail par défaut, suivi du
  test en cours.
- Console : catégories enregistrées, horodatage, défilement automatique et
  limite de 250, 1 000 ou 5 000 événements en mémoire.
- Notifications : notification de fin d'exécution.

Les changements sont prévisualisés automatiquement. Le thème et la taille du
texte affichent « Updating appearance… » avant leur application ; les mouvements
rapides du curseur de taille sont regroupés pour éviter de recalculer toute
l'interface à chaque valeur. Les autres réglages ne mettent à jour que les
éléments concernés. **Apply settings** les
enregistre dans les préférences locales de l'utilisateur, sans modifier le
workspace. **Cancel changes** restaure les préférences enregistrées.

Dans la barre du bas, l'ATR utilise la police de l'interface et une hauteur
compacte, sans agrandir la barre. Le champ reste sélectionnable ; un ATR trop
long peut défiler horizontalement au lieu de réduire le texte.

## Console

La console affiche les commandes réelles des sous-processus avec leur répertoire
de travail, les actions de navigation et de sélection, la sortie pytest et les
rapports d'erreur ou tracebacks. Elle constitue un journal de diagnostic de la
session ; elle ne propose pas de saisie de commandes.

Les filtres et la recherche permettent de retrouver un événement. **Pause
display** fige l'affichage pendant que l'enregistrement continue. **Copy** et
**Export .log** utilisent le contenu affiché et filtré. **Clear** efface le
journal de la session. Le journal ne persiste pas après la fermeture de l'outil.

Les nouveaux événements sont ajoutés au document existant pour préserver la
sélection et limiter les recalculs. Quand la console est cachée, l'enregistrement
continue et l'affichage est actualisé à sa réouverture.

## Fenêtres détachables

**Detach window** ouvre le contenu de Settings ou Console dans une fenêtre
native déplaçable sur un autre écran. L'onglet reste accessible dans le menu.
La fenêtre principale revient à la dernière page utilisée qui est encore
attachée. Fermer une fenêtre détachée la masque ; cliquer sur Settings ou
Console dans le menu la rouvre sans la réattacher. **Reattach to tab** remet le
même contenu dans l'onglet en conservant les réglages, les traces et les filtres.
Le mode détaché ainsi que la taille et la position de ces fenêtres sont conservés
après fermeture et réouverture de l'application.
