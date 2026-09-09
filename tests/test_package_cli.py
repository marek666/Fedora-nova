"""Package CLI binding and packaging boundaries; no host GNOME operations."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_asset_install_boundaries as assets

REPO = Path(__file__).resolve().parents[1]
PROBE = f'''#!{sys.executable}
import json, os, sys
print(json.dumps(dict(file=__file__, args=sys.argv[1:], env={{
    k: v for k, v in os.environ.items() if k.startswith("FEDORA_NOVA_")
}})))
'''


@unittest.skipUnless(shutil.which("meson"), "Meson is required for package CLI tests")
class PackageCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(prefix="nova-package-cli-")
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        cls.prefixes = {}
        for production in [True, False]:
            name = "production" if production else "devel"
            prefix = cls.root / (name + " prefix")
            build = cls.root / (name + "-build")
            stage = cls.root / (name + "-stage")
            for command in [
                ["meson", "setup", str(build), str(REPO), "--prefix=" + str(prefix),
                 "-Dproduction_app=" + str(production).lower()],
                ["meson", "compile", "-C", str(build)],
                ["meson", "install", "-C", str(build), "--destdir", str(stage)],
            ]:
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode:
                    raise AssertionError(result.stdout + result.stderr)
            # Unpack DESTDIR staging into its configured temporary prefix, so
            # absolute package paths execute unchanged. Neither path is a host install.
            shutil.copytree(stage / prefix.relative_to("/"), prefix)
            cls.prefixes[production] = prefix

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-cli-home-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.prefix = self.prefixes[True]
        self.core = self.prefix / "share/fedora-nova/core"
        self.cli = self.prefix / "bin/fedora-nova"
        fake = self.home / "fake"
        fake.mkdir()
        for name in ["fedora-nova", "fedora-nova-settings", "nova", "gsettings", "dconf",
                     "gnome-extensions", "sudo"]:
            path = fake / name
            path.write_text("#!/bin/sh\necho unexpected-command >&2\nexit 97\n")
            path.chmod(0o755)
        self.env = {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_DATA_HOME": str(self.home / "data"),
            "XDG_STATE_HOME": str(self.home / "state"),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "PATH": str(fake) + os.pathsep + os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "FEDORA_NOVA_APP_DIR": "/stale", "FEDORA_NOVA_CORE": "/stale",
            "FEDORA_NOVA_CLI": "/stale/nova",
        }

    @contextmanager
    def replace_file(self, path, text):
        original = path.read_bytes()
        try:
            path.write_text(text)
            yield
        finally:
            path.write_bytes(original)

    def run_cli(self, *args):
        result = subprocess.run([str(self.cli), *args], env=self.env, cwd=self.home,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_production_and_devel_staging_boundary(self):
        for production, prefix in self.prefixes.items():
            for name, expected in [("fedora-nova", production),
                                   ("fedora-nova-settings", production),
                                   ("fedora-nova-settings-devel", True)]:
                with self.subTest(production=production, launcher=name):
                    path = prefix / "bin" / name
                    self.assertEqual(path.is_file(), expected)
                    if expected:
                        self.assertFalse(path.is_symlink())
                        self.assertTrue(os.access(path, os.X_OK))

    def test_real_packaged_version_ignores_stale_paths(self):
        self.assertEqual(self.run_cli("version"), "Fedora Nova 0.8.0-dev\n")

    def test_core_binding_environment_and_exact_arguments(self):
        args = ["status", "with spaces", "", "'quoted'", '"double"', "$HOME",
                "$(exit 99)", "`exit 99`", "a;b", "*", "line\nbreak", "--flag"]
        with self.replace_file(self.core / "nova", PROBE):
            result = json.loads(self.run_cli(*args))
        self.assertEqual(result["file"], str(self.core / "nova"))
        self.assertEqual(result["args"], args)
        self.assertEqual(result["env"], {
            "FEDORA_NOVA_APP_DIR": str(self.core),
            "FEDORA_NOVA_CORE": str(self.core),
            "FEDORA_NOVA_CLI": str(self.core / "nova"),
        })

    def test_profile_reads_packaged_config_not_stale_xdg(self):
        config = self.core / "config/profiles.json"
        packaged = json.loads(config.read_text())
        packaged["profiles"]["tech"]["title"] = "Packaged profile sentinel"
        stale = json.loads(config.read_text())
        stale["profiles"]["tech"]["title"] = "Stale profile sentinel"
        old = self.home / "data/fedora-nova/config/profiles.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps(stale))
        with self.replace_file(config, json.dumps(packaged)):
            result = self.run_cli("profile")
        self.assertIn("Packaged profile sentinel", result)
        self.assertNotIn("Stale profile sentinel", result)
        self.assertEqual(json.loads(old.read_text()), stale)
        self.assertFalse((self.home / "config").exists())

    def test_settings_selects_same_prefix(self):
        settings = self.prefix / "bin/fedora-nova-settings"
        args = ["with spaces", "", "$HOME;*", "line\nbreak"]
        with self.replace_file(settings, PROBE):
            result = json.loads(self.run_cli("settings", *args))
        self.assertEqual(result["file"], str(settings))
        self.assertEqual(result["args"], args)

    def test_control_alias_is_rejected(self):
        settings = self.prefix / "bin/fedora-nova-settings"
        with self.replace_file(settings, PROBE):
            result = subprocess.run([str(self.cli), "control"], env=self.env, cwd=self.home,
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Neznámý příkaz: control", result.stderr)
        self.assertNotIn('"file":', result.stdout)

    def test_runtime_assets_and_preset_preserve_package_cli(self):
        # Reuse the isolated, tiny asset fixture and its fake host commands.
        # Put the actual Meson-generated CLI at the potential collision path.
        fixture = assets.AssetInstallBoundaries()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        shutil.copy2(self.cli, fixture.put(fixture.wrapper, ""))
        before = fixture.wrapper.read_bytes(), fixture.wrapper.stat().st_mode
        fixture.run_script("scripts/install-user-assets.sh")
        self.assertEqual((fixture.wrapper.read_bytes(), fixture.wrapper.stat().st_mode), before)
        fixture.run_script("nova", "preset", "full", "--no-backup", "--no-autostart")
        self.assertEqual((fixture.wrapper.read_bytes(), fixture.wrapper.stat().st_mode), before)
        self.assertFalse(fixture.desktop.exists())


if __name__ == "__main__":
    unittest.main()
