"""Recherche des logs d'un build sans reparcourir le disque pour chaque test."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from runner.domain.logs import (MANIFESTE, PRIME_PARAMETRE, SUFFIXES,
                                _belongs_to_build, _obligatoires, cle,
                                nodeid_tokens, run_directories)


class RunLogIndex:
    """Cache limite a un archivage : jamais reutilise pendant un autre run."""

    def __init__(self, root: Path, build_number: int):
        self.root = Path(root).resolve()
        self.build_number = build_number
        self._manifest = None
        self._manifest_paths = {}
        self._zones = None
        self._directories = {}
        self._files = {}
        self._ranked = {}

    def _manifest_path(self, nodeid, reader):
        key = nodeid, reader
        if key in self._manifest_paths:
            return self._manifest_paths[key]
        path = self._read_manifest_path(nodeid, reader)
        self._manifest_paths[key] = path
        return path

    def _read_manifest_path(self, nodeid, reader):
        if self._manifest is None:
            try:
                table = json.loads((self.root / MANIFESTE).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                table = {}
            self._manifest = {str(key).replace('\\', '/').strip(): value
                              for key, value in table.items()} if isinstance(table, dict) else {}
        wanted = nodeid.replace('\\', '/').strip()
        value = self._manifest.get(wanted)
        if not value:
            value = next((value for key, value in self._manifest.items()
                          if key.endswith(wanted) or wanted.endswith(key)), None)
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        if (not _belongs_to_build(path, self.build_number)
                or (reader and cle(reader) not in {cle(p) for p in path.parts})):
            return None
        return path.resolve() if path.is_file() else None

    def _walk(self, directory):
        # Un dossier deja visite par une zone ou un autre lecteur ne provoque
        # aucune nouvelle lecture disque, meme lors du repli sur la racine.
        if directory not in self._directories:
            files, children = [], []
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        try:
                            path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                if (re.fullmatch(r'Run_\d+', entry.name, re.IGNORECASE)
                                        and not _belongs_to_build(path, self.build_number)):
                                    continue
                                children.append(path)
                            elif (path.suffix.lower() in SUFFIXES and entry.is_file()
                                  and _belongs_to_build(path, self.build_number)):
                                files.append((path, entry.stat().st_mtime))
                        except OSError:
                            continue
            except OSError:
                pass
            self._directories[directory] = files, children
        files, children = self._directories[directory]
        yield from files
        for child in children:
            yield from self._walk(child)

    def _candidates(self, zone):
        if zone not in self._files:
            records = []
            for path, modified in self._walk(zone):
                relative_path = path.relative_to(zone)
                relative = cle(str(relative_path))
                identity = re.sub(r'(?:_B\d+)?_\d{3,}$', '', path.stem,
                                  flags=re.IGNORECASE)
                parameters = tuple((cle(part[:match.start()]), cle(match.group(1)), part == path.name)
                    for part in relative_path.parts
                    if (match := re.search(r'\[(.*)\]', part)) is not None)
                records.append((path, modified, relative, cle(path.stem),
                                cle(identity), frozenset(cle(p) for p in path.parts), parameters))
            self._files[zone] = records
        return self._files[zone]

    def find(self, nodeid: str, reader: str = '', *, excluded=frozenset()):
        if not nodeid:
            return None
        manifest = self._manifest_path(nodeid, reader)
        if manifest is not None and manifest not in excluded:
            return manifest
        cache_key = nodeid, reader
        if cache_key not in self._ranked:
            tokens = nodeid_tokens(nodeid)
            required = _obligatoires(nodeid, tokens)
            if not required:
                return None
            searched = [cle(token) for token in tokens if cle(token)]
            parameter = cle(tokens[-1]) if nodeid.strip().endswith(']') else ''
            function = cle(tokens[-2]) if parameter else ''
            reader_key = cle(reader)
            if self._zones is None:
                self._zones = list(dict.fromkeys(
                    zone / f'Run_{self.build_number:04d}'
                    if (zone / f'Run_{self.build_number:04d}').is_dir() else zone
                    for zone in run_directories(self.root) + [self.root]
                    if not re.fullmatch(r'Run_\d+', zone.name, re.IGNORECASE)
                    or _belongs_to_build(zone, self.build_number)))
            ranked = []
            for zone in self._zones:
                matches = []
                for path, modified, relative, name, identity, parts, fields in self._candidates(zone):
                    if reader_key and reader_key not in parts:
                        continue
                    if any(token not in relative for token in required):
                        continue
                    parameters = {value for prefix, value, is_file in fields
                                  if function in prefix or (is_file and not prefix)} if parameter else set()
                    # [0] ne doit pas prendre [10], puis priver le dixieme
                    # cas de son log. Les crochets donnent ici une identite
                    # exacte, plus fiable que le rapprochement assaini.
                    if parameter and parameters and parameter not in parameters:
                        continue
                    score = sum(token in relative for token in searched)
                    score += sum(token in name for token in searched)
                    if parameter and (parameter in parameters or identity.endswith(parameter) or relative.endswith(parameter)):
                        score += PRIME_PARAMETRE
                    matches.append((score, modified, path))
                ranked.extend(path for _, _, path in sorted(matches, reverse=True))
            self._ranked[cache_key] = tuple(dict.fromkeys(ranked))
        return next((path for path in self._ranked[cache_key] if path not in excluded), None)
