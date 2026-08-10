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


# Cles acceptees pour designer le dossier des logs. La comparaison se fait sans
# tenir compte de la casse ni des separateurs : les projets ecrivent aussi bien
# `LOG_PATH` que `log_directory` ou `log-dir`.
LOG_PATH_KEYS = (
    "log_path",
    "log_directory",
    "log_dir",
    "logs_path",
    "logs_directory",
    "logdir",
    "logpath",
)


def normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def find_log_path_setting(data: dict) -> str | None:
    """Valeur du reglage designant le dossier des logs, quel que soit son nom.

    Le niveau courant est examine en entier avant de descendre : un LOG_PATH a
    la racine du fichier prime sur celui que declarerait un mode particulier.
    Retourne None si aucune cle reconnue n'est presente ou si sa valeur est vide.
    """
    if not isinstance(data, dict):
        return None

    for key, value in data.items():
        if normalize_key(key) in LOG_PATH_KEYS and value:
            texte = str(value).strip()
            if texte:
                return texte

    # Les configurations reelles rangent souvent leurs reglages par section.
    for value in data.values():
        if isinstance(value, dict):
            trouve = find_log_path_setting(value)
            if trouve:
                return trouve
    return None


def find_config_declaring_log_path(workspace: str, preferred: str | None = None) -> Path | None:
    """Premier fichier de configuration du workspace qui declare un dossier de logs.

    Se limiter a config.yml faisait manquer les projets dont le fichier porte un
    autre nom (`configWorkspace.yml`) : le reglage LOG_PATH passait inapercu et
    les logs etaient cherches dans `<workspace>/logs`, qui n'existe pas. On
    examine donc les memes candidats que le bouton "Ouvrir la configuration",
    en commencant par celui que l'utilisateur a designe.
    """
    candidats: list[Path] = []

    if preferred:
        chemin = Path(preferred)
        if chemin.is_file():
            candidats.append(chemin)

    candidats.extend(discover_config_candidates(workspace))

    for chemin in candidats:
        try:
            if find_log_path_setting(load_yaml(chemin)):
                return chemin
        except Exception:
            continue
    return None


def resolve_log_root(workspace: str, config_path: str | None = None) -> Path:
    """Dossier racine des logs pour ce workspace.

    Lit le reglage du dossier de logs dans la configuration du workspace
    (`LOG_PATH`, `log_directory` et variantes, voir LOG_PATH_KEYS), sinon
    `<workspace>/logs`. Utilise a la fois par le conftest (qui ecrit les logs) et
    par le GUI (onglet Log, action "Ouvrir le log") pour regarder au meme endroit.
    """
    root = Path(workspace)
    log_dir = "logs"

    declarant = find_config_declaring_log_path(workspace, config_path)
    if declarant is not None:
        try:
            value = find_log_path_setting(load_yaml(declarant))
            if value:
                log_dir = value
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


def find_test_log_from_manifest(workspace: str, nodeid: str,
                                config_path: str | None = None) -> Path | None:
    """Retrouve le .log via le manifeste `<log_root>/last_run_index.json`.

    Ce manifeste est ecrit par le conftest livre en exemple. Un workspace reel a
    son propre conftest, qui ecrit ses .log sans forcement tenir ce manifeste :
    voir find_test_log_by_search() pour ce cas.

    Le matching est souple (normalisation des slashs + endswith dans les deux
    sens), car le nodeid de l'arbre peut avoir un prefixe de dossier que la cle du
    manifeste n'a pas, selon le rootdir de pytest.
    """
    manifest_path = resolve_log_root(workspace, config_path) / "last_run_index.json"
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


# Plafond de fichiers examines DANS UN dossier de run. Un plafond global
# laissait des mois d'historique consommer le budget avant meme d'atteindre le
# run du jour, et le log cherche n'etait jamais vu.
MAX_LOG_FILES_SCANNED = 4000

# Nombre de dossiers de run explores, du plus recent au plus ancien.
MAX_RUN_DIRS_SCANNED = 12

LOG_SUFFIXES = (".log", ".txt")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def run_directories(log_root: Path) -> list[Path]:
    """Dossiers de run sous la racine des logs, du plus recent au plus ancien.

    Les conftest horodatent le dossier de chaque run (`2026-08-07_18-11-23`) et y
    recreent l'arborescence des tests. Le log cherche est presque toujours dans
    le plus recent : commencer par la evite de parcourir tout l'historique, et
    surtout evite de repondre avec le log d'un run precedent.
    """
    try:
        dossiers = [p for p in log_root.iterdir() if p.is_dir()]
    except OSError:
        return []

    dossiers.sort(key=_mtime, reverse=True)
    return dossiers[:MAX_RUN_DIRS_SCANNED]


