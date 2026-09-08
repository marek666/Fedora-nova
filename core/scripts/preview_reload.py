#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
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
    "_build",
    "_build/**",
    "builddir",
    "builddir/**",
    ".flatpak-build-test",
    ".flatpak-build-test/**",
)

INOTIFY_EXCLUDE_REGEX = (
    r"(^|/)(\.git|\.dev-build|__pycache__|_build|builddir|\.flatpak-build-test)(/|$)"
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

_TRANSIENT_SCAN_ERRNOS = {
    errno.ENOENT,
    errno.ENOTDIR,
    errno.EINVAL,
}

_PARENT_CHECK_SECONDS = 0.25


class SupervisorGone(RuntimeError):
    """Raised when a token-bound preview supervisor no longer owns this watcher."""


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


def _watch_signature(path: Path) -> tuple[object, ...]:
    info = path.lstat()
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        return ("link", os.readlink(path), info.st_mtime_ns, info.st_ino)
    if stat.S_ISREG(mode):
        return ("file", info.st_mtime_ns, info.st_size, info.st_ino, mode)
    return ("other", info.st_mtime_ns, info.st_size, info.st_ino, mode)


def _watch_signature_with_retry(path: Path) -> tuple[object, ...] | None:
    """Read one entry without turning ordinary replace/delete races into failures."""
    for attempt in range(3):
        try:
            return _watch_signature(path)
        except OSError as exc:
            if exc.errno not in _TRANSIENT_SCAN_ERRNOS:
                raise
            if attempt < 2:
                time.sleep(0)
    return None


def _walk_onerror(exc: OSError) -> None:
    # Deleting or replacing a directory during traversal is transient. Access
    # failures and other real traversal errors must remain visible to callers.
    if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
        return
    raise exc


def _scan_repo_state(repo_root: Path) -> dict[str, tuple[object, ...]]:
    root = repo_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"repo root is not a directory: {root}")

    state: dict[str, tuple[object, ...]] = {}
    for dirpath, dirnames, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_walk_onerror,
    ):
        directory = Path(dirpath)
        kept_dirs: list[str] = []

        for name in dirnames:
            entry = directory / name
            rel = entry.relative_to(root).as_posix()
            if _match(rel, IGNORE_GLOBS):
                continue

            signature = _watch_signature_with_retry(entry)
            if signature is None:
                continue
            kind = signature[0]
            if kind == "link" or kind == "file":
                state[rel] = signature
                continue

            # A constant directory marker detects empty-directory create/delete
            # without turning every child mtime update into a second change.
            state[rel] = ("dir",)
            kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in filenames:
            entry = directory / name
            rel = entry.relative_to(root).as_posix()
            if _match(rel, IGNORE_GLOBS):
                continue
            signature = _watch_signature_with_retry(entry)
            if signature is not None:
                state[rel] = signature

    return state


def _valid_preview_token(token: str | None) -> bool:
    if token is None or len(token) != 32:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in token)


def _process_has_token(pid: int, token: str) -> bool:
    if pid <= 0 or not _valid_preview_token(token):
        return False
    try:
        environ = Path(f"/proc/{pid}/environ").read_bytes()
    except FileNotFoundError:
        return False
    marker = os.fsencode(f"NOVA_PREVIEW_TOKEN={token}")
    return marker in environ.split(b"\0")


def _ensure_supervisor(supervisor_pid: int | None, token: str | None) -> None:
    if supervisor_pid is None:
        return
    if not _valid_preview_token(token):
        raise ValueError("supervisor token is missing or invalid")
    if not _process_has_token(supervisor_pid, token):
        raise SupervisorGone("preview supervisor is no longer running")


def _watch_once_polling(
    repo_root: Path,
    debounce_seconds: float,
    poll_seconds: float,
    supervisor_pid: int | None,
    supervisor_token: str | None,
) -> tuple[str, list[dict[str, str]]]:
    root = repo_root.resolve(strict=True)
    _ensure_supervisor(supervisor_pid, supervisor_token)
    previous = _scan_repo_state(root)
    pending: set[str] = set()
    deadline: float | None = None
    next_scan = time.monotonic() + poll_seconds

    while True:
        now = time.monotonic()
        sleep_for = min(_PARENT_CHECK_SECONDS, max(0.0, next_scan - now))
        if sleep_for > 0:
            time.sleep(sleep_for)
        _ensure_supervisor(supervisor_pid, supervisor_token)

        now = time.monotonic()
        if now < next_scan:
            continue
        current = _scan_repo_state(root)
        next_scan = now + poll_seconds
        changed = {
            path
            for path in previous.keys() | current.keys()
            if previous.get(path) != current.get(path)
        }
        previous = current

        if changed:
            pending.update(changed)
            deadline = time.monotonic() + debounce_seconds
            continue

        if pending and deadline is not None and time.monotonic() >= deadline:
            action, details = classify_paths(sorted(pending), root)
            if action == IGNORE:
                pending.clear()
                deadline = None
                continue
            return action, details


