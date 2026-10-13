# Pytest Runner 1.1.3 — diagnostic des erreurs de collection

Lorsqu'une collecte échoue, le message d'erreur affiche le nombre d'erreurs,
le fichier et la ligne concernés ainsi que la cause de la première erreur.
Le panneau défilant contient les traces de toutes les erreurs remontées par
pytest, avec le code source et la chaîne d'appels disponibles.

**Copy errors** copie le diagnostic complet. **Show console** ouvre la page
Console sur **Errors / tracebacks**, efface une recherche précédente et reprend
l'affichage s'il était en pause. Si Console est détachée, sa fenêtre est ramenée
au premier plan.

Le diagnostic conserve également le workspace, l'interpréteur Python, le YAML
effectivement utilisé, la commande et le code de sortie. La sortie standard
et la sortie d'erreur de la collecte sont enregistrées dans la catégorie
**Process output**. Les erreurs d'un autre onglet Run portent le nom de cet
onglet dans la console commune.

Les erreurs précoces de chargement d'un conftest, les erreurs de syntaxe et les
erreurs d'import gardent leur trace. En cas de timeout, les sorties déjà
produites sont conservées avec le délai appliqué. Les catégories enregistrées
restent configurables dans Settings.

Validation : 151 tests ciblés passent, avec de vrais sous-processus pytest pour
les erreurs d'import, de syntaxe, de conftest et les collectes multiples. Les
tests Qt vérifient la remontée jusqu'au message d'erreur et à la console,
l'ouverture directe des erreurs, les onglets Run et les timeouts.
