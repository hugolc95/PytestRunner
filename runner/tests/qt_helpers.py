"""Outils communs des tests de l'interface."""
from __future__ import annotations


def widgets_du_layout(layout) -> list:
    """Les widgets d'un layout, dans l'ordre, sans `layout.itemAt()`.

    `itemAt()` cree une enveloppe Python par QWidgetItem, que PySide garde
    apres que Qt l'a detruit (widget retire ou reparente). Un objet alloue
    ensuite a la meme adresse etait pris pour ce QWidgetItem : erreurs
    "'QWidgetItem' object has no attribute ..." au hasard des tests suivants.
    `indexOf(widget)` ne cree aucune enveloppe d'element.
    """
    hote = layout.parentWidget()
    if hote is None:
        return []
    from PySide6.QtWidgets import QWidget

    candidats = [w for w in hote.findChildren(QWidget) if layout.indexOf(w) >= 0]
    return sorted(candidats, key=layout.indexOf)
