"""Guarded legacy-to-canonical migration; fixtures never touch the real HOME."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class CanonicalInstallMigration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-migration-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.prefix = self.root / "prefix with spaces"
        self.calls = self.root / "session-calls"
        for path in (self.home, self.config, self.data, self.state):
            path.mkdir(parents=True, exist_ok=True)
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_DATA_HOME": str(self.data),
                "XDG_STATE_HOME": str(self.state),
                "PATH": os.defpath,
                "NOVA_TEST_SESSION_CALLS": str(self.calls),
            }
        )
        for key in ("FEDORA_NOVA_APP_DIR", "FEDORA_NOVA_CORE", "FEDORA_NOVA_CLI"):
            self.env.pop(key, None)
        self.core = self.make_package(self.prefix)

    def put(self, path: Path, text: str, executable: bool = False) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def make_package(self, prefix: Path) -> Path:
        core = prefix / "share/fedora-nova/core"
        scripts = core / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "core/nova", core / "nova")
        shutil.copy2(REPO / "core/scripts/lib.sh", scripts / "lib.sh")
        shutil.copy2(REPO / "core/scripts/migrate-installation.sh", scripts / "migrate-installation.sh")
        (prefix / "share/fedora-nova/fedora_nova").mkdir(parents=True, exist_ok=True)
        self.put(prefix / "bin/fedora-nova", "#!/bin/sh\nexit 0\n", executable=True)
        self.put(prefix / "bin/fedora-nova-settings", "#!/bin/sh\nexit 0\n", executable=True)
        self.put(
            scripts / "session-restore.sh",
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "${1:-}" >> "$NOVA_TEST_SESSION_CALLS"
if [[ "${1:-}" == enable ]]; then
  mkdir -p "$XDG_CONFIG_HOME/fedora-nova" "$XDG_CONFIG_HOME/autostart"
  cat > "$XDG_CONFIG_HOME/fedora-nova/session-restore" <<'EOF'
#!/usr/bin/env bash
exec /canonical/fedora-nova session-restore --quiet
EOF
  chmod +x "$XDG_CONFIG_HOME/fedora-nova/session-restore"
  cat > "$XDG_CONFIG_HOME/autostart/fedora-nova-session.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Fedora Nova Session Restore
Exec=/canonical/session-restore
EOF
fi
""",
            executable=True,
        )
        return core

    @property
    def wrapper(self) -> Path:
        return self.home / ".local/bin/fedora-nova"

    @property
    def legacy_desktop(self) -> Path:
        return self.data / "applications/fedora-nova-control.desktop"

    @property
    def session_launcher(self) -> Path:
        return self.config / "fedora-nova/session-restore"

    @property
    def session_desktop(self) -> Path:
        return self.config / "autostart/fedora-nova-session.desktop"

    @property
    def marker(self) -> Path:
        return self.state / "fedora-nova/migration-canonical-layout"

    def seed_legacy(self, *, session_enabled: bool = True) -> None:
        self.put(
            self.wrapper,
            '#!/usr/bin/env bash\nexec "/old/share/fedora-nova/nova" "$@"\n',
            executable=True,
        )
        self.put(
            self.legacy_desktop,
            """[Desktop Entry]
Type=Application
Name=Fedora Nova Settings
Exec=fedora-nova settings
Icon=fedora-nova
""",
        )
        self.put(
            self.session_launcher,
            """#!/usr/bin/env bash
export FEDORA_NOVA_APP_DIR=/old
exec /old/nova session-restore --quiet
""",
            executable=True,
        )
        if session_enabled:
            self.put(
                self.session_desktop,
                """[Desktop Entry]
Type=Application
Name=Fedora Nova Session Restore
Exec=/old/session-restore
X-GNOME-Autostart-enabled=true
""",
            )
        self.put(self.data / "fedora-nova/legacy-core-sentinel", "preserve me\n")

    def run_migration(self, *args: str, core: Path | None = None):
        executable = (core or self.core) / "nova"
        return subprocess.run(
            [str(executable), "migrate-installation", *args],
            cwd=self.root,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_migrates_managed_entries_backs_them_up_and_preserves_payload(self):
        self.seed_legacy(session_enabled=True)
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.wrapper.exists())
        self.assertFalse(self.legacy_desktop.exists())
        self.assertEqual(
            (self.data / "fedora-nova/legacy-core-sentinel").read_text(encoding="utf-8"),
            "preserve me\n",
        )
        self.assertEqual(self.calls.read_text(encoding="utf-8"), "enable\n")
        self.assertIn("/canonical/fedora-nova", self.session_launcher.read_text(encoding="utf-8"))
        self.assertTrue(self.session_desktop.exists())
        self.assertTrue(self.marker.exists())
        backups = list((self.state / "fedora-nova/migrations").glob("legacy-to-canonical.*"))
        self.assertEqual(len(backups), 1)
        for name in (
            "fedora-nova-wrapper",
            "fedora-nova-control.desktop",
            "session-restore",
            "fedora-nova-session.desktop",
        ):
            self.assertTrue((backups[0] / name).exists(), name)

    def test_dry_run_is_read_only(self):
        self.seed_legacy(session_enabled=True)
        before = {
            path: path.read_bytes()
            for path in (self.wrapper, self.legacy_desktop, self.session_launcher, self.session_desktop)
        }
        result = self.run_migration("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY-RUN remove", result.stdout)
        self.assertIn("DRY-RUN regenerate session restore", result.stdout)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.calls.exists())

    def test_unmanaged_wrapper_blocks_before_any_mutation(self):
        self.seed_legacy(session_enabled=True)
        self.wrapper.write_text("#!/bin/sh\necho user-owned\n", encoding="utf-8")
        desktop_before = self.legacy_desktop.read_bytes()
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("není rozpoznaný", result.stderr)
        self.assertTrue(self.wrapper.exists())
        self.assertEqual(self.legacy_desktop.read_bytes(), desktop_before)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.state / "fedora-nova/migrations").exists())
        self.assertFalse(self.calls.exists())

    def test_unmanaged_desktop_blocks_before_wrapper_removal(self):
        self.seed_legacy(session_enabled=False)
        self.legacy_desktop.write_text("[Desktop Entry]\nName=User file\n", encoding="utf-8")
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.wrapper.exists())
        self.assertTrue(self.legacy_desktop.exists())
        self.assertFalse(self.marker.exists())

    def test_disabled_session_stays_disabled_and_orphan_launcher_is_removed(self):
        self.seed_legacy(session_enabled=False)
        result = self.run_migration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.session_desktop.exists())
        self.assertFalse(self.session_launcher.exists())
        self.assertFalse(self.calls.exists())
        self.assertIn("session_enabled=0", self.marker.read_text(encoding="utf-8"))

    def test_missing_production_settings_refuses_migration(self):
        self.seed_legacy(session_enabled=True)
        (self.prefix / "bin/fedora-nova-settings").unlink()
        result = self.run_migration()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production Settings launcher", result.stderr)
        self.assertTrue(self.wrapper.exists())
        self.assertFalse(self.marker.exists())

    def test_non_package_runtime_is_refused(self):
        standalone = self.root / "standalone"
        (standalone / "scripts").mkdir(parents=True)
        shutil.copy2(REPO / "core/nova", standalone / "nova")
        shutil.copy2(REPO / "core/scripts/lib.sh", standalone / "scripts/lib.sh")
        shutil.copy2(
            REPO / "core/scripts/migrate-installation.sh",
            standalone / "scripts/migrate-installation.sh",
        )
        result = self.run_migration(core=standalone)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical package", result.stderr)

    def test_canonical_user_wrapper_is_never_removed(self):
        prefix = self.home / ".local"
        core = self.make_package(prefix)
        env = dict(self.env, XDG_DATA_HOME=str(prefix / "share"))
        self.env = env
        canonical = prefix / "bin/fedora-nova"
        original = canonical.read_bytes()
        legacy_desktop = prefix / "share/applications/fedora-nova-control.desktop"
        self.put(
            legacy_desktop,
            "[Desktop Entry]\nType=Application\nExec=fedora-nova settings\nIcon=fedora-nova\n",
        )
        result = self.run_migration(core=core)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(canonical.read_bytes(), original)
        self.assertFalse(legacy_desktop.exists())

    def test_second_run_is_safe(self):
        self.seed_legacy(session_enabled=True)
        first = self.run_migration()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_migration()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.calls.read_text(encoding="utf-8"), "enable\nenable\n")


if __name__ == "__main__":
    unittest.main()
