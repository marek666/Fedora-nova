import os
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "core/scripts"))
import preview_settings as settings


class PreviewSettingsPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nova-preview-settings-")
        self.root = Path(self.tmp.name) / "preview"
        self.root.mkdir(mode=0o700)

    def tearDown(self):
        self.tmp.cleanup()

    def write_dconf(self, payload=b"nova-settings"):
        dconf = self.root / "config/dconf"
        dconf.mkdir(parents=True, exist_ok=True)
        (dconf / "user").write_bytes(payload)
        return dconf

    def test_save_restore_is_profile_scoped(self):
        self.write_dconf(b"tech-state")
        self.assertEqual(settings.save(self.root, "tech"), "saved")
        self.assertEqual((self.root / "persist/settings/tech/dconf/user").read_bytes(), b"tech-state")

        (self.root / "config").rename(self.root / "old-config")
        (self.root / "config").mkdir()
        self.assertEqual(settings.restore(self.root, "midnight"), "fresh")
        self.assertFalse((self.root / "config/dconf").exists())
        self.assertEqual(settings.restore(self.root, "tech"), "restored")
        self.assertEqual((self.root / "config/dconf/user").read_bytes(), b"tech-state")

    def test_save_current_uses_recorded_preview_profile(self):
        self.write_dconf(b"recorded-state")
        profile = self.root / "config/fedora-nova/current-profile"
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text("pulse\n", encoding="utf-8")
        self.assertEqual(settings.save_current(self.root), "saved")
        self.assertEqual((self.root / "persist/settings/pulse/dconf/user").read_bytes(), b"recorded-state")

    def test_nova_choices_and_custom_profiles_survive_rebuild(self):
        self.write_dconf()
        nova = self.root / 'config/fedora-nova'
        (nova / 'custom-profiles').mkdir(parents=True)
        choices = {'current-profile': 'tech', 'current-curve': 'classic',
                   'current-hover': 'none', 'current-icons': 'system', 'current-gtk': 'off',
                   'custom-profiles/personal.json': '{"title": "Personal"}'}
        for name, value in choices.items():
            (nova / name).write_text(value)
        self.assertEqual(settings.save_current(self.root), 'saved')
        shutil.rmtree(self.root / 'config')
        self.assertEqual(settings.restore(self.root, 'tech'), 'restored')
        for name, value in choices.items():
            self.assertEqual((nova / name).read_text(), value)

    def test_nova_only_snapshot_still_needs_gnome_defaults(self):
        nova = self.root / 'config/fedora-nova'
        nova.mkdir(parents=True)
        (nova / 'current-hover').write_text('none')
        settings.save(self.root, 'tech')
        shutil.rmtree(self.root / 'config')
        self.assertEqual(settings.restore(self.root, 'tech'), 'fresh')
        self.assertEqual((nova / 'current-hover').read_text(), 'none')

    def test_linked_persisted_profile_is_rejected(self):
        outside = Path(self.tmp.name) / 'outside'
        (outside / 'dconf').mkdir(parents=True)
        (outside / 'dconf/user').write_bytes(b'outside')
        persist = self.root / 'persist/settings'
        persist.mkdir(parents=True)
        (persist / 'tech').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(settings.PreviewSettingsError):
            settings.restore(self.root, 'tech')
        self.assertFalse((self.root / 'config').exists())

    def test_reset_only_removes_requested_profile(self):
        for profile, value in (("tech", b"a"), ("clean", b"b")):
            self.write_dconf(value)
            settings.save(self.root, profile)
        self.assertEqual(settings.reset(self.root, "tech"), "reset")
        self.assertFalse((self.root / "persist/settings/tech").exists())
        self.assertTrue((self.root / "persist/settings/clean/dconf/user").is_file())

    def test_symlinks_are_rejected(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "user").write_bytes(b"outside")
        dconf = self.root / "config/dconf"
        dconf.parent.mkdir(parents=True)
        dconf.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(settings.PreviewSettingsError):
            settings.save(self.root, "tech")

    def test_invalid_profile_is_rejected(self):
        self.write_dconf()
        for profile in ("../host", "", "tech/other", " tech"):
            with self.subTest(profile=profile), self.assertRaises(settings.PreviewSettingsError):
                settings.save(self.root, profile)


