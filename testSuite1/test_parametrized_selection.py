import pytest


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param(1, 2, 3, id="small"),
        pytest.param(10, 5, 15, id="medium"),
        pytest.param(100, 23, 123, id="large"),
    ],
)
def test_addition_parametree(left, right, expected):
    """Chaque jeu de donnees apparait comme une feuille selectionnable dans l'interface."""
    assert left + right == expected
