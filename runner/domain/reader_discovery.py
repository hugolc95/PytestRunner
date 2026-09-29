"""HubReader discovery runs in the test interpreter, never in the GUI process."""
import os

PROBE = '''
import json
from Reader.PyHubreader import pyHubReader
hub = pyHubReader()
method = getattr(hub, 'getReaderList', None) or hub.GetAllReaders
print('HUBREADERS_JSON:' + json.dumps(list(method()), ensure_ascii=True))
'''


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
