import yaml


def load_config(path: str) -> dict:
    """Load YAML configuration file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(path: str, data: dict) -> None:
    """Save YAML configuration file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
