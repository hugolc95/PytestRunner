"""Non-regressions des defauts trouves lors de la passe de stabilite 1.8.0.

Ctrl+Z ambigu dans l'editeur de profils : couvert par
`test_profile_sequence_view` et `test_profile_editor_polish`, qui echouaient
avant la correction.
"""
import pytest
from runner.domain.execution import _couvert


@pytest.mark.parametrize("nodeid, verdicts, attendu", [
    ("t.py::test_a", {"t.py::test_a": 1}, True),
    # Fonction devenue parametree depuis la collecte : ses cas la couvrent.
    ("t.py::test_a", {"t.py::test_a[1]": 1, "t.py::test_a[2]": 1}, True),
    ("t.py", {"t.py::test_a": 1}, True),
    ("suite/", {"suite/t.py::test_a": 1}, True),
    ("suite", {"suite/t.py::test_a": 1}, True),
    ("t.py::TestA", {"t.py::TestA::test_x": 1}, True),
    # Un simple prefixe de nom n'est pas un parent.
    ("t.py::test_a", {"t.py::test_ab": 1}, False),
    ("t.py::test_a", {}, False),
])
def test_requested_parent_nodeids_are_covered_by_their_children(nodeid, verdicts, attendu):
    assert _couvert(nodeid, verdicts) is attendu

