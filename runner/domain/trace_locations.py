"""File references in Python/pytest traces, without guessing between files."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, unquote, urlsplit


class SourceNavigationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TraceLocation:
    path: str
    line: int
    column: int = 1
    workspace: str = ""
    context_required: bool = False

    def href(self) -> str:
        return "pytestrunner-source:" + quote(json.dumps(self.__dict__, ensure_ascii=False), safe="")

    @classmethod
    def from_href(cls, href: str):
        if not href.startswith("pytestrunner-source:"):
            return None
        try:
            value = json.loads(unquote(href.partition(":")[2]))
            if (not isinstance(value, dict) or not isinstance(value.get("path"), str)
                    or not value["path"] or "\x00" in value["path"]
                    or type(value.get("line")) is not int or not 1 <= value["line"] <= 10_000_000
                    or type(value.get("column", 1)) is not int
                    or not 1 <= value.get("column", 1) <= 10_000_000
                    or not isinstance(value.get("workspace", ""), str)
                    or type(value.get("context_required", False)) is not bool):
                return None
            return cls(**value)
        except (ValueError, TypeError):
            return None


_PYTHON = re.compile(r'\bFile ["\'](?P<path>[^"\'\n]+)["\'], line (?P<line>[1-9]\d*)')
_PYTEST = re.compile(
    r'^(?:\s*(?:[E>]\s+)?)?(?P<path>(?:[A-Za-z]:)?[^:\n<>"\']+?\.[\w]+)'
    r':(?P<line>[1-9]\d*)(?::(?P<column>[1-9]\d*))?(?=[:\s]|$)')
_EVENT_PREFIX = re.compile(r'^(?:\d\d:\d\d:\d\d\s+)?\[(?:ERRORS|OUTPUT|COMMANDS|ACTIONS)\]\s+(?:\[[^\]\n]+\]\s+)?')
_ERROR_PREFIX = re.compile(r'^Error \d+ — ')


def references(line: str, workspace: str = "", context_required: bool = False):
    """Yield (start, end, location), retaining the original text for copying."""
    matches = list(_PYTHON.finditer(line))
    offset = 0
    if not matches:
        prefix = _EVENT_PREFIX.match(line)
        offset = prefix.end() if prefix else 0
        error = _ERROR_PREFIX.match(line[offset:])
        if error:
            offset += error.end()
        matches = list(_PYTEST.finditer(line[offset:]))
    for match in matches:
        path = match["path"].strip()
        if path.startswith("<") or path.endswith(">"):
            continue
        column = match.groupdict().get("column")
        location = TraceLocation(path, int(match["line"]), int(column or 1), workspace, context_required)
        yield offset + match.start("path"), offset + match.end("column" if column else "line"), location


def resolve_location(location: TraceLocation, workspace: str = "", nodeid: str = "") -> Path:
    raw = location.path
    if raw.startswith("file://"):
        uri = urlsplit(raw)
        raw = unquote(uri.path)
        if uri.netloc:
            raw = "//" + uri.netloc + raw
        elif os.name == "nt" and re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
    elif "://" in raw or raw.startswith("<"):
        raise SourceNavigationError("This trace does not refer to a local source file.")
    windows = PureWindowsPath(raw)
    if windows.drive and os.name != "nt":
        raise SourceNavigationError(f"This Windows path is not available on this computer:\n{raw}")
    path = Path(raw.replace("\\", "/"))
    root = location.workspace or workspace
    if path.is_absolute():
        candidates = [path]
    else:
        if not root or (location.context_required and not location.workspace):
            raise SourceNavigationError("The project for this relative reference is unknown.\n"
                                        "Right-click the link and use Locate file…")
        candidates = [Path(root) / path]
        if nodeid:
            selected = Path(root) / nodeid.partition("::")[0].replace("\\", "/")
            candidates.append(selected.parent / path)
    existing = list(dict.fromkeys(candidate.resolve() for candidate in candidates if candidate.is_file()))
    if len(existing) > 1:
        raise SourceNavigationError("This reference matches several files:\n"
                                    + "\n".join(str(path) for path in existing)
                                    + "\nRight-click the link and use Locate file…")
    if not existing:
        raise SourceNavigationError(f"Source file not found:\n{raw}\n"
                                    "It may have moved since this trace was recorded.\n"
                                    "Right-click the link and use Locate file…")
    return existing[0]


def _workspace_data(text: str):
    # VS Code workspace files accept JSON comments and trailing commas. Keep
    # quoted strings intact, including URLs and escaped Windows separators.
    text = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[1] if m[1] is not None else "\n" * m[0].count("\n"), text)
    text = re.sub(r'("(?:\\.|[^"\\])*")|,(\s*[}\]])',
                  lambda m: m[1] if m[1] is not None else m[2], text)
    return json.loads(text)


def project_for_file(path: Path, workspace: str = "", editor: str = "vscode") -> Path:
    """Find the dependency's own project, including a matching multi-root workspace."""
    fallback = None
    for parent in path.parents:
        if editor == "vscode":
            matches = []
            try:
                descriptors = list(parent.glob("*.code-workspace"))
            except OSError:
                descriptors = []
            for descriptor in descriptors:
                try:
                    data = _workspace_data(descriptor.read_text(encoding="utf-8-sig"))
                    if not isinstance(data, dict):
                        continue
                    for folder in data.get("folders", []):
                        root = (parent / folder["path"]).resolve()
                        if path.is_relative_to(root):
                            matches.append(descriptor)
                            break
                except (OSError, ValueError, TypeError, KeyError):
                    continue
            if len(matches) == 1:
                return matches[0]
        if fallback is None and ((parent / ".git").exists() or (parent / ".idea").is_dir()
                or any((parent / name).is_file() for name in ("pyproject.toml", "setup.py", "setup.cfg"))
                or (workspace and parent == Path(workspace).resolve())):
            fallback = parent
            if editor != "vscode":
                return fallback
    return fallback or (Path(workspace).resolve() if workspace and path.is_relative_to(Path(workspace).resolve()) else path.parent)
