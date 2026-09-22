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
        end = self.script.index('\nfi\n\n# This experimental extension', start)
        guarded = self.script[start:end]
        self.assertIn('org.gnome.desktop.interface accent-color', guarded)
        self.assertIn('org.gnome.mutter dynamic-workspaces', guarded)
        self.assertIn('org.gnome.shell.extensions.dash-to-dock dock-position', guarded)
        bms_settings_version = (
            'org.gnome.shell.extensions.blur-my-shell settings-version 2'
        )
        bms_dash_blur = (
            'org.gnome.shell.extensions.blur-my-shell.dash-to-dock blur false'
        )
        bms_panel_blur = (
            'org.gnome.shell.extensions.blur-my-shell.panel blur false'
        )
        extensions = 'gsettings set org.gnome.shell enabled-extensions'
        self.assertIn(bms_settings_version, guarded)
        self.assertIn(bms_dash_blur, guarded)
        self.assertIn(bms_panel_blur, guarded)
        self.assertLess(guarded.index(bms_settings_version), guarded.index(bms_dash_blur))
        self.assertLess(guarded.index(bms_dash_blur), guarded.index(extensions))
        self.assertLess(guarded.index(bms_panel_blur), guarded.index(extensions))
        self.assertIn('org.gnome.shell enabled-extensions', guarded)
        after = self.script[end:]
        self.assertNotIn(bms_panel_blur, after)
        self.assertNotIn('enabled-extensions "$NOVA_PREVIEW_EXTENSIONS"', after)
        self.assertIn('org.gnome.shell.extensions.user-theme name', after)

    def test_dbus_activated_apps_use_host_runtime_and_preview_wayland_bridge(self):
        shell_environment = self.script[self.script.index('export_preview_env() {'):
                                        self.script.index('\nprint_banner() {')]
        for assignment in (
            'export HOME="$PREVIEW_HOME"',
            'export XDG_CONFIG_HOME="$PREVIEW_CONFIG"',
            'export XDG_DATA_HOME="$PREVIEW_DATA"',
            'export XDG_CACHE_HOME="$PREVIEW_CACHE"',
            'export XDG_STATE_HOME="$PREVIEW_STATE"',
            'export XDG_RUNTIME_DIR="$PREVIEW_SESSION_RUNTIME"',
        ):
            self.assertIn(assignment, shell_environment)

        self.assertIn(
            'NOVA_PREVIEW_WAYLAND_NAME="fedora-nova-preview-${NOVA_PREVIEW_TOKEN:0:8}"',
            self.script)
        self.assertIn('PREVIEW_WAYLAND_SOCKET="$PREVIEW_SESSION_RUNTIME/$NOVA_PREVIEW_WAYLAND_NAME"',
                      self.script)
        self.assertIn('PREVIEW_WAYLAND_BRIDGE="$ORIGINAL_XDG_RUNTIME_DIR/$NOVA_PREVIEW_WAYLAND_NAME"',
                      self.script)
        self.assertIn(
            'exec gnome-shell --devkit --wayland --wayland-display="$NOVA_PREVIEW_WAYLAND_NAME"',
            self.script)

        start = self.script.index('set_dbus_activation_environment() {')
        end = self.script.index('\n\nexec gnome-shell --devkit --wayland --wayland-display=', start)
        activation_environment = self.script[start:end]
        self.assertIn('if ! set_dbus_activation_environment; then', activation_environment)
        self.assertNotIn('gdbus wait --session', activation_environment)
        self.assertNotIn('WAYLAND_DISPLAY="$NOVA_PREVIEW_SESSION_RUNTIME/wayland-0"',
                         activation_environment)
        self.assertEqual(activation_environment.count('set_dbus_activation_environment'), 2)
        for assignment in (
            'HOME="$NOVA_PREVIEW_HOST_HOME"',
            'XDG_CONFIG_HOME="$NOVA_PREVIEW_HOST_XDG_CONFIG_HOME"',
            'XDG_DATA_HOME="$NOVA_PREVIEW_HOST_XDG_DATA_HOME"',
            'XDG_CACHE_HOME="$NOVA_PREVIEW_HOST_XDG_CACHE_HOME"',
            'XDG_STATE_HOME="$NOVA_PREVIEW_HOST_XDG_STATE_HOME"',
            'XDG_DATA_DIRS="$NOVA_PREVIEW_HOST_XDG_DATA_DIRS"',
            'XDG_RUNTIME_DIR="$NOVA_PREVIEW_HOST_XDG_RUNTIME_DIR"',
            'WAYLAND_DISPLAY="$NOVA_PREVIEW_WAYLAND_NAME"',
        ):
            self.assertIn(assignment, activation_environment)
        activation_lines = activation_environment.splitlines()
        for forbidden in (
            'DBUS_SESSION_BUS_ADDRESS=',
            'DISPLAY=',
        ):
            self.assertFalse(any(line.lstrip().startswith(forbidden)
                                 for line in activation_lines))

        bridge_start = self.script.index('create_preview_wayland_bridge() {')
        bridge_end = self.script.index('\n\nprint_banner() {', bridge_start)
        bridge = self.script[bridge_start:bridge_end]
        self.assertIn('ln -s -- "$PREVIEW_WAYLAND_SOCKET" "$PREVIEW_WAYLAND_BRIDGE"', bridge)
        self.assertIn('create_preview_wayland_bridge || return $?', self.script)

        cleanup_start = self.script.index('cleanup_preview_wayland_bridge() {')
        cleanup_end = self.script.index('\n\nprocess_cmdline()', cleanup_start)
        cleanup = self.script[cleanup_start:cleanup_end]
        self.assertIn('actual_target="$(readlink -- "$bridge")"', cleanup)
        self.assertIn('[[ "$actual_target" == "$target" ]] || return 0', cleanup)
        self.assertIn('rm -f -- "$bridge"', cleanup)

    def test_preview_keyring_is_isolated_best_effort_and_starts_before_services(self):
        session_start = self.script.index("SESSION_SCRIPT='\n")
        keyring_start = self.script.index('preview_dbus_name_has_owner() {', session_start)
        keyring_end = self.script.index('\n\nstart_preview_gvfs() {', keyring_start)
        keyring = self.script[keyring_start:keyring_end]
        first_gsettings = self.script.index('gsettings set org.gnome.desktop.interface color-scheme',
                                            session_start)

        self.assertLess(keyring_start, first_gsettings)
        self.assertIn('mkdir -p "$NOVA_PREVIEW_KEYRING_CONTROL_DIR"', keyring)
        self.assertIn('chmod 700 "$NOVA_PREVIEW_KEYRING_CONTROL_DIR"', keyring)
        self.assertIn('>"$NOVA_PREVIEW_KEYRING_LOG" 2>&1 &', keyring)
        self.assertIn('--foreground', keyring)
        self.assertIn('--components=secrets', keyring)
        self.assertIn('--control-directory="$NOVA_PREVIEW_KEYRING_CONTROL_DIR"', keyring)
        self.assertNotIn('--start', keyring)
        self.assertNotIn('NOVA_PREVIEW_HOST_', keyring)
        self.assertNotIn('ORIGINAL_', keyring)

        for inherited in (
            'GNOME_KEYRING_CONTROL',
            'SSH_AUTH_SOCK',
            'DBUS_STARTER_ADDRESS',
            'DBUS_STARTER_BUS_TYPE',
        ):
            self.assertIn(f'-u {inherited}', keyring)
        for preview_value in (
            'HOME="$HOME"',
            'XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR"',
            'XDG_CONFIG_HOME="$XDG_CONFIG_HOME"',
            'XDG_DATA_HOME="$XDG_DATA_HOME"',
            'XDG_CACHE_HOME="$XDG_CACHE_HOME"',
            'XDG_STATE_HOME="$XDG_STATE_HOME"',
            'DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"',
        ):
            self.assertIn(preview_value, keyring)
        self.assertIn('org.freedesktop.DBus.NameHasOwner', keyring)
        self.assertIn('org.freedesktop.secrets', keyring)
        self.assertIn('for attempt in {1..40}; do', keyring)
        self.assertIn('Preview pokračuje bez Secret Service.', keyring)

        self.assertIn('setsid dbus-run-session -- env -u BASH_ENV -u ENV bash -c "$SESSION_SCRIPT" &',
                      self.script)
        self.assertNotIn('NOVA_PREVIEW_KEYRING_PID', self.script)

    def test_preview_gvfs_is_isolated_best_effort_and_precedes_host_activation(self):
        session_start = self.script.index("SESSION_SCRIPT='\n")
        gvfs_start = self.script.index('start_preview_gvfs() {', session_start)
        gvfs_end = self.script.index('\n\nstart_preview_localsearch() {', gvfs_start)
        gvfs = self.script[gvfs_start:gvfs_end]
        keyring_call = self.script.index('\nstart_preview_keyring\n', session_start)
        gvfs_call = self.script.index('\nstart_preview_gvfs\n', gvfs_start)
        first_gsettings = self.script.index('gsettings set org.gnome.desktop.interface color-scheme',
                                            session_start)
        activation_start = self.script.index('set_dbus_activation_environment() {', session_start)

        self.assertLess(keyring_call, gvfs_call)
        self.assertLess(gvfs_call, first_gsettings)
        self.assertLess(first_gsettings, activation_start)
        self.assertIn('/usr/libexec/gvfsd', gvfs)
        self.assertIn('GVFS_DISABLE_FUSE=1', gvfs)
        self.assertIn('>"$NOVA_PREVIEW_GVFS_LOG" 2>&1 &', gvfs)
        self.assertIn('org.gtk.vfs.Daemon', gvfs)
        self.assertIn('for attempt in {1..40}; do', gvfs)
        self.assertIn('Preview pokračuje bez vlastního GVFS.', gvfs)
        self.assertNotIn('gvfsd-fuse', gvfs)
        self.assertNotIn('/run/user/', gvfs)
        self.assertNotIn('NOVA_PREVIEW_HOST_', gvfs)
        self.assertNotIn('ORIGINAL_', gvfs)
        self.assertNotIn('NOVA_PREVIEW_GVFS_PID', self.script)

        for inherited in ('DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE'):
            self.assertIn(f'-u {inherited}', gvfs)
        for preview_value in (
            'HOME="$HOME"',
            'XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR"',
            'XDG_CONFIG_HOME="$XDG_CONFIG_HOME"',
            'XDG_DATA_HOME="$XDG_DATA_HOME"',
            'XDG_CACHE_HOME="$XDG_CACHE_HOME"',
            'XDG_STATE_HOME="$XDG_STATE_HOME"',
            'DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"',
        ):
            self.assertIn(preview_value, gvfs)

    def test_preview_localsearch_is_isolated_best_effort_and_precedes_host_activation(self):
        session_start = self.script.index("SESSION_SCRIPT='\n")
        localsearch_start = self.script.index('start_preview_localsearch() {', session_start)
        localsearch_end = self.script.index('\n\nstart_preview_localsearch\n\nif', localsearch_start)
        localsearch = self.script[localsearch_start:localsearch_end]
        gvfs_call = self.script.index('\nstart_preview_gvfs\n', session_start)
        localsearch_call = self.script.index('\nstart_preview_localsearch\n', localsearch_start)
        first_gsettings = self.script.index('gsettings set org.gnome.desktop.interface color-scheme',
                                            session_start)
        activation_start = self.script.index('set_dbus_activation_environment() {', session_start)

        self.assertLess(gvfs_call, localsearch_call)
        self.assertLess(localsearch_call, first_gsettings)
        self.assertLess(first_gsettings, activation_start)
        self.assertIn('/usr/libexec/localsearch-3', localsearch)
        self.assertIn('org.freedesktop.Tracker3.Miner.Files', localsearch)
        self.assertIn('>"$NOVA_PREVIEW_LOCALSEARCH_LOG" 2>&1 &', localsearch)
        self.assertIn('for attempt in {1..40}; do', localsearch)
        self.assertIn('Preview pokračuje bez vlastního LocalSearch.', localsearch)
        self.assertNotIn('org.freedesktop.systemd1', localsearch)
        self.assertNotIn('NOVA_PREVIEW_HOST_', localsearch)
        self.assertNotIn('ORIGINAL_', localsearch)
        self.assertNotIn('NOVA_PREVIEW_LOCALSEARCH_PID', self.script)

        for inherited in ('DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE'):
            self.assertIn(f'-u {inherited}', localsearch)
        for preview_value in (
            'HOME="$HOME"',
            'XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR"',
            'XDG_CONFIG_HOME="$XDG_CONFIG_HOME"',
            'XDG_DATA_HOME="$XDG_DATA_HOME"',
            'XDG_CACHE_HOME="$XDG_CACHE_HOME"',
            'XDG_STATE_HOME="$XDG_STATE_HOME"',
            'DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"',
        ):
            self.assertIn(preview_value, localsearch)



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
            shell_command = ('exec gnome-shell --devkit --wayland '
                             '--wayland-display="$NOVA_PREVIEW_WAYLAND_NAME"')
            self.assertTrue(startup.endswith(shell_command))
            startup = startup.removesuffix(shell_command)
            result = session(startup + '\n'
                             'gsettings get org.gnome.mutter dynamic-workspaces\n'
                             'gsettings get org.gnome.shell.extensions.dash-to-dock dock-position\n'
                             'gsettings get org.gnome.shell.extensions.dash-to-dock dash-max-icon-size\n'
                             'gsettings get org.gnome.shell enabled-extensions')
            self.assertEqual(result.splitlines(), ['false', "'LEFT'", '64', "['folder-layout-preview@fedora-nova']"])
            self.assertEqual((nova / 'current-hover').read_text(), 'none')
