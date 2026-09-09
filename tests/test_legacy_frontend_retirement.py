from __future__ import annotations

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"
NOVA = CORE / "nova"
INSTALL_ASSETS = CORE / "scripts" / "install-assets.sh"
UNINSTALL = CORE / "uninstall.sh"
INSTALL = CORE / "install.sh"


class LegacyFrontendRetirementTests(unittest.TestCase):
    def test_legacy_frontend_files_are_removed(self) -> None:
        for path in (
            CORE / "scripts" / "settings.py",
            CORE / "scripts" / "control.sh",
            CORE / "scripts" / "control-zenity.sh",
            CORE / "applications" / "fedora-nova-control.desktop",
        ):
            with self.subTest(path=path):
                self.assertFalse(path.exists(), path)

    def test_settings_cli_has_no_legacy_frontend_fallback(self) -> None:
        text = NOVA.read_text(encoding="utf-8")
        self.assertNotIn("scripts/control.sh", text)
        self.assertNotIn("control-zenity", text)
        self.assertNotIn("settings.py", text)
        self.assertIn("fedora-nova-settings", text)
        self.assertIn("FEDORA_NOVA_SETTINGS_LAUNCHER", text)
        self.assertIn("Production Settings launcher není dostupný", text)

    def test_control_alias_is_retired(self) -> None:
        text = NOVA.read_text(encoding="utf-8")
        self.assertIn("settings) launch_settings", text)
        self.assertNotIn("settings|control) launch_settings", text)
        self.assertNotIn("alias pro settings", text)
        self.assertNotIn("\n  control ", text)

    def test_standalone_assets_install_only_cli_integration(self) -> None:
        text = INSTALL_ASSETS.read_text(encoding="utf-8")
        self.assertNotIn("fedora-nova-control.desktop", text)
        self.assertNotIn("APP_DESKTOP_DEST", text)
        self.assertNotIn("update-desktop-database", text)
        self.assertIn("$BIN_DEST/fedora-nova", text)

    def test_standalone_installer_no_longer_advertises_gui(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn("GUI Settings:", text)
        self.assertIn("canonical package/frontend", text)
        self.assertNotIn("Nastavení:      fedora-nova settings", text)

    def test_uninstall_still_cleans_historical_legacy_desktop(self) -> None:
        text = UNINSTALL.read_text(encoding="utf-8")
        self.assertIn("fedora-nova-control.desktop", text)


if __name__ == "__main__":
    unittest.main()
