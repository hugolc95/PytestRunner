"""Application icon shared by both Pytest Runner interfaces."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication


APP_ICON_RELATIVE_PATH = Path("assets") / "pytest_runner.ico"
APP_USER_MODEL_ID = "HugoLeCoz.PytestRunner"


def resource_path(relative_path: str | Path) -> Path:
    """Return an asset path in sources or in a PyInstaller bundle."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    base_path = Path(bundle_root) if bundle_root else Path(__file__).resolve().parent
    return base_path / relative_path


def set_windows_app_user_model_id() -> None:
    """Give Windows a stable taskbar identity for the application."""

    if sys.platform != "win32":
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        # The icon still works without an explicit AppUserModelID on older or
        # restricted Windows environments.
        pass


def install_application_icon(app: QApplication) -> QIcon:
    """Install the icon inherited by every top-level Qt window and dialog."""

    icon = QIcon(str(resource_path(APP_ICON_RELATIVE_PATH)))
    if not icon.isNull():
        app.setWindowIcon(icon)
    return icon
