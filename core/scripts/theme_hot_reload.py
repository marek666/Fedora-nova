#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import ctypes
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

CURVE_BEGIN = "/* NOVA_CURVE_START */"
CURVE_END = "/* NOVA_CURVE_END */"
HOVER_BEGIN = "/* NOVA_HOVER_START */"
HOVER_END = "/* NOVA_HOVER_END */"
TOKEN_RE = re.compile(r"[0-9a-fA-F]{32}")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_cancel_signal = 0


class HotReloadError(RuntimeError):
    pass


class Cancelled(HotReloadError):
    pass


def checkpoint() -> None:
    if _cancel_signal:
        raise Cancelled(f"theme refresh cancelled by signal {_cancel_signal}")


@contextmanager
def cancellation_signals():
    global _cancel_signal
    _cancel_signal = 0
    def cancel(signum, _frame):
        global _cancel_signal
        _cancel_signal = signum
    previous = {s: signal.signal(s, cancel) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def enable_subreaper() -> None:
    # Adopt compiler/command descendants so cancellation can reap them too.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER (Linux)
        raise OSError(ctypes.get_errno(), "cannot enable preview child reaping")


def process_environ(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    return dict(os.fsdecode(item).split("=", 1) for item in raw.split(b"\0") if b"=" in item)


def process_identity(pid: int) -> tuple[int, int, int, int, int]:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    if fields[0] in {"Z", "X"}:
        raise HotReloadError("process is no longer running")
    executable = Path(f"/proc/{pid}/exe").stat()
    return int(fields[19]), int(fields[2]), int(fields[3]), executable.st_dev, executable.st_ino


def child_pids(pid: int | None = None) -> set[int]:
    pid = os.getpid() if pid is None else pid
    try:
        return {int(p) for p in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()}
    except FileNotFoundError:
        return set()


def stop_children(preserved: set[int], grace: float = 0.3) -> None:
    token = os.environ.get("NOVA_PREVIEW_TOKEN")
    handles: dict[int, int] = {}
    def collect(pid):
        if pid in handles or pid in preserved:
            return
        try:
            fd = os.pidfd_open(pid)
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                if state in {"Z", "X"}:
                    os.close(fd)
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
                    return
                owned = not token or process_environ(pid).get("NOVA_PREVIEW_TOKEN") == token
            except OSError:
                os.close(fd)
                raise
            if not owned:
                os.close(fd)
                raise HotReloadError(f"refusing to signal child {pid}: token mismatch")
        except ProcessLookupError:
            return
        except FileNotFoundError:
            return
        handles[pid] = fd
        for child in child_pids(pid):
            collect(child)
    try:
        for pid in child_pids() - preserved:
            collect(pid)
        for fd in handles.values():
            try:
                signal.pidfd_send_signal(fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and child_pids() - preserved:
            time.sleep(0.02)
        # Re-scan for adopted descendants before escalation. pidfds cannot signal
        # a reused PID, and only our children with the inherited token qualify.
        for pid in child_pids() - preserved:
            collect(pid)
        for fd in handles.values():
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in handles:
            deadline = time.monotonic() + 0.5
            try:
                while os.waitpid(pid, os.WNOHANG)[0] == 0:
                    if time.monotonic() >= deadline:
                        raise HotReloadError(f"child {pid} could not be reaped after SIGKILL")
                    time.sleep(0.01)
            except ChildProcessError:
                pass
    finally:
        for fd in handles.values():
            os.close(fd)


def run_checked(command: list[str], *, env: dict[str, str] | None = None,
                timeout: float = 20.0, check_alive=None, ignore_cancel: bool = False,
                cancel_grace: float = 0.3) -> str:
    preserved = child_pids()
    env = dict(os.environ if env is None else env)
    env.pop("BASH_ENV", None)
    env.pop("ENV", None)
    # Regular temporary files avoid a dead child leaving communicate() blocked
    # forever on a pipe inherited by a grandchild.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(command, env=env, stdout=out, stderr=err)
        deadline = time.monotonic() + timeout
        try:
            while True:
                if not ignore_cancel:
                    checkpoint()
                if check_alive is not None:
                    check_alive()
                rc = process.poll()
                if rc is not None:
                    break
                if time.monotonic() >= deadline:
                    raise HotReloadError(f"command timed out: {command[0]}")
                if out.tell() + err.tell() > 4 * 1024 * 1024:
                    raise HotReloadError(f"excessive command output: {command[0]}")
                time.sleep(0.025)
            out.seek(0)
            err.seek(0)
            stdout = out.read().decode("utf-8", errors="replace").strip()
            stderr = err.read().decode("utf-8", errors="replace").strip()
            if rc:
                raise HotReloadError(f"{command[0]}: {stderr or stdout or f'exit status {rc}'}")
            return stdout
        finally:
            stop_children(preserved, grace=cancel_grace)
            process.wait(timeout=0.5)


@contextmanager
def directory_fd(path: Path):
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def require_dir(path: Path, label: str) -> Path:
    path = Path(os.path.abspath(path))
    with directory_fd(path):
        pass
    return path


def check_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise HotReloadError(f"invalid preview theme/profile name: {name!r}")
    return name


def validate_tree(path: Path) -> None:
    def visit(fd):
        for name in os.listdir(fd):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    visit(child)
                finally:
                    os.close(child)
            elif not stat.S_ISREG(info.st_mode):
                raise HotReloadError(f"symlink/special file is not allowed in theme tree: {path}/{name}")
    with directory_fd(path) as fd:
        visit(fd)


def copy_tree(source: Path, target: Path) -> None:
    # Read through directory FDs and O_NOFOLLOW, not check-then-copy pathnames.
    # A concurrent repository symlink replacement cannot redirect a write.
    def copy(source_fd, target_fd):
        for name in os.listdir(source_fd):
            checkpoint()
            info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                src = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source_fd)
                try:
                    os.mkdir(name, 0o700, dir_fd=target_fd)
                    dst = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=target_fd)
                    try:
                        copy(src, dst)
                    finally:
                        os.close(dst)
                finally:
                    os.close(src)
            elif stat.S_ISREG(info.st_mode):
                src = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=source_fd)
                with os.fdopen(src, "rb") as reader:
                    if not stat.S_ISREG(os.fstat(src).st_mode):
                        raise HotReloadError(f"source changed type: {source}/{name}")
                    dst = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=target_fd)
                    with os.fdopen(dst, "wb") as writer:
                        while chunk := reader.read(1024 * 1024):
                            checkpoint()
                            writer.write(chunk)
                        os.fchmod(dst, stat.S_IMODE(info.st_mode) & 0o755)
            else:
                raise HotReloadError(f"symlink/special file is not allowed: {source}/{name}")
    validate_tree(source)
    with directory_fd(source) as src:
        target.mkdir(mode=0o700)
        with directory_fd(target) as dst:
            copy(src, dst)


