from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"
FORGE = CORE / "scripts" / "forge-profile.py"
PROFILES = CORE / "config" / "profiles.json"
TEMPLATE = CORE / "themes" / "Fedora-Nova-Tech" / "gnome-shell" / "gnome-shell.css"
COLOR_ROLES = (
    "bg", "panel", "large", "surface", "surface2", "card",
    "accent", "accent_bright", "accent_fg", "secondary", "text",
    "muted", "border", "shadow",
)


class ForgeProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="nova-forge-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "xdg data"
        self.config = self.root / "xdg config"
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.root / "home"),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.root / "xdg state"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

    def create(self, name="Token Audit", primary="#F05A28", secondary="#35D07F"):
        before = TEMPLATE.read_bytes()
        result = subprocess.run(
            [sys.executable, str(FORGE), "create", name, primary, secondary],
            cwd=REPO,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(TEMPLATE.read_bytes(), before)
        return result.stdout.strip()

    def test_generated_theme_uses_current_tech_profile_as_template_palette(self) -> None:
        profile_id = self.create()
        self.assertEqual(profile_id, "custom-token-audit")

        metadata_path = self.config / "fedora-nova/custom-profiles" / f"{profile_id}.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        css_path = self.data / "themes" / metadata["theme"] / "gnome-shell/gnome-shell.css"
        css = css_path.read_text(encoding="utf-8")
        css_lower = css.lower()

        tech = json.loads(PROFILES.read_text(encoding="utf-8"))["profiles"]["tech"]
        for role in COLOR_ROLES:
            old = tech[role].lower()
            new = metadata[role].lower()
            with self.subTest(role=role):
                self.assertIn(new, css_lower)
                if old != new:
                    self.assertNotIn(old, css_lower)

        self.assertIn("Profile: Nova Forge — Token Audit", css)
        self.assertNotIn("Profile: Nova Tech", css)
        self.assertIn("rgba(240, 90, 40,", css)
        self.assertNotIn("rgba(46, 216, 232,", css)

    def test_forge_has_single_canonical_color_manifest(self) -> None:
        source = FORGE.read_text(encoding="utf-8")
        self.assertIn('config/profiles.json', source)
        self.assertNotIn("TECH_TOKENS", source)
        self.assertNotIn("colors.json", source)
        self.assertFalse((CORE / "config/colors.json").exists())

    def test_generated_companions_match_metadata(self) -> None:
        profile_id = self.create(name="Companion Audit", primary="#D630F2", secondary="#2ED8E8")
        metadata = json.loads(
            (self.config / "fedora-nova/custom-profiles" / f"{profile_id}.json").read_text(
                encoding="utf-8"
            )
        )
        wallpaper = self.data / "backgrounds/fedora-nova" / metadata["wallpaper"]
        palette = self.data / "org.gnome.Ptyxis/palettes" / metadata["palette"]
        self.assertTrue(wallpaper.is_file())
        self.assertTrue(palette.is_file())
        self.assertIn(metadata["accent"], wallpaper.read_text(encoding="utf-8"))
        self.assertIn(f'Cursor={metadata["accent"]}', palette.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
