import os
from pathlib import Path
import sys
import tempfile
import unittest

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
