from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any


FORMAT_VERSION = 2
PREVIEW_MARKER = "fedora-nova-shell-preview"


class InstallerError(RuntimeError):
    """A safety or installation invariant failed."""


def _absolute_from_env(value: str, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise InstallerError(f"{name} must be an absolute path: {path}")
    return path.resolve(strict=False)


@dataclass(frozen=True)
class InstallContext:
    source_root: Path
    home: Path
    data_home: Path
    config_home: Path
    state_home: Path
    cache_home: Path
    prefix: Path
    state_dir: Path
    backup_root: Path
    log_root: Path
    manifest_path: Path
    install_state_path: Path
    testing: bool = False

    @classmethod
    def from_environ(
        cls,
        source_root: Path,
        environ: dict[str, str] | None = None,
    ) -> "InstallContext":
        env = os.environ if environ is None else environ
        source = source_root.resolve(strict=True)
        home = _absolute_from_env(env.get("HOME", ""), "HOME")
        if home == Path("/"):
            raise InstallerError("HOME must not be the filesystem root.")
        data = _absolute_from_env(
            env.get("XDG_DATA_HOME", str(home / ".local/share")),
            "XDG_DATA_HOME",
        )
        config = _absolute_from_env(
            env.get("XDG_CONFIG_HOME", str(home / ".config")),
            "XDG_CONFIG_HOME",
        )
        state = _absolute_from_env(
            env.get("XDG_STATE_HOME", str(home / ".local/state")),
            "XDG_STATE_HOME",
        )
        cache = _absolute_from_env(
            env.get("XDG_CACHE_HOME", str(home / ".cache")),
            "XDG_CACHE_HOME",
        )
        prefix = _absolute_from_env(
            env.get("FEDORA_NOVA_INSTALL_PREFIX", str(home / ".local")),
            "FEDORA_NOVA_INSTALL_PREFIX",
        )
        testing = env.get("FEDORA_NOVA_INSTALLER_TESTING") == "1"
        if os.geteuid() == 0 and not testing:
            raise InstallerError("Do not run Fedora Nova Installer V2 as root.")

        if not testing:
            for label, root in {
                "XDG_DATA_HOME": data,
                "XDG_CONFIG_HOME": config,
                "XDG_STATE_HOME": state,
                "XDG_CACHE_HOME": cache,
                "prefix": prefix,
            }.items():
                if root != home and home not in root.parents:
                    raise InstallerError(
                        f"For host safety, {label} must stay inside HOME: {root}"
                    )

        test_root_raw = env.get("FEDORA_NOVA_INSTALLER_TEST_ROOT")
        if testing:
            if not test_root_raw:
                raise InstallerError(
                    "FEDORA_NOVA_INSTALLER_TEST_ROOT is required in testing mode."
                )
            test_root = _absolute_from_env(test_root_raw, "FEDORA_NOVA_INSTALLER_TEST_ROOT")
            if test_root == Path("/"):
                raise InstallerError(
                    "FEDORA_NOVA_INSTALLER_TEST_ROOT must not be the filesystem root."
                )
            for label, root in {
                "HOME": home,
                "XDG_DATA_HOME": data,
                "XDG_CONFIG_HOME": config,
                "XDG_STATE_HOME": state,
                "XDG_CACHE_HOME": cache,
                "prefix": prefix,
            }.items():
                if root != test_root and test_root not in root.parents:
                    raise InstallerError(f"Testing {label} escapes test root: {root}")

        state_dir = state / "fedora-nova"
        return cls(
            source_root=source,
            home=home,
            data_home=data,
            config_home=config,
            state_home=state,
            cache_home=cache,
            prefix=prefix,
            state_dir=state_dir,
            backup_root=state_dir / "backups",
            log_root=state_dir / "logs",
            manifest_path=state_dir / "install-manifest.json",
            install_state_path=state_dir / "install-state.json",
            testing=testing,
        )

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        roots = {
            self.home,
            self.data_home,
            self.config_home,
            self.state_home,
            self.cache_home,
            self.prefix,
        }
        return tuple(sorted(roots, key=lambda path: (len(path.parts), str(path))))

    def root_for(self, path: Path) -> Path:
        absolute = path if path.is_absolute() else path.absolute()
        candidates = [
            root
            for root in self.allowed_roots
            if absolute == root or root in absolute.parents
        ]
        if not candidates:
            raise InstallerError(f"Path is outside explicit installer roots: {absolute}")
        return max(candidates, key=lambda item: len(item.parts))

    def assert_safe_target(self, path: Path, *, allow_leaf_symlink: bool = True) -> Path:
        if not path.is_absolute():
            raise InstallerError(f"Target is not absolute: {path}")
        normalized = Path(os.path.abspath(path))
        root = self.root_for(normalized)
        if normalized in {Path("/"), self.home, root}:
            raise InstallerError(f"Refusing unsafe target: {normalized}")
        if PREVIEW_MARKER in normalized.parts:
            raise InstallerError(f"Host installer must not operate on Preview state: {normalized}")
        source = self.source_root
        if normalized == source or source in normalized.parents or normalized in source.parents:
            raise InstallerError(
                f"Installer target must not overlap the source checkout: {normalized}"
            )

        relative = normalized.relative_to(root)
        current = root
        # Explicit XDG roots may themselves be symlinks resolved by from_environ;
        # no component below those canonical roots may redirect a write.
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise InstallerError(f"Target parent is a symlink: {current}")
            if current.exists() and not current.is_dir():
                raise InstallerError(f"Target parent is not a directory: {current}")
        if normalized.is_symlink() and not allow_leaf_symlink:
            raise InstallerError(f"Target is a symlink: {normalized}")
        return normalized


@dataclass(frozen=True)
class Artifact:
    component: str
    payload_name: str
    target: Path


@dataclass(frozen=True)
class CleanupCandidate:
    component: str
    target: Path
    ownership: str = "known"


def lexists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def path_kind(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "special"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_tree(
    path: Path,
    *,
    ignored_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Describe a file tree without following symlinks."""
    if not lexists(path):
        return []
    entries: list[dict[str, Any]] = []

    def add(item: Path, relative: str) -> None:
        kind = path_kind(item)
        record: dict[str, Any] = {
            "path": relative,
            "type": kind,
            "mode": stat.S_IMODE(item.lstat().st_mode),
        }
        if kind == "file":
            record["sha256"] = sha256_file(item)
            record["size"] = item.lstat().st_size
        elif kind == "symlink":
            record["target"] = os.readlink(item)
        entries.append(record)

    add(path, ".")
    if path_kind(path) == "directory":
        for root, directories, files in os.walk(path, topdown=True, followlinks=False):
            root_path = Path(root)
            directories.sort()
            files.sort()
            for name in list(directories):
                if name in ignored_names:
                    directories.remove(name)
                    continue
                item = root_path / name
                relative = item.relative_to(path).as_posix()
                add(item, relative)
                if item.is_symlink():
                    directories.remove(name)
            for name in files:
                if name in ignored_names:
                    continue
                item = root_path / name
                add(item, item.relative_to(path).as_posix())
    return entries


def tree_fingerprint(
    path: Path,
    *,
    ignored_names: frozenset[str] = frozenset(),
) -> str:
    payload = json.dumps(
        describe_tree(path, ignored_names=ignored_names),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_owned_tree(path: Path) -> None:
    """Require every object in a tree to belong to the invoking user.

    Symlinks are inspected as links and are never traversed.
    """
    if not lexists(path):
        return

    def check(item: Path) -> None:
        try:
            info = item.lstat()
        except OSError as exc:
            raise InstallerError(f"Cannot establish ownership of {item}: {exc}") from exc
        if info.st_uid != os.getuid():
            raise InstallerError(
                f"Refusing object not owned by the current user: {item}"
            )

    check(path)
    if path_kind(path) != "directory":
        return
    for root, directories, files in os.walk(path, topdown=True, followlinks=False):
        root_path = Path(root)
        directories.sort()
        files.sort()
        for name in list(directories):
            item = root_path / name
            check(item)
            if item.is_symlink():
                directories.remove(name)
        for name in files:
            check(root_path / name)


def copy_path_nofollow(source: Path, destination: Path) -> None:
    kind = path_kind(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        destination.symlink_to(os.readlink(source))
    elif kind == "directory":
        shutil.copytree(source, destination, symlinks=True)
    elif kind == "file":
        shutil.copy2(source, destination, follow_symlinks=False)
    else:
        raise InstallerError(f"Unsupported filesystem object: {source}")


def safe_remove(context: InstallContext, path: Path) -> None:
    target = context.assert_safe_target(path)
    if not lexists(target):
        return
    assert_owned_tree(target)
    kind = path_kind(target)
    if kind == "directory":
        shutil.rmtree(target)
    else:
        target.unlink()


def atomic_replace(context: InstallContext, source: Path, target: Path) -> None:
    destination = context.assert_safe_target(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = context.assert_safe_target(target)
    if destination.parent.is_symlink():
        raise InstallerError(f"Destination parent is a symlink: {destination.parent}")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.nova-v2-", dir=destination.parent)
    )
    staged = temporary / "payload"
    try:
        copy_path_nofollow(source, staged)
        if lexists(destination):
            safe_remove(context, destination)
        os.replace(staged, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def atomic_write_json(context: InstallContext, path: Path, data: Any) -> None:
    target = context.assert_safe_target(path)
    if lexists(target):
        assert_owned_tree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = context.assert_safe_target(path)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