def marker_ranges(text: str, source: Path) -> dict[str, tuple[int, int]]:
    result = {}
    for begin, end in ((CURVE_BEGIN, CURVE_END), (HOVER_BEGIN, HOVER_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise HotReloadError(f"missing/duplicate generated marker in {source}")
        start, finish = text.index(begin), text.index(end)
        if finish <= start:
            raise HotReloadError(f"reversed generated markers in {source}")
        result[begin] = (start, finish + len(end))
    spans = sorted(result.values())
    if spans[0][1] > spans[1][0]:
        raise HotReloadError(f"overlapping generated blocks in {source}")
    return result


def apply_generated_layers(theme_css: Path, layers_css: Path) -> None:
    if not stat.S_ISREG(theme_css.lstat().st_mode):
        raise HotReloadError("staged theme CSS must be a regular file")
    text, layers = theme_css.read_text(), layers_css.read_text()
    target_ranges, source_ranges = marker_ranges(text, theme_css), marker_ranges(layers, layers_css)
    for begin, (start, end) in sorted(target_ranges.items(), key=lambda item: item[1], reverse=True):
        a, b = source_ranges[begin]
        text = text[:start] + layers[a:b] + text[end:]
    theme_css.write_text(text)


def read_choice(path: Path, default: str) -> str:
    try:
        return path.read_text().strip() or default
    except FileNotFoundError:
        return default


def build_staged_theme(repo_root: Path, core: Path, profile: str, theme: str,
                       preview_config: Path, preview_state: Path) -> tuple[Path, Path]:
    check_name(profile)
    check_name(theme)
    source = require_dir(core / "themes" / theme, "source theme")
    validate_tree(source)
    require_dir(preview_state, "preview state")
    staging = Path(tempfile.mkdtemp(prefix="theme-hot-reload-", dir=preview_state))
    try:
        # Build existing Sass tooling against a private copy, never the shared
        # .dev-build output. Repository edits are reconciled by the live collector.
        build_core = staging / "build/core"
        (build_core / "themes-src").mkdir(parents=True)
        copy_tree(core / "themes-src/scss", build_core / "themes-src/scss")
        copy_tree(core / "scripts", build_core / "scripts")
        copy_tree(core / "config", build_core / "config")
        run_checked([str(build_core / "scripts/build-theme-sass.sh"), "--generate"])
        layers = staging / "build/.dev-build/theme-sass" / profile / "gnome-shell-layers.css"
        (staging / "themes").mkdir()
        staged = staging / "themes" / theme
        copy_tree(source, staged)
        css = staged / "gnome-shell/gnome-shell.css"
        apply_generated_layers(css, layers)
        config = preview_config / "fedora-nova"
        curve = read_choice(config / "current-curve", "squircle")
        hover = read_choice(config / "current-hover", "circle")
        if curve != "squircle":
            run_checked([sys.executable, str(build_core / "scripts/curve_style.py"), "apply", curve,
                         str(build_core / "config/curves.json"), str(staging / "themes")])
        if hover != "circle":
            run_checked([sys.executable, str(build_core / "scripts/hover_style.py"), hover,
                         str(build_core / "config/profiles.json"), str(config / "custom-profiles"), str(staging / "themes")])
        validate_tree(staged)
        marker_ranges(css.read_text(), css)
        checkpoint()
        return staging, staged
    except BaseException:
        shutil.rmtree(staging)
        raise


def private_text(path: Path) -> str:
    with directory_fd(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd) as file:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise HotReloadError(f"unsafe runtime metadata: {path}")
            return file.read(8192).strip()


class ShellIdentity:
    def __init__(self, pid: int, token: str, home: Path, config: Path, data: Path,
                 state: Path, profile: str, theme: str):
        if pid <= 0 or not TOKEN_RE.fullmatch(token):
            raise HotReloadError("invalid Shell PID/preview token")
        self.pid, self.token, self.profile, self.theme = pid, token, check_name(profile), check_name(theme)
        self.root = require_dir(home.parent, "preview root")
        self.roots = {"HOME": home, "XDG_CONFIG_HOME": config, "XDG_DATA_HOME": data,
                      "XDG_CACHE_HOME": self.root / "cache", "XDG_STATE_HOME": state}
        for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                          ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
            if self.roots[key] != self.root / name:
                raise HotReloadError("preview roots do not share the expected isolated layout")
            require_dir(self.roots[key], key)
        self.runtime = require_dir(self.root / "runtime", "runtime")
        self.stamp = None
        self.bus_stamp = None
        self.address = None
        self.env = None
        self.layout = {key: (path.stat().st_dev, path.stat().st_ino) for key, path in self.roots.items()}
        config_dir = self.roots["XDG_CONFIG_HOME"] / "fedora-nova"
        self.choices = {name: read_choice(config_dir / name, default)
                        for name, default in (("current-curve", "squircle"), ("current-hover", "circle"))}
        self.verify()

    def dbus(self, method: str, argument: str | None = None, *, rollback=False) -> str:
        command = ["gdbus", "call", "--address", self.address, "--dest", "org.freedesktop.DBus",
                   "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus." + method,
                   "--timeout", "1"]
        if argument is not None:
            command.append(argument)
        return run_checked(command, timeout=0.2 if rollback else 1.5, ignore_cancel=rollback)

    def bus_string(self, method, argument=None, *, rollback=False):
        raw = self.dbus(method, argument, rollback=rollback)
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError) as exc:
            raise HotReloadError("invalid D-Bus identity response") from exc
        if not isinstance(value, tuple) or len(value) != 1 or not isinstance(value[0], str):
            raise HotReloadError("invalid D-Bus identity response")
        return value[0]

    def bus_pid(self, name, *, rollback=False):
        raw = self.dbus("GetConnectionUnixProcessID", name, rollback=rollback)
        match = re.fullmatch(r"\(uint32 ([0-9]+),\)", raw)
        if not match:
            raise HotReloadError("invalid D-Bus Unix PID response")
        return int(match[1])

    def verify(self, *, rollback=False):
        for key, path in self.roots.items():
            with directory_fd(path) as fd:
                info = os.fstat(fd)
                if (info.st_uid != os.getuid() or info.st_mode & 0o022
                        or (info.st_dev, info.st_ino) != self.layout[key]):
                    raise HotReloadError("isolated preview directory identity/ownership changed")
        if not rollback:
            checkpoint()
        if private_text(self.runtime / "preview.token") != self.token:
            raise HotReloadError("runtime token changed")
        if private_text(self.runtime / "shell.pid") != str(self.pid):
            raise HotReloadError("recorded Shell PID changed")
        first = process_identity(self.pid)
        shell_env = process_environ(self.pid)
        argv = [os.fsdecode(a) for a in Path(f"/proc/{self.pid}/cmdline").read_bytes().split(b"\0") if a]
        executable = Path(f"/proc/{self.pid}/exe").resolve(strict=True)
        expected_exe = shutil.which("gnome-shell", path=os.environ.get("PATH"))
        if (len(argv) != 3 or Path(argv[0]).name != "gnome-shell" or argv[1:] != ["--devkit", "--wayland"]
                or expected_exe is None or executable != Path(expected_exe).resolve(strict=True)):
            raise HotReloadError("recorded PID is not the expected gnome-shell --devkit --wayland")
        expected = {key: str(value) for key, value in self.roots.items()}
        expected.update({"NOVA_PREVIEW_TOKEN": self.token, "NOVA_PREVIEW_THEME": self.theme,
                         "NOVA_PREVIEW_SHELL_PID_FILE": str(self.runtime / "shell.pid")})
        for key in ("PATH", "XDG_DATA_DIRS", "XDG_RUNTIME_DIR", "NOVA_PREVIEW_EXTENSIONS"):
            if key in os.environ:
                expected[key] = os.environ[key]
        expected.update({key: value for key, value in os.environ.items()
                         if key.startswith("NOVA_PREVIEW_") and key not in expected})
        if any(shell_env.get(key) != value for key, value in expected.items()):
            raise HotReloadError("Shell environment does not match the isolated preview")
        profile = self.roots["XDG_CONFIG_HOME"] / "fedora-nova/current-profile"
        if profile.read_text().strip() != self.profile:
            raise HotReloadError("active profile changed")
        for name, choice in self.choices.items():
            default = "squircle" if name == "current-curve" else "circle"
            if read_choice(profile.parent / name, default) != choice:
                raise HotReloadError("active curve/hover selection changed")
        session_pid = int(private_text(self.runtime / "session.pid"))
        pgid = int(private_text(self.runtime / "session.pgid"))
        session_env = process_environ(session_pid)
        session_exe = Path(f"/proc/{session_pid}/exe").resolve(strict=True)
        session_identity = process_identity(session_pid)
        if any(session_env.get(key) != str(path) for key, path in self.roots.items()):
            raise HotReloadError("session bootstrap does not use the isolated preview roots")
        if (session_exe.name != "dbus-run-session" or session_env.get("NOVA_PREVIEW_TOKEN") != self.token
                or first[1:3] != (pgid, pgid) or session_identity[1:3] != (pgid, pgid) or session_pid != pgid):
            raise HotReloadError("Shell is not in the recorded nested session")
        address = shell_env.get("DBUS_SESSION_BUS_ADDRESS", "")
        if not re.fullmatch(r"unix:(?:path|abstract)=[^;\s]+", address):
            raise HotReloadError("nested Shell has no single local session D-Bus address")
        stamp = (first, session_identity, address)
        if self.stamp is not None and self.stamp != stamp:
            raise HotReloadError("nested Shell/session identity changed")
        self.address = address
        # Only now is it safe to contact the address obtained from /proc.
        owner = self.bus_string("GetNameOwner", "org.gnome.Shell", rollback=rollback)
        if not re.fullmatch(r":[0-9]+\.[0-9]+", owner) or self.bus_pid(owner, rollback=rollback) != self.pid:
            raise HotReloadError("org.gnome.Shell belongs to a different process")
        daemon = self.bus_pid("org.freedesktop.DBus", rollback=rollback)
        daemon_identity = process_identity(daemon)
        daemon_env = process_environ(daemon)
        if any(daemon_env.get(key) != str(path) for key, path in self.roots.items()):
            raise HotReloadError("D-Bus service activation would use non-preview roots")
        if (daemon_identity[1:3] != first[1:3]
                or daemon_env.get("NOVA_PREVIEW_TOKEN") != self.token
                or Path(f"/proc/{daemon}/exe").resolve().name != "dbus-daemon"):
            raise HotReloadError("D-Bus daemon is not owned by the nested preview session")
        bus_stamp = (owner, daemon, daemon_identity, self.bus_string("GetId", rollback=rollback))
        if self.bus_stamp is not None and bus_stamp != self.bus_stamp:
            raise HotReloadError("nested D-Bus owner changed")
        if process_identity(self.pid) != first:
            raise HotReloadError("Shell changed during identity validation")
        self.stamp, self.bus_stamp = stamp, bus_stamp
        self.env = os.environ.copy()
        self.env.update(expected)
        self.env["DBUS_SESSION_BUS_ADDRESS"] = address
        self.env.pop("BASH_ENV", None)
        self.env.pop("ENV", None)

    def get_theme(self, *, rollback=False):
        self.verify(rollback=rollback)
        raw = run_checked(["gsettings", "get", "org.gnome.shell.extensions.user-theme", "name"],
                          env=self.env, timeout=0.2 if rollback else 1.5, ignore_cancel=rollback)
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError) as exc:
            raise HotReloadError("invalid User Themes setting") from exc
        if not isinstance(value, str):
            raise HotReloadError("invalid User Themes setting")
        self.verify(rollback=rollback)
        return value

    def set_theme(self, name, *, rollback=False):
        self.verify(rollback=rollback)
        run_checked(["gsettings", "set", "org.gnome.shell.extensions.user-theme", "name", repr(name)],
                    env=self.env, timeout=0.2 if rollback else 1.5, ignore_cancel=rollback)
        if self.get_theme(rollback=rollback) != name:
            raise HotReloadError("User Themes setting was not observed after write")


