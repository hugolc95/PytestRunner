from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "campaign_state.txt"


def current_config() -> str:
    if not STATE_FILE.exists():
        return "none"
    return STATE_FILE.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("user", ["admin", "user"])
def test_login(user, apdu_log):
    # Exemple d'utilisation du logging APDU du SmartcardFramework (utils.log).
    apdu_log.logPowerON("3B9F9681B1FE451F070064051E0E6400820218")
    # SELECT applet (INS A4) puis VERIFY PIN (INS 20) fictifs pour la demo.
    apdu_log.logSendAPDU("00A4040007A0000002471001", "9000")
    apdu_log.logSendAPDU(f"0020000008{user.encode().hex().upper()}", "9000")

    config = current_config()
    assert config in {"A", "B"}
    assert user in {"admin", "user"}

    apdu_log.logPowerOFF()


def test_current_config_is_known(apdu_log):
    apdu_log.logReaderInfo("Demo virtual reader")
    assert current_config() in {"A", "B"}
