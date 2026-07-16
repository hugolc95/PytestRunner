"""
Fixtures partagees pour le workspace de demonstration testSuite1.

Deux choses :

1. `apdu_log` : expose le module de log APDU du SmartcardFramework (`utils.log`)
   quand il est disponible sur le PYTHONPATH, sinon un logger minimal de repli.

2. Un fichier `.log` par test execute, ecrit dans un dossier horodate par run
   (l'historique des runs est conserve). Le dossier racine des logs vient de la cle
   `log_directory` de config.yml (defaut `<workspace>/logs`). Un manifeste JSON stable
   (`<log_root>/last_run_index.json`) mappe chaque nodeid vers le chemin de son .log du
   dernier run : c'est ce que le GUI lit pour le clic droit "Ouvrir le log de ce test".

Important : l'import du framework est fait *paresseusement*, jamais au niveau module.
Ainsi ce workspace reste collectable et executable meme sans le framework (ex: clone
sans SmartcardFramework), sans provoquer d'erreur de collecte pytest.
"""

import json
import logging
import re
import time
from pathlib import Path

import pytest


APDU_LOGGER_NAME = "APDU Logger"
FALLBACK_LOGGER_NAME = "APDU Logger (fallback)"


def _apdu_logger() -> logging.Logger:
    """Logger a alimenter par les tests : celui du framework s'il est importable,
    sinon un logger de repli. C'est le meme logger qui recoit les handlers par test,
    donc les appels apdu_log.* atterrissent bien dans le .log du test courant."""
    try:
        from utils import log as framework_log  # noqa: F401
        return framework_log.logger
    except Exception:
        return logging.getLogger(FALLBACK_LOGGER_NAME)


class _FallbackApduLog:
    """Repli minimal quand le SmartcardFramework n'est pas sur le PYTHONPATH.
    Expose les memes noms de fonctions que utils.log."""

    logger = logging.getLogger(FALLBACK_LOGGER_NAME)

    def logSendAPDU(self, command, response):
        self.logger.info("APDU %s -> %s (SmartcardFramework indisponible, log minimal)", command, response)

    def logPowerON(self, atr):
        self.logger.info("Power ON ATR=%s (SmartcardFramework indisponible, log minimal)", atr)

    def logPowerOFF(self):
        self.logger.info("Power OFF (SmartcardFramework indisponible, log minimal)")

    def logReaderInfo(self, reader_name):
        self.logger.info("Reader=%s (SmartcardFramework indisponible, log minimal)", reader_name)


@pytest.fixture
def apdu_log():
    """Module de log du SmartcardFramework (utils.log) si importable, sinon repli."""
    try:
        from utils import log as framework_log
        return framework_log
    except Exception:
        return _FallbackApduLog()


def _sanitize_nodeid(nodeid: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", nodeid).strip("_")


def _resolve_log_root(workspace: Path) -> Path:
    """Dossier racine des logs, lu depuis config.yml (cle `log_directory`), sinon
    `<workspace>/logs`. Logique volontairement identique a
    gui_qt.config.config_loader.resolve_log_root (le GUI et le conftest DOIVENT
    regarder au meme endroit). On la duplique ici pour garder le conftest autonome,
    sans dependance a gui_qt (testSuite1 peut tourner hors du projet)."""
    log_dir = "logs"
    for name in ("config.yaml", "config.yml"):
        cfg = workspace / name
        if cfg.exists():
            try:
                import yaml
                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                if data.get("log_directory"):
                    log_dir = str(data["log_directory"])
            except Exception:
                pass
            break
    root = Path(log_dir)
    return root if root.is_absolute() else workspace / root


@pytest.fixture(scope="session")
def _log_session(request):
    """Prepare une fois par run : dossier de session horodate + manifeste.

    Ancre sur le repertoire d'invocation de pytest (= cwd = le workspace lance par
    le GUI), pas sur rootdir (qui peut differer a cause des multiples pytest.ini)."""
    workspace = Path(request.config.invocation_params.dir)
    log_root = _resolve_log_root(workspace)
    session_dir = log_root / time.strftime("%Y%m%d_%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = log_root / "last_run_index.json"
    manifest: dict[str, str] = {}
    # Repart d'un manifeste vide pour ce run (ne reference que les tests de ce run).
    try:
        manifest_path.write_text("{}", encoding="utf-8")
    except OSError:
        pass

    return session_dir, manifest_path, manifest


@pytest.fixture(autouse=True)
def _per_test_log(request, _log_session):
    """Cree un .log par test, l'attache au logger APDU, et met a jour le manifeste."""
    session_dir, manifest_path, manifest = _log_session
    nodeid = request.node.nodeid

    log_path = session_dir / f"{_sanitize_nodeid(nodeid)}.log"
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    logger = _apdu_logger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("=== %s @ %s ===", nodeid, time.strftime("%Y-%m-%d %H:%M:%S"))

    manifest[nodeid] = str(log_path)
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError:
        pass

    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
