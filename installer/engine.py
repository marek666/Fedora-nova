from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import platform
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterable, TextIO

from .model import (
    FORMAT_VERSION,
    Artifact,
    CleanupCandidate,
    InstallContext,
    InstallerError,
    assert_owned_tree,
    atomic_replace,
    atomic_write_json,
    copy_path_nofollow,
    describe_tree,
    lexists,
    load_json,
    path_kind,
    safe_remove,
    sha256_file,
    tree_fingerprint,
)
from .payload import PTYXIS_PALETTES, TELA_THEMES, THEMES, TOPBAR_UUID, artifacts, build_payload


INSTALLER_VERSION = "2"
LEGACY_PALETTE_SHA256 = "675966d3d4bd29309c61055236ab254def68111eea8de225fa2a21755e4cb0d3"
BACKUP_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{6}$")

SETTING_NAMES = (
    "current-profile",
    "previous-profile",
    "current-dock",
    "previous-dock",
    "current-motion",
    "previous-motion",
    "current-curve",
    "previous-curve",
    "current-icons",
    "current-hover",
    "previous-hover",
    "current-gtk",
)

DCONF_PATHS = {
    "interface": "/org/gnome/desktop/interface/",
    "wm-preferences": "/org/gnome/desktop/wm/preferences/",
    "background": "/org/gnome/desktop/background/",
    "screensaver": "/org/gnome/desktop/screensaver/",
    "shell": "/org/gnome/shell/",
    "user-theme": "/org/gnome/shell/extensions/user-theme/",
    "dash-to-dock": "/org/gnome/shell/extensions/dash-to-dock/",
    "blur-my-shell": "/org/gnome/shell/extensions/blur-my-shell/",
}


