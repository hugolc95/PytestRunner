"""HubReader discovery runs in the test interpreter, never in the GUI process."""
import os

PROBE = '''
import json
from Reader.PyHubreader import pyHubReader
hub = pyHubReader()
method = getattr(hub, 'getReaderList', None) or hub.GetAllReaders
print('HUBREADERS_JSON:' + json.dumps(list(method()), ensure_ascii=True))
'''


# Surveillance de la carte du lecteur principal, dans l'interpreteur des
# tests (PyHubReader n'est utilisable que la).
#
# API de pyHubReader (SmartcardFramework, Reader/PyHubreader.py) : le lecteur
# se choisit a la construction (`readerName`) ; `IsCardPresent()` dit si une
# carte est la ; `OpenReader()` / `GetATR()` / `CloseReader()` lisent l'ATR.
# Tous les lecteurs ne sont pas vus par Windows (PC/SC) : seul PyHubReader
# sait les interroger.
#
# Un seul processus, qui reste ouvert : il demande `IsCardPresent()` toutes
# les `interval` secondes et ne lit l'ATR -- une fois -- que quand une carte
# apparait ; quand elle disparait, il le dit sans rien lire. Si
# `IsCardPresent()` echoue, il lit l'ATR une fois et s'arrete : il ne reste
# alors que le bouton de relecture.
#
# Il ecrit une ligne `HUBATR_JSON:` par changement. Le nom du lecteur arrive
# par `sys.argv[1]`, jamais colle dans le code. L'interface garde son stdin
# ouvert : quand elle se ferme -- ou plante -- ce stdin se ferme et le
# processus s'arrete, pour ne jamais laisser un orphelin interroger le lecteur.
PROBE_MONITOR = r'''
import json, os, sys, threading, time

def out(**fields):
    print('HUBATR_JSON:' + json.dumps(fields, ensure_ascii=True), flush=True)

def describe(exc):
    return f'{type(exc).__name__}: {exc}'

def watch_stdin():
    try:
        sys.stdin.read()
    finally:
        os._exit(0)

threading.Thread(target=watch_stdin, daemon=True).start()

reader, interval = sys.argv[1], float(sys.argv[2])
try:
    from Reader.PyHubreader import pyHubReader
    hub = pyHubReader(readerName=reader)
except Exception as exc:
    out(state='unavailable', detail=describe(exc))
    raise SystemExit(0)

def read_atr():
    # CloseReader toujours, meme en cas d'echec : les tests auront besoin
    # du lecteur.
    try:
        hub.OpenReader()
        atr = hub.GetATR()
    except Exception as exc:
        atr, error = None, exc
    else:
        error = None
    finally:
        try:
            hub.CloseReader()
        except Exception:
            pass
    if error is not None:
        return dict(state='nocard', detail=describe(error))
    if isinstance(atr, (bytes, bytearray, list, tuple)):
        text = ''.join(f'{int(b) & 0xFF:02X}' for b in atr)
    else:
        text = str(atr or '').replace(' ', '').upper()
    if not text:
        return dict(state='nocard', detail='The reader returned an empty ATR.')
    return dict(state='atr', atr=text)

last = None
while True:
    try:
        present = bool(hub.IsCardPresent())
    except Exception as exc:
        out(monitoring=False, presence_error=describe(exc), **read_atr())
        raise SystemExit(0)
    if present != last:
        last = present
        if present:
            out(**read_atr())
        else:
            out(state='nocard', detail='No card detected in the reader.')
    time.sleep(interval)
'''

ATR_OK, ATR_NO_CARD, ATR_UNAVAILABLE = "atr", "nocard", "unavailable"


def parse_atr_line(line: str):
    # (etat, ATR, detail, remarque) pour une ligne `HUBATR_JSON:`, sinon None.
    # La remarque signale une detection automatique impossible.
    import json
    if not line.startswith("HUBATR_JSON:"):
        return None
    try:
        data = json.loads(line.split(":", 1)[1])
    except ValueError:
        return None
    state = data.get("state")
    if state not in (ATR_OK, ATR_NO_CARD, ATR_UNAVAILABLE):
        return None
    note = ""
    if data.get("monitoring") is False:
        note = ("Automatic card detection is off for this reader (IsCardPresent failed: "
                f"{data.get('presence_error') or 'unknown error'}). "
                "Use the refresh button to read the card again.")
    return state, str(data.get("atr") or ""), str(data.get("detail") or ""), note


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
