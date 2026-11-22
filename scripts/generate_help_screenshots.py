"""Genere les captures annotees du centre d'aide (runner/help_assets).

    C:\\Python312\\python.exe scripts\\generate_help_screenshots.py

A relancer avant une version des que l'interface d'un ecran documente change :
les captures sont produites par la vraie application, avec ses modules
d'installation, donc elles montrent ce que l'utilisateur verra.

Les ecrans, les widgets numerotes et leurs legendes sont definis dans
`runner/ui/help_content.py` (SCREENSHOTS) : un widget introuvable ou cache
arrete la generation, plutot que de produire une capture dont les numeros ne
correspondraient plus a la legende.

Tout est isole des donnees de l'utilisateur (reglages, profils, historique),
et la suite de demonstration est copiee dans un dossier temporaire : les logs
du run ne salissent pas le depot.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCENT = "#ea580c"     # orange : ne ressemble a aucun verdict ni lecteur
BADGE = 22
PADDING = 10


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "runner" / "help_assets"))
    parser.add_argument("--size", default="1440x900")
    parser.add_argument("--only", nargs="*", help="Noms de captures a regenerer.")
    return parser.parse_args()


def isolate(tmp: Path) -> None:
    from PySide6.QtCore import QSettings, QStandardPaths

    QStandardPaths.setTestModeEnabled(True)
    import runner.domain.history as history
    history.dossier = lambda: (tmp / "history").mkdir(parents=True, exist_ok=True) or tmp / "history"

    ini = str(tmp / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.IniFormat)

    for name, module in list(sys.modules.items()):
        if name.startswith("runner") and getattr(module, "QSettings", None) is QSettings:
            module.QSettings = IsolatedSettings


def resolve(root, path: str):
    """`a.b`, `nav[2]` (= .widget(2)), `nav_buttons.help` (cle de dict)."""
    obj = root
    for part in path.split("."):
        index = None
        if part.endswith("]"):
            part, index = part[:-1].split("[")
        obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        if callable(obj) and not hasattr(obj, "metaObject"):
            obj = obj()
        if index is not None:
            obj = obj.widget(int(index))
    return obj


def annotate(window, shot, out: Path) -> dict:
    from PySide6.QtCore import QPoint, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtWidgets import QLayout

    pixmap = window.grab()
    ratio = pixmap.devicePixelRatio()
    if shot.crop:
        cible = resolve(window, shot.crop)
        origine = cible.mapTo(window, QPoint(0, 0))
        cadre = QRect(origine, cible.size()).adjusted(-PADDING, -PADDING, PADDING, PADDING)
        cadre = cadre.intersected(window.rect())
    else:
        cadre = window.rect()
    image = pixmap.copy(QRect(cadre.topLeft() * ratio, cadre.size() * ratio))
    image.setDevicePixelRatio(ratio)

    # Tout valider AVANT de peindre : quitter avec un QPainter ouvert plante.
    zones = []
    for chemin, _legende in shot.markers:
        cible_marque = resolve(window, chemin)
        if isinstance(cible_marque, QLayout):
            # Un groupe de controles sans widget propre : sa geometrie de mise
            # en page, dans le widget qui le porte.
            hote, geometrie = cible_marque.parentWidget(), cible_marque.geometry()
        else:
            hote, geometrie = cible_marque, cible_marque.rect()
        if not hote.isVisible() or geometrie.isEmpty():
            raise SystemExit(f"{shot.name}: le widget {chemin} n'est pas visible")
        zones.append(QRect(hote.mapTo(window, geometrie.topLeft()) - cadre.topLeft(), geometrie.size()))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    font = QFont(window.font())
    font.setPixelSize(12)
    font.setBold(True)
    painter.setFont(font)
    places: list[QRectF] = []
    for numero, zone in enumerate(zones, start=1):
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(zone).adjusted(1, 1, -1, -1), 5, 5)
        # Pastille au coin haut-gauche, decalee si elle chevauche une autre.
        x = max(0, min(zone.left() - BADGE / 3, cadre.width() - BADGE))
        y = max(0, min(zone.top() - BADGE / 3, cadre.height() - BADGE))
        pastille = QRectF(x, y, BADGE, BADGE)
        while any(pastille.intersects(autre) for autre in places):
            pastille.translate(BADGE + 2, 0)
        places.append(pastille)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setBrush(QColor(ACCENT))
        painter.drawEllipse(pastille)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pastille, Qt.AlignCenter, str(numero))
    painter.end()
    chemin_image = out / f"{shot.name}.png"
    image.save(str(chemin_image), "PNG")
    return {"width": cadre.width(), "height": cadre.height(), "markers": len(shot.markers)}


def main() -> int:
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    tmp = Path(tempfile.mkdtemp(prefix="help_shots_"))
    # Chemin court et stable : il apparait en clair dans les captures.
    workspace = Path(tempfile.gettempdir()) / "PytestRunner-demo" / "CardSuite"
    shutil.rmtree(workspace, ignore_errors=True)
    shutil.copytree(ROOT / "testSuite1", workspace,
                    ignore=shutil.ignore_patterns("logs", "__pycache__", ".pytest_cache"))
    # Deux lecteurs nommes : la carte Execution, les colonnes par lecteur et
    # les onglets de sortie apparaissent comme chez un utilisateur equipe.
    (workspace / "config.yaml").write_text(
        "Reader: OMNIKEY 3x21 Reader 0\n"
        "Readers:\n  - OMNIKEY 3x21 Reader 1\n"
        "log_directory: logs\n", encoding="utf-8")

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QDialog

    isolate(tmp)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(["help-screenshots"])

    from runner.domain.execution_profile import ExecutionProfile
    from runner.domain.models import Status
    from runner.ui import clean_ui, end_run_feedback, main_ux, runtime_polish
    from runner.ui import tokens as t
    from runner.ui.help_content import SCREENSHOTS
    from runner.ui.main_window import MainWindow
    from runner.ui.results_panel import ONGLET_DETAIL
    from runner.ui.theme import app_stylesheet

    # Theme clair : les captures restent lisibles imprimees ou exportees.
    t.set_theme("light")
    app.setStyleSheet(app_stylesheet())
    for module in (clean_ui, end_run_feedback, main_ux, runtime_polish):
        module.install()
    isolate(tmp)

    def pump(seconds: float) -> None:
        fin = time.time() + seconds
        while time.time() < fin:
            app.processEvents()
            for widget in app.topLevelWidgets():
                if isinstance(widget, QDialog) and widget.isVisible():
                    widget.reject()
            time.sleep(0.01)

    def wait(condition, seconds: float, label: str) -> None:
        fin = time.time() + seconds
        while time.time() < fin:
            app.processEvents()
            if condition():
                return
            time.sleep(0.02)
        raise SystemExit(f"Delai depasse : {label}")

    width, height = (int(v) for v in args.size.lower().split("x"))
    window = MainWindow()
    # Le mode test de QStandardPaths partage un dossier entre deux
    # generations : un magasin de profils neuf a chaque fois.
    from runner.domain.execution_profile import ProfileStore
    window.profiles_page.store = ProfileStore(tmp / "profiles")
    window.apply_theme("light")
    window.resize(width, height)
    window.show()
    pump(0.8)

    window.workspace_combo.setCurrentText(str(workspace))
    window.load_workspace()
    wait(lambda: window._collector is not None and not window._collector.isRunning(), 180, "collecte")
    pump(0.5)
    finished = []
    window.service.finished.connect(lambda *_: finished.append(True))
    window._edit_run_name()
    window.run_name_edit.setText("Nightly validation")
    window._save_run_name()
    window.model.set_all_checked(True)
    window.run_button.click()
    wait(lambda: finished, 300, "fin du run")
    pump(2.5)

    # Un test en echec selectionne : Detail montre une vraie trace.
    echecs = [n for n in window.model._by_nodeid
              if Status.FAILED in window.model.statuses_for_nodeid(n).values()]
    if echecs:
        index = window.model.index_for_nodeid(sorted(echecs)[0])
        parent = index.parent()
        while parent.isValid():
            window.tree.expand(parent)
            parent = parent.parent()
        window.tree.setCurrentIndex(index)
        window.tree.scrollTo(index)
    window.results.show_tab(ONGLET_DETAIL)
    # Aucun champ ne garde le focus : sa selection apparaitrait en bleu.
    window.tree.setFocus()
    pump(0.8)

    # Un profil a deux groupes colores pour la page Execution Profiles.
    noeuds = sorted(window.model._by_nodeid)
    moitie = max(1, len(noeuds[:8]) // 2)
    groupes = (dict(id="smoke", name="Smoke checks", color="#1f6feb",
                    description="Fast checks before every delivery"),
               dict(id="api", name="API and protocols", color="#8250df",
                    description="Card exchanges, T=0 then T=1"))
    profil = ExecutionProfile(
        "Delivery campaign", noeuds[:8], "", "",
        step_groups=[dict(groupes[0]) if i < moitie else dict(groupes[1])
                     for i in range(len(noeuds[:8]))])
    window.profiles_page.store.save(profil)

    manifest = {}
    page_courante = None
    for shot in SCREENSHOTS.values():
        if args.only and shot.name not in args.only:
            continue
        taille = tuple(shot.size) or (width, height)
        if (window.width(), window.height()) != taille:
            window.resize(*taille)
            page_courante = None
        if shot.page != page_courante:
            window._show_page(shot.page)
            if shot.page == "profiles":
                window.profiles_page.refresh()
                window.profiles_page.sequence_list.expandAll()
            if shot.page == "history":
                window.history_dashboard.refresh()
                window.history_dashboard.run_list.setCurrentRow(0)
            page_courante = shot.page
            pump(1.0)
        manifest[shot.name] = annotate(window, shot, out)
        print(f"{shot.name}.png  {manifest[shot.name]}")

    chemin_manifest = out / "manifest.json"
    ancien = json.loads(chemin_manifest.read_text(encoding="utf-8")) if chemin_manifest.exists() else {}
    ancien.update(manifest)
    chemin_manifest.write_text(json.dumps(ancien, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    window.close()
    pump(0.5)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(workspace.parent, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
