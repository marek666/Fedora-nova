from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core"
SOURCE_ONLY = (
    "themes-src/dev.scss",
    "scripts/build-theme-sass.sh",
    "scripts/preview_reload.py",
    "scripts/theme_hot_reload.py",
    "scripts/__pycache__/stale.pyc",
    "scripts/stale.pyc",
)


class StandalonePayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="nova-standalone-payload-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o777)
        self.home = self.root / "home"
        self.data = self.root / "xdg data"
        self.config = self.root / "xdg config"
        self.state = self.root / "xdg state"
        for directory in (self.home, self.data, self.config, self.state):
            directory.mkdir(parents=True)
            directory.chmod(0o777)

        self.core = self.root / "checkout/core"
        for relative in (
            "install.sh",
            "nova",
            "scripts/lib.sh",
            "scripts/profile-info.py",
            "config/profiles.json",
        ):
            target = self.core / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CORE / relative, target)

        install_assets = self.core / "scripts/install-assets.sh"
        install_assets.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        install_assets.chmod(0o755)

        for relative in SOURCE_ONLY:
            target = self.core / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("source-only marker\n", encoding="utf-8")
            if target.suffix == ".sh":
                target.chmod(0o755)

        # The test may run in a root-owned CI container. Keep the checkout
        # readable/traversable when the installer process is demoted to nobody.
        for directory in (self.root / "checkout", self.core, *[p for p in self.core.rglob("*") if p.is_dir()]):
            directory.chmod(0o755)

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        for key in ("FEDORA_NOVA_APP_DIR", "FEDORA_NOVA_CORE", "FEDORA_NOVA_CLI"):
            self.env.pop(key, None)

    def run_installer(self) -> subprocess.CompletedProcess[str]:
        kwargs = {}
        if os.geteuid() == 0:
            kwargs["preexec_fn"] = lambda: os.setuid(65534)
        return subprocess.run(
            [
                str(self.core / "install.sh"),
                "--skip-packages",
                "--no-apply",
                "--force-non-fedora",
            ],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def test_installed_standalone_copy_omits_source_only_helpers_and_bytecode(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        installed = self.data / "fedora-nova"
        for relative in ("install.sh", "nova", "scripts/lib.sh", "scripts/install-assets.sh", "config/profiles.json"):
            with self.subTest(runtime=relative):
                self.assertTrue((installed / relative).is_file())

        for relative in SOURCE_ONLY:
            with self.subTest(source_only=relative):
                self.assertFalse((installed / relative).exists())
                self.assertTrue((self.core / relative).exists())

        self.assertFalse(any(installed.rglob("__pycache__")))
        self.assertFalse(any(installed.rglob("*.pyc")))

    def test_pruning_policy_matches_canonical_source_only_boundary(self) -> None:
        source = (CORE / "install.sh").read_text(encoding="utf-8")
        for relative in (
            "themes-src",
            "scripts/build-theme-sass.sh",
            "scripts/preview_reload.py",
            "scripts/theme_hot_reload.py",
        ):
            with self.subTest(relative=relative):
                self.assertIn(relative, source)
        self.assertIn("__pycache__", source)
        self.assertIn("*.pyc", source)


if __name__ == "__main__":
    unittest.main()
