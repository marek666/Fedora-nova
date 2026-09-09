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
PALETTES = CORE / "terminal" / "ptyxis"
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

    def run_rejected(self, command: list[Path | str], expected: str) -> None:
        env = self.isolated_env()
        result = subprocess.run(
            [str(arg) for arg in command],
            env=env,
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected, result.stderr)
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            self.assertFalse(Path(env[key]).exists())

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
                self.run_rejected([CLI, command], f"Neznámý příkaz: {command}")

    def test_removed_preset_aliases_are_rejected_before_host_changes(self) -> None:
        for preset in ("nova-full", "mutter"):
            with self.subTest(preset=preset):
                self.run_rejected([PRESET, preset], f"Neznámý preset: {preset}")

    def test_removed_session_action_aliases_are_rejected_without_state(self) -> None:
        script = CORE / "scripts" / "session-restore.sh"
        for action in ("restore", "on", "autostart", "off"):
            with self.subTest(action=action):
                self.run_rejected([script, action], "{apply|enable|disable|status}")

    def test_removed_monitor_action_aliases_are_rejected_without_state(self) -> None:
        script = CORE / "scripts" / "monitor-panel.sh"
        for action in ("enable", "disable"):
            with self.subTest(action=action):
                self.run_rejected([script, action], "{install|refresh|on|off|status}")

    def test_removed_welcome_disable_alias_is_rejected_without_state(self) -> None:
        script = CORE / "scripts" / "disable-welcome.sh"
        self.run_rejected([script, "disable"], "{off|status}")

    def test_obsolete_compatibility_report_is_removed(self) -> None:
        self.assertFalse((CORE / "scripts" / "check-compatibility.sh").exists())

    def test_profile_wallpapers_exist_and_preview_orphan_is_removed(self) -> None:
        profiles = json.loads(PROFILES.read_text(encoding="utf-8"))["profiles"]
        referenced = {profile["wallpaper"] for profile in profiles.values()}
        for wallpaper in referenced:
            with self.subTest(wallpaper=wallpaper):
                self.assertTrue((WALLPAPERS / wallpaper).is_file())

        self.assertFalse((WALLPAPERS / "fedora-nova-flow-preview.png").exists())

    def test_builtin_ptyxis_palettes_match_builtin_profiles(self) -> None:
        profiles = json.loads(PROFILES.read_text(encoding="utf-8"))["profiles"]
        expected = {f"Fedora {profile['title']}.palette" for profile in profiles.values()}
        actual = {path.name for path in PALETTES.glob("*.palette")}
        self.assertEqual(actual, expected)
        self.assertNotIn("Fedora Nova.palette", actual)

        for profile in profiles.values():
            name = f"Fedora {profile['title']}"
            path = PALETTES / f"{name}.palette"
            with self.subTest(palette=path.name):
                self.assertIn(f"Name={name}\n", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
