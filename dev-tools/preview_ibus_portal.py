#!/usr/bin/python3
"""Generate and run the private Preview IBus D-Bus activation wrapper."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote


def prepare(root, wayland):
    runtime = root / 'session-runtime'
    wrapper = runtime / 'ibus-portal-wrapper.py'
    config = runtime / 'ibus-portal-environment.json'
    paths = {'HOME': 'home', 'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data',
             'XDG_CACHE_HOME': 'cache', 'XDG_STATE_HOME': 'state',
             'XDG_RUNTIME_DIR': 'session-runtime'}
    environment = {key: str(root / value) for key, value in paths.items()}
    environment['WAYLAND_DISPLAY'] = wayland
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, wrapper)
    config.write_text(json.dumps(environment))
    config.chmod(0o600)
    services = root / 'data/dbus-1/services'
    services.mkdir(parents=True, exist_ok=True)
    def quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'
    (services / 'org.freedesktop.portal.IBus.service').write_text(
        '[D-BUS Service]\nName=org.freedesktop.portal.IBus\n'
        f'Exec=/usr/bin/python3 {quote(wrapper)} --activate {quote(config)}\n')


def owner_pid():
    # Bus-daemon queries never activate IBus. Resolve a unique owner first so
    # its PID cannot accidentally belong to a replacement well-known owner.
    def call(method, name):
        return subprocess.run(
            ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
             '--object-path', '/org/freedesktop/DBus', '--method',
             'org.freedesktop.DBus.' + method, name],
            capture_output=True, text=True, timeout=0.4, check=True).stdout
    if call('NameHasOwner', 'org.freedesktop.IBus').strip() != '(true,)':
        return None
    owner = re.fullmatch(r"\('(:[0-9.]+)',\)\s*", call('GetNameOwner', 'org.freedesktop.IBus'))
    if not owner:
        return None
    pid = re.fullmatch(r'\(uint32 ([0-9]+),\)\s*',
                       call('GetConnectionUnixProcessID', owner[1]))
    return int(pid[1]) if pid else None


def address_for_pid(config, cache, pid):
    directory = config / 'ibus/bus'
    if directory.is_symlink():
        return None
    for path in sorted(directory.glob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            values = {}
            for line in path.read_text().splitlines():
                key, sep, value = line.partition('=')
                if key in ('IBUS_ADDRESS', 'IBUS_DAEMON_PID') and sep:
                    if key in values:
                        raise ValueError('duplicate field')
                    values[key] = value
            if values.get('IBUS_DAEMON_PID') != str(pid):
                continue
            address = values.get('IBUS_ADDRESS', '')
            # Accept only the private Preview socket, never another bus/address.
            match = re.fullmatch(r'unix:path=([^,;\s]+)(?:,guid=[0-9a-fA-F]{32})?', address)
            if match and Path(unquote(match[1])).resolve().is_relative_to((cache / 'ibus').resolve()):
                return address
        except (OSError, UnicodeError, ValueError):
            continue
    return None


def activate(config):
    try:
        environment = json.loads(config.read_text())
        os.environ.update(environment)
        for key in ('IBUS_ADDRESS', 'DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE'):
            os.environ.pop(key, None)
        if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
            raise ValueError('missing nested bus')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                pid = owner_pid()
                address = address_for_pid(Path(environment['XDG_CONFIG_HOME']),
                                          Path(environment['XDG_CACHE_HOME']), pid) if pid else None
                if address and owner_pid() == pid:
                    os.environ['IBUS_ADDRESS'] = address
                    os.execv('/usr/libexec/ibus-portal', ['/usr/libexec/ibus-portal'])
            except (subprocess.SubprocessError, OSError):
                pass
            time.sleep(0.05)
    except (OSError, ValueError, KeyError):
        pass
    print('VAROVÁNÍ: Preview IBus portal nelze spustit: odpovídající Preview IBus adresa není dostupná.',
          file=sys.stderr)
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--wayland')
    parser.add_argument('--activate', type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.prepare.resolve(), args.wayland)
    elif args.activate:
        sys.exit(activate(args.activate))
    else:
        parser.error('choose --prepare or --activate')
