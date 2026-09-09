"""CLI Settings routing with isolated install layouts and harmless launchers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class SettingsRouting(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-settings-routing-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.prefix = self.root / "installation with spaces"
        self.stale_bin = self.root / "stale-prefix/bin"
        self.launcher(self.stale_bin / "fedora-nova-settings", "stale")
        self.env = {
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "PATH": str(self.stale_bin) + os.pathsep + os.defpath,
            "FEDORA_NOVA_APP_DIR": str(self.root / "stale-prefix/share/fedora-nova"),
        }
        self.args = ["--flag", "", "two words", "line\nbreak", "'quotes'",
                     "$(printf injected)", "*", "--", "český profil"]

    def launcher(self, path, label, status=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            f"print(json.dumps(dict(launcher={label!r}, args=sys.argv[1:])))\n"
            f"sys.exit({status})\n"
        )
        path.chmod(0o755)
        return path

    def core(self, layout):
        suffix = {"package": "share/fedora-nova/core",
                  "standalone": "share/fedora-nova",
                  "checkout": "source-checkout/core"}[layout]
        core = self.prefix / suffix
        (core / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "core/nova", core / "nova")
        shutil.copy2(REPO / "core/scripts/lib.sh", core / "scripts/lib.sh")
        self.launcher(core / "scripts/control.sh", "legacy")
        return core / "nova"

    def assert_routes(self, cli, expected, override=None, status=0):
        env = dict(self.env)
        if override is not None:
            env["FEDORA_NOVA_SETTINGS_LAUNCHER"] = str(override)
        for alias in ["settings", "control"]:
            with self.subTest(alias=alias, cli=str(cli), override=override):
                result = subprocess.run([str(cli), alias, *self.args], env=env,
                                        cwd=self.root, capture_output=True, text=True)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 {"launcher": expected, "args": self.args})

    def test_package_layout_prefers_modern_launcher(self):
        cli = self.core("package")
        self.launcher(self.prefix / "bin/fedora-nova-settings", "modern")
        self.assert_routes(cli, "modern")

    def test_standalone_layout_prefers_modern_launcher(self):
        cli = self.core("standalone")
        self.launcher(self.prefix / "bin/fedora-nova-settings", "modern")
        self.assert_routes(cli, "modern")

    def test_missing_modern_launcher_uses_legacy_and_ignores_path(self):
        for layout in ["package", "standalone", "checkout"]:
            with self.subTest(layout=layout):
                self.assert_routes(self.core(layout), "legacy")

    def test_checkout_does_not_guess_an_installation_prefix(self):
        self.launcher(self.prefix / "bin/fedora-nova-settings", "unrelated")
        self.assert_routes(self.core("checkout"), "legacy")

    def test_explicit_override_wins_over_modern_and_legacy(self):
        override = self.launcher(self.root / "explicit with spaces/settings", "explicit")
        self.launcher(self.prefix / "bin/fedora-nova-settings", "modern")
        for layout in ["package", "standalone", "checkout"]:
            with self.subTest(layout=layout):
                self.assert_routes(self.core(layout), "explicit", override=override)

    def test_invalid_explicit_override_fails_without_fallback(self):
        not_executable = self.launcher(self.root / "not-executable", "invalid")
        not_executable.chmod(0o644)
        directory = self.root / "directory"
        directory.mkdir()
        broken = self.root / "broken-symlink"
        broken.symlink_to(self.root / "missing")
        self.launcher(self.prefix / "bin/fedora-nova-settings", "modern")
        for layout in ["package", "standalone"]:
            cli = self.core(layout)
            for override in ["", self.root / "missing", not_executable, directory, broken]:
                for alias in ["settings", "control"]:
                    with self.subTest(layout=layout, override=override, alias=alias):
                        env = dict(self.env, FEDORA_NOVA_SETTINGS_LAUNCHER=str(override))
                        result = subprocess.run([str(cli), alias, *self.args], env=env,
                                                cwd=self.root, capture_output=True, text=True)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("FEDORA_NOVA_SETTINGS_LAUNCHER", result.stderr)

    def test_relative_override_is_a_path_not_a_path_search(self):
        # Same filename exists earlier in PATH; execute the validated local file.
        self.launcher(self.root / "fedora-nova-settings", "relative")
        self.assert_routes(self.core("package"), "relative", override="fedora-nova-settings")

    def test_unusable_prefix_launcher_uses_legacy(self):
        modern = self.launcher(self.prefix / "bin/fedora-nova-settings", "modern")
        modern.chmod(0o644)
        for layout in ["package", "standalone"]:
            with self.subTest(layout=layout):
                self.assert_routes(self.core(layout), "legacy")

    def test_launcher_failure_propagates_without_legacy_fallback(self):
        self.launcher(self.prefix / "bin/fedora-nova-settings", "modern", status=17)
        self.assert_routes(self.core("package"), "modern", status=17)


if __name__ == "__main__":
    unittest.main()
