"""HubReader discovery runs in the test interpreter, never in the GUI process."""
import os

PROBE = '''
import json
from Reader.PyHubreader import pyHubReader
hub = pyHubReader()
method = getattr(hub, 'getReaderList', None) or hub.GetAllReaders
print('HUBREADERS_JSON:' + json.dumps(list(method()), ensure_ascii=True))
'''


# Le nom du lecteur arrive par `sys.argv[1]`, jamais colle dans le code : un
# nom saisi a la main peut contenir n'importe quoi.
#
# Tolerant sur l'API, comme PROBE : la signature de getAtr n'est pas figee --
# soit getAtr(lecteur), soit connexion au lecteur puis getAtr(). La connexion
# est relachee aussitot, pour ne pas garder la main sur un lecteur dont les
# tests auront besoin.
#
# Deux echecs a ne pas confondre : PyHubReader absent ou sans getAtr, c'est
# "unavailable" ; getAtr qui echoue ou ne rend rien sur CE lecteur, c'est qu'il
# n'y a pas de carte a lire -- "nocard".
PROBE_ATR = r'''
import json, sys

def out(**fields):
    print('HUBATR_JSON:' + json.dumps(fields, ensure_ascii=True))

def fail(state, exc):
    out(state=state, detail=f'{type(exc).__name__}: {exc}' if isinstance(exc, BaseException) else str(exc))
    raise SystemExit(0)

reader = sys.argv[1]
try:
    from Reader.PyHubreader import pyHubReader
    hub = pyHubReader()
except Exception as exc:
    fail('unavailable', exc)

def pick(*names):
    for name in names:
        method = getattr(hub, name, None)
        if callable(method):
            return method
    return None

get_atr = pick('getAtr', 'getATR', 'GetAtr', 'GetATR', 'get_atr')
if get_atr is None:
    fail('unavailable', 'PyHubReader has no getAtr method')

def read():
    try:
        return get_atr(reader)
    except TypeError:
        connect = pick('connect', 'Connect', 'selectReader', 'SelectReader', 'open', 'Open')
        if connect is None:
            raise
    connect(reader)
    try:
        return get_atr()
    finally:
        close = pick('disconnect', 'Disconnect', 'close', 'Close')
        if close is not None:
            try:
                close()
            except Exception:
                pass

try:
    atr = read()
except Exception as exc:
    fail('nocard', exc)

if isinstance(atr, (bytes, bytearray, list, tuple)):
    text = ' '.join(f'{int(b) & 0xFF:02X}' for b in atr)
else:
    text = str(atr or '').strip()
    compact = text.replace(' ', '')
    if compact and len(compact) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in compact):
        text = ' '.join(compact[i:i + 2] for i in range(0, len(compact), 2)).upper()
out(state='atr' if text else 'nocard', atr=text)
'''

ATR_OK, ATR_NO_CARD, ATR_UNAVAILABLE = "atr", "nocard", "unavailable"


def parse_atr_output(output: str, errors: str = "") -> tuple[str, str, str]:
    """(etat, ATR, detail) depuis la sortie de PROBE_ATR.

    Une sortie illisible -- interpreteur qui plante avant meme d'afficher quoi
    que ce soit -- ne dit rien de la carte : "unavailable", pas "nocard".
    """
    import json
    for line in output.splitlines():
        if not line.startswith("HUBATR_JSON:"):
            continue
        try:
            data = json.loads(line.split(":", 1)[1])
        except ValueError:
            break
        state = data.get("state")
        if state in (ATR_OK, ATR_NO_CARD, ATR_UNAVAILABLE):
            return state, str(data.get("atr") or ""), str(data.get("detail") or "")
        break
    detail = errors.strip().splitlines()[-1] if errors.strip() else "No valid response from HubReader."
    return ATR_UNAVAILABLE, "", detail


def discovery_environment():
    env = dict(os.environ)
    paths = [env.get('PYTHONPATH', '')]
    if os.name == 'nt':
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    paths.append(winreg.QueryValueEx(handle, 'PYTHONPATH')[0])
            except OSError:
                pass
    env['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(
        os.path.expandvars(part) for value in paths for part in value.split(os.pathsep) if part))
    return env
