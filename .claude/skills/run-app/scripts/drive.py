"""Lance Pytest Runner, le pilote et en rapporte captures, chronos et erreurs.

Toujours isole des donnees de l'utilisateur : reglages, profils, tests
desactives et historique vont dans un dossier temporaire.

    python drive.py --workspace testSuite1 --out shots
    python drive.py --workspace demo_queue_workspace --pause --mode real --record

--mode offscreen (defaut) : sans fenetre, rapide, captures par widget.grab().
--mode real : vraie fenetre Windows a l'ecran ; avec --record, la fenetre est
filmee (~30 ms) et seules les images qui changent sont gardees, pour voir les
defauts qui ne durent qu'une image.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PAGES = ("profiles", "yaml", "history", "comparison", "python", "console", "settings")
TABS = ("detail", "source", "output", "logs")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="testSuite1",
                        help="Dossier a collecter (relatif au depot ou absolu).")
    parser.add_argument("--out", required=True, help="Dossier des captures et du rapport.")
    parser.add_argument("--mode", choices=("offscreen", "real"), default="offscreen")
    parser.add_argument("--size", default="1600x1000", help="Taille de fenetre, ex. 930x990.")
    parser.add_argument("--no-run", action="store_true", help="Collecter seulement.")
    parser.add_argument("--pause", action="store_true",
                        help="Pendant le run : Pause, attendre Resume, reprendre, puis Stop.")
    parser.add_argument("--pages", action="store_true", help="Capturer chaque page de navigation.")
    parser.add_argument("--themes", action="store_true", help="Capturer chaque theme.")
    parser.add_argument("--font-size", type=int, help="Taille de texte des preferences (13 par defaut).")
    parser.add_argument("--record", action="store_true", help="Filmer la fenetre (mode real).")
    parser.add_argument("--time-scale", default="0.15",
                        help="PYTEST_RUNNER_DEMO_TIME_SCALE pour demo_queue_workspace.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Limite pour un run.")
    return parser.parse_args()


def isolate(tmp: Path) -> None:
    """Rien ne doit toucher aux vrais reglages ni a l'historique de l'utilisateur."""
    from PySide6.QtCore import QSettings, QStandardPaths

    QStandardPaths.setTestModeEnabled(True)
    import runner.domain.history as history
    history.dossier = lambda: (tmp / "history").mkdir(parents=True, exist_ok=True) or tmp / "history"


def isolate_settings(tmp: Path) -> None:
    """QSettings(ORG, APP) ecrit dans le registre : setDefaultFormat ne le
    redirige pas. Chaque module de runner recoit une classe qui ecrit dans un
    fichier temporaire, quels que soient les arguments."""
    from PySide6.QtCore import QSettings

    ini = str(tmp / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.IniFormat)

    for name, module in list(sys.modules.items()):
        if name.startswith("runner") and getattr(module, "QSettings", None) is QSettings:
            module.QSettings = IsolatedSettings


class Recorder:
    """Filme la fenetre telle que l'ecran l'affiche, toutes les ~25 ms.

    Les captures se font dans le fil Qt, entre deux traitements d'evenements :
    c'est la que Windows peint, donc la qu'apparaissent les images
    intermediaires qu'un widget.grab() apres coup ne voit jamais.
    """

    def __init__(self, window, out: Path):
        from PySide6.QtCore import QTimer

        self.window, self.out, self.kept = window, out, 0
        self._previous, self._start = None, time.time()
        self._timer = QTimer()
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._grab)
        self._timer.start()

    def _grab(self) -> None:
        from ctypes import wintypes as wt

        rect = wt.RECT()
        ctypes.windll.user32.GetWindowRect(int(self.window.winId()), ctypes.byref(rect))
        image = self.window.screen().grabWindow(
            0, rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top).toImage()
        key = bytes(image.constBits())
        if key != self._previous:
            image.save(str(self.out / f"rec_{int((time.time() - self._start) * 1000):06d}.png"))
            self._previous, self.kept = key, self.kept + 1

    def stop(self) -> None:
        self._timer.stop()


def main() -> int:
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    workspace = Path(args.workspace)
    workspace = (workspace if workspace.is_absolute() else ROOT / workspace).resolve()
    if args.mode == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
    os.environ["PYTEST_RUNNER_DEMO_TIME_SCALE"] = args.time_scale
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    errors: list[str] = []
    qt_messages: list[str] = []
    sys.excepthook = lambda kind, value, tb: errors.append(
        "".join(traceback.format_exception(kind, value, tb)))

    from PySide6.QtCore import Qt, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QDialog

    tmp = Path(tempfile.mkdtemp(prefix="run_app_"))
    isolate(tmp)
    qInstallMessageHandler(lambda mode, context, message: qt_messages.append(message))
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(["run-app"])

    # Meme demarrage que `python -m runner`, modules d'installation compris :
    # ce sont eux qui remplacent des methodes et qu'on oublie de tester.
    from runner.ui.theme import app_stylesheet
    from runner.ui import clean_ui, end_run_feedback, main_ux, runtime_polish
    from runner.ui.main_window import MainWindow
    app.setStyleSheet(app_stylesheet())
    for module in (clean_ui, end_run_feedback, main_ux, runtime_polish):
        module.install()
    # Apres les imports : chaque module a deja son propre nom QSettings.
    isolate_settings(tmp)

    width, height = (int(v) for v in args.size.lower().split("x"))
    window = MainWindow()
    window.resize(width, height)
    window.move(40, 40)
    window.show()
    title = "Pytest Runner (run-app)"
    context = window._selected_run_context()
    if args.font_size and getattr(window, "preferences", None):
        window.preferences.values["font_size"] = args.font_size
        window.preferences.apply_font()

    modals: list[str] = []

    def close_modals():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                modals.append(widget.windowTitle())
                widget.grab().save(str(out / f"modal_{len(modals)}.png"))
                widget.reject()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            close_modals()
            time.sleep(0.01)

    def wait(condition, seconds: float, label: str) -> float | None:
        start = time.time()
        while time.time() - start < seconds:
            app.processEvents()
            close_modals()
            try:
                if condition():
                    return time.time() - start
            except Exception:
                pass
            time.sleep(0.02)
        errors.append(f"TIMEOUT: {label} after {seconds:.0f}s")
        return None

    shots: list[str] = []

    def shot(name: str) -> None:
        pump(0.3)
        path = out / f"{len(shots):02d}_{name}.png"
        window.grab().save(str(path))
        shots.append(path.name)

    recorder = None
    pump(0.8)
    if args.mode == "real":
        window.setWindowTitle(title)
        window.raise_()
        window.activateWindow()
        pump(0.5)
        if args.record:
            recorder = Recorder(window, out)

    timings: dict[str, float | None] = {}
    statuses: list[str] = []
    shot("start")
    context.workspace_combo.setCurrentText(str(workspace))
    context.load_workspace()
    timings["collect"] = wait(lambda: context._collector is not None
                              and not context._collector.isRunning(), 180, "collection")
    pump(0.8)
    statuses.append(f"collected: {context.status_label.text()}")
    if args.mode == "real":
        window.setWindowTitle(title)  # la collecte renomme la fenetre
    shot("collected")

    if not args.no_run:
        finished: list[float] = []
        context.service.finished.connect(lambda *_: finished.append(time.time()))
        context.model.set_all_checked(True)
        start = time.time()
        context.run_button.click()
        pump(1.5)
        shot("running")
        if args.pause:
            context.pause_button.click()
            wait(lambda: context.service.pause_state == "paused", 120, "pause")
            shot("paused")
            context.pause_button.click()
            pump(1.0)
            shot("resumed")
            context.stop_button.click()
        wait(lambda: finished, args.timeout, "run end")
        timings["run"] = time.time() - start
        pump(2.0)
        statuses.append(f"finished: {context.status_label.text()}")
        shot("finished")
        from runner.ui.results_panel import ONGLET_DETAIL, ONGLET_LOGS, ONGLET_OUTPUT, ONGLET_SOURCE
        tree = context.tree
        index = tree.model().index(0, 0)
        while tree.model().rowCount(index):
            tree.expand(index)
            index = tree.model().index(0, 0, index)
        tree.setCurrentIndex(index)
        for name, tab in zip(TABS, (ONGLET_DETAIL, ONGLET_SOURCE, ONGLET_OUTPUT, ONGLET_LOGS)):
            context.results.show_tab(tab)
            shot(f"tab_{name}")

    if args.pages:
        for page in PAGES:
            try:
                window._show_page(page)
                pump(0.8)
                shot(f"page_{page}")
            except Exception:
                errors.append(f"page {page}: {traceback.format_exc()}")
        window._show_page("workspace")
    if args.themes:
        for number in range(3):
            window.toggle_theme()
            pump(0.8)
            shot(f"theme_{number}")

    if recorder is not None:
        recorder.stop()
    window.close()
    pump(0.5)

    report = [
        f"workspace: {workspace}",
        f"mode: {args.mode}  size: {args.size}  isolated data: {tmp}",
        *statuses,
        "timings: " + ", ".join(f"{k}={v:.1f}s" if v is not None else f"{k}=timeout"
                                for k, v in timings.items()),
        f"screenshots ({len(shots)}): {', '.join(shots)}",
        f"recorded frames kept: {recorder.kept}" if recorder else "recorded frames: -",
        f"modal dialogs closed ({len(modals)}): {modals}",
        f"Qt messages ({len(qt_messages)}):", *[f"  {m}" for m in qt_messages[:30]],
        f"ERRORS ({len(errors)}):", *errors,
    ]
    (out / "report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