@dataclass
class Plan:
    backup: list[Path] = field(default_factory=list)
    remove: list[CleanupCandidate] = field(default_factory=list)
    replace: list[Artifact] = field(default_factory=list)
    install: list[Artifact] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    settings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class Reporter:
    def __init__(self, stream: TextIO, log_path: Path | None = None) -> None:
        self.stream = stream
        self.log_path = log_path
        self._log: TextIO | None = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = log_path.open("x", encoding="utf-8")

    def close(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None

    def line(self, text: str = "") -> None:
        print(text, file=self.stream)
        if self._log is not None:
            print(text, file=self._log, flush=True)

    def stage(self, name: str) -> None:
        self.line(f"\n== {name} ==")

    def warning(self, text: str) -> None:
        self.line(f"WARNING: {text}")


class Installer:
    def __init__(
        self,
        context: InstallContext,
        *,
        environ: dict[str, str] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        import sys

        self.context = context
        self.environ = dict(os.environ if environ is None else environ)
        self.stream = sys.stdout if stream is None else stream
        self.reporter = Reporter(self.stream)
        self.last_backup: Path | None = None
        self._mutation_count = 0

    def _artifact_fingerprint(self, path: Path, component: str) -> str:
        ignored = frozenset({"icon-theme.cache"}) if component == "icon-theme" else frozenset()
        return tree_fingerprint(path, ignored_names=ignored)

    def _artifact_entries(self, path: Path, component: str) -> list[dict[str, Any]]:
        ignored = frozenset({"icon-theme.cache"}) if component == "icon-theme" else frozenset()
        return describe_tree(path, ignored_names=ignored)

    def _prepare_state_root(self) -> None:
        context = self.context
        context.assert_safe_target(context.state_dir, allow_leaf_symlink=False)
        context.state_dir.mkdir(parents=True, exist_ok=True)
        for path in (context.state_dir, context.backup_root, context.log_root):
            context.assert_safe_target(path, allow_leaf_symlink=False)
            if not lexists(path):
                continue
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o022
            ):
                raise InstallerError(
                    f"Installer state directory ownership or mode is unsafe: {path}"
                )

    def _preflight_state_files(self) -> None:
        for path in (self.context.manifest_path, self.context.install_state_path):
            self.context.assert_safe_target(path)
            if lexists(path) and path_kind(path) not in {"file", "symlink"}:
                raise InstallerError(
                    f"Installer state file path has an unexpected type: {path}"
                )

    def _acquire_transaction_lock(self) -> int:
        lock_path = self.context.state_dir / ".installer-v2.lock"
        self.context.assert_safe_target(lock_path, allow_leaf_symlink=False)
        try:
            fd = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
            )
        except OSError as exc:
            raise InstallerError(f"Cannot open installer transaction lock: {lock_path}") from exc
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or info.st_mode & 0o022
            ):
                raise InstallerError(f"Unsafe installer transaction lock: {lock_path}")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstallerError(
                    "Another Fedora Nova install, rollback, or uninstall is already running"
                ) from exc
            return fd
        except Exception:
            os.close(fd)
            raise

    def _release_transaction_lock(self, fd: int | None) -> None:
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _rollback_command(self, backup: Path) -> str:
        return f"./install.sh --rollback {shlex.quote(str(backup))}"

    def _project_version(self) -> str:
        path = self.context.source_root / "VERSION"
        if not path.is_file() or path.is_symlink():
            raise InstallerError(f"Missing safe VERSION file: {path}")
        return path.read_text(encoding="utf-8").strip()

    def _git_commit(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.context.source_root,
            env=self.environ,
            text=True,
            capture_output=True,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def _command(self, name: str) -> str | None:
        return shutil.which(name, path=self.environ.get("PATH"))

    def _run(
        self,
        argv: list[str],
        *,
        input_text: str | None = None,
        required: bool = False,
    ) -> subprocess.CompletedProcess[str] | None:
        command = self._command(argv[0])
        if command is None:
            if required:
                raise InstallerError(f"Required command is unavailable: {argv[0]}")
            self.reporter.warning(f"Command unavailable; skipped: {argv[0]}")
            return None
        result = subprocess.run(
            [command, *argv[1:]],
            env=self.environ,
            text=True,
            input=input_text,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            if required:
                raise InstallerError(f"Command failed ({' '.join(argv)}): {detail}")
            self.reporter.warning(f"Command failed ({' '.join(argv)}): {detail}")
        return result

    def _legacy_candidates(self) -> list[CleanupCandidate]:
        data = self.context.data_home
        config = self.context.config_home
        home = self.context.home
        candidates = [
            CleanupCandidate("obsolete-shell-theme", data / "themes/Fedora-Nova"),
            CleanupCandidate(
                "legacy-settings-desktop",
                data / "applications/fedora-nova-control.desktop",
                "legacy-desktop",
            ),
            CleanupCandidate(
                "legacy-ptyxis-palette",
                data / "org.gnome.Ptyxis/palettes/Fedora Nova.palette",
                "legacy-palette",
            ),
            CleanupCandidate("legacy-bundled-config", config / "fedora-nova/colors.json"),
            CleanupCandidate("legacy-bundled-config", config / "fedora-nova/profiles.json"),
            CleanupCandidate("legacy-bundled-config", config / "fedora-nova/curves.json"),
        ]
        for theme in ("Fedora-Nova", *THEMES):
            candidates.append(
                CleanupCandidate("legacy-dot-theme", home / f".themes/{theme}")
            )
        themes_dir = data / "themes"
        if themes_dir.is_dir() and not themes_dir.is_symlink():
            desired_themes = set(THEMES)
            for path in themes_dir.glob("Fedora-Nova-*"):
                if path.name not in desired_themes and not path.name.startswith("Fedora-Nova-Custom-"):
                    candidates.append(
                        CleanupCandidate("stale-shell-theme", path, "uncertain")
                    )
        wallpaper_dir = data / "backgrounds/fedora-nova"
        source_wallpapers = self.context.source_root / "core/assets/wallpapers"
        desired_wallpapers = {
            path.name
            for path in source_wallpapers.iterdir()
            if path.is_file() and not path.is_symlink()
        } if source_wallpapers.is_dir() else set()
        if wallpaper_dir.is_dir() and not wallpaper_dir.is_symlink():
            for path in wallpaper_dir.glob("fedora-nova-*"):
                if path.name not in desired_wallpapers:
                    candidates.append(
                        CleanupCandidate("stale-wallpaper", path, "uncertain")
                    )
        palette_dir = data / "org.gnome.Ptyxis/palettes"
        if palette_dir.is_dir() and not palette_dir.is_symlink():
            for path in palette_dir.glob("Fedora Nova *.palette"):
                if path.name not in PTYXIS_PALETTES and not path.name.startswith("Fedora Nova Custom ") and path.name != "Fedora Nova.palette":
                    candidates.append(
                        CleanupCandidate("stale-ptyxis-palette", path, "uncertain")
                    )
        return candidates

    def _is_owned_legacy(self, candidate: CleanupCandidate) -> bool:
        path = candidate.target
        if not lexists(path):
            return False
        if candidate.ownership == "known":
            return True
        if path.is_symlink() or not path.is_file():
            return False
        if candidate.ownership == "legacy-desktop":
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return False
            return (
                "Type=Application" in text
                and "Icon=fedora-nova" in text
                and ("Exec=fedora-nova settings" in text or "Exec=fedora-nova control" in text)
            )
        if candidate.ownership == "legacy-palette":
            return sha256_file(path) == LEGACY_PALETTE_SHA256
        return False

    def _manifest_stale_candidates(self, desired: set[Path], warnings: list[str]) -> list[CleanupCandidate]:
        manifest = load_json(self.context.manifest_path)
        if manifest is None:
            return []
        if manifest.get("format_version") != FORMAT_VERSION:
            warnings.append(
                f"Ignoring unknown install manifest format: {self.context.manifest_path}"
            )
            return []
        stale: list[CleanupCandidate] = []
        for entry in manifest.get("managed_targets", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                warnings.append("Install manifest contains an invalid managed target entry")
                continue
            path = Path(entry["path"])
            try:
                safe = self.context.assert_safe_target(path)
            except InstallerError as exc:
                warnings.append(f"Unsafe stale manifest path ignored: {exc}")
                continue
            if not self._is_registered_managed_path(safe):
                warnings.append(
                    f"Unregistered stale manifest path ignored: {safe}"
                )
                continue
            if safe not in desired:
                component = entry.get("component")
                expected_type = entry.get("type")
                expected_fingerprint = entry.get("fingerprint")
                if (
                    not isinstance(component, str)
                    or expected_type not in {"file", "directory", "symlink"}
                    or not isinstance(expected_fingerprint, str)
                    or not lexists(safe)
                    or path_kind(safe) != expected_type
                    or self._artifact_fingerprint(safe, component)
                    != expected_fingerprint
                ):
                    warnings.append(
                        f"Stale manifest ownership evidence does not match; "
                        f"path left untouched: {safe}"
                    )
                    continue
                stale.append(CleanupCandidate("stale-manifest-target", safe, "manifest"))
        return stale

    def _is_registered_managed_path(self, path: Path) -> bool:
        """Accept only product-specific destinations, even when a manifest is corrupt."""
        context = self.context
        if path in {artifact.target for artifact in artifacts(context)}:
            return True
        data = context.data_home
        home = context.home
        parent_rules = (
            (data / "themes", "Fedora-Nova-", "Fedora-Nova-Custom-"),
            (data / "backgrounds/fedora-nova", "fedora-nova-", "custom-"),
            (data / "org.gnome.Ptyxis/palettes", "Fedora Nova ", "Fedora Nova Custom "),
            (home / ".themes", "Fedora-Nova-", "Fedora-Nova-Custom-"),
        )
        if path in {
            data / "themes/Fedora-Nova",
            home / ".themes/Fedora-Nova",
            data / "applications/fedora-nova-control.desktop",
            data / "icons/hicolor/scalable/apps/fedora-nova.svg",
            data / "icons/hicolor/scalable/apps/io.github.fedoranova.FedoraNova.Devel.svg",
            data / "org.gnome.Ptyxis/palettes/Fedora Nova.palette",
            context.config_home / "fedora-nova/colors.json",
            context.config_home / "fedora-nova/profiles.json",
            context.config_home / "fedora-nova/curves.json",
        }:
            return True
        return any(
            path.parent == parent
            and path.name.startswith(prefix)
            and not path.name.startswith(excluded)
            for parent, prefix, excluded in parent_rules
        )

    def _is_registered_transaction_path(self, path: Path) -> bool:
        return self._is_registered_managed_path(path) or path in {
            *self._shared_cache_targets(),
            self.context.manifest_path,
            self.context.install_state_path,
        }

    def _is_registered_setting_path(self, path: Path) -> bool:
        context = self.context
        config = context.config_home / "fedora-nova"
        if path in {
            *(config / name for name in SETTING_NAMES),
            config / "custom-profiles",
            config / "integrations/blur-my-shell",
            config / "session-restore",
            context.config_home / "autostart/fedora-nova-session.desktop",
            context.config_home / "gtk-3.0/gtk.css",
            context.config_home / "gtk-4.0/gtk.css",
            context.config_home / "gnome-initial-setup-done",
            context.data_home / "icons/Fedora-Nova-Steam",
            context.state_dir / "steam-icons",
        }:
            return True
        autostart = context.config_home / "autostart"
        if path.parent == autostart and path.name in {
            "org.gnome.Tour.desktop",
            "gnome-tour.desktop",
            "gnome-initial-setup.desktop",
            "gnome-initial-setup-first-login.desktop",
            "fedora-welcome.desktop",
            "org.fedoraproject.Welcome.desktop",
            "liveinst-setup.desktop",
        }:
            return True
        return (
            path.parent == context.data_home / "themes"
            and path.name.startswith("Fedora-Nova-Custom-")
        ) or (
            path.parent == context.data_home / "backgrounds/fedora-nova"
            and path.name.startswith("custom-")
            and path.suffix == ".svg"
        ) or (
            path.parent == context.data_home / "org.gnome.Ptyxis/palettes"
            and path.name.startswith("Fedora Nova Custom ")
            and path.suffix == ".palette"
        )

    def _settings_sources(self) -> list[tuple[str, Path]]:
        config = self.context.config_home / "fedora-nova"
        result = [(name, config / name) for name in SETTING_NAMES]
        result.extend(
            [
                ("custom-profiles", config / "custom-profiles"),
                ("blur-my-shell-integration", config / "integrations/blur-my-shell"),
                ("session-restore", config / "session-restore"),
                (
                    "session-autostart",
                    self.context.config_home / "autostart/fedora-nova-session.desktop",
                ),
                ("custom-themes", self.context.data_home / "themes"),
                (
                    "custom-wallpapers",
                    self.context.data_home / "backgrounds/fedora-nova",
                ),
                (
                    "custom-palettes",
                    self.context.data_home / "org.gnome.Ptyxis/palettes",
                ),
                ("generated-steam-icons", self.context.data_home / "icons/Fedora-Nova-Steam"),
                ("steam-icon-state", self.context.state_dir / "steam-icons"),
                ("gtk3-user-css", self.context.config_home / "gtk-3.0/gtk.css"),
                ("gtk4-user-css", self.context.config_home / "gtk-4.0/gtk.css"),
                ("initial-setup-marker", self.context.config_home / "gnome-initial-setup-done"),
            ]
        )
        for desktop_id in (
            "org.gnome.Tour.desktop",
            "gnome-tour.desktop",
            "gnome-initial-setup.desktop",
            "gnome-initial-setup-first-login.desktop",
            "fedora-welcome.desktop",
            "org.fedoraproject.Welcome.desktop",
            "liveinst-setup.desktop",
        ):
            result.append(
                (
                    f"welcome-mask-{desktop_id}",
                    self.context.config_home / f"autostart/{desktop_id}",
                )
            )
        return result

    def _setting_paths_for_backup(self) -> list[tuple[str, Path]]:
        result: list[tuple[str, Path]] = []
        for name, path in self._settings_sources():
            if name == "custom-themes":
                if path.is_dir() and not path.is_symlink():
                    for child in sorted(path.glob("Fedora-Nova-Custom-*")):
                        if child.is_dir() and not child.is_symlink():
                            result.append((f"custom-theme-{child.name}", child))
                continue
            if name == "custom-wallpapers":
                if path.is_dir() and not path.is_symlink():
                    for child in sorted(path.glob("custom-*.svg")):
                        if child.is_file() and not child.is_symlink():
                            result.append((f"custom-wallpaper-{child.name}", child))
                continue
            if name == "custom-palettes":
                if path.is_dir() and not path.is_symlink():
                    for child in sorted(path.glob("Fedora Nova Custom *.palette")):
                        if child.is_file() and not child.is_symlink():
                            result.append((f"custom-palette-{child.name}", child))
                continue
            result.append((name, path))
        return result

    def _suspicious_state(self) -> list[str]:
        warnings: list[str] = []
        legacy_icons = self.context.home / ".icons"
        if legacy_icons.is_dir() and not legacy_icons.is_symlink():
            for name in (*TELA_THEMES, "Fedora-Nova-Steam"):
                path = legacy_icons / name
                if lexists(path):
                    warnings.append(
                        f"Unmanaged legacy icon path left untouched (ownership unknown): {path}"
                    )
        for uuid in ("dash-to-dock@micxgx.gmail.com", "blur-my-shell@aunetx"):
            path = self.context.data_home / f"gnome-shell/extensions/{uuid}"
            if lexists(path):
                warnings.append(f"Third-party extension intentionally left untouched: {path}")
        preview = self.context.cache_home / "fedora-nova-shell-preview"
        if lexists(preview):
            warnings.append(f"Preview state intentionally outside host installer scope: {preview}")
        return warnings

    def discover(self) -> Plan:
        desired_artifacts = artifacts(self.context)
        desired = {item.target for item in desired_artifacts}
        plan = Plan()
        manifest = load_json(self.context.manifest_path)
        current_commit = self._git_commit()
        manifest_current = bool(
            manifest
            and manifest.get("format_version") == FORMAT_VERSION
            and manifest.get("git_commit") == current_commit
        )

        for artifact in desired_artifacts:
            self.context.assert_safe_target(artifact.target)
            if lexists(artifact.target):
                if manifest_current:
                    entry = next(
                        (
                            item
                            for item in manifest.get("managed_targets", [])
                            if isinstance(item, dict) and item.get("path") == str(artifact.target)
                        ),
                        None,
                    )
                    if entry and entry.get("fingerprint") == self._artifact_fingerprint(
                        artifact.target, artifact.component
                    ):
                        plan.unchanged.append(f"{artifact.component}: {artifact.target}")
                        continue
                plan.replace.append(artifact)
                plan.backup.append(artifact.target)
            else:
                plan.install.append(artifact)

        candidates = self._manifest_stale_candidates(desired, plan.warnings)
        candidates.extend(self._legacy_candidates())
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate.target in seen or candidate.target in desired or not lexists(candidate.target):
                continue
            seen.add(candidate.target)
            self.context.assert_safe_target(candidate.target)
            if self._is_owned_legacy(candidate) or candidate.ownership == "manifest":
                plan.remove.append(candidate)
                plan.backup.append(candidate.target)
            else:
                plan.warnings.append(
                    f"Unrecognized file at a legacy Fedora Nova path; left untouched: {candidate.target}"
                )

        plan.settings.extend(
            [f"export dconf {path}" for path in DCONF_PATHS.values()]
        )
        for name, path in self._settings_sources():
            plan.settings.append(f"preserve {name}: {path}")
        plan.unchanged.extend(
            [
                f"user configuration: {self.context.config_home / 'fedora-nova'}",
                f"generated Steam icon theme: {self.context.data_home / 'icons/Fedora-Nova-Steam'}",
                f"Dash to Dock extension files: {self.context.data_home / 'gnome-shell/extensions/dash-to-dock@micxgx.gmail.com'}",
                f"Blur My Shell extension files: {self.context.data_home / 'gnome-shell/extensions/blur-my-shell@aunetx'}",
                f"Preview workspace: {self.context.cache_home / 'fedora-nova-shell-preview'}",
                "/usr and other system-level paths",
            ]
        )
        plan.warnings.extend(self._suspicious_state())
        if plan.install or plan.replace or plan.remove:
            for path in [
                *self._shared_cache_targets(),
                self.context.manifest_path,
                self.context.install_state_path,
            ]:
                if lexists(path) and path not in plan.backup:
                    plan.backup.append(path)
        return plan

    def print_plan(self, plan: Plan) -> None:
        groups: list[tuple[str, Iterable[str]]] = [
            ("BACKUP", (str(path) for path in plan.backup)),
            ("REMOVE", (f"{item.component}: {item.target}" for item in plan.remove)),
            ("REPLACE", (f"{item.component}: {item.target}" for item in plan.replace)),
            ("INSTALL", (f"{item.component}: {item.target}" for item in plan.install)),
            ("SETTINGS", iter(plan.settings)),
            ("UNCHANGED", iter(plan.unchanged)),
            ("WARNINGS", iter(plan.warnings)),
        ]
        for title, values in groups:
            self.reporter.line(f"{title}:")
            rendered = list(values)
            if not rendered:
                self.reporter.line("  (none)")
            else:
                for value in rendered:
                    self.reporter.line(f"  {value}")

    def dry_run(self) -> Plan:
        # Discovery is deliberately read-only: no log, state, temporary payload,
        # dconf subprocess, mkdir, or cache update is allowed here.
        plan = self.discover()
        self.print_plan(plan)
        return plan

    def _system_metadata(self) -> dict[str, str]:
        os_release = "unknown"
        try:
            values: dict[str, str] = {}
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value.strip('"')
            os_release = values.get("PRETTY_NAME", values.get("NAME", "unknown"))
        except OSError:
            pass
        gnome = "unavailable"
        command = self._command("gnome-shell")
        if command:
            result = subprocess.run(
                [command, "--version"], env=self.environ, text=True, capture_output=True
            )
            if result.returncode == 0:
                gnome = result.stdout.strip()
        return {
            "fedora": os_release,
            "gnome": gnome,
            "kernel": platform.release(),
        }

    def _dump_dconf(self, destination: Path) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        command = self._command("dconf")
        for name, dconf_path in DCONF_PATHS.items():
            record = {"name": name, "path": dconf_path, "status": "unavailable"}
            if command:
                result = subprocess.run(
                    [command, "dump", dconf_path],
                    env=self.environ,
                    text=True,
                    capture_output=True,
                )
                if result.returncode == 0:
                    target = destination / f"{name}.dconf"
                    target.write_text(result.stdout, encoding="utf-8")
                    record["status"] = "saved"
                    record["file"] = target.name
                    record["sha256"] = sha256_file(target)
                else:
                    record["status"] = "failed"
                    record["error"] = result.stderr.strip()
            records.append(record)
        return records

    def _copy_backup_object(self, source: Path, destination: Path) -> tuple[str, str]:
        """Copy one object and prove that the backup matches a stable source view."""
        assert_owned_tree(source)
        original_type = path_kind(source)
        original_fingerprint = tree_fingerprint(source)
        copy_path_nofollow(source, destination)
        backup_fingerprint = tree_fingerprint(destination)
        try:
            current_type = path_kind(source)
            current_fingerprint = tree_fingerprint(source)
        except OSError as exc:
            raise InstallerError(
                f"Backup source changed or disappeared while being copied: {source}"
            ) from exc
        if (
            current_type != original_type
            or current_fingerprint != original_fingerprint
            or backup_fingerprint != original_fingerprint
        ):
            raise InstallerError(
                f"Backup verification failed because the source changed or the copy differs: {source}"
            )
        return original_type, original_fingerprint

    def _create_backup(
        self,
        affected: Iterable[Path],
        *,
        reason: str,
    ) -> Path:
        context = self.context
        self._prepare_state_root()
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in affected:
            safe = context.assert_safe_target(path)
            if safe not in seen:
                seen.add(safe)
                unique.append(safe)
        setting_paths: list[tuple[str, Path]] = []
        for name, path in self._setting_paths_for_backup():
            try:
                safe = context.assert_safe_target(path)
            except InstallerError as exc:
                raise InstallerError(
                    f"Cannot safely back up preserved user setting {name}: {exc}"
                ) from exc
            setting_paths.append((name, safe))

        # Establish ownership for every source before creating even a partial
        # backup. Any unexpected owner aborts the transaction without touching
        # the existing manifest or install state.
        for path in [*unique, *(path for _, path in setting_paths)]:
            if lexists(path):
                assert_owned_tree(path)

        context.backup_root.mkdir(parents=True, exist_ok=True)
        self._prepare_state_root()
        backup_id = self._timestamp()
        temporary = context.backup_root / f".{backup_id}.incomplete"
        final = context.backup_root / backup_id
        temporary.mkdir(mode=0o700)
        if lexists(final):
            raise InstallerError(f"Backup already exists: {final}")
        objects = temporary / "objects"
        settings_dir = temporary / "settings/files"
        dconf_dir = temporary / "settings/dconf"
        objects.mkdir(parents=True)
        settings_dir.mkdir(parents=True)
        dconf_dir.mkdir(parents=True)

        entries: list[dict[str, Any]] = []
        for index, path in enumerate(unique):
            entry: dict[str, Any] = {"path": str(path), "existed": lexists(path)}
            if lexists(path):
                ref = f"objects/{index:04d}"
                backup_object = temporary / ref
                object_type, fingerprint = self._copy_backup_object(
                    path, backup_object
                )
                entry.update(
                    {
                        "backup": ref,
                        "type": object_type,
                        "fingerprint": fingerprint,
                        "backup_fingerprint": fingerprint,
                    }
                )
            entries.append(entry)

        settings: list[dict[str, Any]] = []
        for index, (name, safe) in enumerate(setting_paths):
            entry = {"name": name, "path": str(safe), "existed": lexists(safe)}
            if lexists(safe):
                ref = f"settings/files/{index:04d}"
                backup_object = temporary / ref
                object_type, fingerprint = self._copy_backup_object(
                    safe, backup_object
                )
                entry.update(
                    {
                        "backup": ref,
                        "type": object_type,
                        "fingerprint": fingerprint,
                        "backup_fingerprint": fingerprint,
                    }
                )
            settings.append(entry)

        metadata = {
            "format_version": FORMAT_VERSION,
            "installer_version": INSTALLER_VERSION,
            "backup_id": backup_id,
            "reason": reason,
            "created_at": self._iso_now(),
            "project_version": self._project_version(),
            "git_commit": self._git_commit(),
            "system": self._system_metadata(),
            "entries": entries,
            "settings": settings,
            "dconf": self._dump_dconf(dconf_dir),
        }
        (temporary / "backup.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, final)
        self.last_backup = final
        return final

    def _shared_cache_targets(self) -> list[Path]:
        data = self.context.data_home
        return [
            data / "glib-2.0/schemas/gschemas.compiled",
            data / "icons/hicolor/icon-theme.cache",
            data / "applications/mimeinfo.cache",
        ]

    def _refresh_caches(self) -> None:
        if self.context.testing and self.environ.get("FEDORA_NOVA_TEST_RUN_CACHES") != "1":
            self.reporter.line("Testing mode: shared desktop cache refresh skipped.")
            return
        data = self.context.data_home
        commands = [
            ["glib-compile-schemas", str(data / "glib-2.0/schemas")],
            ["gtk-update-icon-cache", "-f", "-t", str(data / "icons/hicolor")],
            ["update-desktop-database", str(data / "applications")],
        ]
        commands.extend(
            ["gtk-update-icon-cache", "-f", "-t", str(data / f"icons/{theme}")]
            for theme in TELA_THEMES
        )
        for command in commands:
            self._run(command, required=False)

    def _validate_user_settings(self) -> list[str]:
        warnings: list[str] = []
        config = self.context.config_home / "fedora-nova"
        constraints = {
            "current-profile": {"tech", "clean", "midnight", "glass-lite", "pulse", "system"},
            "current-curve": {"squircle", "round", "rounded", "none"},
            "current-hover": {"circle", "none"},
            "current-gtk": {"on", "off"},
        }
        for name, allowed in constraints.items():
            path = config / name
            if not path.is_file() or path.is_symlink():
                continue
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                warnings.append(f"Cannot read preserved setting {path}: {exc}")
                continue
            if value not in allowed and not (name == "current-profile" and (config / f"custom-profiles/{value}.json").is_file()):
                warnings.append(
                    f"Preserved setting is not recognized by this version: {path}={value!r}"
                )
        return warnings

    def _failpoint(self) -> None:
        self._mutation_count += 1
        if not self.context.testing:
            return
        raw = self.environ.get("FEDORA_NOVA_INSTALLER_TEST_FAIL_AFTER")
        if raw and self._mutation_count >= int(raw):
            raise InstallerError(f"Injected test failure after mutation {self._mutation_count}")

    def _reset_transaction_state(self) -> None:
        self.last_backup = None
        self._mutation_count = 0

    def install(self) -> Path | None:
        self._reset_transaction_state()
        context = self.context
        # Complete the read-only path preflight before creating logs or state.
        self.discover()
        self._preflight_state_files()
        self._prepare_state_root()
        lock_fd = self._acquire_transaction_lock()
        try:
            return self._install_locked()
        finally:
            self._release_transaction_lock(lock_fd)

    def _install_locked(self) -> Path | None:
        context = self.context
        # Repeat discovery under the transaction lock so no concurrent Fedora
        # Nova transaction can invalidate the ownership plan.
        initial = self.discover()
        self._preflight_state_files()
        log_path = context.log_root / f"install-{self._timestamp()}.log"
        self.reporter.close()
        self.reporter = Reporter(self.stream, log_path)
        self.reporter.line(f"Fedora Nova Installer V2 log: {log_path}")
        self.reporter.line(f"Installer version: {INSTALLER_VERSION}")
        self.reporter.line(f"Project version: {self._project_version()}")
        self.reporter.line(f"Git commit: {self._git_commit()}")

        backup: Path | None = None
        try:
            self.reporter.stage("DISCOVER")
            for warning in initial.warnings:
                self.reporter.warning(warning)

            work_root = context.state_dir / ".installer-work"
            context.assert_safe_target(work_root, allow_leaf_symlink=False)
            work_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="install-", dir=work_root) as temp:
                payload = Path(temp) / "payload"
                self.reporter.stage("BUILD CURRENT PAYLOAD")
                desired = build_payload(context, payload)

                changed: list[Artifact] = []
                unchanged: list[Artifact] = []
                for artifact in desired:
                    source = payload / artifact.payload_name
                    context.assert_safe_target(artifact.target)
                    if lexists(artifact.target) and self._artifact_fingerprint(
                        source, artifact.component
                    ) == self._artifact_fingerprint(artifact.target, artifact.component):
                        unchanged.append(artifact)
                    else:
                        changed.append(artifact)

                desired_paths = {artifact.target for artifact in desired}
                cleanup_warnings: list[str] = []
                cleanup = self._manifest_stale_candidates(
                    desired_paths, cleanup_warnings
                )
                cleanup.extend(self._legacy_candidates())
                removable: list[CleanupCandidate] = []
                seen: set[Path] = set()
                for candidate in cleanup:
                    if candidate.target in seen or candidate.target in desired_paths or not lexists(candidate.target):
                        continue
                    seen.add(candidate.target)
                    context.assert_safe_target(candidate.target)
                    if self._is_owned_legacy(candidate) or candidate.ownership == "manifest":
                        removable.append(candidate)
                    else:
                        cleanup_warnings.append(
                            f"Unrecognized legacy path left untouched: {candidate.target}"
                        )
                for warning in cleanup_warnings:
                    self.reporter.warning(warning)

                previous_manifest = load_json(context.manifest_path)
                previous_paths = {
                    Path(entry["path"])
                    for entry in (
                        previous_manifest.get("managed_targets", [])
                        if previous_manifest
                        and isinstance(previous_manifest.get("managed_targets"), list)
                        else []
                    )
                    if isinstance(entry, dict)
                    and isinstance(entry.get("path"), str)
                }
                manifest_current = bool(
                    previous_manifest
                    and previous_manifest.get("format_version") == FORMAT_VERSION
                    and previous_manifest.get("git_commit") == self._git_commit()
                    and previous_manifest.get("project_version") == self._project_version()
                    and previous_paths == desired_paths
                )
                file_changes = bool(changed or removable)
                transaction_required = file_changes or not manifest_current

                affected = [artifact.target for artifact in changed]
                affected.extend(candidate.target for candidate in removable)
                if file_changes:
                    affected.extend(self._shared_cache_targets())
                if transaction_required:
                    affected.extend([context.manifest_path, context.install_state_path])

                if transaction_required:
                    self.reporter.stage("BACKUP")
                    backup = self._create_backup(affected, reason="install")
                    self.reporter.line(f"Backup: {backup}")
                else:
                    self.reporter.stage("BACKUP")
                    self.reporter.line("No managed file changes; no backup required.")

                self.reporter.stage("CLEAN OLD FEDORA NOVA")
                for candidate in removable:
                    self.reporter.line(f"REMOVE {candidate.component}: {candidate.target}")
                    safe_remove(context, candidate.target)
                    self._failpoint()
                if not removable:
                    self.reporter.line("No owned legacy paths require removal.")

                self.reporter.stage("FRESH INSTALL CURRENT VERSION")
                for artifact in changed:
                    action = "REPLACE" if lexists(artifact.target) else "INSTALL"
                    self.reporter.line(f"{action} {artifact.component}: {artifact.target}")
                    atomic_replace(context, payload / artifact.payload_name, artifact.target)
                    self._failpoint()
                for artifact in unchanged:
                    self.reporter.line(f"UNCHANGED {artifact.component}: {artifact.target}")

                self.reporter.stage("RESTORE / MIGRATE USER SETTINGS")
                self.reporter.line("Existing Fedora Nova preference files and targeted dconf values were preserved.")
                for warning in self._validate_user_settings():
                    self.reporter.warning(warning)

                if not transaction_required:
                    self.reporter.stage("VALIDATE")
                    report = self.validate(emit=False)
                    for warning in report.warnings:
                        self.reporter.warning(warning)
                    if not report.ok:
                        for error in report.errors:
                            self.reporter.line(f"ERROR: {error}")
                        raise InstallerError("Validation failed during idempotent reinstall")
                    self.reporter.line("Validation PASS")
                    self.reporter.stage("COMPLETE")
                    self.reporter.line("Installation already matches the current manifest.")
                    return None

                if file_changes:
                    self.reporter.stage("REFRESH DESKTOP CACHES")
                    self._refresh_caches()

                manifest_targets = []
                for artifact in desired:
                    manifest_targets.append(
                        {
                            "path": str(artifact.target),
                            "component": artifact.component,
                            "type": path_kind(artifact.target),
                            "fingerprint": self._artifact_fingerprint(
                                artifact.target, artifact.component
                            ),
                            "entries": self._artifact_entries(
                                artifact.target, artifact.component
                            ),
                        }
                    )
                manifest = {
                    "format_version": FORMAT_VERSION,
                    "installer_version": INSTALLER_VERSION,
                    "project_version": self._project_version(),
                    "git_commit": self._git_commit(),
                    "installed_at": self._iso_now(),
                    "source_root": str(context.source_root),
                    "backup": str(backup) if backup else None,
                    "managed_targets": manifest_targets,
                    "preserved_settings": [str(path) for _, path in self._settings_sources()],
                    "preview_roots_managed": False,
                }
                atomic_write_json(context, context.manifest_path, manifest)
                atomic_write_json(
                    context,
                    context.install_state_path,
                    {
                        "format_version": FORMAT_VERSION,
                        "status": "installed",
                        "validated": False,
                        "backup": str(backup) if backup else None,
                        "log": str(log_path),
                        "updated_at": self._iso_now(),
                    },
                )

            self.reporter.stage("VALIDATE")
            report = self.validate(emit=False)
            for warning in report.warnings:
                self.reporter.warning(warning)
            if not report.ok:
                for error in report.errors:
                    self.reporter.line(f"ERROR: {error}")
                raise InstallerError("Post-install validation failed")
            state = load_json(context.install_state_path) or {}
            state["validated"] = True
            state["validation_result"] = "pass"
            state["updated_at"] = self._iso_now()
            atomic_write_json(context, context.install_state_path, state)
            self.reporter.line("Validation PASS")
            self.reporter.stage("COMPLETE")
            self.reporter.line(f"Manifest: {context.manifest_path}")
            if backup:
                self.reporter.line(f"Rollback: {self._rollback_command(backup)}")
            return backup
        except Exception as exc:
            if backup or self.last_backup:
                try:
                    atomic_write_json(
                        context,
                        context.install_state_path,
                        {
                            "format_version": FORMAT_VERSION,
                            "status": "failed",
                            "backup": str(backup or self.last_backup),
                            "log": str(log_path),
                            "error": str(exc),
                            "updated_at": self._iso_now(),
                        },
                    )
                except Exception:
                    pass
            if backup or self.last_backup:
                self.reporter.line(
                    f"Installation failed. Backup: {backup or self.last_backup}"
                )
                self.reporter.line(
                    f"Rollback command: {self._rollback_command(backup or self.last_backup)}"
                )
            raise
        finally:
            work_root = context.state_dir / ".installer-work"
            if work_root.is_dir() and not any(work_root.iterdir()):
                work_root.rmdir()
            self.reporter.close()

    def _check_symlinks(self, target: Path, component: str, report: ValidationReport) -> None:
        paths = [target]
        if target.is_dir() and not target.is_symlink():
            paths.extend(target.rglob("*"))
        icon_root = self.context.data_home / "icons"
        for path in paths:
            if not path.is_symlink():
                continue
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                report.errors.append(f"Broken managed symlink: {path}")
                continue
            allowed = target
            if component == "icon-theme":
                allowed = icon_root
            if resolved != allowed and allowed not in resolved.parents:
                report.errors.append(f"Managed symlink escapes component root: {path} -> {resolved}")
            if self.context.source_root == resolved or self.context.source_root in resolved.parents:
                report.errors.append(f"Managed symlink points into source checkout: {path}")
            if "fedora-nova-shell-preview" in resolved.parts:
                report.errors.append(f"Managed symlink points into Preview state: {path}")

    def validate(self, *, emit: bool = True) -> ValidationReport:
        report = ValidationReport()
        manifest = load_json(self.context.manifest_path)
        if manifest is None:
            report.errors.append(f"Missing or invalid install manifest: {self.context.manifest_path}")
        elif manifest.get("format_version") != FORMAT_VERSION:
            report.errors.append("Unsupported install manifest format")
        else:
            expected_paths = {artifact.target for artifact in artifacts(self.context)}
            listed_paths: set[Path] = set()
            for entry in manifest.get("managed_targets", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    report.errors.append("Malformed managed target in manifest")
                    continue
                path = Path(entry["path"])
                listed_paths.add(path)
                try:
                    self.context.assert_safe_target(path)
                except InstallerError as exc:
                    report.errors.append(str(exc))
                    continue
                if not lexists(path):
                    report.errors.append(f"Missing managed target: {path}")
                    continue
                component = str(entry.get("component", "unknown"))
                actual = self._artifact_fingerprint(path, component)
                if actual != entry.get("fingerprint"):
                    report.errors.append(f"Managed target differs from manifest: {path}")
                self._check_symlinks(path, component, report)
                try:
                    if path.lstat().st_uid != os.getuid():
                        report.errors.append(f"Managed target is not owned by current user: {path}")
                except OSError as exc:
                    report.errors.append(f"Cannot stat managed target {path}: {exc}")
            for missing in sorted(expected_paths - listed_paths, key=str):
                report.errors.append(f"Expected target missing from manifest: {missing}")
            for unexpected in sorted(listed_paths - expected_paths, key=str):
                report.errors.append(f"Unexpected stale target remains in manifest: {unexpected}")

        desired = {artifact.target for artifact in artifacts(self.context)}
        for candidate in self._legacy_candidates():
            if candidate.target in desired or not lexists(candidate.target):
                continue
            if self._is_owned_legacy(candidate):
                report.errors.append(f"Owned legacy Fedora Nova path remains: {candidate.target}")
            else:
                report.warnings.append(
                    f"Unrecognized legacy path remains untouched: {candidate.target}"
                )
        report.warnings.extend(self._suspicious_state())

        gsettings = self._command("gsettings")
        if gsettings:
            checks = [
                [gsettings, "get", "org.gnome.shell.extensions.user-theme", "name"],
                [gsettings, "get", "org.gnome.desktop.interface", "icon-theme"],
                [gsettings, "get", "org.gnome.shell", "enabled-extensions"],
            ]
            for command in checks:
                result = subprocess.run(command, env=self.environ, text=True, capture_output=True)
                if result.returncode != 0:
                    report.warnings.append(f"Could not read setting: {' '.join(command[2:])}")
        else:
            report.warnings.append("gsettings unavailable; live GNOME setting checks skipped")

        if emit:
            self.reporter.stage("VALIDATE")
            for error in report.errors:
                self.reporter.line(f"ERROR: {error}")
            for warning in report.warnings:
                self.reporter.warning(warning)
            self.reporter.line("Validation PASS" if report.ok else "Validation FAIL")
        return report

    def _validated_backup(self, path: Path) -> tuple[Path, dict[str, Any]]:
        self.context.assert_safe_target(
            self.context.backup_root, allow_leaf_symlink=False
        )
        root = self.context.backup_root.resolve(strict=False)
        if not root.is_dir() or root.is_symlink():
            raise InstallerError(f"Backup root is missing or unsafe: {root}")
        if path.is_symlink():
            raise InstallerError(f"Backup path must not be a symlink: {path}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise InstallerError(f"Backup does not exist: {path}") from exc
        if resolved.parent != root:
            raise InstallerError(f"Backup must be a direct child of {root}: {resolved}")
        info = resolved.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o022
        ):
            raise InstallerError(f"Backup directory ownership or mode is unsafe: {resolved}")
        if not BACKUP_ID_RE.fullmatch(resolved.name):
            raise InstallerError(f"Backup directory name is invalid: {resolved.name}")
        metadata_path = resolved / "backup.json"
        if metadata_path.is_symlink():
            raise InstallerError("Backup metadata must not be a symlink")
        try:
            metadata_info = metadata_path.lstat()
        except OSError as exc:
            raise InstallerError(f"Backup metadata is missing: {metadata_path}") from exc
        if (
            not stat.S_ISREG(metadata_info.st_mode)
            or metadata_info.st_uid != os.getuid()
            or metadata_info.st_nlink != 1
        ):
            raise InstallerError(f"Backup metadata object is unsafe: {metadata_path}")
        metadata = load_json(metadata_path)
        if metadata is None or metadata.get("format_version") != FORMAT_VERSION:
            raise InstallerError(f"Invalid Installer V2 backup: {resolved}")
        if metadata.get("installer_version") != INSTALLER_VERSION:
            raise InstallerError(f"Backup installer version is invalid: {resolved}")
        if metadata.get("backup_id") != resolved.name:
            raise InstallerError(f"Backup identity does not match its directory: {resolved}")
        for parts in (("objects",), ("settings", "files"), ("settings", "dconf")):
            self._backup_directory(resolved, parts)
        return resolved, metadata

    def _backup_directory(self, backup: Path, parts: tuple[str, ...]) -> Path:
        current = backup
        for part in parts:
            current = current / part
            try:
                info = current.lstat()
            except OSError as exc:
                raise InstallerError(f"Backup directory is missing: {current}") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise InstallerError(f"Backup path must be a real directory: {current}")
            if info.st_uid != os.getuid():
                raise InstallerError(
                    f"Backup directory ownership is unsafe: {current}"
                )
        try:
            current.resolve(strict=True).relative_to(backup.resolve(strict=True))
        except (OSError, RuntimeError, ValueError) as exc:
            raise InstallerError(f"Backup directory escapes its root: {current}") from exc
        return current

    def _backup_object(
        self,
        backup: Path,
        reference: object,
        *,
        settings: bool = False,
    ) -> Path:
        if not isinstance(reference, str):
            raise InstallerError("Backup object reference is missing")
        relative = PurePosixPath(reference)
        expected = ("settings", "files") if settings else ("objects",)
        parts = relative.parts
        if relative.is_absolute() or ".." in parts:
            raise InstallerError(f"Unsafe backup object reference: {reference}")
        if settings:
            valid = (
                len(parts) == 3
                and parts[:2] == expected
                and re.fullmatch(r"[0-9]+", parts[2]) is not None
            )
        else:
            valid = (
                len(parts) == 2
                and parts[:1] == expected
                and re.fullmatch(r"[0-9]+", parts[1]) is not None
            )
        if not valid:
            raise InstallerError(f"Unexpected backup object reference: {reference}")
        expected_parent = self._backup_directory(backup, tuple(parts[:-1]))
        candidate = expected_parent / parts[-1]
        return candidate

    def _restore_entry(
        self,
        backup: Path,
        entry: dict[str, Any],
        *,
        settings: bool = False,
    ) -> None:
        path = Path(entry["path"])
        self.context.assert_safe_target(path)
        ref: Path | None = None
        if entry.get("existed"):
            ref = self._backup_object(
                backup, entry.get("backup"), settings=settings
            )
            if not lexists(ref):
                raise InstallerError(f"Backup object is missing: {ref}")
            assert_owned_tree(ref)
            expected = entry.get("backup_fingerprint", entry.get("fingerprint"))
            if not isinstance(expected, str) or tree_fingerprint(ref) != expected:
                raise InstallerError(f"Backup object checksum mismatch: {ref}")
            if entry.get("type") != path_kind(ref):
                raise InstallerError(f"Backup object type mismatch: {ref}")
        if lexists(path):
            safe_remove(self.context, path)
        if ref is not None:
            atomic_replace(self.context, ref, path)

    def _validated_dconf_entries(
        self, backup: Path, metadata: dict[str, Any]
    ) -> list[tuple[dict[str, Any], Path]]:
        raw = metadata.get("dconf", [])
        if not isinstance(raw, list):
            raise InstallerError("Backup dconf metadata is malformed")
        result: list[tuple[dict[str, Any], Path]] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, dict):
                raise InstallerError("Backup dconf metadata contains a malformed entry")
            entry_name = entry.get("name")
            entry_path = entry.get("path")
            if (
                not isinstance(entry_name, str)
                or DCONF_PATHS.get(entry_name) != entry_path
            ):
                raise InstallerError(
                    f"Unexpected dconf restore target: {entry_name!r} {entry_path!r}"
                )
            if entry_name in seen:
                raise InstallerError(f"Duplicate dconf backup entry: {entry_name}")
            seen.add(entry_name)
            status = entry.get("status")
            if status not in {"saved", "failed", "unavailable"}:
                raise InstallerError(
                    f"Unexpected dconf backup status for {entry_name}: {status!r}"
                )
            if status != "saved":
                continue
            name = entry.get("file")
            if (
                not isinstance(name, str)
                or name != f"{entry_name}.dconf"
            ):
                raise InstallerError(f"Unsafe dconf backup reference: {name!r}")
            dconf_dir = self._backup_directory(backup, ("settings", "dconf"))
            source = dconf_dir / name
            if not source.is_file() or source.is_symlink():
                raise InstallerError(f"Missing dconf backup file: {source}")
            source_info = source.lstat()
            if source_info.st_uid != os.getuid() or source_info.st_nlink != 1:
                raise InstallerError(f"Unsafe dconf backup file: {source}")
            if not isinstance(entry.get("sha256"), str) or sha256_file(source) != entry["sha256"]:
                raise InstallerError(f"dconf backup checksum mismatch: {source}")
            result.append((entry, source))
        if seen != set(DCONF_PATHS):
            missing = sorted(set(DCONF_PATHS) - seen)
            extra = sorted(seen - set(DCONF_PATHS))
            raise InstallerError(
                f"Backup dconf metadata is incomplete (missing={missing}, extra={extra})"
            )
        return result

    def rollback(self, backup_path: Path) -> Path:
        self._reset_transaction_state()
        # Reject an untrusted path before creating state, then revalidate it
        # after taking the transaction lock to close the concurrent-operation
        # window.
        self._validated_backup(backup_path)
        self._prepare_state_root()
        lock_fd = self._acquire_transaction_lock()
        try:
            return self._rollback_locked(backup_path)
        finally:
            self._release_transaction_lock(lock_fd)

    def _rollback_locked(self, backup_path: Path) -> Path:
        backup, metadata = self._validated_backup(backup_path)
        log_path = self.context.log_root / f"rollback-{self._timestamp()}.log"
        self.reporter.close()
        self.reporter = Reporter(self.stream, log_path)
        safety: Path | None = None
        try:
            self.reporter.stage("ROLLBACK PREFLIGHT")
            entries = metadata.get("entries", [])
            settings = metadata.get("settings", [])
            if not isinstance(entries, list) or not isinstance(settings, list):
                raise InstallerError("Backup entry lists are malformed")
            current_paths: list[Path] = []
            seen_paths: set[Path] = set()
            for collection, is_settings in ((entries, False), (settings, True)):
                for entry in collection:
                    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                        raise InstallerError("Backup contains a malformed path entry")
                    path = Path(entry["path"])
                    self.context.assert_safe_target(path)
                    if path in seen_paths:
                        raise InstallerError(f"Backup contains a duplicate target: {path}")
                    seen_paths.add(path)
                    registered = (
                        self._is_registered_setting_path(path)
                        if is_settings
                        else self._is_registered_transaction_path(path)
                    )
                    if not registered:
                        raise InstallerError(
                            f"Backup target is not in the Fedora Nova registry: {path}"
                        )
                    if not isinstance(entry.get("existed"), bool):
                        raise InstallerError(f"Backup existence marker is invalid: {path}")
                    if not is_settings:
                        current_paths.append(path)
                    if entry["existed"]:
                        ref = self._backup_object(
                            backup,
                            entry.get("backup"),
                            settings=is_settings,
                        )
                        if not lexists(ref):
                            raise InstallerError(f"Backup object is missing: {ref}")
                        if entry.get("type") not in {
                            "file", "directory", "symlink"
                        } or path_kind(ref) != entry["type"]:
                            raise InstallerError(
                                f"Backup object type mismatch: {ref}"
                            )
                        expected = entry.get(
                            "backup_fingerprint", entry.get("fingerprint")
                        )
                        if (
                            not isinstance(expected, str)
                            or tree_fingerprint(ref) != expected
                        ):
                            raise InstallerError(
                                f"Backup object checksum mismatch: {ref}"
                            )
                    elif any(
                        key in entry
                        for key in ("backup", "type", "fingerprint", "backup_fingerprint")
                    ):
                        raise InstallerError(
                            f"Nonexistent backup target has object metadata: {path}"
                        )

            dconf_entries = self._validated_dconf_entries(backup, metadata)

            for cache in self._shared_cache_targets():
                if cache not in current_paths:
                    current_paths.append(cache)
            safety = self._create_backup(
                current_paths, reason=f"pre-rollback-{backup.name}"
            )
            self.reporter.line(f"Current state backed up before rollback: {safety}")
            self.reporter.stage("RESTORE FILES")
            for entry in reversed(entries):
                self.reporter.line(f"RESTORE {entry['path']}")
                self._restore_entry(backup, entry)
                self._failpoint()
            self.reporter.stage("RESTORE USER SETTINGS")
            self.reporter.line(
                "Preserved settings and dconf were not modified by Installer V2; "
                "their backup copies remain available and are not replayed over newer user state."
            )
            if settings or dconf_entries:
                self.reporter.line(
                    f"Settings snapshot retained in: {backup / 'settings'}"
                )
            self._refresh_caches()
            self.reporter.stage("ROLLBACK COMPLETE")
            self.reporter.line(f"Restored backup: {backup}")
            return safety
        except Exception:
            if safety is not None:
                self.reporter.line(f"Rollback failed. Pre-rollback backup: {safety}")
                self.reporter.line(
                    f"Recovery command: {self._rollback_command(safety)}"
                )
            raise
        finally:
            self.reporter.close()

    def _validated_uninstall_targets(self, manifest: dict[str, Any]) -> list[Path]:
        raw_targets = manifest.get("managed_targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise InstallerError("Install manifest has no valid managed target list")
        expected = {
            artifact.target: artifact.component for artifact in artifacts(self.context)
        }
        targets: list[Path] = []
        seen: set[Path] = set()
        for entry in raw_targets:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise InstallerError("Malformed managed target in manifest")
            target = self.context.assert_safe_target(Path(entry["path"]))
            if target in seen:
                raise InstallerError(f"Duplicate managed target in manifest: {target}")
            seen.add(target)
            if target not in expected:
                raise InstallerError(
                    f"Manifest target is not an exact current Fedora Nova artifact: {target}"
                )
            component = entry.get("component")
            expected_type = entry.get("type")
            expected_fingerprint = entry.get("fingerprint")
            if (
                component != expected[target]
                or expected_type not in {"file", "directory", "symlink"}
                or not isinstance(expected_fingerprint, str)
            ):
                raise InstallerError(
                    f"Manifest ownership evidence is incomplete: {target}"
                )
            if lexists(target):
                if expected_type != path_kind(target):
                    raise InstallerError(
                        f"Managed target type changed; refusing uninstall: {target}"
                    )
                if self._artifact_fingerprint(
                    target, component
                ) != expected_fingerprint:
                    raise InstallerError(
                        f"Managed target differs from the install manifest; "
                        f"refusing to remove possible user data: {target}"
                    )
            targets.append(target)
        missing = set(expected) - seen
        if missing:
            rendered = ", ".join(str(path) for path in sorted(missing, key=str))
            raise InstallerError(
                f"Install manifest is incomplete; refusing partial uninstall: {rendered}"
            )
        return targets

    def uninstall(self, *, dry_run: bool = False) -> Path | None:
        if not dry_run:
            self._reset_transaction_state()
        manifest = load_json(self.context.manifest_path)
        if manifest is None or manifest.get("format_version") != FORMAT_VERSION:
            raise InstallerError("Installer V2 manifest is required for safe uninstall")
        targets = self._validated_uninstall_targets(manifest)
        if dry_run:
            self.reporter.line("BACKUP:")
            for target in targets:
                if lexists(target):
                    self.reporter.line(f"  {target}")
            self.reporter.line("REMOVE:")
            for target in targets:
                self.reporter.line(f"  {target}")
            self.reporter.line("UNCHANGED:")
            self.reporter.line(f"  user settings: {self.context.config_home / 'fedora-nova'}")
            self.reporter.line(f"  backups and logs: {self.context.state_dir}")
            return None

        self._prepare_state_root()
        lock_fd = self._acquire_transaction_lock()
        try:
            manifest = load_json(self.context.manifest_path)
            if manifest is None or manifest.get("format_version") != FORMAT_VERSION:
                raise InstallerError(
                    "Installer V2 manifest is required for safe uninstall"
                )
            targets = self._validated_uninstall_targets(manifest)
            return self._uninstall_locked(targets)
        finally:
            self._release_transaction_lock(lock_fd)

    def _uninstall_locked(self, targets: list[Path]) -> Path:
        log_path = self.context.log_root / f"uninstall-{self._timestamp()}.log"
        self.reporter.close()
        self.reporter = Reporter(self.stream, log_path)
        backup: Path | None = None
        try:
            affected = [
                *targets,
                *self._shared_cache_targets(),
                self.context.manifest_path,
                self.context.install_state_path,
            ]
            backup = self._create_backup(affected, reason="uninstall")
            self.reporter.line(f"Backup before uninstall: {backup}")
            for target in reversed(targets):
                if lexists(target):
                    self.reporter.line(f"REMOVE {target}")
                    safe_remove(self.context, target)
                    self._failpoint()
            safe_remove(self.context, self.context.manifest_path)
            self._failpoint()
            safe_remove(self.context, self.context.install_state_path)
            self._failpoint()
            self._refresh_caches()
            self.reporter.line(
                f"Uninstall complete. Rollback: {self._rollback_command(backup)}"
            )
            return backup
        except Exception:
            if backup or self.last_backup:
                recovery = backup or self.last_backup
                self.reporter.line(f"Uninstall failed. Backup: {recovery}")
                self.reporter.line(
                    f"Rollback command: {self._rollback_command(recovery)}"
                )
            raise
        finally:
            self.reporter.close()
