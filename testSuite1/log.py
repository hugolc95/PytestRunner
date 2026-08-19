"""Construction des fichiers de log d'un workspace pytest.

Ce module ne depend ni du GUI ni du SmartcardFramework. Il peut donc etre copie
tel quel dans un autre workspace avec son conftest.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path


FILE_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
CONSOLE_LOG_FORMAT = "%(levelname)s - %(message)s"


def safe_path_name(value: object) -> str:
    """Retourne un nom de fichier valide, notamment sous Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")
    return cleaned[:180] or "unnamed"


def relative_test_directory(test_file: Path, workspace_root: Path) -> Path:
    """Reconstruit toute l'arborescence du test sous la racine du workspace."""
    test_file = Path(test_file).resolve()
    workspace_root = Path(workspace_root).resolve()
    try:
        return test_file.relative_to(workspace_root).parent
    except ValueError:
        # Repli pour un test externe au workspace : les quatre derniers parents
        # sont conserves, sans jamais reintroduire une racine absolue.
        parts = [safe_path_name(part) for part in test_file.parent.parts[-4:]]
        return Path(*parts) if parts else Path()


def _exclusive_handler(directory: Path, stem: str, numbered: bool) -> tuple[logging.FileHandler, Path]:
    """Reserve un nom avec le mode ``x`` : aucun ancien log ne peut etre ecrase."""
    index = 1
    while True:
        if numbered:
            filename = f"{stem}_{index:03d}.log"
        elif index == 1:
            filename = f"{stem}.log"
        else:
            filename = f"{stem}_{index:03d}.log"

        path = directory / filename
        try:
            return logging.FileHandler(path, mode="x", encoding="utf-8"), path
        except FileExistsError:
            index += 1


def next_available_build_number(log_root: Path, datestamp: str) -> int:
    """Numero local de repli pour un lancement pytest effectue hors du GUI."""
    date_root = Path(log_root) / datestamp
    if not date_root.is_dir():
        return 1

    numbers: set[int] = set()
    run_re = re.compile(r"^Run_(\d+)$")
    file_re = re.compile(r"_B(\d+)_\d+\.log$")

    for child in date_root.iterdir():
        match = run_re.match(child.name) if child.is_dir() else None
        if match:
            numbers.add(int(match.group(1)))

    for log_file in date_root.rglob("*.log"):
        match = file_re.search(log_file.name)
        if match:
            numbers.add(int(match.group(1)))

    return max(numbers, default=0) + 1


def configure_console_logging(logger: logging.Logger, log_level: int) -> None:
    """Retire l'horodatage des handlers affiches dans la console/PyCharm.

    ``FileHandler`` herite de ``StreamHandler`` : il faut donc l'exclure
    explicitement pour conserver l'horodatage dans les fichiers ``.log``.
    """
    formatter = logging.Formatter(CONSOLE_LOG_FORMAT)
    for console_handler in logger.handlers:
        if (
            isinstance(console_handler, logging.StreamHandler)
            and not isinstance(console_handler, logging.FileHandler)
        ):
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)


def setup_logging(
    *,
    test_file: Path,
    test_name: str,
    log_directory: Path,
    session_datestamp: str,
    workspace_root: Path,
    reader: str,
    build_number: int,
    incremental_log: bool,
    logger: logging.Logger,
    log_level: int = logging.INFO,
) -> tuple[Path, logging.FileHandler]:
    """Attache au logger un fichier unique pour le test courant.

    Mode normal::

        logs/date/Run_0042/reader/chemin/test.log

    Mode incremental::

        logs/date/reader/chemin/test_B0042_001.log
    """
    test_file = Path(test_file).resolve()
    log_directory = Path(log_directory).resolve()
    relative_directory = relative_test_directory(test_file, workspace_root)
    build_label = f"{int(build_number):04d}"

    parts = [log_directory, Path(session_datestamp)]
    if not incremental_log:
        parts.append(Path(f"Run_{build_label}"))
    if reader:
        parts.append(Path(safe_path_name(reader)))
    parts.append(relative_directory)

    test_log_directory = parts[0]
    for part in parts[1:]:
        test_log_directory /= part
    test_log_directory.mkdir(parents=True, exist_ok=True)

    stem = safe_path_name(test_name)
    if incremental_log:
        stem = f"{stem}_B{build_label}"

    handler, log_path = _exclusive_handler(
        test_log_directory,
        stem,
        numbered=incremental_log,
    )
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT))

    logger.setLevel(log_level)
    configure_console_logging(logger, log_level)
    logger.addHandler(handler)
    return log_path, handler