if __name__ == "__main__":
    unittest.main()

class ShellPreviewPersistenceWiring(unittest.TestCase):
    def setUp(self):
        self.script = (REPO / 'dev-shell-preview.sh').read_text(encoding='utf-8')

    def test_preview_script_exposes_reset_and_persistence(self):
        self.assertIn('--reset-settings', self.script)
        self.assertIn('preview_settings.py', self.script)
        self.assertIn('save-current --preview-root "$PREVIEW_ROOT"', self.script)
        self.assertIn('restore --preview-root "$PREVIEW_ROOT" --profile "$PROFILE"', self.script)
        self.assertIn('NOVA_PREVIEW_RESTORE_SETTINGS', self.script)

    def test_restored_session_does_not_reseed_user_preferences(self):
        guard = 'if [[ "${NOVA_PREVIEW_RESTORE_SETTINGS:-0}" != "1" ]]; then'
        self.assertIn(guard, self.script)
        start = self.script.index(guard)
        end = self.script.index('\nfi\n\nif gsettings writable org.gnome.shell welcome-dialog-last-shown-version', start)
        guarded = self.script[start:end]
        self.assertIn('org.gnome.desktop.interface accent-color', guarded)
        self.assertIn('org.gnome.mutter dynamic-workspaces', guarded)
        self.assertIn('org.gnome.shell.extensions.dash-to-dock dock-position', guarded)
        self.assertIn('org.gnome.shell enabled-extensions', guarded)
        after = self.script[end:]
        self.assertNotIn('org.gnome.shell enabled-extensions', after)
        self.assertIn('org.gnome.shell.extensions.user-theme name', after)


@unittest.skipUnless(os.environ.get('NOVA_LIFECYCLE_TESTS') == '1', 'opt-in private D-Bus/dconf test')
class RealDconfPersistence(unittest.TestCase):
    def test_settings_and_extension_choices_survive_actual_session_startup(self):
        with tempfile.TemporaryDirectory(prefix='nova-dconf-test-') as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            nova = root / 'config/fedora-nova'
            nova.mkdir(parents=True)
            (nova / 'current-profile').write_text('tech')
            (nova / 'current-hover').write_text('none')
            env = {**os.environ, 'HOME': str(root / 'home'),
                   'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_RUNTIME_DIR': str(runtime),
                   'GSETTINGS_BACKEND': 'dconf', 'NOVA_PREVIEW_RESTORE_SETTINGS': '1',
                   'NOVA_PREVIEW_SHELL_PID_FILE': str(root / 'shell.pid'),
                   'NOVA_PREVIEW_THEME': 'Fedora-Nova-Tech',
                   'NOVA_PREVIEW_EXTENSIONS': "['user-theme@gnome-shell-extensions.gcampax.github.com']"}
            def session(script):
                result = subprocess.run(['dbus-run-session', '--', 'bash', '-ec', script],
                                        env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            session('gsettings set org.gnome.mutter dynamic-workspaces false\n'
                    'gsettings set org.gnome.shell.extensions.dash-to-dock dock-position LEFT\n'
                    'gsettings set org.gnome.shell.extensions.dash-to-dock dash-max-icon-size 64\n'
                    'gsettings set org.gnome.shell enabled-extensions "[]"')
            self.assertEqual(settings.save_current(root), 'saved')
            shutil.rmtree(root / 'config')
            self.assertEqual(settings.restore(root, 'tech'), 'restored')
            script = (REPO / 'dev-shell-preview.sh').read_text()
            startup = script.split("SESSION_SCRIPT='\n", 1)[1].split("\n'\n", 1)[0]
            self.assertTrue(startup.endswith('exec gnome-shell --devkit --wayland'))
            startup = startup.removesuffix('exec gnome-shell --devkit --wayland')
            result = session(startup + '\n'
                             'gsettings get org.gnome.mutter dynamic-workspaces\n'
                             'gsettings get org.gnome.shell.extensions.dash-to-dock dock-position\n'
                             'gsettings get org.gnome.shell.extensions.dash-to-dock dash-max-icon-size\n'
                             'gsettings get org.gnome.shell enabled-extensions')
            self.assertEqual(result.splitlines(), ['false', "'LEFT'", '64', '@as []'])
            self.assertEqual((nova / 'current-hover').read_text(), 'none')
