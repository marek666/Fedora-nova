from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from installer.engine import Installer, InstallerError
from installer.model import (
    InstallContext,
    assert_owned_tree,
    copy_path_nofollow,
    lexists,
    tree_fingerprint,
)
from installer.payload import PTYXIS_PALETTES, TELA_THEMES, THEMES, artifacts


class InstallerV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="nova installer v2 [] ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source checkout"
        self.home = self.root / "home with spaces"
        self.data = self.root / "xdg data"
        self.config = self.root / "xdg config"
        self.state = self.root / "xdg state"
        self.cache = self.root / "xdg cache"
        self.prefix = self.root / "prefix [local]"
        self.fake_bin = self.root / "fake bin"
        self.fake_bin.mkdir(parents=True)
        self._make_source()
        self._make_fake_commands()
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "XDG_CACHE_HOME": str(self.cache),
                "FEDORA_NOVA_INSTALL_PREFIX": str(self.prefix),
                "FEDORA_NOVA_INSTALLER_TESTING": "1",
                "FEDORA_NOVA_INSTALLER_TEST_ROOT": str(self.root),
                "FAKE_DCONF_LOG": str(self.root / "dconf loads.log"),
                "PATH": str(self.fake_bin) + os.pathsep + os.defpath,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        self.context = InstallContext.from_environ(self.source, self.env)

    def put(self, path: Path, content: str, mode: int = 0o644) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)
        return path

    def _make_source(self) -> None:
        self.put(self.source / "VERSION", "9.9-test\n")
        core = self.source / "core"
        self.put(core / "nova", "#!/bin/sh\necho nova\n", 0o755)
        self.put(core / "scripts/lib.sh", "# runtime helper\n")
        self.put(core / "scripts/preview_reload.py", "# excluded\n")
        self.put(core / "scripts/preview_paths.py", "# excluded\n")
        self.put(core / "scripts/theme_hot_reload_core.py", "# excluded\n")
        self.put(core / "install.sh", "# excluded\n")
        self.put(core / "config/profiles.json", "{}\n")
        self.put(core / "config/packages.txt", "excluded\n")
        self.put(core / "themes-src/source.scss", "excluded\n")
        for theme in THEMES:
            self.put(core / f"themes/{theme}/gnome-shell/gnome-shell.css", f"{theme}\n")
        self.put(core / "assets/wallpapers/nova.svg", "wallpaper\n")
        self.put(
            self.source / "assets/icons/io.github.fedoranova.FedoraNova.svg",
            "app icon\n",
        )
        self.put(core / "assets/icons/user-trash.svg", "trash empty\n")
        self.put(core / "assets/icons/user-trash-full.svg", "trash full\n")
        for palette in PTYXIS_PALETTES:
            self.put(core / f"terminal/ptyxis/{palette}", f"{palette}\n")
        self.put(core / "terminal/fastfetch/fedora-nova.jsonc", "{}\n")
        self.put(
            core / "third-party/topbar-all-monitors/topbar-all-monitors@fa8i.github.io/extension.js",
            "// extension\n",
        )

        archive = core / "third-party/Tela-circle/Tela-circle.tar.xz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:xz") as handle:
            for theme in TELA_THEMES:
                base = self.root / "tar source" / theme
                self.put(base / "index.theme", f"[{theme}]\n")
                self.put(base / "scalable/places/original.svg", "original\n")
                handle.add(base, arcname=theme, recursive=True)
            broken_metadata = tarfile.TarInfo(
                "Tela-circle/scalable/places/newline-link.svg"
            )
            broken_metadata.type = tarfile.SYMTYPE
            broken_metadata.linkname = "original.svg\n"
            handle.addfile(broken_metadata)

        app_python = self.source / "app/src/fedora_nova"
        self.put(app_python / "__init__.py", "# package\n")
        self.put(app_python / "application.py", "def main(): return 0\n")
        self.put(
            self.source / "app/src/fedora-nova.in",
            "#!/bin/sh\nexport FEDORA_NOVA_APP_DIR='@PKGDATADIR@/core'\nexec \"$FEDORA_NOVA_APP_DIR/nova\" \"$@\"\n",
            0o755,
        )
        for name in ("fedora-nova-settings.in", "fedora-nova-settings-devel.in"):
            self.put(
                self.source / f"app/src/{name}",
                "#!@PYTHON@\nPKGDATADIR = '@PKGDATADIR@'\n",
                0o755,
            )
        for app_id in (
            "io.github.fedoranova.FedoraNova",
            "io.github.fedoranova.FedoraNova.Devel",
        ):
            self.put(self.source / f"app/data/{app_id}.desktop.in", "[Desktop Entry]\nType=Application\n")
            self.put(self.source / f"app/data/{app_id}.metainfo.xml", "<component/>\n")
            self.put(self.source / f"app/data/{app_id}.gschema.xml", "<schemalist/>\n")

    def _make_fake_commands(self) -> None:
        self.put(
            self.fake_bin / "dconf",
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            " dump) printf '[/]\\nvalue=\\x27preserved\\x27\\n' ;;\n"
            " load) cat >> \"$FAKE_DCONF_LOG\"; printf '%s\\n' \"$2\" >> \"$FAKE_DCONF_LOG\" ;;\n"
            " *) exit 2 ;;\n"
            "esac\n",
            0o755,
        )
        self.put(
            self.fake_bin / "gsettings",
            "#!/bin/sh\n"
            "if [ \"$1\" = get ]; then printf \"'test'\\n\"; exit 0; fi\n"
            "exit 2\n",
            0o755,
        )
        self.put(self.fake_bin / "gnome-shell", "#!/bin/sh\necho 'GNOME Shell test'\n", 0o755)

    def installer(self, env: dict[str, str] | None = None) -> Installer:
        selected = self.env if env is None else env
        context = InstallContext.from_environ(self.source, selected)
        return Installer(context, environ=selected, stream=io.StringIO())

    def snapshot(self, root: Path) -> dict[str, tuple[str, object]]:
        if not root.exists():
            return {}
        result: dict[str, tuple[str, object]] = {}
        for path in sorted([root, *root.rglob("*")], key=str):
            relative = "." if path == root else path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                result[relative] = ("link", os.readlink(path))
            elif stat.S_ISREG(mode):
                result[relative] = ("file", path.read_bytes())
            elif stat.S_ISDIR(mode):
                result[relative] = ("dir", stat.S_IMODE(mode))
        return result

    def test_clean_first_install_and_validation(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        self.assertTrue(self.context.manifest_path.is_file())
        self.assertTrue((self.data / "fedora-nova/core/nova").is_file())
        self.assertTrue((self.data / f"gnome-shell/extensions/topbar-all-monitors@fa8i.github.io/extension.js").is_file())
        self.assertTrue((self.data / "themes/Fedora-Nova-Tech/gnome-shell/gnome-shell.css").is_file())
        app_icon = self.data / "icons/hicolor/scalable/apps/io.github.fedoranova.FedoraNova.svg"
        self.assertEqual(app_icon.read_text(), "app icon\n")
        self.assertFalse(
            (self.data / "icons/hicolor/scalable/apps/io.github.fedoranova.FedoraNova.Devel.svg").exists()
        )
        self.assertFalse((self.data / "icons/hicolor/scalable/apps/fedora-nova.svg").exists())
        newline_link = self.data / "icons/Tela-circle/scalable/places/newline-link.svg"
        self.assertTrue(newline_link.is_symlink())
        self.assertEqual(os.readlink(newline_link), "original.svg")
        self.assertTrue(newline_link.resolve(strict=True).is_file())
        self.assertTrue(self.installer().validate(emit=False).ok)
        self.assertFalse((self.data / "fedora-nova/core/themes-src").exists())
        self.assertFalse((self.data / "fedora-nova/core/install.sh").exists())
        self.assertFalse((self.data / "fedora-nova/core/uninstall.sh").exists())
        self.assertFalse(
            (self.data / "fedora-nova/core/scripts/install-assets.sh").exists()
        )
        self.assertFalse((self.data / "fedora-nova/core/scripts/preview_paths.py").exists())
        self.assertFalse((self.data / "fedora-nova/core/scripts/theme_hot_reload_core.py").exists())

    def test_payload_excludes_untracked_checkout_debug_files(self) -> None:
        subprocess.run(
            ["git", "init", "-q", str(self.source)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(self.source), "add", "."],
            check=True,
            capture_output=True,
        )
        self.put(self.source / "core/debug-local.log", "not payload\n")
        self.put(self.source / "core/scripts/local-backup.py", "# not payload\n")
        self.put(self.source / "app/src/fedora_nova/local_debug.py", "# not payload\n")
        self.put(self.source / "core/assets/wallpapers/debug-local.svg", "not payload\n")
        self.put(
            self.source / "core/themes/Fedora-Nova-Tech/debug-local.txt", "not payload\n"
        )
        self.put(
            self.source
            / "core/third-party/topbar-all-monitors"
            / "topbar-all-monitors@fa8i.github.io/debug-local.txt",
            "not payload\n",
        )
        self.installer().install()
        runtime = self.data / "fedora-nova/core"
        self.assertFalse((runtime / "debug-local.log").exists())
        self.assertFalse((runtime / "scripts/local-backup.py").exists())
        self.assertFalse((self.data / "fedora-nova/fedora_nova/local_debug.py").exists())
        self.assertFalse(
            (self.data / "backgrounds/fedora-nova/debug-local.svg").exists()
        )
        self.assertFalse(
            (self.data / "themes/Fedora-Nova-Tech/debug-local.txt").exists()
        )
        self.assertFalse(
            (
                self.data
                / "gnome-shell/extensions/topbar-all-monitors@fa8i.github.io/debug-local.txt"
            ).exists()
        )

    def test_payload_rejects_source_link_that_escapes_after_relocation(self) -> None:
        link = self.source / "core/scripts/relocated-escape"
        link.symlink_to("../../VERSION")
        with self.assertRaisesRegex(InstallerError, "Source symlink escapes"):
            self.installer().install()
        self.assertFalse((self.data / "fedora-nova").exists())
        self.assertFalse(self.context.backup_root.exists())

    def test_payload_rejects_link_that_escapes_only_its_installed_component(self) -> None:
        link = self.source / "core/themes/Fedora-Nova-Tech/cross-theme-link"
        link.symlink_to(
            "../Fedora-Nova-Clean/gnome-shell/gnome-shell.css"
        )
        with self.assertRaisesRegex(InstallerError, "Source symlink escapes"):
            self.installer().install()
        self.assertFalse((self.data / "themes/Fedora-Nova-Tech").exists())
        self.assertFalse(self.context.backup_root.exists())

    def test_home_must_not_be_filesystem_root(self) -> None:
        env = dict(self.env)
        env["HOME"] = "/"
        with self.assertRaises(InstallerError):
            InstallContext.from_environ(self.source, env)

    def test_testing_root_must_not_be_filesystem_root(self) -> None:
        env = dict(self.env)
        env["FEDORA_NOVA_INSTALLER_TEST_ROOT"] = "/"
        with self.assertRaises(InstallerError):
            InstallContext.from_environ(self.source, env)

    def test_path_preflight_rejects_empty_relative_root_and_home_targets(self) -> None:
        attacks = (
            Path(""),
            Path("."),
            Path("relative/../path"),
            Path("$HOME"),
            Path("/"),
            self.home,
            self.home / "..",
            self.cache / "fedora-nova-shell-preview/data",
        )
        for attack in attacks:
            with self.subTest(path=str(attack)):
                with self.assertRaises(InstallerError):
                    self.context.assert_safe_target(attack)
        special = self.config / "Unicode [] $() ; č/child"
        self.assertEqual(self.context.assert_safe_target(special), special)
        self.assertEqual(
            self.context.assert_safe_target(Path(str(special) + "///")), special
        )

    def test_reinstall_is_idempotent(self) -> None:
        self.installer().install()
        before = {
            str(item.target): tree_fingerprint(item.target)
            for item in artifacts(self.context)
        }
        manifest_before = self.context.manifest_path.read_bytes()
        state_before = self.context.install_state_path.read_bytes()
        backup_names_before = {
            path.name for path in self.context.backup_root.iterdir()
        }
        backup = self.installer().install()
        after = {
            str(item.target): tree_fingerprint(item.target)
            for item in artifacts(self.context)
        }
        self.assertEqual(before, after)
        self.assertIsNone(backup)
        self.assertEqual(self.context.manifest_path.read_bytes(), manifest_before)
        self.assertEqual(self.context.install_state_path.read_bytes(), state_before)
        self.assertEqual(
            {path.name for path in self.context.backup_root.iterdir()},
            backup_names_before,
        )

    def test_concurrent_mutating_transaction_is_refused_before_host_changes(self) -> None:
        holder = self.installer()
        holder._prepare_state_root()
        lock_fd = holder._acquire_transaction_lock()
        try:
            with self.assertRaisesRegex(InstallerError, "already running"):
                self.installer().install()
        finally:
            holder._release_transaction_lock(lock_fd)
        self.assertFalse((self.data / "fedora-nova").exists())
        self.assertFalse(self.context.manifest_path.exists())
        self.assertFalse(self.context.backup_root.exists())

    def test_generated_icon_caches_do_not_force_reinstall(self) -> None:
        self.installer().install()
        caches = []
        for theme in TELA_THEMES:
            cache = self.put(
                self.data / f"icons/{theme}/icon-theme.cache", "generated\n"
            )
            caches.append(cache)
        backup = self.installer().install()
        self.assertIsNone(backup)
        self.assertTrue(all(path.read_text() == "generated\n" for path in caches))
        self.assertTrue(self.installer().validate(emit=False).ok)

    def test_upgrade_replaces_legacy_program_files_and_preserves_settings(self) -> None:
        self.put(self.data / "fedora-nova/old-only.txt", "legacy runtime\n")
        self.put(self.data / "themes/Fedora-Nova-Tech/old.css", "legacy theme\n")
        self.put(self.data / "themes/Fedora-Nova/stale.css", "obsolete\n")
        self.put(self.config / "fedora-nova/current-profile", "pulse\n")
        self.put(self.config / "fedora-nova/custom-profiles/my.json", "{}\n")
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        self.assertFalse((self.data / "fedora-nova/old-only.txt").exists())
        self.assertFalse((self.data / "themes/Fedora-Nova").exists())
        self.assertEqual((self.config / "fedora-nova/current-profile").read_text(), "pulse\n")
        self.assertEqual((self.config / "fedora-nova/custom-profiles/my.json").read_text(), "{}\n")

    def test_uncertain_product_prefixed_user_assets_are_reported_not_deleted(self) -> None:
        theme = self.put(self.data / "themes/Fedora-Nova-My-Handmade/marker", "mine\n")
        wallpaper = self.put(
            self.data / "backgrounds/fedora-nova/fedora-nova-family.svg", "mine\n"
        )
        palette = self.put(
            self.data / "org.gnome.Ptyxis/palettes/Fedora Nova Personal.palette",
            "mine\n",
        )
        output = io.StringIO()
        Installer(self.context, environ=self.env, stream=output).install()
        self.assertEqual(theme.read_text(), "mine\n")
        self.assertEqual(wallpaper.read_text(), "mine\n")
        self.assertEqual(palette.read_text(), "mine\n")
        self.assertIn("left untouched", output.getvalue())

    def test_stale_manifest_target_is_backed_up_and_removed(self) -> None:
        self.installer().install()
        stale = self.data / "themes/Fedora-Nova-Old-Managed"
        self.put(stale / "marker", "old\n")
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"].append(
            {
                "path": str(stale),
                "component": "old",
                "type": "directory",
                "fingerprint": tree_fingerprint(stale),
                "entries": [],
            }
        )
        self.context.manifest_path.write_text(json.dumps(manifest))
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        self.assertFalse(stale.exists())
        metadata = json.loads((backup / "backup.json").read_text())
        self.assertIn(str(stale), {entry["path"] for entry in metadata["entries"]})

    def test_stale_manifest_application_icons_are_safely_removed(self) -> None:
        self.installer().install()
        icon_root = self.data / "icons/hicolor/scalable/apps"
        stale_icons = [
            self.put(icon_root / "fedora-nova.svg", "old legacy icon\n"),
            self.put(
                icon_root / "io.github.fedoranova.FedoraNova.Devel.svg",
                "old devel icon\n",
            ),
        ]
        manifest = json.loads(self.context.manifest_path.read_text())
        for icon in stale_icons:
            manifest["managed_targets"].append(
                {
                    "path": str(icon),
                    "component": "old-app-icon",
                    "type": "file",
                    "fingerprint": tree_fingerprint(icon),
                    "entries": [],
                }
            )
        self.context.manifest_path.write_text(json.dumps(manifest))

        self.installer().install()

        for icon in stale_icons:
            self.assertFalse(icon.exists())
        self.assertTrue(
            (icon_root / "io.github.fedoranova.FedoraNova.svg").is_file()
        )

    def test_unregistered_manifest_target_is_never_removed(self) -> None:
        self.installer().install()
        unrelated = self.put(self.data / "documents/important.txt", "keep\n")
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"].append(
            {
                "path": str(unrelated),
                "component": "corrupt-entry",
                "type": "file",
                "fingerprint": tree_fingerprint(unrelated),
                "entries": [],
            }
        )
        self.context.manifest_path.write_text(json.dumps(manifest))
        output = io.StringIO()
        Installer(self.context, environ=self.env, stream=output).install()
        self.assertEqual(unrelated.read_text(), "keep\n")
        self.assertIn("Unregistered stale manifest path ignored", output.getvalue())

    def test_stale_manifest_target_with_mismatched_ownership_is_preserved(self) -> None:
        self.installer().install()
        user_theme = self.put(
            self.data / "themes/Fedora-Nova-User-Owned/marker", "keep\n"
        )
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"].append(
            {
                "path": str(user_theme.parent),
                "component": "old",
                "type": "directory",
                "fingerprint": "0" * 64,
                "entries": [],
            }
        )
        self.context.manifest_path.write_text(json.dumps(manifest))
        output = io.StringIO()
        Installer(self.context, environ=self.env, stream=output).install()
        self.assertEqual(user_theme.read_text(), "keep\n")
        self.assertIn("ownership evidence does not match", output.getvalue())

    def test_broken_leaf_symlink_is_backed_up_without_following_and_replaced(self) -> None:
        target = self.data / "themes/Fedora-Nova-Tech"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.root / "does not exist", target_is_directory=True)
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        self.assertTrue(target.is_dir())
        self.assertFalse(target.is_symlink())
        metadata = json.loads((backup / "backup.json").read_text())
        entry = next(item for item in metadata["entries"] if item["path"] == str(target))
        self.assertEqual(entry["type"], "symlink")

    def test_managed_child_symlink_is_backed_up_and_restored_without_following(self) -> None:
        outside = self.put(self.root / "outside/sentinel", "outside\n")
        runtime = self.data / "fedora-nova"
        runtime.mkdir(parents=True)
        (runtime / "outside-link").symlink_to(outside)
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        self.assertEqual(outside.read_text(), "outside\n")
        self.installer().rollback(backup)
        restored = runtime / "outside-link"
        self.assertTrue(restored.is_symlink())
        self.assertEqual(os.readlink(restored), str(outside))
        self.assertEqual(outside.read_text(), "outside\n")

    def test_symlinked_parent_escaping_root_aborts_before_outside_write(self) -> None:
        outside = self.root / "outside target"
        self.put(outside / "sentinel", "do not touch\n")
        self.data.mkdir(parents=True)
        (self.data / "themes").symlink_to(outside, target_is_directory=True)
        before = self.snapshot(outside)
        with self.assertRaises(InstallerError):
            self.installer().install()
        self.assertEqual(self.snapshot(outside), before)
        self.assertFalse(self.context.backup_root.exists())

    def test_symlinked_installer_state_root_is_rejected(self) -> None:
        outside = self.root / "outside state"
        self.put(outside / "sentinel", "keep\n")
        self.state.mkdir(parents=True)
        (self.state / "fedora-nova").symlink_to(outside, target_is_directory=True)
        before = self.snapshot(outside)
        with self.assertRaises(InstallerError):
            self.installer().install()
        self.assertEqual(self.snapshot(outside), before)

    def test_install_target_cannot_overlap_source_checkout(self) -> None:
        env = dict(self.env)
        env["XDG_DATA_HOME"] = str(self.source)
        context = InstallContext.from_environ(self.source, env)
        with self.assertRaises(InstallerError):
            Installer(context, environ=env, stream=io.StringIO()).dry_run()

    def test_symlinked_user_settings_root_aborts_before_install(self) -> None:
        outside = self.root / "outside settings"
        self.put(outside / "current-profile", "pulse\n")
        self.config.mkdir(parents=True)
        (self.config / "fedora-nova").symlink_to(outside, target_is_directory=True)
        before = self.snapshot(outside)
        with self.assertRaises(InstallerError):
            self.installer().install()
        self.assertEqual(self.snapshot(outside), before)
        self.assertFalse((self.data / "fedora-nova").exists())

    def test_unknown_third_party_neighbor_is_untouched(self) -> None:
        third_party = self.put(self.data / "themes/Third Party Theme/custom.css", "mine\n")
        self.installer().install()
        self.assertEqual(third_party.read_text(), "mine\n")

    def test_failed_install_can_be_rolled_back(self) -> None:
        old_runtime = self.put(
            self.data / "fedora-nova/original", "old runtime\n", 0o600
        )
        old_runtime.parent.chmod(0o700)
        env = dict(self.env)
        env["FEDORA_NOVA_INSTALLER_TEST_FAIL_AFTER"] = "1"
        failing = self.installer(env)
        with self.assertRaises(InstallerError):
            failing.install()
        backup = failing.last_backup
        self.assertIsNotNone(backup)
        self.installer().rollback(backup)
        self.assertTrue(old_runtime.is_file())
        self.assertEqual(old_runtime.read_text(), "old runtime\n")
        self.assertEqual(stat.S_IMODE(old_runtime.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(old_runtime.parent.stat().st_mode), 0o700)
        self.assertFalse(self.context.manifest_path.exists())
        self.assertFalse((self.root / "dconf loads.log").exists())

    def test_rollback_does_not_replay_preserved_settings_over_newer_user_state(self) -> None:
        setting = self.put(self.config / "fedora-nova/current-profile", "clean\n")
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        setting.write_text("pulse\n", encoding="utf-8")
        self.installer().rollback(backup)
        self.assertEqual(setting.read_text(), "pulse\n")
        self.assertFalse((self.root / "dconf loads.log").exists())

    def test_interrupted_rollback_reports_and_can_restore_pre_rollback_state(self) -> None:
        old_runtime = self.put(self.data / "fedora-nova/original", "old runtime\n")
        original_backup = self.installer().install()
        self.assertIsNotNone(original_backup)
        env = dict(self.env)
        env["FEDORA_NOVA_INSTALLER_TEST_FAIL_AFTER"] = "1"
        output = io.StringIO()
        failing = Installer(
            InstallContext.from_environ(self.source, env),
            environ=env,
            stream=output,
        )
        with self.assertRaises(InstallerError):
            failing.rollback(original_backup)
        safety = failing.last_backup
        self.assertIsNotNone(safety)
        self.assertIn("Pre-rollback backup", output.getvalue())
        self.installer().rollback(safety)
        self.assertTrue(self.installer().validate(emit=False).ok)
        self.installer().rollback(original_backup)
        self.assertEqual(old_runtime.read_text(), "old runtime\n")

    def test_backup_copy_mismatch_aborts_before_install_mutation(self) -> None:
        target = self.put(self.prefix / "bin/fedora-nova", "original\n", 0o755)
        old_state = self.put(
            self.context.install_state_path,
            '{"status": "previous"}\n',
        )
        old_state_bytes = old_state.read_bytes()

        def corrupt_copy(source: Path, destination: Path) -> None:
            copy_path_nofollow(source, destination)
            if source == target:
                destination.write_text("corrupt\n", encoding="utf-8")

        with mock.patch("installer.engine.copy_path_nofollow", side_effect=corrupt_copy):
            with self.assertRaisesRegex(InstallerError, "Backup verification failed"):
                self.installer().install()
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse((self.data / "fedora-nova").exists())
        self.assertEqual(old_state.read_bytes(), old_state_bytes)

    def test_unexpected_target_owner_aborts_before_backup_or_mutation(self) -> None:
        target = self.put(self.prefix / "bin/fedora-nova", "original\n", 0o755)

        def ownership_check(path: Path) -> None:
            if path == target:
                raise InstallerError(
                    f"Refusing object not owned by the current user: {path}"
                )
            assert_owned_tree(path)

        with mock.patch(
            "installer.engine.assert_owned_tree", side_effect=ownership_check
        ):
            with self.assertRaisesRegex(InstallerError, "not owned"):
                self.installer().install()
        self.assertEqual(target.read_text(), "original\n")
        self.assertFalse((self.data / "fedora-nova").exists())
        self.assertFalse(self.context.backup_root.exists())

    def test_rollback_rejects_backup_object_path_escape_before_mutation(self) -> None:
        original = self.put(self.data / "fedora-nova/original", "old runtime\n")
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        metadata_path = backup / "backup.json"
        metadata = json.loads(metadata_path.read_text())
        entry = next(item for item in metadata["entries"] if item.get("existed"))
        entry["backup"] = "../../outside-object"
        metadata_path.write_text(json.dumps(metadata))
        installed_before = self.snapshot(self.data)
        with self.assertRaises(InstallerError):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)
        self.assertFalse(original.exists())

    def test_rollback_rejects_symlinked_backup_object_directory(self) -> None:
        self.put(self.data / "fedora-nova/original", "old runtime\n")
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        outside = self.root / "outside backup objects"
        outside.mkdir()
        objects = backup / "objects"
        shutil.rmtree(objects)
        objects.symlink_to(outside, target_is_directory=True)
        installed_before = self.snapshot(self.data)
        with self.assertRaisesRegex(InstallerError, "real directory"):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)

    def test_rollback_rejects_symlinked_dconf_directory(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        outside = self.root / "outside dconf"
        outside.mkdir()
        dconf = backup / "settings/dconf"
        shutil.rmtree(dconf)
        dconf.symlink_to(outside, target_is_directory=True)
        installed_before = self.snapshot(self.data)
        with self.assertRaisesRegex(InstallerError, "real directory"):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)

    def test_rollback_rejects_backup_identity_mismatch(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        metadata_path = backup / "backup.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["backup_id"] = "20000101-000000-000000"
        metadata_path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(InstallerError, "identity"):
            self.installer().rollback(backup)

    def test_rollback_rejects_valid_backup_copied_outside_backup_root(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        outside = self.root / backup.name
        shutil.copytree(backup, outside, symlinks=True)
        installed_before = self.snapshot(self.data)
        with self.assertRaisesRegex(InstallerError, "direct child"):
            self.installer().rollback(outside)
        self.assertEqual(self.snapshot(self.data), installed_before)

    def test_backup_name_collision_never_overwrites_existing_directory(self) -> None:
        backup_id = "20000101-000000-000000"
        existing = self.context.backup_root / backup_id
        sentinel = self.put(existing / "keep", "old backup\n")
        installer = self.installer()
        with mock.patch.object(installer, "_timestamp", return_value=backup_id):
            with self.assertRaisesRegex(InstallerError, "already exists"):
                installer._create_backup([], reason="collision-test")
        self.assertEqual(sentinel.read_text(), "old backup\n")

    def test_backup_name_collision_never_replaces_existing_symlink(self) -> None:
        backup_id = "20000101-000000-000000"
        outside = self.put(self.root / "outside backup/keep", "outside\n")
        self.context.backup_root.mkdir(parents=True)
        collision = self.context.backup_root / backup_id
        collision.symlink_to(outside.parent, target_is_directory=True)
        installer = self.installer()
        with mock.patch.object(installer, "_timestamp", return_value=backup_id):
            with self.assertRaisesRegex(InstallerError, "already exists"):
                installer._create_backup([], reason="collision-test")
        self.assertTrue(collision.is_symlink())
        self.assertEqual(outside.read_text(), "outside\n")

    def test_rollback_rejects_unregistered_target_before_file_mutation(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        metadata_path = backup / "backup.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["entries"][0]["path"] = str(self.data / "documents/unrelated")
        metadata_path.write_text(json.dumps(metadata))
        installed_before = self.snapshot(self.data)
        with self.assertRaises(InstallerError):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)

    def test_rollback_rejects_changed_dconf_target_before_file_mutation(self) -> None:
        original = self.put(self.data / "fedora-nova/original", "legacy\n")
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        metadata_path = backup / "backup.json"
        metadata = json.loads(metadata_path.read_text())
        saved = next(entry for entry in metadata["dconf"] if entry["status"] == "saved")
        saved["path"] = "/org/example/unrelated/"
        metadata_path.write_text(json.dumps(metadata))
        installed_before = self.snapshot(self.data)
        with self.assertRaises(InstallerError):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)
        self.assertFalse(original.exists())

    def test_rollback_rejects_incomplete_dconf_metadata_before_mutation(self) -> None:
        backup = self.installer().install()
        self.assertIsNotNone(backup)
        metadata_path = backup / "backup.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["dconf"].pop()
        metadata_path.write_text(json.dumps(metadata))
        installed_before = self.snapshot(self.data)
        with self.assertRaisesRegex(InstallerError, "dconf metadata is incomplete"):
            self.installer().rollback(backup)
        self.assertEqual(self.snapshot(self.data), installed_before)

    def test_user_settings_and_generated_assets_survive_install(self) -> None:
        values = {
            "current-profile": "clean\n",
            "current-hover": "none\n",
            "current-icons": "tela-steam\n",
        }
        for name, value in values.items():
            self.put(self.config / f"fedora-nova/{name}", value)
        generated = self.put(self.data / "icons/Fedora-Nova-Steam/apps/game.svg", "user generated\n")
        bms = self.put(
            self.config / "fedora-nova/integrations/blur-my-shell/previous-style-components",
            "2\n",
        )
        self.installer().install()
        for name, value in values.items():
            self.assertEqual((self.config / f"fedora-nova/{name}").read_text(), value)
        self.assertEqual(generated.read_text(), "user generated\n")
        self.assertEqual(bms.read_text(), "2\n")

    def test_dry_run_performs_no_writes_or_removals(self) -> None:
        stale = self.put(self.data / "themes/Fedora-Nova/stale", "old\n")
        third_party = self.put(self.data / "themes/Third Party/keep", "keep\n")
        before = self.snapshot(self.root)
        output = io.StringIO()
        Installer(self.context, environ=self.env, stream=output).dry_run()
        self.assertEqual(self.snapshot(self.root), before)
        self.assertTrue(stale.exists())
        self.assertTrue(third_party.exists())
        for heading in (
            "BACKUP:", "REMOVE:", "REPLACE:", "INSTALL:", "SETTINGS:",
            "UNCHANGED:", "WARNINGS:",
        ):
            self.assertIn(heading, output.getvalue())

    def test_cli_dry_run_does_not_create_python_bytecode(self) -> None:
        cli_source = self.root / "cli source"
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "installer",
            cli_source / "installer",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(
            Path(__file__).resolve().parents[1] / "install.sh",
            cli_source / "install.sh",
        )
        shutil.copy2(self.source / "VERSION", cli_source / "VERSION")
        shutil.copytree(self.source / "core", cli_source / "core", symlinks=True)
        shutil.copytree(self.source / "app", cli_source / "app", symlinks=True)
        env = dict(self.env)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run(
            [str(cli_source / "install.sh"), "--dry-run"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(cli_source.rglob("*.pyc")), [])
        self.assertEqual(list(cli_source.rglob("__pycache__")), [])

    def test_unrecognized_legacy_file_is_warned_and_preserved(self) -> None:
        desktop = self.put(
            self.data / "applications/fedora-nova-control.desktop",
            "[Desktop Entry]\nType=Application\nExec=third-party\n",
        )
        output = io.StringIO()
        installer = Installer(self.context, environ=self.env, stream=output)
        installer.install()
        self.assertTrue(desktop.is_file())
        self.assertIn("left untouched", output.getvalue())

    def test_manifest_uninstall_and_rollback_touch_only_owned_targets(self) -> None:
        neighbor = self.put(self.data / "applications/third-party.desktop", "keep\n")
        self.installer().install()
        backup = self.installer().uninstall()
        self.assertIsNotNone(backup)
        self.assertTrue(neighbor.is_file())
        self.assertFalse((self.data / "fedora-nova").exists())
        self.installer().rollback(backup)
        self.assertTrue((self.data / "fedora-nova/core/nova").is_file())
        self.assertTrue(neighbor.is_file())
        self.assertTrue(self.installer().validate(emit=False).ok)

    def test_uninstall_dry_run_is_pure(self) -> None:
        self.installer().install()
        before = self.snapshot(self.root)
        output = io.StringIO()
        Installer(self.context, environ=self.env, stream=output).uninstall(dry_run=True)
        self.assertEqual(self.snapshot(self.root), before)
        self.assertIn("BACKUP:", output.getvalue())
        self.assertIn("REMOVE:", output.getvalue())

    def test_uninstall_rejects_unregistered_manifest_target_before_mutation(self) -> None:
        self.installer().install()
        unrelated = self.put(self.data / "documents/important.txt", "keep\n")
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"][0].update(
            {
                "path": str(unrelated),
                "type": "file",
                "fingerprint": tree_fingerprint(unrelated),
            }
        )
        self.context.manifest_path.write_text(json.dumps(manifest))
        managed_before = self.snapshot(self.data / "fedora-nova")
        with self.assertRaisesRegex(InstallerError, "not an exact current"):
            self.installer().uninstall()
        self.assertEqual(unrelated.read_text(), "keep\n")
        self.assertEqual(self.snapshot(self.data / "fedora-nova"), managed_before)

    def test_uninstall_rejects_registered_looking_user_theme_from_manifest(self) -> None:
        self.installer().install()
        user_theme = self.put(
            self.data / "themes/Fedora-Nova-Personal/marker", "keep\n"
        )
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"][0] = {
            "path": str(user_theme.parent),
            "component": "shell-theme",
            "type": "directory",
            "fingerprint": tree_fingerprint(user_theme.parent),
            "entries": [],
        }
        self.context.manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(InstallerError, "not an exact current"):
            self.installer().uninstall()
        self.assertEqual(user_theme.read_text(), "keep\n")

    def test_uninstall_rejects_incomplete_manifest(self) -> None:
        self.installer().install()
        manifest = json.loads(self.context.manifest_path.read_text())
        manifest["managed_targets"].pop()
        self.context.manifest_path.write_text(json.dumps(manifest))
        runtime_before = self.snapshot(self.data / "fedora-nova")
        with self.assertRaisesRegex(InstallerError, "incomplete"):
            self.installer().uninstall()
        self.assertEqual(self.snapshot(self.data / "fedora-nova"), runtime_before)

    def test_uninstall_rejects_modified_managed_tree_as_possible_user_data(self) -> None:
        self.installer().install()
        added = self.put(self.data / "fedora-nova/user-note.txt", "keep\n")
        with self.assertRaisesRegex(InstallerError, "possible user data"):
            self.installer().uninstall()
        self.assertEqual(added.read_text(), "keep\n")
        self.assertTrue(self.context.manifest_path.is_file())

    def test_interrupted_uninstall_has_working_rollback_backup(self) -> None:
        self.installer().install()
        env = dict(self.env)
        env["FEDORA_NOVA_INSTALLER_TEST_FAIL_AFTER"] = "2"
        output = io.StringIO()
        failing = Installer(
            InstallContext.from_environ(self.source, env),
            environ=env,
            stream=output,
        )
        with self.assertRaises(InstallerError):
            failing.uninstall()
        self.assertIsNotNone(failing.last_backup)
        self.assertIn("Uninstall failed. Backup:", output.getvalue())
        self.assertIn("Rollback command:", output.getvalue())
        self.installer().rollback(failing.last_backup)
        self.assertTrue((self.data / "fedora-nova/core/nova").is_file())
        self.assertTrue(self.installer().validate(emit=False).ok)


if __name__ == "__main__":
    unittest.main()