def _inotify_command(binary: str, root: Path) -> list[str]:
    return [
        binary,
        "--monitor",
        "--recursive",
        "--quiet",
        "--no-dereference",
        "--event",
        "create",
        "--event",
        "delete",
        "--event",
        "modify",
        "--event",
        "attrib",
        "--event",
        "moved_to",
        "--event",
        "moved_from",
        "--format",
        "%w%f%0",
        "--no-newline",
        "--exclude",
        INOTIFY_EXCLUDE_REGEX,
        os.fspath(root),
    ]


def _watch_once_inotify(
    repo_root: Path,
    debounce_seconds: float,
    supervisor_pid: int | None,
    supervisor_token: str | None,
) -> tuple[str, list[dict[str, str]]]:
    binary = shutil.which("inotifywait")
    if binary is None:
        raise RuntimeError("inotifywait is not available")

    root = repo_root.resolve(strict=True)
    _ensure_supervisor(supervisor_pid, supervisor_token)
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    process = subprocess.Popen(
        _inotify_command(binary, root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=False,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise RuntimeError("failed to capture inotifywait output")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b""
    pending: set[str] = set()
    deadline: float | None = None

    try:
        while True:
            _ensure_supervisor(supervisor_pid, supervisor_token)
            now = time.monotonic()
            timeout = _PARENT_CHECK_SECONDS
            if deadline is not None:
                timeout = min(timeout, max(0.0, deadline - now))

            ready = selector.select(timeout)
            _ensure_supervisor(supervisor_pid, supervisor_token)

            if not ready:
                if process.poll() is not None:
                    stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
                    detail = stderr or f"inotifywait exited with status {process.returncode}"
                    raise RuntimeError(detail)
                if pending and deadline is not None and time.monotonic() >= deadline:
                    action, details = classify_paths(sorted(pending), root)
                    if action == IGNORE:
                        pending.clear()
                        deadline = None
                        continue
                    return action, details
                continue

            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                if process.poll() is None:
                    continue
                stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
                detail = stderr or f"inotifywait exited with status {process.returncode}"
                raise RuntimeError(detail)
            buffer += chunk

            while b"\0" in buffer:
                raw_path, buffer = buffer.split(b"\0", 1)
                if not raw_path:
                    continue
                event_path = _lexical_absolute(Path(os.fsdecode(raw_path)))
                try:
                    rel = event_path.relative_to(root).as_posix()
                except ValueError:
                    continue
                if not rel or _match(rel, IGNORE_GLOBS):
                    continue
                pending.add(rel)
                deadline = time.monotonic() + debounce_seconds
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def watch_once(
    repo_root: Path,
    debounce_seconds: float = 0.25,
    poll_seconds: float = 0.50,
    collector: str = "auto",
    supervisor_pid: int | None = None,
    supervisor_token: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    if debounce_seconds <= 0:
        raise ValueError("debounce must be greater than zero")
    if poll_seconds <= 0:
        raise ValueError("poll interval must be greater than zero")
    if collector not in {"auto", "inotify", "poll"}:
        raise ValueError(f"unknown collector: {collector}")

    root = repo_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"repo root is not a directory: {root}")

    chosen = collector
    if chosen == "auto":
        chosen = "inotify" if shutil.which("inotifywait") else "poll"

    if chosen == "inotify":
        return _watch_once_inotify(
            root,
            debounce_seconds,
            supervisor_pid,
            supervisor_token,
        )
    return _watch_once_polling(
        root,
        debounce_seconds,
        poll_seconds,
        supervisor_pid,
        supervisor_token,
    )


def _cmd_watch_once(args: argparse.Namespace) -> int:
    token = os.environ.get("NOVA_PREVIEW_TOKEN") if args.supervisor_pid else None
    try:
        action, details = watch_once(
            Path(args.repo_root),
            debounce_seconds=args.debounce_ms / 1000.0,
            poll_seconds=args.poll_ms / 1000.0,
            collector=args.collector,
            supervisor_pid=args.supervisor_pid,
            supervisor_token=token,
        )
    except SupervisorGone:
        # The supervisor owns this process. If it disappears abruptly there is
        # nobody left to consume a result, so exit quietly after child cleanup.
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"preview_reload.py: watch-once: {exc}", file=sys.stderr)
        return 2

    payload = {"action": action, "changes": details}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(action)
        for item in details:
            print(f"{item['action']}\t{item['path']}")
    return 0


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

    watch_once_parser = sub.add_parser(
        "watch-once",
        help="wait for a debounced batch of repository changes and classify it",
    )
    watch_once_parser.add_argument("--repo-root", required=True)
    watch_once_parser.add_argument("--debounce-ms", type=int, default=250)
    watch_once_parser.add_argument("--poll-ms", type=int, default=500)
    watch_once_parser.add_argument(
        "--collector",
        choices=("auto", "inotify", "poll"),
        default="auto",
    )
    watch_once_parser.add_argument("--supervisor-pid", type=int)
    watch_once_parser.add_argument("--json", action="store_true")
    watch_once_parser.set_defaults(func=_cmd_watch_once)

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
