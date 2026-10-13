"""Open an IDE project and a line through argument lists, never a command shell."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from runner.domain.trace_locations import SourceNavigationError, project_for_file


def _native_launcher(path: Path) -> Path | None:
    if sys.platform == "darwin" and path.suffix == ".app":
        if "visual studio code" in path.name.casefold():
            path = path / "Contents/Resources/app/bin/code"
        else:
            path = path / "Contents/MacOS/pycharm"
    if sys.platform == "win32" and path.suffix.lower() in (".cmd", ".bat"):
        for base in (path.parent, path.parent.parent):
            for name in ("Code.exe", "Code - Insiders.exe", "pycharm64.exe"):
                candidate = base / name
                if candidate.is_file():
                    return candidate
        return None
    return path if path.is_file() else None


def find_editor(kind: str, configured: str = "") -> Path | None:
    if configured:
        path = _native_launcher(Path(configured).expanduser())
        if path is None:
            raise SourceNavigationError(f"The configured {kind} executable is unavailable:\n{configured}\n"
                                        "Check Settings → External editor.")
        return path
    names = ("code", "code-insiders") if kind == "vscode" else ("pycharm", "pycharm64", "charm")
    for name in names:
        found = shutil.which(name)
        if found and (path := _native_launcher(Path(found))):
            return path
    candidates = []
    if sys.platform == "win32":
        bases = [Path(value) for name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
                 if (value := os.environ.get(name))]
        for base in bases:
            if kind == "vscode":
                candidates.extend(base / suffix for suffix in (
                    "Programs/Microsoft VS Code/Code.exe", "Microsoft VS Code/Code.exe",
                    "Programs/Microsoft VS Code Insiders/Code - Insiders.exe",
                    "Microsoft VS Code Insiders/Code - Insiders.exe"))
            else:
                for prefix in (base / "JetBrains", base / "Programs", base / "JetBrains/Toolbox/apps"):
                    for pattern in ("PyCharm*/bin/pycharm64.exe", "pycharm*/bin/pycharm64.exe",
                                    "PyCharm*/*/bin/pycharm64.exe", "PyCharm*/ch-*/*/bin/pycharm64.exe"):
                        candidates.extend(sorted(prefix.glob(pattern), reverse=True))
    elif sys.platform == "darwin":
        if kind == "vscode":
            candidates = [Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")]
        else:
            candidates = list(Path("/Applications").glob("PyCharm*.app/Contents/MacOS/pycharm"))
    else:
        candidates = ([Path("/usr/bin/code"), Path("/snap/bin/code")] if kind == "vscode" else
                      [*Path("/opt").glob("pycharm*/bin/pycharm.sh"),
                       Path("/snap/bin/pycharm-community"), Path("/snap/bin/pycharm-professional")])
    return next((path for candidate in candidates if (path := _native_launcher(candidate))), None)


def open_external(location, path: Path, workspace: str, values: dict) -> str:
    preferred = values.get("external_editor", "Automatic")
    order = ("pycharm", "vscode") if preferred == "PyCharm" else ("vscode", "pycharm")
    for kind in order:
        executable = find_editor(kind, values.get(kind + "_path", ""))
        if executable is None:
            continue
        project = project_for_file(path, workspace, kind)
        if kind == "vscode":
            # Let VS Code target the matching project window; --reuse-window
            # would replace an unrelated window, --new-window duplicates it.
            command = [str(executable), str(project), "--goto", f"{path}:{location.line}:{location.column}"]
        else:
            command = [str(executable), str(project), "--line", str(location.line),
                       "--column", str(location.column), str(path)]
        try:
            subprocess.Popen(command, cwd=str(project.parent if project.is_file() else project))
        except OSError as exc:
            raise SourceNavigationError(f"Could not open {kind}: {exc}\n"
                                        "Check Settings → External editor.") from exc
        return "VS Code" if kind == "vscode" else "PyCharm"
    raise SourceNavigationError("Neither VS Code nor PyCharm was found.\n"
                                "Install an editor or select its executable in Settings → External editor.")
