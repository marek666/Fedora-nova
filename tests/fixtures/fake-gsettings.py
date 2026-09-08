#!/usr/bin/python3
import ast
import json
import os
from pathlib import Path
import sys
import time

args = sys.argv[1:]
if len(args) < 3 or args[1:3] != ['org.gnome.shell.extensions.user-theme', 'name']:
    raise SystemExit(0)
root = Path(os.environ['NOVA_TEST_DIR'])
state = root / 'theme-setting.json'
current = json.loads(state.read_text()) if state.exists() else os.environ.get('NOVA_PREVIEW_THEME', 'Fedora-Nova-Tech')
if args[0] == 'get':
    print(repr(current))
    raise SystemExit(0)
try:
    value = ast.literal_eval(args[3])
except (SyntaxError, ValueError):
    value = args[3]
with (root / 'calls.jsonl').open('a') as log:
    log.write(json.dumps({'value': value, 'bus': os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'pid': os.getpid()}) + '\n')
state.write_text(json.dumps(value))
phase = 'restored' if value else 'unloaded'
(root / phase).touch()
while (root / ('pause-' + phase)).exists():
    time.sleep(.02)
