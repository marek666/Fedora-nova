from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
LEGACY_PALETTE = """[Palette]
Name=Fedora Nova Tech
Background=#0b1120
Foreground=#eaf2ff
Cursor=#2ed8e8
CursorForeground=#0b1120
SelectionBackground=#8c5cff
SelectionForeground=#eaf2ff
Color0=#10182b
Color1=#ff5c7a
Color2=#35d07f
Color3=#f4b942
Color4=#4aa8ff
Color5=#8c5cff
Color6=#2ed8e8
Color7=#d7e3f5
Color8=#526078
Color9=#ff7890
Color10=#59e49a
Color11=#ffd16a
Color12=#75bdff
Color13=#2ed8e8
Color14=#8c5cff
Color15=#ffffff
"""


class LegacyPtyxisCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="nova-legacy-ptyxis-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_DATA_HOME": str(self.data),
                "XDG_STATE_HOME": str(self.state),
                "PATH": str(self.fake_bin) + os.pathsep + os.defpath,
            }
        )
        for key in ("FEDORA_NOVA_APP_DIR", "FEDORA_NOVA_CORE", "FEDORA_NOVA_CLI"):
            self.env.pop(key, None)
        for command in ("gsettings", "gnome-extensions", "dconf", "sudo", "dnf"):
            self.put(self.fake_bin / command, "#!/usr/bin/env bash\nexit 1\n", executable=True)

    def put(self, path: Path, text: str, executable: bool = False) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    @property
    def palette(self) -> Path:
        return self.data / "org.gnome.Ptyxis/palettes/Fedora Nova.palette"

    def make_package(self) -> Path:
        prefix = self.root / "canonical prefix"
        core = prefix / "share/fedora-nova/core"
        scripts = core / "scripts"
        scripts.mkdir(parents=True)
        for relative in ("nova", "scripts/lib.sh", "scripts/migrate-installation.sh"):
            target = core / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / relative, target)
        (prefix / "share/fedora-nova/fedora_nova").mkdir(parents=True)
        self.put(prefix / "bin/fedora-nova", "#!/bin/sh\nexit 0\n", executable=True)
        self.put(prefix / "bin/fedora-nova-settings", "#!/bin/sh\nexit 0\n", executable=True)
        self.put(scripts / "session-restore.sh", "#!/bin/sh\nexit 0\n", executable=True)
        return core

    def run_migration(self, core: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(core / "nova"), "migrate-installation", *args],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
        )

    def make_standalone(self) -> Path:
        core = self.root / "standalone core"
        (core / "scripts").mkdir(parents=True)
        for relative in ("uninstall.sh", "scripts/lib.sh"):
            target = core / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / relative, target)
        for name in ("gtk-theme.sh", "steam-icons.sh"):
            self.put(core / "scripts" / name, "#!/bin/sh\nexit 0\n", executable=True)
        self.put(self.data / "fedora-nova/sentinel", "legacy payload\n")
        return core

    def run_uninstall(self, core: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(core / "uninstall.sh")],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
        )

    def test_shared_helper_recognizes_only_exact_historical_palette(self) -> None:
        lib = REPO / "core/scripts/lib.sh"
        owned = self.put(self.root / "owned.palette", LEGACY_PALETTE)
        modified = self.put(self.root / "modified.palette", LEGACY_PALETTE.replace("#0b1120", "#0b1121", 1))
        symlink = self.root / "symlink.palette"
        symlink.symlink_to(owned)

        for path, expected in ((owned, 0), (modified, 1), (symlink, 1)):
            with self.subTest(path=path):
                result = subprocess.run(
                    [
                        "/bin/bash",
                        "-c",
                        'source "$1"; is_managed_legacy_ptyxis_palette "$2"',
                        "probe",
                        str(lib),
                        str(path),
                    ],
                    env=self.env,
                    cwd=self.root,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_migration_backs_up_and_removes_owned_legacy_palette(self) -> None:
        core = self.make_package()
        self.put(self.palette, LEGACY_PALETTE)
        result = self.run_migration(core)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.palette.exists())
        backups = list((self.state / "fedora-nova/migrations").glob("legacy-to-canonical.*"))
        self.assertEqual(len(backups), 1)
        backup = backups[0] / "Fedora Nova.palette"
        self.assertEqual(backup.read_text(encoding="utf-8"), LEGACY_PALETTE)

    def test_migration_refuses_modified_or_symlink_palette_before_mutation(self) -> None:
        for kind in ("modified", "symlink"):
            with self.subTest(kind=kind):
                core = self.make_package()
                if kind == "modified":
                    self.put(self.palette, LEGACY_PALETTE + "# user edit\n")
                else:
                    target = self.put(self.root / "target.palette", LEGACY_PALETTE)
                    self.palette.parent.mkdir(parents=True, exist_ok=True)
                    self.palette.symlink_to(target)
                result = self.run_migration(core)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("není rozpoznaná legacy Fedora Nova Ptyxis paleta", result.stderr)
                self.assertFalse((self.state / "fedora-nova/migration-canonical-layout").exists())
                self.assertFalse((self.state / "fedora-nova/migrations").exists())
                if kind == "modified":
                    self.assertTrue(self.palette.exists())
                else:
                    self.assertTrue(self.palette.is_symlink())
                shutil.rmtree(self.root / "canonical prefix", ignore_errors=True)
                if self.palette.exists() or self.palette.is_symlink():
                    self.palette.unlink()

    def test_migration_dry_run_reports_palette_without_mutating_it(self) -> None:
        core = self.make_package()
        original = self.put(self.palette, LEGACY_PALETTE).read_bytes()
        result = self.run_migration(core, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"DRY-RUN backup {self.palette}", result.stdout)
        self.assertIn(f"DRY-RUN remove {self.palette}", result.stdout)
        self.assertEqual(self.palette.read_bytes(), original)
        self.assertFalse((self.state / "fedora-nova/migrations").exists())

    def test_standalone_uninstall_removes_owned_legacy_palette(self) -> None:
        core = self.make_standalone()
        self.put(self.palette, LEGACY_PALETTE)
        result = self.run_uninstall(core)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.palette.exists())

    def test_standalone_uninstall_preserves_unowned_legacy_palette(self) -> None:
        core = self.make_standalone()
        original = self.put(self.palette, LEGACY_PALETTE + "# customized by user\n").read_bytes()
        result = self.run_uninstall(core)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.palette.read_bytes(), original)
        self.assertIn("Zachovávám", result.stderr)


if __name__ == "__main__":
    unittest.main()
