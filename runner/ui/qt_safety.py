"""Gardes pour le code Python appele par Qt pendant une destruction.

Quand une fenetre est detruite, QWidget detruit ses enfants un par un, et
chacun envoie encore des evenements (LayoutRequest, Hide, ChildRemoved...) a
ses parents et a leurs filtres. Un `eventFilter` ou un `event` ecrits en
Python touchent alors un minuteur ou un widget deja detruit : PySide leve
"Internal C++ object already deleted". A la fermeture de l'application, cela
donnait des traces d'erreur parasites, et dans les tests des echecs au hasard.

Seule cette erreur precise est ignoree : toute autre exception remonte.
"""
from __future__ import annotations

import functools

_DELETED = "already deleted"


def is_deleted_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and _DELETED in str(exc)


def tolerate_destruction(default=False):
    """Decore un gestionnaire Qt : rend `default` si un objet est detruit."""

    def decorateur(methode):
        @functools.wraps(methode)
        def enveloppe(*args, **kwargs):
            try:
                return methode(*args, **kwargs)
            except RuntimeError as exc:
                if is_deleted_error(exc):
                    return default
                raise

        return enveloppe

    return decorateur
