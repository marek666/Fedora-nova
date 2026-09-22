from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import tarfile
from typing import Callable

from .model import Artifact, InstallContext, InstallerError


THEMES = (
    "Fedora-Nova-Tech",
    "Fedora-Nova-Clean",
    "Fedora-Nova-Midnight",
    "Fedora-Nova-Glass-Lite",
    "Fedora-Nova-Pulse",
)
TELA_THEMES = ("Tela-circle", "Tela-circle-dark", "Tela-circle-light")
PTYXIS_PALETTES = (
    "Fedora Nova Tech.palette",
    "Fedora Nova Clean.palette",
    "Fedora Nova Midnight.palette",
    "Fedora Nova Glass Lite.palette",
    "Fedora Nova Pulse.palette",
)
TOPBAR_UUID = "topbar-all-monitors@fa8i.github.io"

CORE_EXCLUDED_FILES = {
    "SHA256SUMS",
    "install.sh",
    "uninstall.sh",
    "config/packages.txt",
    "scripts/install-assets.sh",
    "scripts/build-theme-sass.sh",
    "scripts/preview_reload.py",
    "scripts/preview_settings.py",
    "scripts/preview_paths.py",
    "scripts/theme_hot_reload.py",
    "scripts/theme_hot_reload_core.py",
}
CORE_EXCLUDED_DIRS = {
    "themes-src",
}


def _ensure_source(path: Path, kind: str = "file") -> Path:
    good = path.is_dir() if kind == "directory" else path.is_file()
    if not good or path.is_symlink():
        raise InstallerError(f"Required source {kind} is missing or unsafe: {path}")
    return path


def _validate_source_tree(root: Path) -> None:
    canonical = root.resolve(strict=True)
    for item in root.rglob("*"):
        mode = item.lstat().st_mode
        if not (item.is_file() or item.is_dir() or item.is_symlink()):
            raise InstallerError(f"Unsupported special source object: {item} ({mode:o})")
        if not item.is_symlink():
            continue
        try:
            resolved = item.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise InstallerError(f"Broken source symlink: {item}") from exc
        if resolved != canonical and canonical not in resolved.parents:
            raise InstallerError(f"Source symlink escapes repository tree: {item} -> {resolved}")


