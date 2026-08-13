"""Liste des lecteurs disponibles, proposee dans la fenetre de configuration.

============================================================================
  C'EST ICI QUE VOUS BRANCHEZ VOTRE FONCTION DE DETECTION DES LECTEURS.
============================================================================

Remplacez le corps de `list_connected_readers()` par l'appel de votre
framework. Par exemple, avec pyscard :

    from smartcard.System import readers

    def list_connected_readers() -> list[str]:
        return [str(r) for r in readers()]

...ou avec votre propre couche :

    from SmartcardFramework.Reader import getAvailableReaders

    def list_connected_readers() -> list[str]:
        return list(getAvailableReaders())

Deux regles a respecter :

1. Retourner une liste de chaines, exactement telles que vos tests les
   attendent dans la cle `Reader`. Ce sont ces chaines qui seront ecrites
   dans la configuration.

2. Ne jamais laisser une exception sortir. La detection touche du materiel :
   service PC/SC arrete, lecteur debranche, DLL absente. `available_readers()`
   ci-dessous s'en charge deja, mais le plus tot est le mieux -- une fenetre de
   configuration qui refuse de s'ouvrir parce qu'aucun lecteur n'est branche
   serait un mauvais echange.

Tant que cette fonction retourne une liste vide, le champ Reader reste une
simple zone de saisie libre : rien ne casse, il n'y a juste rien a proposer.
"""

from __future__ import annotations


def list_connected_readers() -> list[str]:
    """Lecteurs actuellement branches sur la machine.

    Retourne une liste vide tant que la detection n'est pas branchee.
    """
    return []


def available_readers(deja_connus: list[str] | None = None) -> list[str]:
    """Lecteurs a proposer dans la liste deroulante.

    Reunit ceux que la machine detecte et ceux que la configuration connait
    deja : un lecteur momentanement debranche doit rester choisissable, sans
    quoi rouvrir la configuration ferait disparaitre le reglage en cours.
    """
    propositions: list[str] = []

    try:
        detectes = list_connected_readers() or []
    except Exception:
        # La detection touche du materiel : service arrete, DLL absente,
        # lecteur retire en cours de route. Aucune de ces situations ne doit
        # empecher d'ouvrir la configuration.
        detectes = []

    for nom in list(detectes) + list(deja_connus or []):
        nom = str(nom).strip()
        if nom and nom not in propositions:
            propositions.append(nom)

    return propositions
