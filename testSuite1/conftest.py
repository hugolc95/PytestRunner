"""
Fixtures partagees pour le workspace de demonstration testSuite1.

Deux choses :

1. `apdu_log` : expose le module de log APDU du SmartcardFramework (`utils.log`)
   quand il est disponible sur le PYTHONPATH, sinon un logger minimal de repli.

2. Un fichier `.log` par test execute, range par date, numero de build, lecteur
   et chemin relatif dans le workspace. Le dossier racine des logs vient de la cle
   `log_directory` de config.yml (defaut `<workspace>/logs`). Un manifeste JSON stable
   (`<log_root>/last_run_index.json`) mappe chaque nodeid vers le chemin de son .log du
   dernier run : c'est ce que le GUI lit pour le clic droit "Ouvrir le log de ce test".

Important : l'import du framework est fait *paresseusement*, jamais au niveau module.
Ainsi ce workspace reste collectable et executable meme sans le framework (ex: clone
sans SmartcardFramework), sans provoquer d'erreur de collecte pytest.
"""

import json
import logging
import os
import time
from pathlib import Path

import pytest

from log import next_available_build_number, safe_path_name, setup_logging


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


def _logging_settings(workspace: Path) -> tuple[Path, bool, str]:
    """Retourne racine, mode incremental et lecteur declares par le workspace.

    Logique volontairement identique a
    gui_qt.config.config_loader.resolve_log_root (le GUI et le conftest DOIVENT
    regarder au meme endroit). On la duplique ici pour garder le conftest autonome,
    sans dependance a gui_qt (testSuite1 peut tourner hors du projet)."""
    log_dir = "logs"
    incremental_log = False
    reader = os.environ.get("PYTESTRUNNER_READER", "").strip()

    preferred = (
        os.environ.get("PYTESTRUNNER_READER_CONFIG_PATH", "")
        or os.environ.get("PYTESTRUNNER_READER_CONFIG", "")
    ).strip()
    candidates = [Path(preferred)] if preferred else []
    candidates.extend(workspace / name for name in ("config.yaml", "config.yml"))
    try:
        candidates.extend(sorted(workspace.glob("*.yml")))
        candidates.extend(sorted(workspace.glob("*.yaml")))
    except OSError:
        pass

    def find_value(data, accepted):
        if not isinstance(data, dict):
            return None
        for key, value in data.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in accepted and value not in (None, ""):
                return value
        for value in data.values():
            nested = find_value(value, accepted)
            if nested is not None:
                return nested
        return None

    seen: set[Path] = set()
    path_selected = False
    increment_selected = False
    for cfg in candidates:
        try:
            cfg = cfg.resolve()
        except OSError:
            continue
        if cfg in seen:
            continue
        seen.add(cfg)
        if cfg.exists():
            try:
                import yaml
                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    configured_path = find_value(
                        data, {"log_directory", "log_path", "log_dir", "logpath"})
                    if configured_path and not path_selected:
                        log_dir = str(configured_path)
                        path_selected = True

                    raw_increment = find_value(
                        data, {"incremental_log", "incrementallog"})
                    if raw_increment is not None and not increment_selected:
                        incremental_log = (
                            raw_increment if isinstance(raw_increment, bool)
                            else str(raw_increment).strip().lower() in {"1", "true", "yes", "on"}
                        )
                        increment_selected = True

                    if not reader:
                        reader = str(find_value(data, {"reader"}) or "").strip()
            except Exception:
                pass

    root = Path(log_dir)
    root = root if root.is_absolute() else workspace / root
    return root, incremental_log, reader


@pytest.fixture(scope="session")
def _log_session(request):
    """Prepare une fois par run : date, build, lecteur et manifestes.

    Ancre sur le repertoire d'invocation de pytest (= cwd = le workspace lance par
    le GUI), pas sur rootdir (qui peut differer a cause des multiples pytest.ini)."""
    workspace = Path(request.config.invocation_params.dir).resolve()
    log_root, incremental_log, reader = _logging_settings(workspace)
    datestamp = time.strftime("%Y%m%d")

    raw_build = os.environ.get("PYTEST_RUNNER_BUILD_NUMBER", "").strip()
    try:
        build_number = int(raw_build)
    except (TypeError, ValueError):
        build_number = next_available_build_number(log_root, datestamp)

    log_root.mkdir(parents=True, exist_ok=True)

    manifest_path = log_root / "last_run_index.json"
    reader_suffix = f"_{safe_path_name(reader)}" if reader else ""
    build_manifest_path = (
        log_root / datestamp / f"build_{build_number:04d}{reader_suffix}.json"
    )
    build_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, str] = {}
    # Repart d'un manifeste vide pour ce run (ne reference que les tests de ce run).
    for path in (manifest_path, build_manifest_path):
        try:
            path.write_text("{}", encoding="utf-8")
        except OSError:
            pass

    return {
        "workspace": workspace,
        "log_root": log_root,
        "datestamp": datestamp,
        "build_number": build_number,
        "reader": reader,
        "incremental_log": incremental_log,
        "manifest_path": manifest_path,
        "build_manifest_path": build_manifest_path,
        "manifest": manifest,
    }


@pytest.fixture(autouse=True)
def _per_test_log(request, _log_session):
    """Cree un .log par test, l'attache au logger APDU, et met a jour le manifeste."""
    nodeid = request.node.nodeid
    logger = _apdu_logger()

    node_path = getattr(request.node, "path", None)
    if node_path is None:
        node_path = request.node.fspath

    log_path, handler = setup_logging(
        test_file=Path(str(node_path)),
        test_name=request.node.name,
        log_directory=_log_session["log_root"],
        session_datestamp=_log_session["datestamp"],
        workspace_root=_log_session["workspace"],
        reader=_log_session["reader"],
        build_number=_log_session["build_number"],
        incremental_log=_log_session["incremental_log"],
        logger=logger,
    )
    logger.info("=== %s @ %s ===", nodeid, time.strftime("%Y-%m-%d %H:%M:%S"))

    manifest = _log_session["manifest"]
    manifest[nodeid] = str(log_path)
    for path in (_log_session["manifest_path"], _log_session["build_manifest_path"]):
        try:
            path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except OSError:
            pass

    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
