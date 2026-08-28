import time

import pytest


def test_fast_pass():
    assert 2 + 2 == 4


def test_slow_pass():
    time.sleep(0.4)
    assert True


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5], ids=lambda value: f"case_{value}")
def test_parametrized(value):
    time.sleep(0.1)
    assert value > 0


def test_skipped_example():
    pytest.skip("Demo skipped test")


def test_failure_example():
    assert "runner" == "pytest", "Intentional demo failure"
