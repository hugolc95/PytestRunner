"""Les erreurs de collecte ne sont pas des verdicts de tests executes."""


def summary(errors):
    if '__collection__' in errors:
        return 'Collection failed'
    count = len(errors)
    return f"{count} file{'s' if count != 1 else ''} not collected" if count else ''


def details(errors):
    return '\n\n'.join(f"{item.get('location') or path}\n{item.get('body') or item.get('message', '')}"
                       for path, item in errors.items())
