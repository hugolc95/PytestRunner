from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "campaign_state.txt"

STATE_FILE.write_text("A", encoding="utf-8")
print("Configuration A applied")
print(f"State file: {STATE_FILE}")
