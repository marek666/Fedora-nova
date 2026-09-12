import sys
from pathlib import Path
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'core/scripts'))
import theme_hot_reload as hot


class FakeIdentity:
    theme = 'Fedora-Nova-Tech'
    address = 'unix:path=/tmp/fedora-nova-fake-bus'
    env = {'DBUS_SESSION_BUS_ADDRESS': address}

    def __init__(self):
        self.verified = 0

    def verify(self, **_kwargs):
        self.verified += 1

    def get_theme(self, **_kwargs):
        return self.theme


class ShellReloadBridgeTests(unittest.TestCase):
    def test_transaction_boundaries_toggle_user_theme_extension(self):
        identity = FakeIdentity()
        calls = []

        def run_checked(command, **_kwargs):
            calls.append(command)
            return '(true,)'

        with patch.object(hot, 'run_checked', side_effect=run_checked):
            hot.ShellIdentity.set_theme(identity, '')
            hot.ShellIdentity.set_theme(identity, identity.theme)

        self.assertEqual(len(calls), 2)
        self.assertIn('org.gnome.Shell.Extensions.DisableExtension', calls[0])
        self.assertIn('org.gnome.Shell.Extensions.EnableExtension', calls[1])
        for command in calls:
            self.assertIn('--address', command)
            self.assertIn(identity.address, command)
            self.assertIn('--dest', command)
            self.assertIn('org.gnome.Shell', command)
            self.assertIn('user-theme@gnome-shell-extensions.gcampax.github.com', command)
        self.assertGreaterEqual(identity.verified, 4)


if __name__ == '__main__':
    unittest.main()
