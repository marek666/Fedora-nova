#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

ARCHIVE="$PROJECT_DIR/third-party/Tela-circle/Tela-circle.tar.xz"
ICONS_ROOT="$NOVA_DATA_HOME/icons"
[[ -f "$ARCHIVE" ]] || die "Chybí bundled Tela Circle archiv."
command_exists python3 || die "Chybí python3."

# Keep the extraction workspace on the configured cache filesystem instead of
# assuming /tmp has enough tmpfs space for the expanded icon payload.
TMP_BASE="${XDG_CACHE_HOME:-${TMPDIR:-/tmp}}"
mkdir -p "$TMP_BASE"
TMP="$(mktemp -d "$TMP_BASE/fedora-nova-tela.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

python3 - "$ARCHIVE" "$TMP" <<'PY'
import os
import posixpath
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive, destination = sys.argv[1:]
allowed_roots = {"Tela-circle", "Tela-circle-dark", "Tela-circle-light"}
destination_root = Path(destination).resolve()


def validated_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe Tela archive path: {name}")
    if not path.parts or path.parts[0] not in allowed_roots:
        raise SystemExit(f"Unexpected Tela archive root: {name}")
    return path


def filesystem_path(path: PurePosixPath) -> Path:
    return destination_root.joinpath(*path.parts)


def ensure_inside_destination(path: Path, description: str) -> None:
    try:
        resolved = path.resolve(strict=False)
    except RuntimeError as exc:
        raise SystemExit(f"Unsafe Tela link cycle in {description}: {path}") from exc
    if not resolved.is_relative_to(destination_root):
        raise SystemExit(f"Tela link escapes extraction root in {description}: {path}")


def ensure_link_destination_available(path: Path, member_name: str) -> None:
    ensure_inside_destination(path.parent, member_name)
    if path.exists() or path.is_symlink():
        raise SystemExit(f"Duplicate Tela archive link destination: {member_name}")


with tarfile.open(archive, "r:xz") as tf:
    members = tf.getmembers()

    for member in members:
        path = validated_path(member.name)
        if member.ischr() or member.isblk() or member.isfifo():
            raise SystemExit(f"Unsupported Tela archive entry: {member.name}")
        if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
            raise SystemExit(f"Unsupported Tela archive entry type: {member.name}")

        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            if target.is_absolute():
                raise SystemExit(f"Unsafe absolute Tela link: {member.name}")
            if member.issym():
                resolved = PurePosixPath(posixpath.normpath(str(path.parent / target)))
            else:
                resolved = PurePosixPath(posixpath.normpath(str(target)))
            if not resolved.parts or resolved.parts[0] not in allowed_roots or ".." in resolved.parts:
                raise SystemExit(f"Tela link escapes theme root: {member.name} -> {member.linkname}")

    # First extract only real filesystem objects. No archive link exists yet, so
    # later regular members cannot accidentally traverse a directory symlink.
    regular_members = [member for member in members if not (member.issym() or member.islnk())]
    tf.extractall(destination, members=regular_members, filter="data")

    # tarfile's link extraction may fall back to extracting/materializing the
    # referenced member when the target cannot be resolved immediately. With
    # large icon themes that can duplicate payload data and exhaust tmpfs. Keep
    # the archive semantics explicitly: symlinks stay symlinks and hardlinks
    # stay hardlinks, created only after all real files/directories exist.
    symlink_members = [member for member in members if member.issym()]
    hardlink_members = [member for member in members if member.islnk()]

    for member in symlink_members:
        member_path = validated_path(member.name)
        link_path = filesystem_path(member_path)
        ensure_link_destination_available(link_path, member.name)
        os.symlink(member.linkname, link_path)
        try:
            ensure_inside_destination(link_path, member.name)
        except BaseException:
            link_path.unlink(missing_ok=True)
            raise

    # Hardlink targets can themselves be hardlinks declared later in the
    # archive. Resolve them in passes until every target exists, or fail cleanly
    # if the archive contains an unresolved/cyclic hardlink chain.
    pending = list(hardlink_members)
    while pending:
        remaining = []
        progress = False

        for member in pending:
            member_path = validated_path(member.name)
            target_path = validated_path(posixpath.normpath(member.linkname))
            link_path = filesystem_path(member_path)
            source_path = filesystem_path(target_path)

            ensure_link_destination_available(link_path, member.name)
            ensure_inside_destination(source_path, f"{member.name} -> {member.linkname}")

            if not source_path.exists() and not source_path.is_symlink():
                remaining.append(member)
                continue

            os.link(source_path, link_path, follow_symlinks=False)
            progress = True

        if remaining and not progress:
            unresolved = ", ".join(member.name for member in remaining[:5])
            raise SystemExit(f"Unresolved Tela hardlink targets: {unresolved}")

        pending = remaining
PY

mkdir -p "$ICONS_ROOT"
for theme in Tela-circle Tela-circle-dark Tela-circle-light; do
  [[ -d "$TMP/$theme" ]] || die "V archivu chybí $theme."
  rm -rf "$ICONS_ROOT/$theme"
  cp -a "$TMP/$theme" "$ICONS_ROOT/"
done

"$SCRIPT_DIR/install-trash-icons.sh" "$ICONS_ROOT"

for theme in Tela-circle Tela-circle-dark Tela-circle-light; do
  if command_exists gtk-update-icon-cache; then
    gtk-update-icon-cache -f -t "$ICONS_ROOT/$theme" >/dev/null 2>&1 || true
  fi
done
log "Tela Circle: nainstalovány varianty standard, dark a light včetně Nova koše."
