from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "campaign_state.txt"


def current_config() -> str:
    if not STATE_FILE.exists():
        return "none"
    return STATE_FILE.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("case, expected", [("case_1", 2), ("case_2", 4)])
def test_compute(case, expected, apdu_log):
    apdu_log.logSendAPDU("00B0000000", "9000")  # READ BINARY fictif pour la demo
    assert current_config() in {"A", "B"}
    assert expected == int(case.split("_")[-1]) * 2
