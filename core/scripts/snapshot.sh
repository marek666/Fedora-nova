#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ROOT="$NOVA_STATE_DIR/snapshots"
mkdir -p "$ROOT"

sanitize() {
  printf '%s' "$1" | tr -cs '[:alnum:]_.-' '-' | sed 's/^-//;s/-$//'
}

create_snapshot() {
  local raw="${1:-$(date +%Y%m%d-%H%M%S)}" name dir
  name="$(sanitize "$raw")"
  [[ -n "$name" ]] || die "Neplatný název snapshotu."
  dir="$ROOT/$name"
  [[ ! -e "$dir" ]] || die "Snapshot už existuje: $name"
  mkdir -p "$dir/dconf"

  dconf dump /org/gnome/desktop/interface/ > "$dir/dconf/interface.dconf" || true
  dconf dump /org/gnome/desktop/wm/preferences/ > "$dir/dconf/wm-preferences.dconf" || true
  dconf dump /org/gnome/desktop/background/ > "$dir/dconf/background.dconf" || true
  dconf dump /org/gnome/desktop/screensaver/ > "$dir/dconf/screensaver.dconf" || true
  dconf dump /org/gnome/shell/ > "$dir/dconf/shell.dconf" || true
  dconf dump /org/gnome/shell/extensions/user-theme/ > "$dir/dconf/user-theme.dconf" || true
  dconf dump /org/gnome/shell/extensions/dash-to-dock/ > "$dir/dconf/dash-to-dock.dconf" || true
  dconf dump /org/gnome/shell/extensions/blur-my-shell/ > "$dir/dconf/blur-my-shell.dconf" || true

  for f in current-profile previous-profile current-dock previous-dock current-motion previous-motion current-curve previous-curve current-icons current-hover previous-hover current-gtk; do
    [[ -f "$NOVA_CONFIG_DIR/$f" ]] && cp "$NOVA_CONFIG_DIR/$f" "$dir/$f"
  done
  cat > "$dir/manifest.txt" <<EOF
Fedora Nova snapshot
version=$NOVA_VERSION
created=$(date --iso-8601=seconds)
profile=$(current_profile)
curve=$(current_curve)
hostname=$(hostname)
EOF
  printf '%s\n' "$dir" > "$NOVA_STATE_DIR/latest-snapshot"
  log "Snapshot vytvořen: $name"
}

list_snapshots() {
  find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort || true
}

restore_snapshot() {
  local name="${1:-}" dir
  [[ -n "$name" ]] || die "Chybí název snapshotu."
  dir="$ROOT/$(sanitize "$name")"
  [[ -d "$dir" ]] || die "Snapshot neexistuje: $name"

  load() {
    local file="$1" path="$2"
    [[ -s "$dir/dconf/$file.dconf" ]] && dconf load "$path" < "$dir/dconf/$file.dconf"
  }
  load interface /org/gnome/desktop/interface/
  load wm-preferences /org/gnome/desktop/wm/preferences/
  load background /org/gnome/desktop/background/
  load screensaver /org/gnome/desktop/screensaver/
  load shell /org/gnome/shell/
  load user-theme /org/gnome/shell/extensions/user-theme/
  load dash-to-dock /org/gnome/shell/extensions/dash-to-dock/
  load blur-my-shell /org/gnome/shell/extensions/blur-my-shell/

  mkdir -p "$NOVA_CONFIG_DIR"
  for f in current-profile previous-profile current-dock previous-dock current-motion previous-motion current-curve previous-curve current-icons current-hover previous-hover current-gtk; do
    [[ -f "$dir/$f" ]] && cp "$dir/$f" "$NOVA_CONFIG_DIR/$f"
  done
  disable_extension blur-my-shell@aunetx
  "$SCRIPT_DIR/apply-hover.sh" "$(current_hover)" >/dev/null 2>&1 || true
  "$SCRIPT_DIR/gtk-theme.sh" "$(current_gtk)" >/dev/null 2>&1 || true
  log "Snapshot obnoven: $name. Pro jistotu proveď relogin."
}

delete_snapshot() {
  local name="${1:-}" dir
  [[ -n "$name" ]] || die "Chybí název snapshotu."
  dir="$ROOT/$(sanitize "$name")"
  [[ -d "$dir" ]] || die "Snapshot neexistuje: $name"
  rm -rf -- "$dir"
  log "Snapshot odstraněn: $name"
}

case "${1:-list}" in
  create) create_snapshot "${2:-}" ;;
  list) list_snapshots ;;
  restore) restore_snapshot "${2:-}" ;;
  delete) delete_snapshot "${2:-}" ;;
  *) die "Použij: snapshot.sh {create [NAME]|list|restore NAME|delete NAME}" ;;
esac
