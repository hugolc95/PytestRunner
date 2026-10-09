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

Les changements sont prévisualisés immédiatement. **Apply settings** les
enregistre dans les préférences locales de l'utilisateur, sans modifier le
workspace. **Cancel changes** restaure les préférences enregistrées.

## Console

La console affiche les commandes réelles des sous-processus avec leur répertoire
de travail, les actions de navigation et de sélection, la sortie pytest et les
rapports d'erreur ou tracebacks. Elle constitue un journal de diagnostic de la
session ; elle ne propose pas de saisie de commandes.

Les filtres et la recherche permettent de retrouver un événement. **Pause
display** fige l'affichage pendant que l'enregistrement continue. **Copy** et
**Export .log** utilisent le contenu affiché et filtré. **Clear** efface le
journal de la session. Le journal ne persiste pas après la fermeture de l'outil.

## Fenêtres détachables

**Detach window** ouvre le contenu de Settings ou Console dans une fenêtre
native déplaçable sur un autre écran. L'onglet reste accessible dans le menu.
**Reattach to tab**, ou la fermeture de la fenêtre détachée, remet le même
contenu dans l'onglet en conservant les réglages, les traces et les filtres.
