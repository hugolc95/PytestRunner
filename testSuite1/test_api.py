from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "campaign_state.txt"


def current_config() -> str:
    if not STATE_FILE.exists():
        return "none"
    return STATE_FILE.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("user", ["admin", "user"])
def test_login(user):
    config = current_config()
    assert config in {"A", "B"}
    assert user in {"admin", "user"}


def test_current_config_is_known():
    assert current_config() in {"A", "B"}
