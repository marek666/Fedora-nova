"""Session autostart binding; temporary runtimes and HOME, no host GNOME calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
STALE = {
    "FEDORA_NOVA_APP_DIR": "/old", "FEDORA_NOVA_CORE": "/old",
    "FEDORA_NOVA_CLI": "/old/nova",
}
PROBE = f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
output = Path(os.environ["PROBE_OUTPUT"])
pending = output.with_suffix(".pending")
pending.write_text(json.dumps({{
    "file": __file__, "args": sys.argv[1:],
    "env": {{k: os.environ[k] for k in {list(STALE)!r} if k in os.environ}},
}}))
pending.replace(output)
'''
GIO_LAUNCH = '''
from gi.repository import Gio
from pathlib import Path
import sys, time
app = Gio.DesktopAppInfo.new_from_filename(sys.argv[1])
assert app is not None, "Desktop entry could not be parsed"
assert app.launch([], None), "Desktop entry could not be launched"
for _ in range(250):
    if Path(sys.argv[2]).exists():
        break
    time.sleep(0.02)
else:
    raise AssertionError("Session launcher did not execute the bound CLI")
'''


class SessionRestoreBinding(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-session-binding-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.fake = self.root / "fake-bin"
        self.fake.mkdir()
        self.output = self.root / "probe.json"
        self.env = {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "user config"),
            "XDG_DATA_HOME": str(self.home / "data"),
            "XDG_STATE_HOME": str(self.home / "state"),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "XDG_RUNTIME_DIR": str(self.home / "run"),
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(self.root / "no-bus"),
            "PATH": str(self.fake) + os.pathsep + os.defpath,
            "PROBE_OUTPUT": str(self.output), "PYTHONDONTWRITEBYTECODE": "1",
            "FEDORA_NOVA_SESSION_DELAY": "0", **STALE,
        }
        for name in ["fedora-nova", "gsettings", "dconf", "gnome-extensions", "sudo"]:
            self.put(self.fake / name,
                     '#!/bin/sh\nprintf unexpected > "$HOME/unexpected-command"\nexit 97\n')
        self.put(self.fake / "sleep", '#!/bin/sh\nprintf "%s" "$1" > "$HOME/delay"\n')

    @property
    def config(self):
        return Path(self.env.get("XDG_CONFIG_HOME", str(self.home / ".config")))

    @property
    def launcher(self):
        return self.config / "fedora-nova/session-restore"

    @property
    def desktop(self):
        return self.config / "autostart/fedora-nova-session.desktop"

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)
        return path

    def make_core(self, path):
        for name in ["nova", "scripts/lib.sh", "scripts/session-restore.sh"]:
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / name, target)
        # A real direct core invocation can read this probe without applying GNOME settings.
        self.put(path / "scripts/apply-settings.sh", PROBE)
        return path

    def make_package(self, prefix=None):
        prefix = prefix or self.root / "package prefix"
        core = self.make_core(prefix / "share/fedora-nova/core")
        (core.parent / "fedora_nova").mkdir()
        cli = self.put(prefix / "bin/fedora-nova", PROBE)
        return core, cli

    def run_command(self, command, success=True, env=None):
        result = subprocess.run([str(arg) for arg in command], env=env or self.env,
                                cwd=self.home, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "unexpected-command").exists())
        return result

    def action(self, core, action="enable", success=True):
        return self.run_command([core / "scripts/session-restore.sh", action], success)

    def run_launcher(self, expected, desktop=False):
        self.output.unlink(missing_ok=True)
        if desktop:
            self.run_command([sys.executable, "-c", GIO_LAUNCH, self.desktop, self.output])
        else:
            self.run_command([self.launcher])
        result = json.loads(self.output.read_text())
        self.assertEqual(result["file"], str(expected))
        self.assertEqual(result["args"], ["session-restore", "--quiet"])
        self.assertEqual(result["env"], {})
        self.assertEqual((self.home / "delay").read_text(), "0")

    def snapshot(self):
        return {str(p.relative_to(self.config)): (p.read_bytes(), p.stat().st_mode,
                                                 p.stat().st_mtime_ns)
                for p in self.config.rglob("*") if p.is_file()}

    def test_package_prefers_same_prefix_and_ignores_path_and_stale_env(self):
        core, cli = self.make_package()
        self.action(core)
        self.run_launcher(cli)
        text = self.launcher.read_text()
        self.assertNotIn("/old", text)
        self.assertNotIn("export FEDORA_NOVA_", text)
        self.assertNotIn("command -v", text)
        self.assertIn('sleep "${FEDORA_NOVA_SESSION_DELAY:-2}"', text)
        self.assertIn("session-restore --quiet", text)
        for entry in ["Type=Application", "Name=Fedora Nova Session Restore",
                      "OnlyShowIn=GNOME;", "X-GNOME-Autostart-enabled=true", "NoDisplay=true"]:
            self.assertIn(entry, self.desktop.read_text().splitlines())

    def test_package_missing_or_nonexecutable_wrapper_falls_back_to_physical_core(self):
        core, cli = self.make_package()
        self.put(core / "nova", PROBE)
        for missing in [False, True]:
            with self.subTest(missing=missing):
                if missing:
                    cli.unlink()
                else:
                    cli.chmod(0o644)
                self.action(core)
                self.run_launcher(core / "nova")

    def test_standalone_and_source_bind_physical_cli(self):
        for suffix in ["data/fedora-nova", "source/core"]:
            with self.subTest(layout=suffix):
                core = self.make_core(self.root / suffix)
                self.put(core / "nova", PROBE)
                self.action(core)
                self.run_launcher(core / "nova")

    def test_actual_source_checkout_cli(self):
        self.action(REPO / "core")
        # A system profile makes the real CLI safely skip all GNOME operations.
        (self.config / "fedora-nova/current-profile").write_text("system\n")
        self.run_command([self.launcher])
        log = Path(self.env["XDG_STATE_HOME"]) / "fedora-nova/session-restore.log"
        self.assertIn("systémový profil", log.read_text())
        self.assertIn(str(REPO / "core/nova"), self.launcher.read_text())

    def test_real_direct_cli_derives_current_runtime_after_unsetting_stale_env(self):
        core = self.make_core(self.root / "direct core")
        self.action(core)
        self.run_command([self.launcher])
        result = json.loads(self.output.read_text())
        self.assertEqual(result["file"], str(core / "scripts/apply-settings.sh"))
        self.assertEqual(result["args"], ["tech", "--session-restore"])
        self.assertEqual(result["env"], {})

    def test_package_marker_and_standard_physical_layout_are_required(self):
        core, cli = self.make_package()
        (core.parent / "fedora_nova").rmdir()
        self.put(core / "nova", PROBE)
        self.action(core)
        self.run_launcher(core / "nova")
        other = self.make_core(self.root / "nonstandard/fedora-nova/core")
        (other.parent / "fedora_nova").mkdir()
        self.put(self.root / "nonstandard/bin/fedora-nova", PROBE)
        self.put(other / "nova", PROBE)
        self.action(other)
        self.run_launcher(other / "nova")

    def test_symlinked_runtime_uses_physical_package_prefix(self):
        core, cli = self.make_package()
        alias = self.root / "alias/share/fedora-nova/core"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(core, target_is_directory=True)
        self.put(self.root / "alias/bin/fedora-nova", PROBE)
        self.action(alias)
        self.run_launcher(cli)

    def test_unusable_runtime_fails_without_creating_autostart(self):
        core, cli = self.make_package()
        cli.unlink()
        (core / "nova").chmod(0o644)
        result = self.action(core, success=False)
        self.assertIn("CLI není spustitelné", result.stderr)
        self.assertFalse(self.config.exists())
        (core / "nova").unlink()
        self.action(core, success=False)
        self.assertFalse(self.config.exists())

    def test_failed_regeneration_preserves_existing_files(self):
        core, cli = self.make_package()
        self.action(core)
        before = self.snapshot()
        cli.unlink()
        (core / "nova").chmod(0o644)
        self.action(core, success=False)
        self.assertEqual(self.snapshot(), before)

    def test_desktop_exec_launches_with_spaces_and_reserved_characters(self):
        core, cli = self.make_package()
        for suffix in ["space dir", 'quotes " \' dollar $ backtick ` slash \\ ; & ()',
                       "percent %f %",
                       "tab\tand\nnewline", "equal=sign"]:
            with self.subTest(path=suffix):
                self.env["XDG_CONFIG_HOME"] = str(self.home / suffix)
                self.action(core)
                self.run_launcher(cli, desktop=True)

    def test_desktop_exec_with_home_default_config(self):
        self.env.pop("XDG_CONFIG_HOME")
        core, cli = self.make_package()
        self.action(core)
        self.run_launcher(cli, desktop=True)

    def test_shell_special_runtime_path_and_arguments(self):
        prefix = self.root / 'prefix " \' $HOME $(exit 96) `exit 95` ; & * ? \\ %'
        core, cli = self.make_package(prefix)
        self.action(core)
        self.run_launcher(cli)
        cli.unlink()
        self.put(core / "nova", PROBE)
        self.action(core)
        self.run_launcher(core / "nova")

    def test_enable_regenerates_both_files_for_new_runtime(self):
        core, cli = self.make_package(self.root / "OLD")
        self.action(core)
        self.run_launcher(cli)
        self.desktop.write_text("OLD desktop\n")
        new_core, new_cli = self.make_package(self.root / "NEW")
        self.action(new_core)
        self.run_launcher(new_cli, desktop=True)
        self.assertNotIn("OLD", self.launcher.read_text())
        self.assertNotIn("OLD", self.desktop.read_text())
        self.assertEqual(len(self.snapshot()), 2)

    def test_disable_only_removes_managed_files_and_is_idempotent(self):
        core, _ = self.make_package()
        self.action(core)
        other = self.put(self.config / "autostart/unrelated.desktop", "preserve\n")
        profile = self.put(self.config / "fedora-nova/current-profile", "system\n")
        self.action(core, "disable")
        self.action(core, "disable")
        self.assertFalse(self.launcher.exists())
        self.assertFalse(self.desktop.exists())
        self.assertEqual(other.read_text(), "preserve\n")
        self.assertEqual(profile.read_text(), "system\n")

    def test_status_is_read_only_with_and_without_autostart(self):
        core, _ = self.make_package()
        self.assertIn("Autostart:  no", self.action(core, "status").stdout)
        self.assertFalse(self.config.exists())
        self.action(core)
        before = self.snapshot()
        self.assertIn("Autostart:  yes", self.action(core, "status").stdout)
        self.assertEqual(self.snapshot(), before)

    def test_session_delay_default_and_override(self):
        core, cli = self.make_package()
        self.action(core)
        for delay in [None, "0.125"]:
            with self.subTest(delay=delay):
                env = dict(self.env)
                if delay is None:
                    env.pop("FEDORA_NOVA_SESSION_DELAY")
                else:
                    env["FEDORA_NOVA_SESSION_DELAY"] = delay
                self.run_command([self.launcher], env=env)
                self.assertEqual((self.home / "delay").read_text(), delay or "2")
                self.assertEqual(json.loads(self.output.read_text())["file"], str(cli))

    @unittest.skipUnless(shutil.which("meson"), "Meson is required for package staging")
    def test_staged_package_cli_enable_binds_same_prefix(self):
        # Own build and DESTDIR: never mutate the package CLI suite's staging.
        prefix = self.root / "installed prefix"
        build = self.root / "meson-build"
        stage = self.root / "stage"
        for command in [
            ["meson", "setup", build, REPO, "--prefix=" + str(prefix), "-Dproduction_app=true"],
            ["meson", "compile", "-C", build],
            ["meson", "install", "-C", build, "--destdir", stage],
        ]:
            self.run_command(command)
        shutil.copytree(stage / prefix.relative_to("/"), prefix)
        cli = prefix / "bin/fedora-nova"
        core = prefix / "share/fedora-nova/core"
        self.run_command([cli, "session-restore", "enable"])
        # Keep the real canonical wrapper; probe its actual core dispatch.
        self.put(core / "nova", PROBE)
        self.run_command([self.launcher])
        result = json.loads(self.output.read_text())
        self.assertEqual(result["file"], str(core / "nova"))
        self.assertEqual(result["args"], ["session-restore", "--quiet"])
        self.assertEqual(result["env"], {
            "FEDORA_NOVA_APP_DIR": str(core), "FEDORA_NOVA_CORE": str(core),
            "FEDORA_NOVA_CLI": str(core / "nova"),
        })


if __name__ == "__main__":
    unittest.main()
