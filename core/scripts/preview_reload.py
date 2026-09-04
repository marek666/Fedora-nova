#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Iterable

IGNORE = "IGNORE"
THEME_RELOAD = "THEME_RELOAD"
ASSET_REFRESH = "ASSET_REFRESH"
CONFIG_REFRESH = "CONFIG_REFRESH"
FULL_SHELL_RESTART = "FULL_SHELL_RESTART"

RANK = {
    IGNORE: 0,
    THEME_RELOAD: 10,
    ASSET_REFRESH: 20,
    CONFIG_REFRESH: 30,
    FULL_SHELL_RESTART: 40,
}

IGNORE_GLOBS = (
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    "*.pyo",
    "**/*.pyo",
    "*.swp",
    "**/*.swp",
    "*.swo",
    "**/*.swo",
    "*~",
    "**/*~",
    "*.tmp",
    "**/*.tmp",
    ".dev-build",
    ".dev-build/**",
    ".git",
    ".git/**",
)

THEME_GLOBS = (
    "core/themes/**",
    "core/themes-src/scss/**",
    "core/scripts/hover_style.py",
    "core/scripts/curve_style.py",
    "core/scripts/build-theme-sass.sh",
    "core/config/curves.json",
)

ASSET_GLOBS = (
    "core/assets/wallpapers/**",
    "core/assets/icons/**",
    "core/third-party/Tela-circle/**",
)

CONFIG_GLOBS = (
    "core/config/profiles.json",
    "core/config/colors.json",
)

FULL_GLOBS = (
    "dev-shell-preview.sh",
    "dev-setup-fedora.sh",
    "core/third-party/topbar-all-monitors/**",
    "core/extensions/**",
)


def _match(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute normalized path without following symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def normalize_repo_path(raw: str, repo_root: Path | None = None) -> str:
    path = Path(raw)
    if repo_root is not None:
        # Classification is about where an event was reported, not where a symlink
        # eventually points. Keep this lexical so an outside symlink into the repo
        # cannot turn an untrusted absolute path into a trusted core/... path.
        root = _lexical_absolute(repo_root)
        candidate = _lexical_absolute(path if path.is_absolute() else root / path)
        try:
            path = candidate.relative_to(root)
        except ValueError:
            return candidate.as_posix()
    text = path.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def classify_path(raw: str, repo_root: Path | None = None) -> str:
    path = normalize_repo_path(raw, repo_root)

    if _match(path, IGNORE_GLOBS):
        return IGNORE
    if _match(path, FULL_GLOBS):
        return FULL_SHELL_RESTART
    if _match(path, CONFIG_GLOBS):
        return CONFIG_REFRESH
    if _match(path, ASSET_GLOBS):
        return ASSET_REFRESH
    if _match(path, THEME_GLOBS):
        return THEME_RELOAD

    # Stay conservative for unknown project changes.
    if path.startswith("core/"):
        return FULL_SHELL_RESTART
    return FULL_SHELL_RESTART


def classify_paths(
    paths: Iterable[str], repo_root: Path | None = None
) -> tuple[str, list[dict[str, str]]]:
    details: list[dict[str, str]] = []
    strongest = IGNORE
    for raw in paths:
        normalized = normalize_repo_path(raw, repo_root)
        action = classify_path(raw, repo_root)
        details.append({"path": normalized, "action": action})
        if RANK[action] > RANK[strongest]:
            strongest = action
    return strongest, details


def _hash_file(path: Path, digest: "hashlib._Hash") -> None:
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)


def fingerprint_path(path: Path) -> str:
    # Do not resolve the top-level path before checking for a symlink. The link
    # target is part of the preview state even when two targets have equal content.
    path = _lexical_absolute(path)
    digest = hashlib.sha256()

    if path.is_symlink():
        digest.update(b"link\0")
        digest.update(os.fsencode(os.readlink(path)))
        return digest.hexdigest()

    if not path.exists():
        digest.update(b"missing\0")
        digest.update(os.fsencode(path))
        return digest.hexdigest()

    if path.is_file():
        digest.update(b"file\0")
        _hash_file(path, digest)
        return digest.hexdigest()

    digest.update(b"dir\0")
    root = path
    entries = sorted(
        root.rglob("*"),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    for entry in entries:
        rel = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            digest.update(b"l\0")
            digest.update(os.fsencode(rel))
            digest.update(b"\0")
            digest.update(os.fsencode(os.readlink(entry)))
            digest.update(b"\0")
        elif entry.is_dir():
            digest.update(b"d\0")
            digest.update(os.fsencode(rel))
            digest.update(b"\0")
        elif entry.is_file():
            digest.update(b"f\0")
            digest.update(os.fsencode(rel))
            digest.update(b"\0")
            _hash_file(entry, digest)
            digest.update(b"\0")
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _validate_sync_symlinks(source: Path) -> None:
    """Reject links that would expose paths outside a managed preview tree."""
    root = source.resolve(strict=True)
    for entry in root.rglob("*"):
        if not entry.is_symlink():
            continue

        raw_target = os.readlink(entry)
        target = Path(raw_target)
        if target.is_absolute():
            raise ValueError(f"absolute symlink is not allowed: {entry} -> {raw_target}")

        resolved_target = (entry.parent / target).resolve(strict=False)
        try:
            resolved_target.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"out-of-tree symlink is not allowed: {entry} -> {raw_target}"
            ) from exc


def sync_tree(source: Path, target: Path, stamp: Path) -> bool:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"source is not a directory: {source}")

    _validate_sync_symlinks(source)
    signature = fingerprint_path(source)
    try:
        previous = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        previous = ""

    if previous == signature and target.is_dir():
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.sync-", dir=target.parent)
    )
    try:
        # mkdtemp creates the directory, so copy the source contents into it.
        for item in source.iterdir():
            destination = temp / item.name
            if item.is_symlink():
                destination.symlink_to(os.readlink(item))
            elif item.is_dir():
                shutil.copytree(item, destination, symlinks=True)
            else:
                shutil.copy2(item, destination, follow_symlinks=False)

        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        os.replace(temp, target)
        _atomic_write_text(stamp, signature + "\n")
        return True
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def _cmd_classify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else None
    action, details = classify_paths(args.paths, repo_root)
    if args.json:
        print(json.dumps({"action": action, "changes": details}, ensure_ascii=False))
    else:
        print(action)
    return 0


def _cmd_fingerprint(args: argparse.Namespace) -> int:
    print(fingerprint_path(Path(args.path)))
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    try:
        changed = sync_tree(
            Path(args.source),
            Path(args.target),
            Path(args.stamp),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"preview_reload.py: sync: {exc}", file=sys.stderr)
        return 2

    print("updated" if changed else "unchanged")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fedora Nova preview reload classifier and incremental sync helper."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    classify = sub.add_parser("classify", help="classify changed repository paths")
    classify.add_argument("--repo-root")
    classify.add_argument("--json", action="store_true")
    classify.add_argument("paths", nargs="+")
    classify.set_defaults(func=_cmd_classify)

    fingerprint = sub.add_parser("fingerprint", help="hash a file or directory tree")
    fingerprint.add_argument("path")
    fingerprint.set_defaults(func=_cmd_fingerprint)

    sync = sub.add_parser(
        "sync",
        help="replace a target tree only when source contents changed",
    )
    sync.add_argument("--source", required=True)
    sync.add_argument("--target", required=True)
    sync.add_argument("--stamp", required=True)
    sync.set_defaults(func=_cmd_sync)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
