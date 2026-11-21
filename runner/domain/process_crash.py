"""Identifier un arret natif sans le confondre avec un verdict pytest."""
import re
import signal

from runner.domain.ansi import strip_ansi


_WINDOWS = {
    0xC0000005: 'access violation',
    0xC000001D: 'illegal instruction',
    0xC00000FD: 'stack overflow',
    0xC0000409: 'stack buffer overrun / fast fail',
    0xC0000374: 'heap corruption',
    0xC0000094: 'integer division by zero',
    0xC0000096: 'privileged instruction',
    0x80000003: 'breakpoint',
}
_FATAL = re.compile(r'Windows fatal exception:\s*([^\r\n]+)|Fatal Python error:\s*([^\r\n]+)', re.I)
_WORKER = re.compile(r"worker\s+['\"]gw\d+['\"]\s+crashed|\[gw\d+\]\s+node down:\s*Not properly terminated", re.I)


def worker_crash(text):
    return bool(_WORKER.search(text or ''))


def native_crash(output, code):
    """Conserver la trace complete, y compris quand aucun XML n'a ete ecrit.

    Un faulthandler peut imprimer un diagnostic puis laisser le processus
    continuer : une sortie reussie n'est donc jamais declaree fatale ici.
    Les codes Windows peuvent etre signes ou non selon le lanceur.
    """
    if not code:
        return None
    text = strip_ansi(output or '')
    match = _FATAL.search(text)
    worker = _WORKER.search(text)
    unsigned = code & 0xffffffff
    known_windows = unsigned in _WINDOWS
    if known_windows:
        message = f'Windows fatal exception: {_WINDOWS[unsigned]} (0x{unsigned:08X}; exit code {code})'
    elif code in {-int(getattr(signal, name)) for name in
                  ('SIGSEGV', 'SIGABRT', 'SIGBUS', 'SIGILL', 'SIGFPE', 'SIGKILL', 'SIGTERM', 'SIGHUP')
                  if hasattr(signal, name)}:
        message = f'Python process terminated: {signal.Signals(-code).name} (exit code {code})'
    elif match:
        message = match.group(0).strip() + f' (exit code {code})'
    elif worker:
        message = f'Pytest worker process crashed (controller exit code {code})'
    elif (unsigned >= 0x80000000 and code > 255) or code < -255:
        message = f'Test process terminated abnormally (0x{unsigned:08X}; exit code {code})'
    elif code > 5:
        message = f'Test process terminated unexpectedly (exit code {code})'
    else:
        return None
    trace = text[match.start():].strip() if match else '\n'.join(text.splitlines()[-100:]).strip()
    return dict(message=message, body=message + ('\n\n' + trace if trace else ''),
                exit_code=code, native_code=known_windows or code not in (0, 1))
