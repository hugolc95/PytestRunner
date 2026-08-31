"""PySide6 bootstrap for the existing PyQt5-based UI.

The application UI runs with PySide6/Qt 6 while the existing source modules can
continue importing ``PyQt5`` during the migration.  Keeping the compatibility
layer at the process boundary lets us preserve every current feature first, then
modernise modules incrementally without mixing the GUI runtime with the Python
runtime used to execute pytest.
"""

from __future__ import annotations

import sys
import types


def install_pyqt5_compat() -> None:
    """Expose the PySide6 modules under the PyQt5 import names used by the app."""
    if "PyQt5" in sys.modules:
        return

    import PySide6
    from PySide6 import QtCore, QtGui, QtWidgets

    # Names that differ between the bindings.
    if not hasattr(QtCore, "pyqtSignal"):
        QtCore.pyqtSignal = QtCore.Signal
    if not hasattr(QtCore, "pyqtSlot"):
        QtCore.pyqtSlot = QtCore.Slot
    if not hasattr(QtCore, "pyqtProperty"):
        QtCore.pyqtProperty = QtCore.Property

    package = types.ModuleType("PyQt5")
    package.__path__ = []
    package.__version__ = getattr(PySide6, "__version__", "")
    package.QtCore = QtCore
    package.QtGui = QtGui
    package.QtWidgets = QtWidgets

    sys.modules["PyQt5"] = package
    sys.modules["PyQt5.QtCore"] = QtCore
    sys.modules["PyQt5.QtGui"] = QtGui
    sys.modules["PyQt5.QtWidgets"] = QtWidgets

    # Optional Qt modules are registered only when available.  This keeps the
    # bootstrap light and avoids importing large modules the Runner does not use.
    for module_name in ("QtSvg", "QtPrintSupport"):
        try:
            module = __import__(f"PySide6.{module_name}", fromlist=[module_name])
        except ImportError:
            continue
        setattr(package, module_name, module)
        sys.modules[f"PyQt5.{module_name}"] = module
