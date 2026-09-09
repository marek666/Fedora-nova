"""Legacy install guards; all commands and data stay in temporary fixtures."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class InstallLayoutGuard(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-layout-guard-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "test home"
        self.data = self.home / "data"
        self.destination = self.data / "fedora-nova"
        self.calls = self.root / "side-effects.log"
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        self.env = {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_STATE_HOME": str(self.home / "state"),
            "PATH": str(self.fake_bin) + os.pathsep + os.defpath,
            "NOVA_TEST_CALLS": str(self.calls),
        }
        self.recorder = '''#!/bin/bash
printf '%s\\n' "$0 $*" >> "$NOVA_TEST_CALLS"
exit 97
'''
        # Catch host commands and prevent destructive commands if a guard fails.
        for command in ["gsettings", "gnome-extensions", "dconf", "sudo", "dnf",
                        "rm", "cp", "mkdir", "find", "chmod", "sleep"]:
            self.put(self.fake_bin / command, self.recorder, executable=True)
        for path in [self.home / ".local/bin/fedora-nova",
                     self.home / "config/fedora-nova/sentinel",
                     self.data / "themes/Fedora-Nova-Tech/sentinel",
                     self.data / "applications/fedora-nova-control.desktop"]:
            self.put(path, "untouched\n")
        self.source = self.make_core(self.root / "source core")

    def put(self, path, text="sentinel\n", executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def make_core(self, path):
        (path / "scripts").mkdir(parents=True, exist_ok=True)
        for name in ["install.sh", "uninstall.sh", "scripts/lib.sh",
                     "scripts/profile-info.py", "config/profiles.json", "config/packages.txt"]:
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core" / name, target)
        self.put(path / "nova", executable=True)
        for name in ["backup-settings.sh", "apply-preset.sh", "install-assets.sh",
                     "gtk-theme.sh", "steam-icons.sh", "restore-settings.sh"]:
            self.put(path / "scripts" / name, self.recorder, executable=True)
        return path

    def make_package(self, path):
        self.make_core(path / "core")
        self.put(path / "core/sentinel", "core intact\n")
        self.put(path / "fedora_nova/sentinel", "frontend intact\n")
        return path

    def snapshot(self):
        result = {}
        for path in self.root.rglob("*"):
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                value = os.readlink(path)
            elif stat.S_ISREG(mode):
                value = path.read_bytes()
            else:
                value = None
            result[str(path.relative_to(self.root))] = (mode, value)
        return result

    def detect(self, path):
        return subprocess.run(
            ["/bin/bash", "-c", 'source "$1"; package_layout_present "$2"',
             "probe", str(self.source / "scripts/lib.sh"), str(path)],
            env=self.env, cwd=self.root, capture_output=True, text=True,
        )

    def assert_refused(self, script, env=None, message="package instalace"):
        before = self.snapshot()
        result = subprocess.run([str(script)], env=env or self.env,
                                cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)
        self.assertFalse(self.calls.exists(), self.calls.read_text() if self.calls.exists() else "")
        self.assertEqual(self.snapshot(), before)

    def test_package_destination_refused_before_install_and_uninstall_effects(self):
        self.make_package(self.destination)
        # Even profile validation must not run before the install guard.
        self.put(self.fake_bin / "python3", self.recorder, executable=True)
        for name in ["install.sh", "uninstall.sh"]:
            with self.subTest(script=name):
                self.assert_refused(self.source / name)

    def test_bundled_core_refused_with_same_or_different_destination(self):
        self.make_package(self.destination)
        for data in [self.data, self.root / "different data"]:
            for name in ["install.sh", "uninstall.sh"]:
                with self.subTest(data=data, script=name):
                    env = dict(self.env, XDG_DATA_HOME=str(data))
                    self.assert_refused(self.destination / "core" / name, env=env)

    def test_detection_requires_both_package_artifacts(self):
        empty = self.root / "empty"
        empty.mkdir()
        legacy = self.make_core(self.root / "legacy")
        (legacy / "themes").mkdir()
        only_core = self.root / "only-core"
        self.put(only_core / "core/nova")
        only_frontend = self.root / "only-frontend"
        (only_frontend / "fedora_nova").mkdir(parents=True)
        no_nova = self.root / "no-nova"
        (no_nova / "core").mkdir(parents=True)
        (no_nova / "fedora_nova").mkdir()
        for path in [empty, legacy, only_core, only_frontend, no_nova,
                     self.root / "missing", ""]:
            with self.subTest(path=path):
                self.assertEqual(self.detect(path).returncode, 1)
        self.assertEqual(self.detect(self.make_package(self.root / "package")).returncode, 0)

    def test_symlink_destination_detected_without_changes(self):
        package = self.make_package(self.root / "physical package")
        self.data.mkdir(parents=True, exist_ok=True)
        self.destination.symlink_to(package, target_is_directory=True)
        self.assertEqual(self.detect(self.destination).returncode, 0)
        for name in ["install.sh", "uninstall.sh"]:
            with self.subTest(script=name):
                self.assert_refused(self.source / name)

    def test_symlinked_installer_and_parent_directory_detected(self):
        package = self.make_package(self.root / "physical package")
        alias = self.root / "package alias"
        alias.symlink_to(package, target_is_directory=True)
        for name in ["install.sh", "uninstall.sh"]:
            link = self.root / name
            link.symlink_to(package / "core" / name)
            for script in [link, alias / "core" / name]:
                with self.subTest(script=script):
                    self.assert_refused(script)

    def test_root_destination_symlink_rejected(self):
        self.data.mkdir(parents=True, exist_ok=True)
        self.destination.symlink_to("/", target_is_directory=True)
        for name in ["install.sh", "uninstall.sh"]:
            with self.subTest(script=name):
                self.assert_refused(self.source / name, message="kořenovým adresářem")

    def test_empty_and_relative_guard_destination_rejected(self):
        for destination in ["", "/", "relative/path"]:
            with self.subTest(destination=destination):
                result = subprocess.run(
                    ["/bin/bash", "-c", 'source "$1"; require_legacy_layout "$2" "$3"',
                     "probe", str(self.source / "scripts/lib.sh"), str(self.source), destination],
                    env=self.env, cwd=self.root, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_standalone_source_and_destination_remain_allowed(self):
        for existing in [False, True]:
            if existing:
                self.make_core(self.destination)
            for project in [self.source] + ([self.destination] if existing else []):
                with self.subTest(existing=existing, project=project):
                    result = subprocess.run(
                        ["/bin/bash", "-c", 'source "$1"; require_legacy_layout "$2" "$3"',
                         "probe", str(project / "scripts/lib.sh"), str(project), str(self.destination)],
                        env=self.env, cwd=self.root, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(self.calls.exists())

    @unittest.skipIf(os.geteuid() == 0, "Legacy installer intentionally refuses root")
    def test_standalone_install_dry_run_remains_allowed(self):
        for existing in [False, True]:
            if existing:
                self.make_core(self.destination)
            before = self.snapshot()
            result = subprocess.run(
                [str(self.source / "install.sh"), "--dry-run", "--skip-packages",
                 "--no-apply", "--force-non-fedora"], env=self.env, cwd=self.root,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("install-assets.sh", result.stdout)
            self.assertFalse(self.calls.exists())
            self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
