#!/usr/bin/env python3
"""Filesystem boundaries for the Shell Preview launcher, including --stop."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import sys

from theme_hot_reload_core import directory_fd, validate_tree


ROOT_DIRS = ('home', 'config', 'data', 'cache', 'state', 'session-runtime',
             'runtime', 'persist', 'host-export', 'flatpak-export', 'live.lock')


def checked_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError(f'Preview path must be absolute: {path}')
    if '..' in path.parts:
        raise ValueError(f'Preview path must not contain parent traversal: {path}')
    path = Path(os.path.abspath(path))
    # Inspect every existing ancestor before any mkdir, chmod, write or delete.
    for entry in reversed((path, *path.parents)):
        if entry.is_symlink():
            raise ValueError(f'Preview path contains a symlink: {entry}')
    if path.resolve(strict=False) != path:
        raise ValueError(f'Preview path changed during validation: {path}')
    return path


def validate_root(root: Path) -> Path:
    root = checked_path(root)
    if root.name != 'fedora-nova-shell-preview':
        raise ValueError(f'Unexpected Preview root: {root}')
    for path in (root, *(root / name for name in ROOT_DIRS)):
        checked_path(path)
        if path.exists():
            info = path.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError(f'Unsafe Preview directory: {path}')
    runtime = root / 'runtime'
    if runtime.exists():
        for entry in runtime.iterdir():
            checked_path(entry)
    return root


def remove(root: Path, paths: list[Path]) -> None:
    root = validate_root(root)
    # Validate the complete batch before deleting anything.
    targets = []
    for path in paths:
        path = checked_path(path)
        if path == root or not path.is_relative_to(root):
            raise ValueError(f'Refusing cleanup outside Preview root: {path}')
        targets.append(path)
    for path in targets:
        if not path.parent.exists():
            continue
        with directory_fd(path.parent) as fd:
            try:
                info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(info.st_mode):
                shutil.rmtree(path.name, dir_fd=fd)
            else:
                # unlink never follows a concurrently replaced leaf symlink.
                os.unlink(path.name, dir_fd=fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('check', 'remove', 'sources', 'socket'))
    parser.add_argument('root', type=Path)
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    try:
        validate_root(args.root)
        if args.operation == 'remove':
            remove(args.root, args.paths)
        elif args.operation == 'sources':
            for path in args.paths:
                validate_tree(path)
        elif args.operation == 'socket':
            for path in args.paths:
                if len(os.fsencode(path)) >= 108:
                    raise ValueError(f'Wayland socket path exceeds 107 bytes; use a shorter XDG_CACHE_HOME: {path}')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'CHYBA: Preview filesystem boundary: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
