#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class PreviewSettingsError(RuntimeError):
    pass


def _root(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise PreviewSettingsError(f"unsafe preview root: {path}")
    return path


def _profile(name: str) -> str:
    if not PROFILE_RE.fullmatch(name):
        raise PreviewSettingsError(f"invalid preview profile: {name!r}")
    return name


def _validate_tree(path: Path) -> None:
    if path.is_symlink():
        raise PreviewSettingsError(f"symlink is not allowed in preview settings: {path}")
    if not path.exists():
        return
    for entry in path.rglob("*"):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise PreviewSettingsError(f"unsafe preview settings entry: {entry}")


SETTINGS_DIRS = ("dconf", "fedora-nova")


def _settings_root(root: Path) -> Path:
    # Validate parents too: validating a leaf does not catch a symlink above it.
    for path in (root / "config", root / "persist", root / "persist/settings"):
        if path.is_symlink():
            raise PreviewSettingsError(f"unsafe preview settings directory: {path}")
    return root / "persist/settings"


def save(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    settings_root = _settings_root(root)
    sources = [root / "config" / name for name in SETTINGS_DIRS]
    for source in sources:
        _validate_tree(source)
    if not any(source.exists() for source in sources):
        return "empty"
    settings_root.mkdir(parents=True, exist_ok=True)
    os.chmod(settings_root, 0o700)
    temp = Path(tempfile.mkdtemp(prefix=f".{profile}.", dir=settings_root))
    backup = settings_root / f".{profile}.backup"
    profile_dir = settings_root / profile
    try:
        for source in sources:
            if source.exists():
                shutil.copytree(source, temp / source.name)
        _validate_tree(temp)
        if backup.exists():
            shutil.rmtree(backup)
        if profile_dir.exists():
            if profile_dir.is_symlink():
                raise PreviewSettingsError(f"unsafe persisted profile directory: {profile_dir}")
            os.replace(profile_dir, backup)
        os.replace(temp, profile_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if not profile_dir.exists() and backup.exists():
            os.replace(backup, profile_dir)
        raise
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
    return "saved"


def save_current(root: Path) -> str:
    root = _root(root)
    _settings_root(root)
    _validate_tree(root / "config/fedora-nova")
    profile_file = root / "config/fedora-nova/current-profile"
    try:
        profile = profile_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "empty"
    return save(root, _profile(profile))


def restore(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    profile_dir = _settings_root(root) / profile
    _validate_tree(profile_dir)
    if not any((profile_dir / name).exists() for name in SETTINGS_DIRS):
        return "fresh"
    # Old dconf-only snapshots remain readable. Validate all destinations before
    # restoring either part, so unsafe Nova paths cannot partially replace dconf.
    for name in SETTINGS_DIRS:
        _validate_tree(root / "config" / name)
    (root / "config").mkdir(parents=True, exist_ok=True)
    for name in SETTINGS_DIRS:
        source, target = profile_dir / name, root / "config" / name
        if source.exists():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
            _validate_tree(target)
    # Nova files alone can survive a failed first start. They do not mean that
    # GNOME defaults were ever seeded into a dconf database.
    return "restored" if (profile_dir / "dconf/user").is_file() else "fresh"


def reset(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    target = _settings_root(root) / profile
    if target.is_symlink():
        raise PreviewSettingsError(f"unsafe persisted profile directory: {target}")
    if target.exists():
        shutil.rmtree(target)
    return "reset"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Persist isolated Fedora Nova Shell Preview dconf settings.")
    sub = result.add_subparsers(dest="command", required=True)
    for command in ("save", "restore", "reset"):
        item = sub.add_parser(command)
        item.add_argument("--preview-root", required=True, type=Path)
        item.add_argument("--profile", required=True)
    current = sub.add_parser("save-current")
    current.add_argument("--preview-root", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "save":
            result = save(args.preview_root, args.profile)
        elif args.command == "save-current":
            result = save_current(args.preview_root)
        elif args.command == "restore":
            result = restore(args.preview_root, args.profile)
        else:
            result = reset(args.preview_root, args.profile)
    except (OSError, PreviewSettingsError) as exc:
        print(f"preview_settings.py: {exc}", file=__import__("sys").stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
