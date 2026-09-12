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


def _paths(root: Path, profile: str) -> tuple[Path, Path]:
    source = root / "config/dconf"
    target = root / "persist/settings" / profile / "dconf"
    return source, target


def save(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    source, target = _paths(root, profile)
    if not source.exists():
        return "empty"
    _validate_tree(source)
    settings_root = root / "persist/settings"
    settings_root.mkdir(parents=True, exist_ok=True)
    os.chmod(settings_root, 0o700)
    temp = Path(tempfile.mkdtemp(prefix=f".{profile}.", dir=settings_root))
    backup = settings_root / f".{profile}.backup"
    profile_dir = target.parent
    try:
        shutil.copytree(source, temp / "dconf")
        _validate_tree(temp / "dconf")
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
    profile_file = root / "config/fedora-nova/current-profile"
    try:
        profile = profile_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "empty"
    return save(root, _profile(profile))


def restore(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    source, target = _paths(root, profile)
    if not target.exists():
        return "fresh"
    _validate_tree(target)
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists() or source.is_symlink():
        if source.is_symlink():
            raise PreviewSettingsError(f"unsafe preview dconf target: {source}")
        shutil.rmtree(source)
    shutil.copytree(target, source)
    _validate_tree(source)
    return "restored"


def reset(root: Path, profile: str) -> str:
    root = _root(root)
    profile = _profile(profile)
    target = root / "persist/settings" / profile
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
