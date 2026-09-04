#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

ARCHIVE="$PROJECT_DIR/third-party/Tela-circle/Tela-circle.tar.xz"
ICONS_ROOT="$NOVA_DATA_HOME/icons"
[[ -f "$ARCHIVE" ]] || die "Chybí bundled Tela Circle archiv."
command_exists python3 || die "Chybí python3."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$ARCHIVE" "$TMP" <<'PY'
import posixpath
import sys
import tarfile
from pathlib import PurePosixPath

archive, destination = sys.argv[1:]
allowed_roots = {"Tela-circle", "Tela-circle-dark", "Tela-circle-light"}

with tarfile.open(archive, "r:xz") as tf:
    members = tf.getmembers()

    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"Unsafe Tela archive path: {member.name}")
        if not path.parts or path.parts[0] not in allowed_roots:
            raise SystemExit(f"Unexpected Tela archive root: {member.name}")
        if member.ischr() or member.isblk() or member.isfifo():
            raise SystemExit(f"Unsupported Tela archive entry: {member.name}")

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

    # Tela variants intentionally contain directory symlinks that point back to
    # shared content in another bundled variant. GNU tar can encounter one of
    # those links before later members and then fail to create the remaining
    # real directory tree beneath that path. Extract real entries first and
    # create symlinks/hardlinks only after the filesystem tree is complete.
    regular_members = [member for member in members if not (member.issym() or member.islnk())]
    link_members = [member for member in members if member.issym() or member.islnk()]

    tf.extractall(destination, members=regular_members, filter="data")
    tf.extractall(destination, members=link_members, filter="data")
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
