"""Bilan du perimetre prevu, distinct des seuls verdicts pytest recus."""


def coverage(scope, statuses, reader):
    if not scope:
        return {}
    selected = set(scope['selected'])
    latest = {}
    for (position, attempt, index), status in (statuses or {}).items():
        if index == reader and position in selected and (position not in latest or attempt >= latest[position][0]):
            latest[position] = attempt, status
    executed = sum(getattr(status, 'is_final', False) for _, status in latest.values())
    total = scope['planned']
    unavailable = len(scope['unavailable'])
    return dict(planned=total, selected=len(selected), executed=executed,
                unavailable=unavailable, not_selected=max(0, total - len(selected) - unavailable),
                not_completed=max(0, len(selected) - executed), complete=bool(total and executed == total))


def summary(values):
    values = [v for v in values if v]
    if not values or all(v.get('complete') for v in values):
        return ''
    executed = sum(v.get('executed', 0) for v in values)
    planned = sum(v.get('planned', 0) for v in values)
    unit = 'tests' if len(values) == 1 else 'test/reader checks'
    text = f'Campaign incomplete · {executed}/{planned} {unit} executed'
    for key, label, aggregate in (('unavailable', 'unavailable', max), ('not_selected', 'not selected', max), ('not_completed', 'not finished', sum)):
        count = aggregate(v.get(key, 0) for v in values)
        if count:
            text += f' · {count} {label}'
    return text
