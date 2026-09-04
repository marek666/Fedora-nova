#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

ICONS_ROOT="${1:-$NOVA_DATA_HOME/icons}"
EMPTY_ICON="$PROJECT_DIR/assets/icons/user-trash.svg"
FULL_ICON="$PROJECT_DIR/assets/icons/user-trash-full.svg"

[[ -f "$EMPTY_ICON" && -f "$FULL_ICON" ]] ||
  die "Chybí Nova ikony koše v $PROJECT_DIR/assets/icons."

copy_icon() {
  local source="$1"
  local target="$2"
  cp -f "$source" "$target"
}

install_theme_trash_icons() {
  local theme="$1"
  local root="$ICONS_ROOT/$theme"
  local copied=0
  local dir name

  [[ -d "$root" ]] || return 0

  for dir in \
    "$root/scalable/places" \
    "$root/24/places" \
    "$root/22/places" \
    "$root/16/places"; do
    [[ -d "$dir" ]] || continue
    for name in user-trash trash-empty trashcan_empty gnome-stock-trash \
                gnome-fs-trash-empty stock_trash_empty xfce-trash_empty \
                emptytrash edittrash; do
      copy_icon "$EMPTY_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
    for name in user-trash-full trash-full trashcan_full gnome-stock-trash-full \
                stock_trash_full xfce-trash_full; do
      copy_icon "$FULL_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
  done

  for dir in \
    "$root/24/actions" \
    "$root/22/actions" \
    "$root/16/actions"; do
    [[ -d "$dir" ]] || continue
    for name in user-trash trash-empty trashcan_empty; do
      copy_icon "$EMPTY_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
    for name in user-trash-full trash-full trashcan_full; do
      copy_icon "$FULL_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
  done

  # GNOME Shell/St.Icon can prefer symbolic variants even when the themed icon
  # starts as "user-trash". Ensure the symbolic lookup directories exist for
  # every bundled Tela variant (Tela-circle-light omits them in the archive),
  # then install the Fedora Nova rounded trash artwork there too.
  for dir in \
    "$root/symbolic/places" \
    "$root/symbolic/status"; do
    mkdir -p "$dir"
    for name in user-trash-symbolic trash-empty-symbolic; do
      copy_icon "$EMPTY_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
    for name in user-trash-full-symbolic trash-full-symbolic; do
      copy_icon "$FULL_ICON" "$dir/$name.svg"
      copied=$((copied + 1))
    done
  done

  if ((copied > 0)); then
    printf '  trash overlay %-18s %s ikon\n' "$theme" "$copied"
  fi
}

for theme in Tela-circle Tela-circle-dark Tela-circle-light; do
  install_theme_trash_icons "$theme"
done
