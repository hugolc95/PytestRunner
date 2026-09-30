"""HubReader discovery runs in the test interpreter, never in the GUI process."""
import os

PROBE = '''
import json
from Reader.PyHubreader import pyHubReader
hub = pyHubReader()
method = getattr(hub, 'getReaderList', None) or hub.GetAllReaders
print('HUBREADERS_JSON:' + json.dumps(list(method()), ensure_ascii=True))
'''


# API de pyHubReader (SmartcardFramework, Reader/PyHubreader.py) : le lecteur
# se choisit a la construction (`readerName`), `OpenReader()` s'y connecte,
# `GetATR()` rend l'ATR en `bytes` -- ou leve s'il n'y a pas de connexion ou pas
# de carte -- et `CloseReader()` relache la connexion, aussitot : les tests
# auront besoin du lecteur.
#
# Le nom du lecteur arrive par `sys.argv[1]`, jamais colle dans le code : un
# nom saisi a la main peut contenir n'importe quoi.
#
# Deux echecs a ne pas confondre : PyHubReader absent ou inutilisable, c'est
# "unavailable" ; l'ouverture ou la lecture qui echoue sur CE lecteur, ou un ATR
# vide, c'est qu'il n'y a pas de carte a lire -- "nocard". La valeur rendue par
# `OpenReader()` n'est pas interpretee : une connexion ratee fait lever
# `GetATR()`, ce qui dit la meme chose sans supposer de convention.
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
    hub = pyHubReader(readerName=reader)
except Exception as exc:
    fail('unavailable', exc)

try:
    hub.OpenReader()
    atr = hub.GetATR()
except Exception as exc:
    atr, erreur = None, exc
else:
    erreur = None
finally:
    try:
        hub.CloseReader()
    except Exception:
        pass
if erreur is not None:
    fail('nocard', erreur)

if isinstance(atr, (bytes, bytearray, list, tuple)):
    text = ''.join(f'{int(b) & 0xFF:02X}' for b in atr)
else:
    text = str(atr or '').replace(' ', '').upper()
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
