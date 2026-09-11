from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"


class CLIAuditRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="nova-cli-audit-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)

        self.put(
            "dconf",
            """#!/bin/sh
case "$1" in
  dump) exit 0 ;;
  load) cat >/dev/null; exit 0 ;;
  *) exit 0 ;;
esac
""",
        )
        self.put(
            "gsettings",
            """#!/bin/sh
case "$1" in
  get)
    if [ "$2:$3" = "org.gnome.desktop.interface:icon-theme" ]; then
      printf "'Adwaita'\\n"
    elif [ "$2:$3" = "org.gnome.shell:enabled-extensions" ]; then
      printf '[]\\n'
    else
      printf "''\\n"
    fi
    ;;
  list-schemas) exit 0 ;;
  *) exit 0 ;;
esac
""",
        )
        self.put("gnome-extensions", "#!/bin/sh\nexit 1\n")
        self.put("gnome-shell", "#!/bin/sh\necho 'GNOME Shell test'\n")
        self.put("journalctl", "#!/bin/sh\nexit 0\n")

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "XDG_CACHE_HOME": str(self.root / "cache"),
                "FEDORA_NOVA_APP_DIR": str(CORE),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.bin) + os.pathsep + os.defpath,
            }
        )

    def put(self, name: str, text: str) -> None:
        path = self.bin / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)

    def run_script(self, relative: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(CORE / "scripts" / relative), *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_steam_icons_status_on_clean_config_reports_zero(self) -> None:
        result = self.run_script("steam-icons.sh", "status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Generated:  0 PNG files", result.stdout)

    def test_export_succeeds_without_optional_asset_directories(self) -> None:
        archive = self.root / "clean-export.tar.gz"
        result = self.run_script("export-config.sh", str(archive))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(archive.is_file())

    def test_snapshot_restore_accepts_empty_dconf_dumps(self) -> None:
        created = self.run_script("snapshot.sh", "create", "empty")
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        restored = self.run_script("snapshot.sh", "restore", "empty")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertIn("Snapshot obnoven", restored.stdout)

    def test_import_accepts_export_with_empty_dconf_dumps(self) -> None:
        archive = self.root / "empty-dconf.tar.gz"
        exported = self.run_script("export-config.sh", str(archive))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        imported = self.run_script("import-config.sh", str(archive))
        self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
        self.assertIn("Import dokončen", imported.stdout)

    def test_doctor_missing_theme_has_no_traceback_and_is_unhealthy(self) -> None:
        result = self.run_script("doctor.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL Theme soubor chybí", result.stdout)
        self.assertIn("Výsledek:", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
