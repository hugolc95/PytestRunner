"""Reglages communs aux tests de l'interface.

Ces tests fabriquent beaucoup de widgets sans parent -- une barre de
recherche, une console, une fenetre entiere. Sans parent, c'est Python qui les
possede : ils survivent au test, et disparaissent quand le ramasse-miettes
cyclique passe, a un moment que personne ne choisit.

Ce moment tombait parfois PENDANT que Qt parcourait sa liste de widgets, ce
que fait `QApplication.setStyleSheet()` -- donc chaque changement de theme. Le
widget detruit en cours de route laissait Qt sur une adresse liberee, et la
suite se terminait par un segment de memoire. Sur un test innocent, plusieurs
fichiers plus loin, et une fois sur deux : le genre de panne qu'on met une
journee a rattacher a sa cause.

Verifie en coupant le ramasse-miettes cyclique sur la suite complete : plus un
seul plantage. La destruction est donc rendue DETERMINISTE ici -- a la fin du
test qui les a crees, pas quand le ramasse-miettes le decide.

L'application, elle, n'a jamais ete concernee : elle n'ouvre qu'une fenetre,
dont tout le reste est enfant.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def sans_widget_orphelin():
    """Detruit les widgets sans parent qu'un test laisse derriere lui."""
    from PyQt5.QtWidgets import QApplication

    application = QApplication.instance()
    # Les widgets deja la sont gardes par reference le temps du test : ils ne
    # doivent surtout pas etre ramasses non plus.
    avant = set(application.topLevelWidgets()) if application is not None else set()

    yield

    application = QApplication.instance()
    if application is None:
        return

    for widget in application.topLevelWidgets():
        if widget in avant:
            continue
        widget.close()
        widget.deleteLater()

    # Les suppressions differees ne partent qu'au prochain tour de boucle :
    # sans cela on quitte le test avec exactement le meme sursis qu'avant.
    application.processEvents()
