"""User assets versus legacy integration, using isolated HOME/XDG fixtures."""
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
THEMES = ["Fedora-Nova-Tech", "Fedora-Nova-Clean", "Fedora-Nova-Midnight",
          "Fedora-Nova-Glass-Lite", "Fedora-Nova-Pulse"]
UUID = "topbar-all-monitors@fa8i.github.io"


class AssetInstallBoundaries(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-assets-")
        self.root = Path(tmp.name)
        self.addCleanup(self.cleanup, tmp)
        self.home = self.root / "home"
        self.data = self.root / "xdg data"
        self.config = self.root / "xdg config"
        self.wrapper = self.home / ".local/bin/fedora-nova"
        self.desktop = self.data / "applications/fedora-nova-control.desktop"
        binary = self.root / "bin"
        for name in ["gsettings", "gnome-extensions", "dconf", "sudo", "dnf"]:
            self.put(binary / name, '#!/bin/sh\necho "unexpected host command" >&2\nexit 97\n', executable=True)
        # Keep cache generation deterministic and inside the fixture boundaries.
        for name in ["gtk-update-icon-cache", "update-desktop-database"]:
            self.put(binary / name, '#!/bin/sh\nexit 0\n', executable=True)
        self.env = {"HOME": str(self.home), "XDG_DATA_HOME": str(self.data),
                    "XDG_CONFIG_HOME": str(self.config),
                    "XDG_STATE_HOME": str(self.root / "state"),
                    "XDG_CACHE_HOME": str(self.root / "cache"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": str(binary) + os.pathsep + os.defpath}
        self.core = self.make_core(self.root / "checkout/core")

    def cleanup(self, tmp):
        for path in [self.root, *self.root.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        tmp.cleanup()

    def put(self, path, text, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def make_core(self, core, label="current core"):
        for name in ["nova", "install.sh", "scripts/lib.sh", "scripts/install-assets.sh",
                     "scripts/install-user-assets.sh", "scripts/install-tela-icons.sh",
                     "scripts/install-trash-icons.sh", "scripts/monitor-panel.sh",
                     "scripts/apply-preset.sh", "scripts/profile-info.py",
                     "applications/fedora-nova-control.desktop", "config/profiles.json",
                     "config/colors.json", "config/curves.json", "config/packages.txt"]:
            target = core / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / name, target)
        # Rendering/applying GNOME settings is outside this integration test.
        self.put(core / "scripts/apply-settings.sh", '#!/bin/sh\nexit 0\n', executable=True)
        for theme in THEMES:
            self.put(core / "themes" / theme / "gnome-shell/gnome-shell.css", label + "\n")
        for name in ["assets/wallpapers/wall.svg", "assets/icons/fedora-nova.svg",
                     "assets/icons/user-trash.svg", "assets/icons/user-trash-full.svg",
                     "terminal/ptyxis/Fedora Nova.palette", "terminal/fastfetch/fedora-nova.jsonc",
                     f"third-party/topbar-all-monitors/{UUID}/extension.js"]:
            self.put(core / name, label + "\n")
        archive = core / "third-party/Tela-circle/Tela-circle.tar.xz"
        archive.parent.mkdir(parents=True)
        # Exercise the real Tela installer with a tiny, valid three-theme archive.
        with tarfile.open(archive, "w:xz") as tf:
            for theme in ["Tela-circle", "Tela-circle-dark", "Tela-circle-light"]:
                payload = (label + "\n").encode()
                info = tarfile.TarInfo(theme + "/index.theme")
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
        return core

    def snapshot(self, root):
        return {str(p.relative_to(root)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in root.rglob("*") if p.is_file()}

    def run_script(self, relative, *args, core=None, env=None):
        core = core or self.core
        before = self.snapshot(core)
        result = subprocess.run([str(core / relative), *args], env=env or self.env,
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(core), before)
        return result

    def assert_assets(self, label="current core"):
        for theme in THEMES:
            css = self.data / "themes" / theme / "gnome-shell/gnome-shell.css"
            self.assertEqual(css.read_text(), label + "\n")
            self.assertTrue(css.stat().st_mode & stat.S_IWUSR)
        for path in [self.data / "backgrounds/fedora-nova/wall.svg",
                     self.data / "org.gnome.Ptyxis/palettes/Fedora Nova.palette",
                     self.config / "fastfetch/fedora-nova.jsonc",
                     self.data / "icons/hicolor/scalable/apps/fedora-nova.svg",
                     self.data / f"gnome-shell/extensions/{UUID}/extension.js"]:
            self.assertEqual(path.read_text(), label + "\n")
        for name in ["colors.json", "profiles.json", "curves.json"]:
            self.assertTrue((self.config / "fedora-nova" / name).is_file())
        for theme in ["Tela-circle", "Tela-circle-dark", "Tela-circle-light"]:
            self.assertTrue((self.data / "icons" / theme / "index.theme").is_file())
            self.assertTrue((self.data / "icons" / theme / "symbolic/places/user-trash-symbolic.svg").is_file())
        self.assertFalse((self.data / "applications/io.github.fedoranova.FedoraNova.desktop").exists())

    def test_user_assets_create_no_integration(self):
        self.run_script("scripts/install-user-assets.sh")
        self.assert_assets()
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.desktop.exists())
        self.assertFalse(self.wrapper.parent.exists())
        self.assertFalse(self.desktop.parent.exists())

    def test_stale_integration_is_preserved(self):
        self.put(self.wrapper, "stale wrapper\n", executable=True)
        self.put(self.desktop, "stale desktop\n")
        before = (self.wrapper.read_bytes(), self.desktop.read_bytes())
        self.run_script("scripts/install-user-assets.sh")
        self.assertEqual((self.wrapper.read_bytes(), self.desktop.read_bytes()), before)
        self.assert_assets()

    def test_preset_full_uses_only_user_assets(self):
        # Any accidental compatibility call must fail rather than go unnoticed.
        self.put(self.core / "scripts/install-assets.sh", '#!/bin/sh\nexit 98\n', executable=True)
        for stale in [False, True]:
            if stale:
                self.put(self.wrapper, "stale wrapper\n", executable=True)
                self.put(self.desktop, "stale desktop\n")
            self.run_script("nova", "preset", "full", "--no-backup", "--no-autostart")
            self.assert_assets()
            self.assertEqual(self.wrapper.exists(), stale)
            self.assertEqual(self.desktop.exists(), stale)
            if stale:
                self.assertEqual(self.wrapper.read_text(), "stale wrapper\n")
                self.assertEqual(self.desktop.read_text(), "stale desktop\n")

    def test_compatibility_entrypoint_adds_only_legacy_integration(self):
        self.run_script("scripts/install-user-assets.sh")
        before = self.snapshot(self.root)
        self.run_script("scripts/install-assets.sh")
        after = self.snapshot(self.root)
        self.assertEqual(set(after) - set(before), {
            str(self.wrapper.relative_to(self.root)), str(self.desktop.relative_to(self.root))})
        for name, value in before.items():
            self.assertEqual(after[name], value, name)
        self.assert_assets()
        self.assertTrue(os.access(self.wrapper, os.X_OK))
        self.assertEqual(self.desktop.read_bytes(), (self.core / "applications/fedora-nova-control.desktop").read_bytes())
        result = subprocess.run([str(self.wrapper), "version"], env=self.env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "Fedora Nova 0.8.0-dev\n")
        self.assertIn(str(self.core / "nova"), self.wrapper.read_text())

    @unittest.skipIf(os.geteuid() == 0, "Standalone installer intentionally refuses root")
    def test_standalone_installer_keeps_compatibility_entrypoint(self):
        self.run_script("install.sh", "--skip-packages", "--no-apply", "--force-non-fedora")
        installed = self.data / "fedora-nova"
        self.assertTrue((installed / "scripts/install-user-assets.sh").is_file())
        self.assertIn(str(installed / "nova"), self.wrapper.read_text())
        self.assertTrue(self.desktop.is_file())
        self.assert_assets()

    def test_package_and_standalone_helpers_use_current_core(self):
        self.put(self.data / "fedora-nova/assets/wallpapers/wall.svg", "stale data\n")
        for layout in ["other-prefix/share/fedora-nova/core", "standalone/fedora-nova"]:
            core = self.make_core(self.root / layout, "selected core")
            self.run_script("scripts/install-user-assets.sh", core=core)
            self.assert_assets("selected core")
            self.assertFalse(self.wrapper.exists())
            self.assertFalse(self.desktop.exists())

    def test_read_only_bundled_themes_remain_unchanged(self):
        source = self.core / "themes"
        for path in [source, *source.rglob("*")]:
            path.chmod(0o555 if path.is_dir() else 0o444)
        self.run_script("scripts/install-user-assets.sh")
        self.assert_assets()

    def test_sync_replaces_only_managed_builtins_and_is_repeatable(self):
        self.put(self.data / "themes/Fedora-Nova-Tech/gnome-shell/gnome-shell.css", "old built-in edit\n")
        self.put(self.data / "themes/Fedora-Nova/old.css", "obsolete built-in\n")
        protected = [
            self.put(self.data / "themes/Fedora-Nova-Custom-example/gnome-shell/gnome-shell.css", "Forge sentinel\n"),
            self.put(self.data / "themes/OtherTheme/theme.css", "other theme\n"),
            self.put(self.config / "fedora-nova/custom-profiles/custom-example.json", "{}\n"),
            self.put(self.config / "fedora-nova/current-profile", "custom-example\n"),
            self.put(self.data / "backgrounds/fedora-nova/custom-example.svg", "custom wallpaper\n"),
            self.put(self.data / "org.gnome.Ptyxis/palettes/Fedora Nova Custom Example.palette", "custom palette\n"),
        ]
        before = {p: p.read_bytes() for p in protected}
        self.run_script("scripts/install-user-assets.sh")
        self.assertFalse((self.data / "themes/Fedora-Nova").exists())
        self.assert_assets()
        first = self.snapshot(self.data), self.snapshot(self.config)
        self.run_script("scripts/install-user-assets.sh")
        self.assertEqual((self.snapshot(self.data), self.snapshot(self.config)), first)
        self.assertEqual({p: p.read_bytes() for p in protected}, before)

    def test_theme_destination_cannot_alias_source(self):
        self.data.mkdir(parents=True)
        (self.data / "themes").symlink_to(self.core / "themes", target_is_directory=True)
        before = self.snapshot(self.core)
        result = subprocess.run([str(self.core / "scripts/install-user-assets.sh")],
                                env=self.env, cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundled themes", result.stderr)
        self.assertEqual(self.snapshot(self.core), before)
        self.assertFalse(self.wrapper.exists())


if __name__ == "__main__":
    unittest.main()
