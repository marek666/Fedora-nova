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
            if 'org.gnome.Shell.Extensions.GetExtensionInfo' in command:
                return "({'state': <1.0>},)"
            return '(true,)'

        with patch.object(hot, 'run_checked', side_effect=run_checked):
            hot.ShellIdentity.set_theme(identity, '')
            hot.ShellIdentity.set_theme(identity, identity.theme)

        self.assertEqual(len(calls), 3)
        self.assertIn('org.gnome.Shell.Extensions.DisableExtension', calls[1])
        self.assertIn('org.gnome.Shell.Extensions.EnableExtension', calls[2])
        for command in calls:
            self.assertIn('--address', command)
            self.assertIn(identity.address, command)
            self.assertIn('--dest', command)
            self.assertIn('org.gnome.Shell', command)
            self.assertIn('user-theme@gnome-shell-extensions.gcampax.github.com', command)
        self.assertGreaterEqual(identity.verified, 4)

    def test_user_disabled_theme_stays_disabled_including_rollback(self):
        identity = FakeIdentity()
        with patch.object(hot, 'run_checked', return_value="({'state': <2.0>},)") as run:
            hot.ShellIdentity.set_theme(identity, '')
            hot.ShellIdentity.set_theme(identity, identity.theme)
            hot.ShellIdentity.set_theme(identity, identity.theme, rollback=True)
        self.assertEqual(run.call_count, 1)
        self.assertIn('org.gnome.Shell.Extensions.GetExtensionInfo', run.call_args.args[0])

    def test_rejected_disable_raises_and_rollback_can_enable(self):
        identity = FakeIdentity()
        with patch.object(hot, 'run_checked', side_effect=["({'state': <1.0>},)", '(false,)', '(true,)']):
            with self.assertRaises(hot.HotReloadError):
                hot.ShellIdentity.set_theme(identity, '')
            hot.ShellIdentity.set_theme(identity, identity.theme, rollback=True)


if __name__ == '__main__':
    unittest.main()
