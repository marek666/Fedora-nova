from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class LegacyIntegrationOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="nova-legacy-owner-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home with spaces"
        self.data = self.root / "xdg data"
        self.config = self.root / "xdg config"
        self.state = self.root / "xdg state"
        self.calls = self.root / "user-assets-called"
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir(parents=True)
        self.core = self.root / "standalone core $() ; 'quote'"
        (self.core / "scripts").mkdir(parents=True)
        shutil.copy2(REPO / "core/scripts/lib.sh", self.core / "scripts/lib.sh")
        shutil.copy2(REPO / "core/scripts/install-assets.sh", self.core / "scripts/install-assets.sh")
        shutil.copy2(REPO / "core/uninstall.sh", self.core / "uninstall.sh")
        self.put(
            self.core / "scripts/install-user-assets.sh",
            '#!/usr/bin/env bash\nprintf called > "$NOVA_TEST_CALLS"\n',
            executable=True,
        )
        self.put(
            self.core / "scripts/gtk-theme.sh",
            "#!/usr/bin/env bash\nexit 0\n",
            executable=True,
        )
        self.put(
            self.core / "scripts/steam-icons.sh",
            "#!/usr/bin/env bash\nexit 0\n",
            executable=True,
        )
        self.put(
            self.core / "nova",
            "#!/usr/bin/env bash\nprintf 'target=%s\\n' \"$0\"\nprintf '<%s>\\n' \"$@\"\n",
            executable=True,
        )
        self.wrapper = self.home / ".local/bin/fedora-nova"
        self.desktop = self.data / "applications/fedora-nova-control.desktop"
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "NOVA_TEST_CALLS": str(self.calls),
                "PATH": str(self.fake_bin) + os.pathsep + os.defpath,
            }
        )
        for name in ("gsettings", "gnome-extensions", "dconf", "sudo", "dnf"):
            self.put(self.fake_bin / name, "#!/usr/bin/env bash\nexit 1\n", executable=True)

    def put(self, path: Path, text: str, executable: bool = False) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def run_install_assets(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.core / "scripts/install-assets.sh")],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
        )

    def helper_result(self, function: str, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "/bin/bash",
                "-c",
                'source "$1"; "$2" "$3"',
                "probe",
                str(self.core / "scripts/lib.sh"),
                function,
                str(path),
            ],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
        )

    def test_unowned_wrapper_blocks_install_before_user_assets(self) -> None:
        original = self.put(
            self.wrapper,
            "#!/usr/bin/env bash\n# canonical package sentinel\nexit 91\n",
            executable=True,
        ).read_bytes()
        result = self.run_install_assets()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Odmítám přepsat", result.stderr)
        self.assertEqual(self.wrapper.read_bytes(), original)
        self.assertFalse(self.calls.exists())

    def test_symlink_wrapper_is_never_claimed(self) -> None:
        target = self.put(self.root / "canonical-wrapper", "canonical\n")
        self.wrapper.parent.mkdir(parents=True, exist_ok=True)
        self.wrapper.symlink_to(target)
        result = self.run_install_assets()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.wrapper.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "canonical\n")
        self.assertFalse(self.calls.exists())

    def test_historical_wrapper_is_upgraded_to_owned_shell_safe_wrapper(self) -> None:
        self.put(
            self.wrapper,
            '#!/usr/bin/env bash\nexec "/old standalone/nova" "$@"\n',
            executable=True,
        )
        result = self.run_install_assets()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.calls.exists())
        text = self.wrapper.read_text(encoding="utf-8")
        self.assertIn("# Fedora Nova legacy standalone CLI wrapper", text)
        self.assertNotIn("/old standalone/nova", text)
        self.assertTrue(os.access(self.wrapper, os.X_OK))

        args = ["two words", "$(touch should-not-exist)", "'quoted'", "--"]
        invoked = subprocess.run(
            [str(self.wrapper), *args],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn(f"target={self.core / 'nova'}", invoked.stdout)
        for arg in args:
            self.assertIn(f"<{arg}>", invoked.stdout)
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_owned_wrapper_is_idempotently_replaceable(self) -> None:
        first = self.run_install_assets()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        before = self.wrapper.read_bytes()
        self.calls.unlink()
        second = self.run_install_assets()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertTrue(self.calls.exists())
        self.assertEqual(self.wrapper.read_bytes(), before)

    def test_shared_helpers_recognize_only_owned_legacy_files(self) -> None:
        historical = self.put(
            self.root / "old-wrapper",
            '#!/usr/bin/env bash\nexec "/legacy/fedora-nova/nova" "$@"\n',
        )
        owned = self.put(
            self.root / "owned-wrapper",
            '#!/usr/bin/env bash\n# Fedora Nova legacy standalone CLI wrapper\nexec /legacy/fedora-nova/nova "$@"\n',
        )
        canonical = self.put(
            self.root / "canonical-wrapper",
            "#!/usr/bin/env bash\nexport FEDORA_NOVA_APP_DIR=/pkg/core\nexec /pkg/core/nova \"$@\"\n",
        )
        for path in (historical, owned):
            with self.subTest(path=path):
                self.assertEqual(self.helper_result("is_managed_legacy_cli_wrapper", path).returncode, 0)
        self.assertNotEqual(self.helper_result("is_managed_legacy_cli_wrapper", canonical).returncode, 0)

        legacy_desktop = self.put(
            self.root / "legacy.desktop",
            "[Desktop Entry]\nType=Application\nExec=fedora-nova settings\nIcon=fedora-nova\n",
        )
        unrelated_desktop = self.put(
            self.root / "unrelated.desktop",
            "[Desktop Entry]\nType=Application\nExec=other-app\nIcon=fedora-nova\n",
        )
        self.assertEqual(
            self.helper_result("is_managed_legacy_settings_desktop", legacy_desktop).returncode,
            0,
        )
        self.assertNotEqual(
            self.helper_result("is_managed_legacy_settings_desktop", unrelated_desktop).returncode,
            0,
        )

    def prepare_uninstall_fixture(self) -> None:
        (self.data / "fedora-nova").mkdir(parents=True, exist_ok=True)
        self.put(self.data / "fedora-nova/sentinel", "legacy payload\n")

    def test_uninstall_preserves_unowned_wrapper_and_desktop(self) -> None:
        self.prepare_uninstall_fixture()
        wrapper_bytes = self.put(self.wrapper, "canonical wrapper\n", executable=True).read_bytes()
        desktop_bytes = self.put(self.desktop, "custom desktop\n").read_bytes()
        result = subprocess.run(
            [str(self.core / "uninstall.sh")],
            env=self.env,
            cwd=self.root,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.wrapper.read_bytes(), wrapper_bytes)
        self.assertEqual(self.desktop.read_bytes(), desktop_bytes)
        self.assertIn("Zachovávám", result.stderr)

    def test_migration_reuses_shared_ownership_helpers(self) -> None:
        text = (REPO / "core/scripts/migrate-installation.sh").read_text(encoding="utf-8")
        self.assertIn("is_managed_legacy_cli_wrapper", text)
        self.assertIn("is_managed_legacy_settings_desktop", text)
        self.assertNotIn("managed_legacy_wrapper()", text)
        self.assertNotIn("managed_legacy_desktop()", text)


if __name__ == "__main__":
    unittest.main()
