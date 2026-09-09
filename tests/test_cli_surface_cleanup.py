from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"
CLI = CORE / "nova"
PRESET = CORE / "scripts" / "apply-preset.sh"
WALLPAPERS = CORE / "assets" / "wallpapers"
PROFILES = CORE / "config" / "profiles.json"


class CliSurfaceCleanupTests(unittest.TestCase):
    def isolated_env(self) -> dict[str, str]:
        root = Path(tempfile.mkdtemp(prefix="nova-cli-surface-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        return {
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "PATH": os.defpath,
            "FEDORA_NOVA_APP_DIR": str(CORE),
        }

    def test_cli_help_exposes_only_canonical_commands(self) -> None:
        result = subprocess.run(
            [str(CLI), "--help"],
            env=self.isolated_env(),
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("preset [full]", result.stdout)
        self.assertIn("migrate-installation [--dry-run]", result.stdout)
        self.assertNotIn("full-setup", result.stdout)
        self.assertNotIn("alias pro", result.stdout)

    def test_removed_cli_aliases_are_rejected(self) -> None:
        for command in ("full-setup", "migrate"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [str(CLI), command],
                    env=self.isolated_env(),
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"Neznámý příkaz: {command}", result.stderr)

    def test_removed_preset_aliases_are_rejected_before_host_changes(self) -> None:
        for preset in ("nova-full", "mutter"):
            with self.subTest(preset=preset):
                result = subprocess.run(
                    [str(PRESET), preset],
                    env=self.isolated_env(),
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"Neznámý preset: {preset}", result.stderr)

    def test_obsolete_compatibility_report_is_removed(self) -> None:
        self.assertFalse((CORE / "scripts" / "check-compatibility.sh").exists())

    def test_profile_wallpapers_exist_and_preview_orphan_is_removed(self) -> None:
        profiles = json.loads(PROFILES.read_text(encoding="utf-8"))["profiles"]
        referenced = {profile["wallpaper"] for profile in profiles.values()}
        for wallpaper in referenced:
            with self.subTest(wallpaper=wallpaper):
                self.assertTrue((WALLPAPERS / wallpaper).is_file())

        self.assertFalse((WALLPAPERS / "fedora-nova-flow-preview.png").exists())


if __name__ == "__main__":
    unittest.main()
