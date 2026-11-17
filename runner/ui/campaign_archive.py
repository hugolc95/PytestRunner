"""Instantane du contenu de campagne au lancement, jamais reconstruit apres un edit."""
import copy
from dataclasses import asdict

from runner.domain.campaign_coverage import coverage


def begin(window, display_profile, selection):
    window._archive_campaign = None
    if display_profile is None:
        return
    saved = asdict(display_profile)
    config = getattr(window, '_archive_replay_profile', None) or {}
    for key in ('configuration_name', 'configuration_text'):
        if key in config:
            saved[key] = config[key]
    sequence = list(display_profile.sequence) * display_profile.execution.repetitions
    selected = list(selection.positions) if selection is not None else list(range(len(sequence)))
    available = set(window.model._by_nodeid)
    unavailable = [p for p, nodeid in enumerate(sequence) if nodeid not in available]
    window._archive_campaign = dict(profile=copy.deepcopy(saved), sequence=sequence,
        selected=selected, unavailable=unavailable, planned=len(sequence))


def result(window, reader):
    return coverage(getattr(window, '_archive_campaign', None), getattr(window, '_profile_count_statuses', None), reader)
