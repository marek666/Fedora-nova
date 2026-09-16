import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_ibus_portal', REPO / 'dev-tools/preview_ibus_portal.py')
portal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portal)


class PreviewIBusActivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='preview ibus ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        portal.prepare(self.root, 'fedora-nova-preview-test')
        self.config = self.root / 'session-runtime/ibus-portal-environment.json'
        self.bus = self.root / 'config/ibus/bus'
        self.bus.mkdir(parents=True)
        # Real paths can contain spaces; the D-Bus address escapes these bytes.
        self.address = 'unix:path=' + str(self.root / 'cache/ibus/socket').replace(' ', '%20')

    def test_override_and_startup_order(self):
        service = (self.root / 'data/dbus-1/services/org.freedesktop.portal.IBus.service').read_text()
        self.assertIn('Name=org.freedesktop.portal.IBus\n', service)
        self.assertIn('Exec=/usr/bin/python3 "', service)
        self.assertIn('--activate "', service)
        self.assertTrue((self.root / 'session-runtime/ibus-portal-wrapper.py').exists())
        script = (REPO / 'dev-shell-preview.sh').read_text()
        startup = script[script.index('start_shell() {'):]
        self.assertLess(startup.index('preview_ibus_portal.py'), startup.index('setsid dbus-run-session'))
        self.assertNotIn('start_preview_ibus_portal', script)

    def test_matching_pid_and_invalid_files(self):
        (self.bus / 'stale').write_text('IBUS_DAEMON_PID=99\nIBUS_ADDRESS=' + self.address)
        invalid = ['IBUS_DAEMON_PID=42\nIBUS_ADDRESS=unix:path=/host/ibus',
                   'IBUS_DAEMON_PID=42\nIBUS_ADDRESS=garbage',
                   'IBUS_DAEMON_PID=42\nIBUS_DAEMON_PID=42\nIBUS_ADDRESS=' + self.address,
                   'IBUS_ADDRESS=' + self.address]
        for content in invalid:
            (self.bus / 'candidate').write_text(content)
            self.assertIsNone(portal.address_for_pid(self.root / 'config', self.root / 'cache', 42))
        (self.bus / 'candidate').write_text('IBUS_ADDRESS=' + self.address + '\nIBUS_DAEMON_PID=42')
        self.assertEqual(portal.address_for_pid(self.root / 'config', self.root / 'cache', 42), self.address)

    def test_activation_restores_preview_paths_preserves_bus_and_execs(self):
        (self.bus / 'current').write_text('IBUS_DAEMON_PID=42\nIBUS_ADDRESS=' + self.address)
        inherited = {'HOME': '/host', 'XDG_CONFIG_HOME': '/host/config',
                     'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/nested/bus', 'DISPLAY': ':2',
                     'IBUS_ADDRESS': 'unix:path=/host/ibus', 'DBUS_STARTER_ADDRESS': 'bad',
                     'DBUS_STARTER_BUS_TYPE': 'session'}
        with patch.dict(os.environ, inherited, clear=True), patch.object(portal, 'owner_pid', return_value=42), \
                patch.object(portal.os, 'execv', side_effect=SystemExit(0)) as execute:
            with self.assertRaises(SystemExit):
                portal.activate(self.config)
            execute.assert_called_once_with('/usr/libexec/ibus-portal', ['/usr/libexec/ibus-portal'])
            for key, value in json.loads(self.config.read_text()).items():
                self.assertEqual(os.environ[key], value)
            self.assertEqual(os.environ['IBUS_ADDRESS'], self.address)
            self.assertEqual(os.environ['DISPLAY'], ':2')
            self.assertEqual(os.environ['DBUS_SESSION_BUS_ADDRESS'], 'unix:path=/nested/bus')
            self.assertNotIn('DBUS_STARTER_ADDRESS', os.environ)

    def test_missing_address_fails_once_without_exec(self):
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'nested'}), \
                patch.object(portal, 'owner_pid', return_value=42), \
                patch.object(portal.time, 'monotonic', side_effect=[0, 0, 4]), \
                patch.object(portal.time, 'sleep'), patch.object(portal.os, 'execv') as execute, \
                patch('builtins.print') as warning:
            self.assertEqual(portal.activate(self.config), 1)
            execute.assert_not_called()
            warning.assert_called_once()