def _tracked_repository_paths(repository: Path) -> set[str] | None:
    if (repository / ".git").exists():
        git = shutil.which("git")
        if git is None:
            raise InstallerError(
                "git is required to select reviewed payload files from a checkout"
            )
        result = subprocess.run(
            [git, "-C", str(repository), "ls-files", "-z"],
            text=False,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip()
            raise InstallerError(f"Cannot enumerate tracked payload files: {detail}")
        return {
            Path(os.fsdecode(name)).as_posix()
            for name in result.stdout.split(b"\0")
            if name
        }
    return None


def _is_reviewed_path(
    repository: Path,
    path: Path,
    tracked: set[str] | None,
) -> bool:
    if tracked is None:
        return True
    relative = path.relative_to(repository).as_posix()
    return relative in tracked or any(item.startswith(relative + "/") for item in tracked)


def _copy_reviewed_tree(
    repository: Path,
    source: Path,
    destination: Path,
    tracked: set[str] | None,
    *,
    extra_ignore: Callable[[str, list[str]], set[str]] | None = None,
) -> None:
    def ignored(directory: str, names: list[str]) -> set[str]:
        ignored_names = set(extra_ignore(directory, names)) if extra_ignore else set()
        for name in names:
            path = Path(directory) / name
            if not _is_reviewed_path(repository, path, tracked):
                ignored_names.add(name)
        return ignored_names

    shutil.copytree(source, destination, symlinks=True, ignore=ignored)


def _copy_core(
    source: Path,
    destination: Path,
    tracked: set[str] | None = None,
) -> None:
    _ensure_source(source, "directory")
    _validate_source_tree(source)
    repository = source.parent

    def core_ignored(directory: str, names: list[str]) -> set[str]:
        parent = Path(directory).relative_to(source)
        ignored_names: set[str] = set()
        for name in names:
            relative = (parent / name).as_posix()
            if relative in CORE_EXCLUDED_FILES or relative in CORE_EXCLUDED_DIRS:
                ignored_names.add(name)
            elif name == "__pycache__" or name.endswith(".pyc"):
                ignored_names.add(name)
        return ignored_names

    _copy_reviewed_tree(
        repository,
        source,
        destination,
        tracked,
        extra_ignore=core_ignored,
    )


def _render(source: Path, destination: Path, replacements: dict[str, str], mode: int) -> None:
    text = _ensure_source(source).read_text(encoding="utf-8")
    for old, new in replacements.items():
        text = text.replace(old, new)
    if "@PYTHON@" in text or "@PKGDATADIR@" in text:
        raise InstallerError(f"Unresolved launcher placeholder in {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(mode)


def _tar_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise InstallerError(f"Unsafe Tela archive path: {name}")
    if not path.parts or path.parts[0] not in TELA_THEMES:
        raise InstallerError(f"Unexpected Tela archive root: {name}")
    return path


def _archive_link_target(member: tarfile.TarInfo) -> str:
    """Normalize the one known archive metadata defect, never path whitespace."""
    target = member.linkname
    normalized = target.rstrip("\r\n")
    if not normalized:
        raise InstallerError(f"Empty Tela archive link target: {member.name}")
    return normalized


def _inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except RuntimeError as exc:
        raise InstallerError(f"Symlink cycle while extracting Tela: {path}") from exc
    return resolved == root or root in resolved.parents


def extract_tela(archive: Path, destination: Path) -> None:
    _ensure_source(archive)
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve(strict=True)
    with tarfile.open(archive, "r:xz") as handle:
        members = handle.getmembers()
        for member in members:
            path = _tar_path(member.name)
            if member.ischr() or member.isblk() or member.isfifo():
                raise InstallerError(f"Unsupported Tela archive entry: {member.name}")
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                raise InstallerError(f"Unsupported Tela archive entry type: {member.name}")
            if member.issym() or member.islnk():
                link_target = _archive_link_target(member)
                target = PurePosixPath(link_target)
                if target.is_absolute():
                    raise InstallerError(f"Unsafe absolute Tela link: {member.name}")
                if member.issym():
                    resolved = PurePosixPath(posixpath.normpath(str(path.parent / target)))
                else:
                    resolved = PurePosixPath(posixpath.normpath(str(target)))
                if (
                    not resolved.parts
                    or resolved.parts[0] not in TELA_THEMES
                    or ".." in resolved.parts
                ):
                    raise InstallerError(
                        f"Tela link escapes theme root: {member.name} -> {member.linkname}"
                    )

        regular = [member for member in members if not (member.issym() or member.islnk())]
        handle.extractall(destination, members=regular, filter="data")

        for member in (entry for entry in members if entry.issym()):
            link = root.joinpath(*_tar_path(member.name).parts)
            if link.exists() or link.is_symlink() or not _inside(link.parent, root):
                raise InstallerError(f"Unsafe duplicate Tela link: {member.name}")
            os.symlink(_archive_link_target(member), link)
            if not _inside(link, root):
                link.unlink(missing_ok=True)
                raise InstallerError(f"Tela link escapes extraction root: {member.name}")

        pending = [entry for entry in members if entry.islnk()]
        while pending:
            remaining: list[tarfile.TarInfo] = []
            progress = False
            for member in pending:
                link = root.joinpath(*_tar_path(member.name).parts)
                source = root.joinpath(
                    *_tar_path(posixpath.normpath(_archive_link_target(member))).parts
                )
                if link.exists() or link.is_symlink() or not _inside(link.parent, root):
                    raise InstallerError(f"Unsafe duplicate Tela hardlink: {member.name}")
                if not _inside(source, root):
                    raise InstallerError(f"Tela hardlink escapes extraction root: {member.name}")
                if not source.exists() and not source.is_symlink():
                    remaining.append(member)
                    continue
                os.link(source, link, follow_symlinks=False)
                progress = True
            if remaining and not progress:
                raise InstallerError("Unresolved or cyclic Tela hardlinks")
            pending = remaining

    for theme in TELA_THEMES:
        _ensure_source(destination / theme, "directory")


def _install_trash_icons(core: Path, icons_root: Path) -> None:
    empty = _ensure_source(core / "assets/icons/user-trash.svg")
    full = _ensure_source(core / "assets/icons/user-trash-full.svg")
    places_empty = (
        "user-trash", "trash-empty", "trashcan_empty", "gnome-stock-trash",
        "gnome-fs-trash-empty", "stock_trash_empty", "xfce-trash_empty",
        "emptytrash", "edittrash",
    )
    places_full = (
        "user-trash-full", "trash-full", "trashcan_full", "gnome-stock-trash-full",
        "stock_trash_full", "xfce-trash_full",
    )
    for theme in TELA_THEMES:
        root = icons_root / theme
        for relative in ("scalable/places", "24/places", "22/places", "16/places"):
            directory = root / relative
            if not directory.is_dir():
                continue
            for name in places_empty:
                shutil.copy2(empty, directory / f"{name}.svg")
            for name in places_full:
                shutil.copy2(full, directory / f"{name}.svg")
        for relative in ("24/actions", "22/actions", "16/actions"):
            directory = root / relative
            if not directory.is_dir():
                continue
            for name in ("user-trash", "trash-empty", "trashcan_empty"):
                shutil.copy2(empty, directory / f"{name}.svg")
            for name in ("user-trash-full", "trash-full", "trashcan_full"):
                shutil.copy2(full, directory / f"{name}.svg")
        for relative in ("symbolic/places", "symbolic/status"):
            directory = root / relative
            directory.mkdir(parents=True, exist_ok=True)
            for name in ("user-trash-symbolic", "trash-empty-symbolic"):
                shutil.copy2(empty, directory / f"{name}.svg")
            for name in ("user-trash-full-symbolic", "trash-full-symbolic"):
                shutil.copy2(full, directory / f"{name}.svg")


def artifacts(context: InstallContext) -> list[Artifact]:
    data = context.data_home
    config = context.config_home
    tracked = _tracked_repository_paths(context.source_root)
    result = [
        Artifact("runtime", "package-runtime", data / "fedora-nova"),
        Artifact("launcher", "bin/fedora-nova", context.prefix / "bin/fedora-nova"),
        Artifact("launcher", "bin/fedora-nova-settings", context.prefix / "bin/fedora-nova-settings"),
        Artifact("launcher", "bin/fedora-nova-settings-devel", context.prefix / "bin/fedora-nova-settings-devel"),
    ]
    for app_id in ("io.github.fedoranova.FedoraNova", "io.github.fedoranova.FedoraNova.Devel"):
        result.extend(
            [
                Artifact("desktop", f"applications/{app_id}.desktop", data / f"applications/{app_id}.desktop"),
                Artifact("metainfo", f"metainfo/{app_id}.metainfo.xml", data / f"metainfo/{app_id}.metainfo.xml"),
                Artifact("schema", f"schemas/{app_id}.gschema.xml", data / f"glib-2.0/schemas/{app_id}.gschema.xml"),
                Artifact("app-icon", f"app-icons/{app_id}.svg", data / f"icons/hicolor/scalable/apps/{app_id}.svg"),
            ]
        )
    result.append(
        Artifact("legacy-app-icon", "app-icons/fedora-nova.svg", data / "icons/hicolor/scalable/apps/fedora-nova.svg")
    )
    result.extend(
        Artifact("shell-theme", f"themes/{theme}", data / f"themes/{theme}")
        for theme in THEMES
    )
    wallpaper_source = context.source_root / "core/assets/wallpapers"
    if wallpaper_source.is_dir() and not wallpaper_source.is_symlink():
        result.extend(
            Artifact(
                "wallpaper",
                f"backgrounds/fedora-nova/{path.name}",
                data / f"backgrounds/fedora-nova/{path.name}",
            )
            for path in sorted(wallpaper_source.iterdir())
            if path.is_file()
            and not path.is_symlink()
            and _is_reviewed_path(context.source_root, path, tracked)
        )
    result.extend(
        Artifact("ptyxis", f"ptyxis/{name}", data / f"org.gnome.Ptyxis/palettes/{name}")
        for name in PTYXIS_PALETTES
    )
    result.append(
        Artifact("fastfetch", "fastfetch/fedora-nova.jsonc", config / "fastfetch/fedora-nova.jsonc")
    )
    result.extend(
        Artifact("icon-theme", f"icons/{theme}", data / f"icons/{theme}")
        for theme in TELA_THEMES
    )
    result.append(
        Artifact(
            "shell-extension",
            f"extensions/{TOPBAR_UUID}",
            data / f"gnome-shell/extensions/{TOPBAR_UUID}",
        )
    )
    return result


def build_payload(context: InstallContext, destination: Path) -> list[Artifact]:
    source = context.source_root
    _validate_source_tree(source)
    tracked = _tracked_repository_paths(source)
    core = source / "core"
    _ensure_source(core, "directory")
    destination.mkdir(parents=True, exist_ok=False)

    package = destination / "package-runtime"
    package.mkdir()
    _copy_core(core, package / "core", tracked)
    _copy_reviewed_tree(
        source,
        _ensure_source(source / "app/src/fedora_nova", "directory"),
        package / "fedora_nova",
        tracked,
        extra_ignore=lambda directory, names: set(
            shutil.ignore_patterns("__pycache__", "*.pyc")(directory, names)
        ),
    )

    python = shutil.which("python3") or "/usr/bin/python3"
    package_path = context.data_home / "fedora-nova"
    replacements = {"@PYTHON@": python, "@PKGDATADIR@": str(package_path)}
    _render(source / "app/src/fedora-nova.in", destination / "bin/fedora-nova", replacements, 0o755)
    _render(
        source / "app/src/fedora-nova-settings.in",
        destination / "bin/fedora-nova-settings",
        replacements,
        0o755,
    )
    _render(
        source / "app/src/fedora-nova-settings-devel.in",
        destination / "bin/fedora-nova-settings-devel",
        replacements,
        0o755,
    )

    app_data = source / "app/data"
    for app_id in ("io.github.fedoranova.FedoraNova", "io.github.fedoranova.FedoraNova.Devel"):
        mapping = {
            app_data / f"{app_id}.desktop.in": destination / f"applications/{app_id}.desktop",
            app_data / f"{app_id}.metainfo.xml": destination / f"metainfo/{app_id}.metainfo.xml",
            app_data / f"{app_id}.gschema.xml": destination / f"schemas/{app_id}.gschema.xml",
            app_data / f"{app_id}.svg": destination / f"app-icons/{app_id}.svg",
        }
        for origin, target in mapping.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_ensure_source(origin), target)
    (destination / "app-icons").mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_source(core / "assets/icons/fedora-nova.svg"), destination / "app-icons/fedora-nova.svg")

    for theme in THEMES:
        target = destination / f"themes/{theme}"
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_reviewed_tree(
            source,
            _ensure_source(core / f"themes/{theme}", "directory"),
            target,
            tracked,
        )
    _copy_reviewed_tree(
        source,
        _ensure_source(core / "assets/wallpapers", "directory"),
        destination / "backgrounds/fedora-nova",
        tracked,
    )
    for name in PTYXIS_PALETTES:
        target = destination / f"ptyxis/{name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_ensure_source(core / f"terminal/ptyxis/{name}"), target)
    fastfetch = destination / "fastfetch/fedora-nova.jsonc"
    fastfetch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_ensure_source(core / "terminal/fastfetch/fedora-nova.jsonc"), fastfetch)

    icons = destination / "icons"
    extract_tela(core / "third-party/Tela-circle/Tela-circle.tar.xz", icons)
    _install_trash_icons(core, icons)

    extension = destination / f"extensions/{TOPBAR_UUID}"
    extension.parent.mkdir(parents=True, exist_ok=True)
    _copy_reviewed_tree(
        source,
        _ensure_source(core / f"third-party/topbar-all-monitors/{TOPBAR_UUID}", "directory"),
        extension,
        tracked,
    )

    # Source links that are in-repository can still escape after relocation
    # into the package layout. Validate the completed payload in its own root.
    _validate_source_tree(destination)
    # Managed directory artifacts are installed independently. A link that is
    # safe only because another staging sibling exists would escape its final
    # installed component, so validate those component boundaries as well.
    _validate_source_tree(package)
    for theme in THEMES:
        _validate_source_tree(destination / f"themes/{theme}")
    _validate_source_tree(destination / "backgrounds/fedora-nova")
    _validate_source_tree(icons)
    _validate_source_tree(extension)
    result = artifacts(context)
    for artifact in result:
        if not (destination / artifact.payload_name).exists() and not (destination / artifact.payload_name).is_symlink():
            raise InstallerError(f"Payload builder did not create {artifact.payload_name}")
    return result
