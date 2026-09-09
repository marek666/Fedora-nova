"""Prepare user theme copies and edit CSS without following links."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys


@contextmanager
def open_theme_css(path: Path):
    # Walk each directory using descriptors: a symlink swap must not redirect a
    # renderer into bundled data. Never truncate until the file is validated.
    path = path.absolute()
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(f"Theme CSS musí být běžný soubor bez hardlinků: {path}")
            with os.fdopen(fd, "r+", encoding="utf-8") as stream:
                fd = -1
                yield stream
        finally:
            if fd != -1:
                os.close(fd)
    finally:
        os.close(directory)


def edit_theme_css(path: Path, transform) -> bool:
    with open_theme_css(path) as stream:
        text = stream.read()
        updated = transform(text)
        if updated == text:
            return False
        stream.seek(0)
        stream.write(updated)
        stream.truncate()
    return True


def prepare_user_themes(source: Path, runtime: Path, profiles: Path, project: Path) -> None:
    runtime = runtime.absolute()
    resolved = runtime.resolve()
    for bundled in {source.resolve(), project.resolve()}:
        if resolved.is_relative_to(bundled) or bundled.is_relative_to(resolved):
            raise ValueError(f"Runtime themes se nesmějí překrývat s bundled themes: {runtime}")

    data = json.loads(profiles.read_text(encoding="utf-8"))
    names = {item["theme"] for item in data["profiles"].values()}
    if not names or any(not re.fullmatch(r"Fedora-Nova-(?!Custom-)[A-Za-z0-9_-]+", name)
                        for name in names):
        raise ValueError(f"Neplatný seznam built-in themes: {profiles}")

    # Reject linked target directories before mkdir, copying or chmod.
    for path in [*reversed(runtime.parents), runtime]:
        if path.is_symlink():
            raise ValueError(f"Runtime theme cesta nesmí obsahovat symlink: {path}")
    runtime.mkdir(parents=True, exist_ok=True)
    missing = []
    for name in sorted(names):
        target = runtime / name
        if target.is_symlink():
            raise ValueError(f"Runtime theme nesmí být symlink: {target}")
        if target.exists():
            with open_theme_css(target / "gnome-shell/gnome-shell.css"):
                pass
        else:
            original = source / name
            if not (original / "gnome-shell/gnome-shell.css").is_file():
                raise ValueError(f"Chybí bundled theme i uživatelská kopie: {name}")
            if original.is_symlink() or any(p.is_symlink() for p in original.rglob("*")):
                raise ValueError(f"Bundled theme pro kopírování obsahuje symlink: {original}")
            missing.append((original, target))

    # Include existing custom themes in the preflight, without bootstrapping or
    # replacing them. Renderers retain their existing profile selection rules.
    for theme in runtime.glob("Fedora-Nova*"):
        if theme.is_symlink() or (theme / "gnome-shell").is_symlink():
            raise ValueError(f"Runtime theme nesmí obsahovat symlink: {theme}")
        css = theme / "gnome-shell/gnome-shell.css"
        if css.exists() or css.is_symlink():
            with open_theme_css(css):
                pass

    for original, target in missing:
        # Exclusive creation preserves an existing user copy, including one
        # created concurrently. Only our new copy receives owner permissions.
        target.mkdir()
        try:
            shutil.copytree(original, target, dirs_exist_ok=True, symlinks=True)
            for path in [target, *target.rglob("*")]:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError(f"Kopie theme obsahuje symlink: {path}")
                mode = info.st_mode | stat.S_IRUSR | stat.S_IWUSR
                if stat.S_ISDIR(info.st_mode):
                    mode |= stat.S_IXUSR
                os.chmod(path, stat.S_IMODE(mode), follow_symlinks=False)
            with open_theme_css(target / "gnome-shell/gnome-shell.css"):
                pass
        except Exception:
            shutil.rmtree(target)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare writable user theme copies")
    parser.add_argument("source", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("profiles", type=Path)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        prepare_user_themes(args.source, args.runtime, args.profiles, args.project)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: Nelze připravit uživatelské themes: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
