from pathlib import Path
import yaml


def find_config_yaml(workspace: str) -> Path | None:
    root = Path(workspace)

    for name in ("config.yaml", "config.yml"):
        path = root / name
        if path.exists():
            return path

    return None


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
