"""Instantane des caches du run ; aucune lecture de fichier dans le fil UI."""
import copy

from runner.domain.models import Status
from runner.domain.report_timing import valid_duration
from runner.version import __version__


def capture_report(window, report):
    reader = report.reader.index
    played = tuple(getattr(window, '_archive_run_nodeids', ()))
    profile = getattr(window, '_running_execution_profile', None)
    records = []
    if profile is not None:
        current = getattr(window, '_profile_count_statuses', {}) or {}
        for position, nodeid in enumerate(played):
            original = window.profile_run_tree.position(position)
            keys = sorted(window.profile_model.occurrence_keys(original),
                          key=lambda key: window.profile_model.locations[key][1])
            attempts = []
            for key in keys:
                attempt = window.profile_model.locations[key][1]
                status = current.get((original, attempt, reader))
                if status is None:
                    continue
                live = window._profile_live_details.get((key, reader), {})
                path = window._profile_logs.paths.get((key, reader)) if window._profile_logs else None
                duration = window.profile_model._durations.get(key, {}).get(reader)
                if not valid_duration(duration):
                    duration = live.get('duration')
                if not valid_duration(duration):
                    batch = window._profile_reports.get((key, reader))
                    duration = batch.durations.get(nodeid) if batch is not None else None
                attempts.append(dict(attempt=attempt, status=status.name,
                    duration=duration if valid_duration(duration) else None,
                    details=copy.deepcopy(list(live.get('records', {}).values())),
                    log_path=str(path) if path else ''))
            records.append(dict(position=position, nodeid=nodeid, attempts=attempts,
                                not_run=not attempts))
    else:
        statuses = getattr(window, '_archive_statuses_by_reader', {}).get(reader, {})
        for position, nodeid in enumerate(played):
            status = statuses.get(nodeid)
            attempts = [dict(attempt=0, status=status, duration=report.durations.get(nodeid))] if status else []
            records.append(dict(position=position, nodeid=nodeid, attempts=attempts, not_run=not attempts))
    atrs = getattr(window, '_archive_reader_atrs', {})
    request = getattr(window, '_archive_request', None)
    return dict(schema=1, occurrences=records,
                app_version=__version__, interpreter=request.interpreter if request else '',
                atr=atrs.get(report.reader.name, ''),
                commands=copy.deepcopy(report.commands), issues=list(report.issues),
                save_logs=getattr(window, '_archive_save_logs', True))
