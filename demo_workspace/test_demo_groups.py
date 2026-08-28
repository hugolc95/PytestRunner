import time

import pytest


class TestAuthentication:
    def test_login_ok(self):
        time.sleep(0.15)
        assert True

    @pytest.mark.parametrize("role", ["admin", "user", "guest"])
    def test_roles(self, role):
        assert role in {"admin", "user", "guest"}


class TestCryptoSimulation:
    @pytest.mark.parametrize("algorithm", ["AES", "RSA", "ML-KEM", "ML-DSA"])
    def test_algorithm_available(self, algorithm):
        time.sleep(0.12)
        assert algorithm

    @pytest.mark.xfail(reason="Intentional flaky/failing-looking demo case")
    def test_known_issue(self):
        assert False
