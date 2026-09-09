"""Runtime root resolution; only temporary user data and read-only CLI calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
VARIABLES = ["NOVA_APP_DIR", "NOVA_DATA_HOME", "NOVA_CONFIG_HOME", "NOVA_STATE_HOME",
             "NOVA_CONFIG_DIR", "NOVA_STATE_DIR", "NOVA_THEMES_DIR", "NOVA_WALLPAPER_DIR"]


class RuntimeRoot(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-runtime-root-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = {
            "HOME": str(self.root / "home"),
            "XDG_DATA_HOME": str(self.root / "user data"),
            "XDG_CONFIG_HOME": str(self.root / "user config"),
            "XDG_STATE_HOME": str(self.root / "user state"),
            "PATH": os.defpath,
        }

    def make_core(self, path, profile="current"):
        for name in ["nova", "scripts/lib.sh", "scripts/apply-profile.sh",
                     "scripts/profile-info.py"]:
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / name, target)
        (path / "config").mkdir()
        (path / "config/profiles.json").write_text(json.dumps({"profiles": {
            profile: {"title": profile, "description": "fixture profile"}
        }}))
        return path

    def probe(self, lib, env=None):
        # Neither cwd, $0 nor the caller's ROOT identifies the loaded library.
        command = 'ROOT=/unrelated/caller; source "$1"; printf "%s\\0" ' + " ".join(
            '"$' + name + '"' for name in VARIABLES)
        result = subprocess.run(["/bin/bash", "-c", command, "unrelated-caller", str(lib)],
                                env=env or self.env, cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        values = result.stdout.decode().split("\0")[:-1]
        self.assertEqual(len(values), len(VARIABLES))
        return dict(zip(VARIABLES, values))

    def test_source_checkout_root(self):
        self.assertEqual(self.probe(REPO / "core/scripts/lib.sh")["NOVA_APP_DIR"],
                         str((REPO / "core").resolve()))

    def test_standalone_and_package_roots_ignore_old_xdg_core(self):
        self.make_core(Path(self.env["XDG_DATA_HOME"]) / "fedora-nova", "stale")
        for suffix in ["standalone/fedora-nova", "prefix/share/fedora-nova/core"]:
            with self.subTest(layout=suffix):
                core = self.make_core(self.root / suffix)
                self.assertEqual(self.probe(core / "scripts/lib.sh")["NOVA_APP_DIR"], str(core))

    def test_file_scripts_and_core_symlinks_resolve_physical_root(self):
        core = self.make_core(self.root / "physical core")
        core_link = self.root / "core link"
        core_link.symlink_to(core, target_is_directory=True)
        scripts_link = self.root / "scripts link"
        scripts_link.symlink_to(core / "scripts", target_is_directory=True)
        file_link = self.root / "lib-link.sh"
        file_link.symlink_to(core / "scripts/lib.sh")
        for lib in [core_link / "scripts/lib.sh", scripts_link / "lib.sh", file_link]:
            with self.subTest(lib=lib):
                self.assertEqual(self.probe(lib)["NOVA_APP_DIR"], str(core))

    def test_explicit_override_is_preserved_without_auto_detection(self):
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        resolver = fake_bin / "realpath"
        resolver.write_text("#!/bin/sh\nexit 99\n")
        resolver.chmod(0o755)
        env = dict(self.env, FEDORA_NOVA_APP_DIR="/explicit/root",
                   PATH=str(fake_bin) + os.pathsep + os.defpath)
        self.assertEqual(self.probe(REPO / "core/scripts/lib.sh", env)["NOVA_APP_DIR"],
                         "/explicit/root")

    def test_user_paths_remain_xdg_based(self):
        for explicit_xdg in [True, False]:
            with self.subTest(explicit_xdg=explicit_xdg):
                env = dict(self.env)
                if not explicit_xdg:
                    for name in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"]:
                        env.pop(name)
                values = self.probe(REPO / "core/scripts/lib.sh", env)
                home = Path(env["HOME"])
                data = env.get("XDG_DATA_HOME", str(home / ".local/share"))
                config = env.get("XDG_CONFIG_HOME", str(home / ".config"))
                state = env.get("XDG_STATE_HOME", str(home / ".local/state"))
                self.assertEqual({k: v for k, v in values.items() if k != "NOVA_APP_DIR"}, {
                    "NOVA_DATA_HOME": data, "NOVA_CONFIG_HOME": config, "NOVA_STATE_HOME": state,
                    "NOVA_CONFIG_DIR": config + "/fedora-nova",
                    "NOVA_STATE_DIR": state + "/fedora-nova",
                    "NOVA_THEMES_DIR": data + "/themes",
                    "NOVA_WALLPAPER_DIR": data + "/backgrounds/fedora-nova",
                })

    def test_direct_cli_lists_current_profiles_for_both_layouts(self):
        self.make_core(Path(self.env["XDG_DATA_HOME"]) / "fedora-nova", "stale-profile")
        for suffix in ["standalone/fedora-nova", "prefix/share/fedora-nova/core"]:
            with self.subTest(layout=suffix):
                core = self.make_core(self.root / suffix, "current-profile")
                result = subprocess.run([str(core / "nova"), "profile"], env=self.env,
                                        cwd=self.root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("current-profile", result.stdout)
                self.assertNotIn("stale-profile", result.stdout)
                self.assertFalse(Path(self.env["XDG_CONFIG_HOME"]).exists())
                self.assertFalse(Path(self.env["XDG_STATE_HOME"]).exists())

    def test_resolution_failure_stops_even_without_errexit(self):
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        resolver = fake_bin / "realpath"
        for body in ["exit 99", "exit 0", "printf '/scripts/lib.sh\\n'"]:
            with self.subTest(resolver=body):
                resolver.write_text("#!/bin/sh\n" + body + "\n")
                resolver.chmod(0o755)
                env = dict(self.env, PATH=str(fake_bin) + os.pathsep + os.defpath)
                result = subprocess.run(
                    ["/bin/bash", "-c", 'source "$1"; echo continued',
                     "probe", str(REPO / "core/scripts/lib.sh")], env=env,
                    cwd=self.root, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("Nelze určit fyzický root core", result.stderr)

    def test_production_launcher_override_reaches_lib(self):
        pkg = self.root / "prefix/share/fedora-nova"
        core = self.make_core(pkg / "core")
        frontend = pkg / "fedora_nova"
        frontend.mkdir()
        (frontend / "__init__.py").write_text("")
        # Replace only UI startup; execute the real configured launcher and lib.
        (frontend / "application.py").write_text('''
import os, subprocess

def main():
    subprocess.run(["/bin/bash", "-c",
                    'source "$FEDORA_NOVA_APP_DIR/scripts/lib.sh"; printf "%s" "$NOVA_APP_DIR"'],
                   check=True)
    return 0
''')
        launcher = self.root / "fedora-nova-settings"
        template = (REPO / "app/src/fedora-nova-settings.in").read_text()
        launcher.write_text(template.replace("@PYTHON@", sys.executable)
                            .replace("@PKGDATADIR@", str(pkg)))
        result = subprocess.run([sys.executable, str(launcher)],
                                env=dict(self.env, FEDORA_NOVA_APP_DIR="/stale/core"),
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(core))


if __name__ == "__main__":
    unittest.main()