def _match_key(value: str) -> str:
    """Reduit une chaine a ses caracteres alphanumeriques, en minuscules.

    Les conftest assainissent les nodeids chacun a leur facon : `cas-1`, `cas_1`
    et `cas.1` doivent tous se reconnaitre dans un nom de fichier.
    """
    return "".join(c for c in str(value).lower() if c.isalnum())


def nodeid_tokens(nodeid: str) -> list[str]:
    """Morceaux identifiants d'un nodeid, du fichier au parametre.

    'a/b/test_x.py::TestC::test_f[cas-1]' donne
    ['test_x', 'TestC', 'test_f', 'cas-1'].
    """
    nodeid = str(nodeid).replace("\\", "/").strip()
    chemin, _, reste = nodeid.partition("::")

    tokens = [Path(chemin).stem] if chemin else []
    for morceau in reste.split("::"):
        if not morceau:
            continue
        base, _, parametre = morceau.partition("[")
        if base:
            tokens.append(base)
        if parametre:
            tokens.append(parametre.rstrip("]"))
    return tokens


def _required_tokens(nodeid: str, tokens: list[str]) -> list[str]:
    """Morceaux qui doivent obligatoirement apparaitre pour retenir un fichier.

    Le nom de la fonction ne suffit pas : normalise, `test_pso` se retrouve dans
    `test_PSO_CDS_RSA`, donc tout log du meme fichier passerait. On exige donc
    aussi l'identifiant du parametre, bien plus discriminant.
    """
    if str(nodeid).strip().endswith("]") and len(tokens) >= 2:
        obligatoires = [_match_key(tokens[-2]), _match_key(tokens[-1])]
    else:
        obligatoires = [_match_key(tokens[-1])] if tokens else []
    return [t for t in obligatoires if t]


def _best_log_under(zone: Path, obligatoires: list[str], recherches: list[str]) -> Path | None:
    """Meilleur fichier de log sous ce dossier, ou None.

    Le rapprochement porte sur le chemin RELATIF au dossier de run, pas sur le
    seul nom de fichier : le conftest y recree l'arborescence des tests, donc
    une partie de l'identite du test est portee par les dossiers
    (`.../TestSuiteCDS/test_PSO_CDS_RSA/[cas].log`). Ne regarder que le nom
    faisait manquer tous ces logs.

    Un morceau reconnu dans le nom du fichier compte double : a dossier egal,
    `[cas-25].log` est un meilleur candidat que le `setup.log` voisin.
    """
    meilleur: tuple[int, float, Path] | None = None
    examines = 0

    for fichier in zone.rglob("*"):
        if examines >= MAX_LOG_FILES_SCANNED:
            break
        if fichier.suffix.lower() not in LOG_SUFFIXES or not fichier.is_file():
            continue
        examines += 1

        try:
            relatif = fichier.relative_to(zone)
        except ValueError:
            relatif = fichier
        chemin = _match_key(str(relatif))
        if any(t not in chemin for t in obligatoires):
            continue

        nom = _match_key(fichier.stem)
        score = sum(1 for t in recherches if t in chemin)
        score += sum(1 for t in recherches if t in nom)

        candidat = (score, _mtime(fichier), fichier)
        if meilleur is None or candidat[:2] > meilleur[:2]:
            meilleur = candidat

    return meilleur[2] if meilleur else None


def find_test_log_by_search(workspace: str, nodeid: str,
                            config_path: str | None = None) -> Path | None:
    """Cherche le .log d'un test dans le dossier des logs.

    Utilise quand aucun manifeste n'est tenu, ce qui est le cas des workspaces
    dont le conftest se contente d'ecrire des fichiers. On examine les dossiers
    de run du plus recent au plus ancien et on s'arrete au premier qui contient
    le test : c'est le resultat qui vient d'etre produit. La racine elle-meme est
    examinee en dernier, pour les conftest qui n'horodatent pas.
    """
    racine = resolve_log_root(workspace, config_path)
    if not racine.is_dir():
        return None

    tokens = nodeid_tokens(nodeid)
    if not tokens:
        return None

    obligatoires = _required_tokens(nodeid, tokens)
    if not obligatoires:
        return None
    recherches = [_match_key(t) for t in tokens if _match_key(t)]

    for zone in run_directories(racine) + [racine]:
        trouve = _best_log_under(zone, obligatoires, recherches)
        if trouve is not None:
            return trouve

    return None


def find_test_log(workspace: str, nodeid: str, config_path: str | None = None) -> Path | None:
    """Fichier .log du dernier run pour ce test, ou None.

    Le manifeste est prioritaire quand il existe : il est exact et immediat. A
    defaut, on cherche dans le dossier des logs, ce qui fonctionne avec
    n'importe quel conftest.
    """
    return (
        find_test_log_from_manifest(workspace, nodeid, config_path)
        or find_test_log_by_search(workspace, nodeid, config_path)
    )
