from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import textwrap

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "core/scripts/integrations/blur-my-shell.sh"
DOCTOR = REPO / "core/scripts/doctor.sh"

class BlurMyShellIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="nova-bms-")
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()

        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.value_file = self.root / "style-components"

        self.value_file.write_text("1\n", encoding="utf-8")

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "PATH": str(self.bin) + os.pathsep + os.defpath,
            }
        )
        self.env["NOVA_BMS_TEST_VALUE_FILE"] = str(self.value_file)

        self.put_command(
            "gsettings",
            """
            #!/usr/bin/env python3
            import os
            from pathlib import Path
            import sys

            value_file = Path(os.environ["NOVA_BMS_TEST_VALUE_FILE"])
            command = sys.argv[1:]

            if command[:1] == ["list-keys"]:
                if os.environ.get("NOVA_BMS_TEST_SCHEMA") != "missing":
                    print("style-components")
            elif command[:1] == ["get"]:
                print(value_file.read_text(encoding="utf-8").strip())
            elif command[:1] == ["writable"]:
                if os.environ.get("NOVA_BMS_TEST_WRITABLE") == "false":
                    print("false")
                else:
                    print("true")
            elif command[:1] == ["set"]:
                value_file.write_text(command[3] + "\\n", encoding="utf-8")
            else:
                raise SystemExit(f"Neočekávaný gsettings příkaz: {command}")
            """,
        )
        self.put_command(
            "gnome-extensions",
            """
            #!/usr/bin/env python3
            import os
            import sys

            if sys.argv[1:] == ["list", "--enabled"]:
                if os.environ.get("NOVA_BMS_TEST_ENABLED") == "true":
                    print("blur-my-shell@aunetx")
            """,
        )
        self.put_command(
            "journalctl",
            """
            #!/bin/sh
            exit 0
            """,
        )
        self.put_command(
            "gnome-shell",
            """
            #!/bin/sh
            printf 'GNOME Shell test\n'
            """,
        )
    def put_command(self, name: str, content: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/usr/bin/bash", str(HELPER), *args],
            env=self.env,
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def run_doctor(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/usr/bin/bash", str(DOCTOR)],
            env=self.env,
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def test_apply_saves_original_value_once_and_sets_zero(self) -> None:
        result = self.run_helper("apply")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "0\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertEqual(backup.read_text(encoding="utf-8"), "1\n")

        repeated = self.run_helper("apply")

        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "0\n")
        self.assertEqual(backup.read_text(encoding="utf-8"), "1\n")

    def test_restore_returns_saved_value_and_removes_backup(self) -> None:
        applied = self.run_helper("apply")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

        restored = self.run_helper("restore")

        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "1\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertFalse(backup.exists())

    def test_restore_preserves_manual_nonzero_change_and_backup(self) -> None:
        applied = self.run_helper("apply")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

        self.value_file.write_text("2\n", encoding="utf-8")

        restored = self.run_helper("restore")

        self.assertNotEqual(restored.returncode, 0)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "2\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertEqual(backup.read_text(encoding="utf-8"), "1\n")

    def test_status_reports_values_without_changing_them(self) -> None:
        applied = self.run_helper("apply")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

        status = self.run_helper("status")

        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("Aktuální style-components: 0", status.stdout)
        self.assertIn("Zálohovaná původní hodnota: 1", status.stdout)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "0\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertEqual(backup.read_text(encoding="utf-8"), "1\n")

    def test_apply_skips_cleanly_when_bms_schema_is_unavailable(self) -> None:
        self.env["NOVA_BMS_TEST_SCHEMA"] = "missing"

        result = self.run_helper("apply")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Nastavení Blur My Shell není dostupné", result.stdout)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "1\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertFalse(backup.exists())

    def test_apply_fails_without_writable_bms_setting(self) -> None:
        self.env["NOVA_BMS_TEST_WRITABLE"] = "false"

        result = self.run_helper("apply")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Nastavení Blur My Shell není zapisovatelné", result.stderr)
        self.assertEqual(self.value_file.read_text(encoding="utf-8"), "1\n")

        backup = (
            self.config
            / "fedora-nova/integrations/blur-my-shell/previous-style-components"
        )
        self.assertFalse(backup.exists())

    def test_doctor_accepts_active_bms_with_compatible_overview_style(self) -> None:
        self.env["NOVA_BMS_TEST_ENABLED"] = "true"
        self.value_file.write_text("0\n", encoding="utf-8")

        result = self.run_doctor()

        self.assertIn(
            "OK   Blur My Shell je aktivní a jeho stylování přehledu je vypnuté.",
            result.stdout,
        )
        self.assertNotIn(
            "Blur My Shell je zapnutý — může vrátit lag compositoru.",
            result.stdout,
        )

    def test_doctor_warns_when_active_bms_styles_the_overview(self) -> None:
        self.env["NOVA_BMS_TEST_ENABLED"] = "true"
        self.value_file.write_text("1\n", encoding="utf-8")

        result = self.run_doctor()

        self.assertIn(
            "WARN Blur My Shell přepisuje stylování přehledu. "
            "Spusť znovu aplikaci profilu.",
            result.stdout,
        )
        self.assertNotIn(
            "OK   Blur My Shell je aktivní a jeho stylování přehledu je vypnuté.",
            result.stdout,
        )

    def test_doctor_warns_when_active_bms_setting_is_unavailable(self) -> None:
        self.env["NOVA_BMS_TEST_ENABLED"] = "true"
        self.env["NOVA_BMS_TEST_SCHEMA"] = "missing"

        result = self.run_doctor()

        self.assertIn(
            "WARN Blur My Shell je aktivní, ale jeho nastavení přehledu nelze ověřit.",
            result.stdout,
        )

if __name__ == "__main__":
    unittest.main()