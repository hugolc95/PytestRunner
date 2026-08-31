"""L'anneau proportionnel qui remplace la somme de quatre badges par une
seule forme : la largeur de chaque arc dit la part de ce statut, le taux de
reussite tient dans une bulle-info -- pas besoin de compter les badges.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

from runner.domain.models import Status
from runner.ui import tokens as t


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_it_is_forty_five_pixels_by_default(qapp):
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()

    assert anneau.width() == 45
    assert anneau.height() == 45


def test_the_tooltip_gives_the_pass_rate_and_the_breakdown(qapp):
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()
    anneau.set_counts({
        Status.PASSED: 7, Status.FAILED: 1, Status.SKIPPED: 2, Status.ERROR: 0,
    })

    assert "70%" in anneau.toolTip()
    assert "7 passed" in anneau.toolTip()
    assert "1 failed" in anneau.toolTip()
    assert "2 skipped" in anneau.toolTip()
    assert "0 error" in anneau.toolTip()


def test_missing_statuses_default_to_zero(qapp):
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()
    anneau.set_counts({Status.PASSED: 4})

    assert "4 passed" in anneau.toolTip()
    assert "0 failed" in anneau.toolTip()


def test_an_empty_run_paints_the_ring_grey_and_does_not_crash(qapp):
    """Avant le premier run, aucun statut n'a de valeur -- l'anneau doit
    quand meme se dessiner (gris, complet) plutot que lever ou rester vide."""
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()
    anneau.set_counts({})

    assert "0%" in anneau.toolTip()

    anneau.show()
    qapp.processEvents()
    image = anneau.grab().toImage()
    attendu = QColor(t.BORDER)
    proches = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 128
        and max(abs(image.pixelColor(x, y).red() - attendu.red()),
                abs(image.pixelColor(x, y).green() - attendu.green()),
                abs(image.pixelColor(x, y).blue() - attendu.blue())) <= 24)
    assert proches >= 3
    anneau.close()


def test_a_fully_passed_run_paints_the_whole_ring_in_the_passed_color(qapp):
    """Le pixel qui manquait : verifier que l'arc est bien peint dans la
    couleur du statut, pas seulement que le compte est stocke."""
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()
    anneau.set_counts({Status.PASSED: 5})
    anneau.show()
    qapp.processEvents()

    image = anneau.grab().toImage()
    attendu = QColor(t.status_color(Status.PASSED))
    proches = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 128
        and max(abs(image.pixelColor(x, y).red() - attendu.red()),
                abs(image.pixelColor(x, y).green() - attendu.green()),
                abs(image.pixelColor(x, y).blue() - attendu.blue())) <= 24)
    assert proches >= 20
    anneau.close()


def test_switching_status_color_changes_what_gets_painted(qapp):
    """Sabotage naturel : deux runs de couleurs differentes ne doivent pas
    peindre le meme pixel -- sinon set_counts ne repeindrait pas vraiment."""
    from runner.ui.widgets import CompassRing

    anneau = CompassRing()
    anneau.set_counts({Status.PASSED: 5})
    anneau.show()
    qapp.processEvents()
    avant = anneau.grab().toImage().pixelColor(22, 4)

    anneau.set_counts({Status.FAILED: 5})
    qapp.processEvents()
    apres = anneau.grab().toImage().pixelColor(22, 4)

    assert avant != apres
    anneau.close()
