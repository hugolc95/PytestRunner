"""Ecriture hors du fil UI des donnees necessaires au rapport portable."""
from dataclasses import replace
import copy
import json
from pathlib import Path


def persist_analysis(entry, directory, *, log_index=None):
    from runner.domain.history import _sain
    data = copy.deepcopy(entry.analysis_data)
    data.setdefault('warnings', [])
    used = set()
    contents = {}
    for occurrence in data.get('occurrences', []):
        for attempt in occurrence.get('attempts', []):
            if not data.get('save_logs', True):
                attempt['log_notice'] = 'Complete logs were disabled in this profile at launch.'
            path = attempt.get('log_path')
            if not path and data.get('save_logs', True) and entry.build_number is not None and entry.log_root:
                from runner.domain.log_index import RunLogIndex
                try:
                    if log_index is None:
                        log_index = RunLogIndex(Path(entry.log_root), entry.build_number)
                    found = log_index.find(occurrence.get('nodeid', ''), entry.reader,
                                           excluded=used)
                    path = str(found) if found is not None else ''
                    attempt['log_path'] = path
                except OSError:
                    path = ''
            if path and data.get('save_logs', True):
                try:
                    resolved = Path(path).resolve()
                    # Un log partage reste partage : ne pas le presenter
                    # comme une capture exclusive d'une autre occurrence.
                    if resolved not in contents:
                        contents[resolved] = resolved.read_text(encoding='utf-8', errors='replace')
                    attempt['log'] = contents[resolved]
                    if resolved in used:
                        attempt['log_shared'] = True
                    used.add(resolved)
                except OSError as exc:
                    attempt['log_notice'] = f'Log unavailable at archive time: {exc}'
    path = Path(directory) / f'{_sain(entry.id)}_{_sain(entry.reader) or "no-reader"}.analysis.json'
    temporary = path.with_suffix('.tmp')
    try:
        # Ecrire par morceaux evite une enorme chaine JSON temporaire et une
        # longue phase de serialisation qui monopolise le GIL sur de gros logs.
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
        temporary.replace(path)
    except (OSError, ValueError, TypeError):
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        # L'historique leger doit subsister meme si ce fichier ne peut etre
        # ecrit. L'export signalera explicitement les donnees manquantes.
        return replace(entry, analysis_data=None)
    return replace(entry, analysis_file=str(path), analysis_data=None)


def read_analysis(entry):
    if entry.analysis_data is not None:
        return entry.analysis_data
    try:
        data = json.loads(Path(entry.analysis_file).read_text(encoding='utf-8')) if entry.analysis_file else {}
        return data if isinstance(data, dict) and data.get('schema') == 1 else {}
    except (OSError, ValueError, TypeError):
        return {}
