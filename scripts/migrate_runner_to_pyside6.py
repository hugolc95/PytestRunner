"""One-shot source migration for the active Runner UI: PyQt5 -> PySide6.

This intentionally targets only the active ``runner/`` application and its
unit tests. The legacy ``gui_qt/`` interface stays untouched on this migration
branch and is excluded from the PyInstaller build.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "runner", ROOT / "main_runner.py", ROOT / "app_icon.py"]

REPLACEMENTS = (
    ("from PyQt5.", "from PySide6."),
    ("from PyQt5 import", "from PySide6 import"),
    ("import PyQt5.", "import PySide6."),
    ("import PyQt5", "import PySide6"),
    ("pyqtSignal", "Signal"),
    ("pyqtSlot", "Slot"),
    ("pyqtProperty", "Property"),
    (".exec_()", ".exec()"),
)


def python_files(target: Path):
    if target.is_file() and target.suffix == ".py":
        yield target
    elif target.is_dir():
        yield from target.rglob("*.py")


def qt6_api_moves(path: Path, text: str) -> str:
    """Apply API moves that happened between Qt5 and Qt6.

    These are deliberately file-specific so the migration stays conservative:
    we only move symbols that the CI has proven are imported from the wrong Qt6
    module instead of broadly rewriting every Qt import.
    """
    relative = path.relative_to(ROOT).as_posix()

    if relative == "runner/ui/results_panel.py":
        text = text.replace(
            "from PySide6.QtGui import QKeySequence\n",
            "from PySide6.QtGui import QKeySequence, QShortcut\n",
        )
        text = text.replace("    QShortcut,\n", "")

    if relative == "runner/ui/history_dashboard.py":
        text = text.replace(
            "from PySide6.QtGui import QColor, QDesktopServices\n",
            "from PySide6.QtGui import QActionGroup, QColor, QDesktopServices\n",
        )
        text = text.replace("    QActionGroup,\n", "")

    return text


def migrate(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    for before, after in REPLACEMENTS:
        updated = updated.replace(before, after)
    updated = qt6_api_moves(path, updated)

    if updated == original:
        return False

    path.write_text(updated, encoding="utf-8")
    print(f"migrated: {path.relative_to(ROOT)}")
    return True


def main() -> int:
    changed = 0
    seen: set[Path] = set()
    for target in TARGETS:
        for path in python_files(target):
            path = path.resolve()
            if path in seen:
                continue
            seen.add(path)
            changed += int(migrate(path))

    print(f"PySide6 migration complete: {changed} file(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
