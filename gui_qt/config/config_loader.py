from pathlib import Path
import json
import yaml


# Noms reconnus automatiquement. Ce sont aussi ceux que lit le conftest du
# workspace : resolve_log_root() doit rester aligne dessus, sinon le GUI et les
# tests chercheraient les logs a deux endroits differents.
STANDARD_CONFIG_NAMES = ("config.yaml", "config.yml")


def find_config_yaml(workspace: str) -> Path | None:
    root = Path(workspace)

    for name in STANDARD_CONFIG_NAMES:
        path = root / name
        if path.exists():
            return path

    return None


def discover_config_candidates(workspace: str) -> list[Path]:
    """Fichiers YAML de la racine du workspace pouvant servir de configuration.

    Les noms standards viennent en tete, le reste par ordre alphabetique. Sert au
    bouton "Open Config" pour les projets dont le fichier de configuration ne
    s'appelle pas exactement config.yml.
    """
    root = Path(workspace)
    if not root.is_dir():
        return []

    candidates: list[Path] = []

    for name in STANDARD_CONFIG_NAMES:
        path = root / name
        if path.is_file():
            candidates.append(path)

    others = [
        path
        for path in root.iterdir()
        if path.is_file()
        and path.suffix.lower() in (".yml", ".yaml")
        and path.name not in STANDARD_CONFIG_NAMES
    ]

    candidates.extend(sorted(others, key=lambda p: p.name.lower()))
    return candidates


def resolve_log_root(workspace: str) -> Path:
    """Dossier racine des logs pour ce workspace.

    Lit la cle `log_directory` de config.yml si presente (relative au workspace),
    sinon `<workspace>/logs`. Utilise a la fois par le conftest (qui ecrit les logs)
    et par le GUI (clic droit "Ouvrir le log") pour regarder au meme endroit.
    """
    root = Path(workspace)
    log_dir = "logs"

    config_path = find_config_yaml(workspace)
    if config_path is not None:
        try:
            data = load_yaml(config_path)
            value = data.get("log_directory")
            if value:
                log_dir = str(value)
        except Exception:
            pass

    log_root = Path(log_dir)
    if not log_root.is_absolute():
        log_root = root / log_root
    return log_root


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def find_test_log(workspace: str, nodeid: str) -> Path | None:
    """Retrouve le fichier .log du dernier run pour un nodeid, via le manifeste
    `<log_root>/last_run_index.json` ecrit par le conftest. Retourne None si aucun
    log (test jamais lance, ou manifeste absent).

    Le matching est souple (normalisation des slashs + endswith dans les deux sens),
    car le nodeid stocke dans l'arbre du GUI peut avoir un prefixe de dossier que la
    cle du manifeste n'a pas (selon le rootdir pytest), comme dans _find_item_for_nodeid.
    """
    manifest_path = resolve_log_root(workspace) / "last_run_index.json"
    if not manifest_path.is_file():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    def norm(value: str) -> str:
        return str(value).replace("\\", "/").strip()

    target = norm(nodeid)

    path = manifest.get(nodeid) or manifest.get(target)
    if not path:
        for key, value in manifest.items():
            nkey = norm(key)
            if nkey == target or nkey.endswith(target) or target.endswith(nkey):
                path = value
                break

    if path and Path(path).is_file():
        return Path(path)
    return None
