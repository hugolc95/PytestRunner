"""Non-blocking update UX for the packaged Windows application."""

from __future__ import annotations

import os
import subprocess
import sys

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox

from runner.services.update_service import (
    PreparedUpdate,
    UpdateManifest,
    check_for_update,
    make_restart_script,
    prepare_update,
)
from runner.version import __version__


class _CheckWorker(QThread):
    completed = pyqtSignal(object, object, object)  # update_dir, manifest, error

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = (None, None, None)
        self.finished.connect(self._emit_after_finished)

    def run(self) -> None:
        try:
            found = check_for_update(__version__)
            if found is None:
                self._result = (None, None, None)
            else:
                self._result = (found[0], found[1], None)
        except Exception as exc:  # update failures must never prevent startup
            self._result = (None, None, exc)

    def _emit_after_finished(self) -> None:
        self.completed.emit(*self._result)


class _PrepareWorker(QThread):
    completed = pyqtSignal(object, object)  # PreparedUpdate, error

    def __init__(self, update_dir, manifest: UpdateManifest, parent=None):
        super().__init__(parent)
        self._update_dir = update_dir
        self._manifest = manifest
        self._result = (None, None)
        self.finished.connect(self._emit_after_finished)

    def run(self) -> None:
        try:
            self._result = (prepare_update(self._update_dir, self._manifest), None)
        except Exception as exc:
            self._result = (None, exc)

    def _emit_after_finished(self) -> None:
        self.completed.emit(*self._result)


class UpdateController(QObject):
    """Checks the corporate share and coordinates a safe restart update."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._check_worker: _CheckWorker | None = None
        self._prepare_worker: _PrepareWorker | None = None

    def check_at_startup(self) -> None:
        # Source launches are developer sessions. They can still exercise the
        # pure update-service functions, but must never offer to overwrite a
        # checkout with a PyInstaller package.
        if not getattr(sys, "frozen", False):
            return
        self._check_worker = _CheckWorker(self)
        self._check_worker.completed.connect(self._on_checked)
        self._check_worker.start()

    def _on_checked(self, update_dir, manifest, error) -> None:
        self._check_worker = None
        if error is not None or manifest is None:
            # A disconnected corporate share is normal on laptops/VPN. Startup
            # stays silent rather than showing an error every time.
            return

        answer = QMessageBox.question(
            self.window,
            "Pytest Runner update",
            f"Pytest Runner {manifest.version} is available.\n\n"
            f"Current version: {__version__}\n\n"
            "Install the update and restart now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        if getattr(self.window.service, "busy", False):
            QMessageBox.information(
                self.window,
                "Update postponed",
                "A test run is active. Install the update after the run finishes.",
            )
            return

        self.window._set_status_live(f"Preparing update {manifest.version}…")
        self._prepare_worker = _PrepareWorker(update_dir, manifest, self)
        self._prepare_worker.completed.connect(self._on_prepared)
        self._prepare_worker.start()

    def _on_prepared(self, prepared: PreparedUpdate | None, error) -> None:
        self._prepare_worker = None
        if error is not None or prepared is None:
            self.window._set_status_idle("Update failed")
            QMessageBox.warning(
                self.window,
                "Update failed",
                "The update could not be prepared.\n\n"
                f"{error}",
            )
            return

        try:
            script = make_restart_script(prepared, os.getpid())
            creationflags = 0
            if os.name == "nt":
                creationflags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(script)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.window._set_status_idle("Update failed")
            QMessageBox.warning(
                self.window,
                "Update failed",
                "The updater could not be started.\n\n"
                f"{exc}",
            )
            return

        # From here the temporary updater owns the operation. It waits until
        # this PID is actually gone before touching the installation directory.
        QApplication.instance().quit()
