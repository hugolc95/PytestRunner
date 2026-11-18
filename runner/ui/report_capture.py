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
    scope = getattr(window, '_archive_campaign', None)
    if profile is not None:
        current = getattr(window, '_profile_count_statuses', {}) or {}
        sequence = scope['sequence'] if scope else played
        selected = set(scope['selected']) if scope else set(range(len(sequence)))
        unavailable = set(scope['unavailable']) if scope else set()
        for position, nodeid in enumerate(sequence):
            original = position if scope else window.profile_run_tree.position(position)
            keys = sorted(window.profile_model.occurrence_keys(original),
                          key=lambda key: window.profile_model.locations[key][1])
            attempts = []
            for key in keys:
                attempt = window.profile_model.locations[key][1]
                status = current.get((original, attempt, reader)) if position in selected else None
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
                if not status.is_final:
                    attempts[-1]['status'] = 'NOTRUN'
                    attempts[-1]['duration'] = None
            unfinished = not attempts or attempts[-1]['status'] == 'NOTRUN'
            reason = ('Unavailable at launch' if position in unavailable else
                      'Not selected for this run' if position not in selected else 'Not reached before the run ended')
            if attempts and unfinished:
                reason = 'Stopped before this test finished'
            records.append(dict(position=position, nodeid=nodeid, attempts=attempts,
                                not_run=unfinished, reason=reason if unfinished else ''))
    else:
        statuses = getattr(window, '_archive_statuses_by_reader', {}).get(reader, {})
        for position, nodeid in enumerate(played):
            status = statuses.get(nodeid)
            attempts = [dict(attempt=0, status=status, duration=report.durations.get(nodeid))] if status else []
            records.append(dict(position=position, nodeid=nodeid, attempts=attempts, not_run=not attempts))
    atrs = getattr(window, '_archive_reader_atrs', {})
    request = getattr(window, '_archive_request', None)
    from runner.ui.campaign_archive import result as campaign_result
    coverage = campaign_result(window, reader)
    if coverage and getattr(report, 'cancelled', False):
        coverage.update(stopped=True, complete=False)
    return dict(schema=1, occurrences=records,
                coverage=coverage, campaign_profile=copy.deepcopy(scope['profile']) if scope else None,
                app_version=__version__, interpreter=request.interpreter if request else '',
                atr=atrs.get(report.reader.name, ''),
                commands=copy.deepcopy(report.commands), issues=list(report.issues),
                save_logs=getattr(window, '_archive_save_logs', True))
