from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
STEAM_ICONS = REPO / "core/scripts/steam-icons.py"


class SteamIconSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="nova-steam-safety-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.apps = self.data / "applications"
        self.backups = self.state / "fedora-nova/steam-icons/desktop-backups"
        self.manifest = self.state / "fedora-nova/steam-icons/desktop-overrides.json"
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_STATE_HOME": str(self.state),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

    def put(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_restore(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(STEAM_ICONS),
                "Tela-circle-dark",
                "#2ED8E8",
                "#120C25",
                "--restore-desktops",
            ],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def record(self, target: Path, backup: Path, patched_sha256: str) -> None:
        self.put(
            self.manifest,
            json.dumps(
                [
                    {
                        "target": str(target),
                        "backup": str(backup),
                        "patched_sha256": patched_sha256,
                    }
                ]
            ),
        )

    def test_restore_rejects_target_outside_applications(self) -> None:
        outside = self.put(self.root / "important.desktop", "keep\n")
        backup = self.put(self.backups / ("a" * 64 + ".desktop"), "original\n")
        self.record(outside, backup, self.digest(outside))
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes its root", result.stderr)
        self.assertEqual(outside.read_text(), "keep\n")
        self.assertTrue(self.manifest.is_file())

    def test_restore_rejects_symlinked_desktop(self) -> None:
        outside = self.put(self.root / "important.desktop", "keep\n")
        target = self.apps / "game.desktop"
        target.parent.mkdir(parents=True)
        target.symlink_to(outside)
        backup = self.put(self.backups / ("b" * 64 + ".desktop"), "original\n")
        self.record(target, backup, self.digest(outside))
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsafe Steam desktop target", result.stderr)
        self.assertEqual(outside.read_text(), "keep\n")
        self.assertTrue(target.is_symlink())

    def test_restore_refuses_to_overwrite_desktop_changed_by_user(self) -> None:
        target = self.put(self.apps / "game.desktop", "user changed\n")
        backup = self.put(self.backups / ("c" * 64 + ".desktop"), "original\n")
        self.record(target, backup, hashlib.sha256(b"patched\n").hexdigest())
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed since it was patched", result.stderr)
        self.assertEqual(target.read_text(), "user changed\n")
        self.assertTrue(self.manifest.is_file())

    def test_valid_restore_is_atomic_and_removes_manifest(self) -> None:
        target = self.put(self.apps / "game.desktop", "patched\n")
        backup = self.put(self.backups / ("d" * 64 + ".desktop"), "original\n")
        self.record(target, backup, self.digest(target))
        result = self.run_restore()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