def write_recovery(path: Path, record: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".theme-recovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(record, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def replace_live_theme(staged_theme: Path, live_theme: Path, *, identity: ShellIdentity,
                       recovery: Path) -> None:
    validate_tree(live_theme)
    validate_tree(staged_theme)
    if not stat.S_ISREG((live_theme / "gnome-shell/gnome-shell.css").lstat().st_mode):
        raise HotReloadError("live CSS must be a regular file")
    backup_name = f".{live_theme.name}.hot-reload-backup"
    backup = live_theme.parent / backup_name
    if os.path.lexists(backup) or os.path.lexists(recovery):
        raise HotReloadError(f"unfinished theme transaction requires restart recovery: {backup}")
    if identity.get_theme() != identity.theme:
        raise HotReloadError("nested Shell is not using the expected theme")
    moved_old = moved_new = unloaded = committed = False
    record = {"format_version": 1, "token": identity.token, "shell_pid": identity.pid,
              "process_identity": getattr(identity, "stamp", None),
              "live": str(live_theme), "backup": str(backup), "phase": "prepared"}
    with directory_fd(live_theme.parent) as live_fd, directory_fd(staged_theme.parent) as staged_fd:
        old_stat, new_stat = live_theme.stat(), staged_theme.stat()
        record["old_inode"] = [old_stat.st_dev, old_stat.st_ino]
        record["new_inode"] = [new_stat.st_dev, new_stat.st_ino]
        def same_inode(name, info):
            current = os.stat(name, dir_fd=live_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISDIR(current.st_mode):
                raise HotReloadError("live/backup directory changed during transaction")
        try:
            write_recovery(recovery, record)
            checkpoint()
            # Set before the command: cancellation may arrive after the backend
            # write but before gsettings returns.
            unloaded = True
            identity.set_theme("")
            checkpoint()
            same_inode(live_theme.name, old_stat)
            os.rename(live_theme.name, backup_name, src_dir_fd=live_fd, dst_dir_fd=live_fd)
            moved_old = True
            record["phase"] = "old-backed-up"
            write_recovery(recovery, record)
            checkpoint()
            os.rename(staged_theme.name, live_theme.name, src_dir_fd=staged_fd, dst_dir_fd=live_fd)
            moved_new = True
            record["phase"] = "new-installed"
            write_recovery(recovery, record)
            checkpoint()
            identity.set_theme(identity.theme)
            checkpoint()
            committed = True
            same_inode(backup_name, old_stat)
            shutil.rmtree(backup_name, dir_fd=live_fd)
            recovery.unlink()
        except BaseException as original:
            if committed:
                # The backup may already be partly deleted. Never discard the
                # complete new live tree to restore a partial old tree.
                record.update(phase="committed-cleanup-required", error=str(original))
                write_recovery(recovery, record)
                raise HotReloadError(f"theme transaction committed; cleanup failed: {original}; recovery: {recovery}") from original
            failures = []
            try:
                if moved_new:
                    same_inode(live_theme.name, new_stat)
                    shutil.rmtree(live_theme.name, dir_fd=live_fd)
                if moved_old:
                    same_inode(backup_name, old_stat)
                    os.rename(backup_name, live_theme.name, src_dir_fd=live_fd, dst_dir_fd=live_fd)
                record.update(live_restored=True, phase="filesystem-restored")
                write_recovery(recovery, record)
            except (OSError, HotReloadError) as exc:
                failures.append(f"filesystem rollback failed; last good backup preserved: {exc}")
            if unloaded:
                try:
                    identity.set_theme(identity.theme, rollback=True)
                except (OSError, HotReloadError, ValueError) as exc:
                    failures.append(f"setting rollback could not be confirmed: {exc}")
            if failures:
                record.update(phase="recovery-required", errors=failures)
                write_recovery(recovery, record)
                raise HotReloadError(f"{original}; {'; '.join(failures)}; recovery record: {recovery}") from original
            recovery.unlink(missing_ok=True)
            raise


@contextmanager
def transaction_lock(runtime: Path):
    with directory_fd(runtime) as directory:
        fd = os.open("theme-hot-reload.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise HotReloadError("unsafe theme transaction lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise HotReloadError("another theme transaction is active") from exc
            yield
        finally:
            os.close(fd)


def archive_recovery(data: Path, state: Path, runtime: Path) -> Path | None:
    journal = state / "theme-hot-reload-recovery.json"
    themes = data / "themes"
    if not os.path.lexists(journal) and not any(themes.glob(".*.hot-reload-backup")):
        return None
    root = data.parent
    if data != root / "data" or state != root / "state" or runtime != root / "runtime":
        raise HotReloadError("invalid preview recovery layout")
    # Archive the complete live/backup pair without trusting paths from a journal
    # or dereferencing anything in the theme trees. A restart may then rebuild
    # data/state without destroying the only recoverable theme copy.
    if os.path.lexists(journal):
        private_text(journal)
    with directory_fd(data) as data_fd, directory_fd(runtime):
        info = os.stat("themes", dir_fd=data_fd, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise HotReloadError("recovery themes must be a real directory")
        archive = Path(tempfile.mkdtemp(prefix="theme-recovery-", dir=runtime))
        try:
            with directory_fd(archive) as archive_fd:
                os.rename("themes", "themes", src_dir_fd=data_fd, dst_dir_fd=archive_fd)
                if os.path.lexists(journal):
                    with directory_fd(state) as state_fd:
                        os.rename(journal.name, "recovery.json", src_dir_fd=state_fd, dst_dir_fd=archive_fd)
                else:
                    write_recovery(archive / "recovery.json", {"phase": "unrecorded-backup-preserved"})
        except OSError as exc:
            raise HotReloadError(f"recovery archive incomplete; refusing reset, inspect {archive}: {exc}") from exc
    print(f"Previous theme recovery preserved at {archive}", file=sys.stderr)
    return archive


def archive_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Preserve preview recovery before a full restart.")
    for name in ("preview-data", "preview-state", "runtime-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        archive_recovery(args.preview_data, args.preview_state, args.runtime_dir)
        return 0
    except (HotReloadError, OSError, ValueError) as exc:
        print(f"theme_hot_reload.py: recovery: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--archive-recovery":
        return archive_main(argv[1:])
    parser = argparse.ArgumentParser(description="Request a theme refresh in a verified nested Shell.")
    for name in ("repo-root", "preview-home", "preview-config", "preview-data", "preview-state"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--shell-pid", required=True, type=int)
    args = parser.parse_args(argv)
    with cancellation_signals():
        staging = None
        try:
            enable_subreaper()
            repo = require_dir(args.repo_root, "repository")
            identity = ShellIdentity(args.shell_pid, os.environ.get("NOVA_PREVIEW_TOKEN", ""),
                                     args.preview_home, args.preview_config, args.preview_data,
                                     args.preview_state, args.profile, args.theme)
            with transaction_lock(identity.runtime):
                live = args.preview_data / "themes" / check_name(args.theme)
                validate_tree(live)
                recovery = args.preview_state / "theme-hot-reload-recovery.json"
                if os.path.lexists(live.parent / f".{live.name}.hot-reload-backup") or os.path.lexists(recovery):
                    raise HotReloadError("unfinished theme transaction; full restart recovery required")
                try:
                    staging, staged = build_staged_theme(repo, repo / "core", args.profile, args.theme,
                                                         args.preview_config, args.preview_state)
                    identity.verify()
                    replace_live_theme(staged, live, identity=identity, recovery=recovery)
                    print("Theme setting restored; nested Shell identity verified. CSS application is not acknowledged by GNOME.")
                finally:
                    if staging is not None:
                        shutil.rmtree(staging)
            return 0
        except (HotReloadError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"theme_hot_reload.py: {exc}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
