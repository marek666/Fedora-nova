#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE="$ROOT/core"
PROFILE="tech"
WATCH=0
STOP=0

usage() {
  cat <<'USAGE'
Fedora Nova Shell Preview

Usage:
  ./dev-shell-preview.sh [--watch] [PROFILE]
  ./dev-shell-preview.sh [PROFILE] --watch
  ./dev-shell-preview.sh --stop

Examples:
  ./dev-shell-preview.sh tech
  ./dev-shell-preview.sh --watch tech
  ./dev-shell-preview.sh --stop

In --watch mode the nested GNOME Shell is restarted when anything under
core/ changes. The host GNOME session is untouched.
USAGE
}

while (($#)); do
  case "$1" in
    --watch|-w) WATCH=1 ;;
    --stop) STOP=1 ;;
    -h|--help) usage; exit 0 ;;
    *) PROFILE="$1" ;;
  esac
  shift
done

if [[ $STOP -eq 1 ]]; then
  preview_root="${XDG_CACHE_HOME:-$HOME/.cache}/fedora-nova-shell-preview"
  live_pid_file="$preview_root/live.pid"
  live_lock_dir="$preview_root/live.lock"
  pid=""
  if [[ -s "$live_pid_file" ]]; then
    pid="$(<"$live_pid_file")"
  fi
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
  rm -rf "$live_lock_dir" "$live_pid_file"
  echo "Live Shell Preview zastaveno."
  exit 0
fi

command -v gnome-shell >/dev/null 2>&1 || {
  echo "CHYBA: gnome-shell není dostupný." >&2
  exit 1
}

if [[ ! -x /usr/libexec/mutter-devkit ]]; then
  cat >&2 <<'EOF'
CHYBA: Mutter Development Kit není nainstalovaný.

Na Fedoře:
  sudo dnf install mutter-devkit
EOF
  exit 1
fi

command -v dbus-run-session >/dev/null 2>&1 || {
  echo "CHYBA: chybí dbus-run-session." >&2
  exit 1
}

if [[ $WATCH -eq 1 ]]; then
  command -v setsid >/dev/null 2>&1 || {
    echo "CHYBA: live preview potřebuje setsid." >&2
    exit 1
  }
fi

PROFILE_JSON="$CORE/config/profiles.json"
[[ -f "$PROFILE_JSON" ]] || {
  echo "CHYBA: chybí $PROFILE_JSON" >&2
  exit 1
}

USER_THEME_UUID="user-theme@gnome-shell-extensions.gcampax.github.com"
DOCK_UUID="dash-to-dock@micxgx.gmail.com"
TOPBAR_UUID="topbar-all-monitors@fa8i.github.io"
TOPBAR_SOURCE="$CORE/third-party/topbar-all-monitors/$TOPBAR_UUID"

if [[ ! -d "/usr/share/gnome-shell/extensions/$USER_THEME_UUID" ]]; then
  cat >&2 <<EOF
CHYBA: chybí GNOME User Themes extension.

Na Fedoře:
  sudo dnf install gnome-shell-extension-user-theme
EOF
  exit 1
fi

ENABLED="['$USER_THEME_UUID'"
if [[ -d "/usr/share/gnome-shell/extensions/$DOCK_UUID" ]]; then
  ENABLED+=", '$DOCK_UUID'"
fi
if [[ -d "$TOPBAR_SOURCE" ]]; then
  ENABLED+=", '$TOPBAR_UUID'"
fi
ENABLED+="]"

ORIGINAL_XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
ORIGINAL_XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

PREVIEW_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/fedora-nova-shell-preview"
PREVIEW_CONFIG="$PREVIEW_ROOT/config"
PREVIEW_DATA="$PREVIEW_ROOT/data"
PREVIEW_CACHE="$PREVIEW_ROOT/cache"
PREVIEW_STATE="$PREVIEW_ROOT/state"
LIVE_LOCK_DIR="$PREVIEW_ROOT/live.lock"
LIVE_PID_FILE="$PREVIEW_ROOT/live.pid"

SHELL_PID=""
WATCH_PID=""

is_pid() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

live_pid() {
  local pid=""
  if [[ -s "$LIVE_PID_FILE" ]]; then
    pid="$(<"$LIVE_PID_FILE")"
  fi
  if is_pid "$pid"; then
    printf '%s\n' "$pid"
  fi
  return 0
}

live_running() {
  local pid
  pid="$(live_pid)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

stop_live_preview() {
  local pid
  pid="$(live_pid)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
  rm -rf "$LIVE_LOCK_DIR" "$LIVE_PID_FILE"
}

acquire_live_lock() {
  mkdir -p "$PREVIEW_ROOT"
  if mkdir "$LIVE_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LIVE_PID_FILE"
    return
  fi

  if live_running; then
    echo "Live Shell Preview už běží. Zavři jeho okno nebo spusť ./dev-shell-preview.sh --stop." >&2
    exit 2
  fi

  rm -rf "$LIVE_LOCK_DIR" "$LIVE_PID_FILE"
  mkdir "$LIVE_LOCK_DIR"
  printf '%s\n' "$$" > "$LIVE_PID_FILE"
}

release_live_lock() {
  if [[ -s "$LIVE_PID_FILE" ]] && [[ "$(<"$LIVE_PID_FILE")" == "$$" ]]; then
    rm -rf "$LIVE_LOCK_DIR" "$LIVE_PID_FILE"
  fi
}

load_profile() {
  mapfile -t PROFILE_DATA < <(
    python3 - "$PROFILE_JSON" "$PROFILE" <<'PY'
import json
import sys

path, profile_id = sys.argv[1:]
data = json.load(open(path, encoding="utf-8"))
item = data.get("profiles", {}).get(profile_id)
if not item:
    raise SystemExit(f"Neznámý profil: {profile_id}")

for value in (
    item["theme"],
    item["wallpaper"],
    item.get("accent_name", "teal"),
    item.get("dock_color", item.get("panel", "#08091B")),
    str(item.get("dock_opacity", 0.80)),
    str(item.get("dock_icon_size", 42)),
):
    print(value)
PY
  )

  THEME="${PROFILE_DATA[0]}"
  WALLPAPER="${PROFILE_DATA[1]}"
  ACCENT="${PROFILE_DATA[2]}"
  DOCK_COLOR="${PROFILE_DATA[3]}"
  DOCK_OPACITY="${PROFILE_DATA[4]}"
  DOCK_SIZE="${PROFILE_DATA[5]}"
}

prepare_preview_root() {
  rm -rf "$PREVIEW_CONFIG" "$PREVIEW_DATA" "$PREVIEW_CACHE" "$PREVIEW_STATE"
  mkdir -p \
    "$PREVIEW_CONFIG" \
    "$PREVIEW_CONFIG/autostart" \
    "$PREVIEW_CONFIG/fedora-nova" \
    "$PREVIEW_DATA/themes" \
    "$PREVIEW_DATA/icons" \
    "$PREVIEW_DATA/gnome-shell/extensions" \
    "$PREVIEW_DATA/backgrounds/fedora-nova" \
    "$PREVIEW_CACHE" \
    "$PREVIEW_STATE"

  cp -a "$CORE/themes/." "$PREVIEW_DATA/themes/"
  cp -a "$CORE/assets/wallpapers/." "$PREVIEW_DATA/backgrounds/fedora-nova/"
  if [[ -d "$TOPBAR_SOURCE" ]]; then
    cp -a "$TOPBAR_SOURCE" "$PREVIEW_DATA/gnome-shell/extensions/"
  fi

  for desktop_id in \
    org.gnome.Tour.desktop \
    gnome-tour.desktop \
    gnome-initial-setup.desktop \
    gnome-initial-setup-first-login.desktop \
    fedora-welcome.desktop \
    org.fedoraproject.Welcome.desktop; do
    cat > "$PREVIEW_CONFIG/autostart/$desktop_id" <<EOF
[Desktop Entry]
Type=Application
Name=${desktop_id%.desktop}
Hidden=true
X-GNOME-Autostart-enabled=false
NoDisplay=true
EOF
  done
  : > "$PREVIEW_CONFIG/gnome-initial-setup-done"

  printf '%s\n' "$PROFILE" > "$PREVIEW_CONFIG/fedora-nova/current-profile"
  printf 'squircle\n' > "$PREVIEW_CONFIG/fedora-nova/current-curve"
  printf 'circle\n' > "$PREVIEW_CONFIG/fedora-nova/current-hover"
  printf 'tela\n' > "$PREVIEW_CONFIG/fedora-nova/current-icons"
  printf 'on\n' > "$PREVIEW_CONFIG/fedora-nova/current-gtk"

  XDG_DATA_HOME="$PREVIEW_DATA" \
    FEDORA_NOVA_APP_DIR="$CORE" \
    "$CORE/scripts/install-tela-icons.sh" >/dev/null 2>&1 || true
  XDG_CONFIG_HOME="$PREVIEW_CONFIG" \
    XDG_DATA_HOME="$PREVIEW_DATA" \
    XDG_STATE_HOME="$PREVIEW_STATE" \
    FEDORA_NOVA_APP_DIR="$CORE" \
    "$CORE/scripts/gtk-theme.sh" on >/dev/null 2>&1 || true
  python3 "$CORE/scripts/curve_style.py" apply squircle \
    "$CORE/config/curves.json" "$PREVIEW_DATA/themes" >/dev/null 2>&1 || true
  python3 "$CORE/scripts/hover_style.py" circle \
    "$CORE/config/profiles.json" "$PREVIEW_CONFIG/fedora-nova/custom-profiles" \
    "$PREVIEW_DATA/themes" >/dev/null 2>&1 || true

  WALL_PATH="$PREVIEW_DATA/backgrounds/fedora-nova/$WALLPAPER"
  [[ -f "$WALL_PATH" ]] || {
    echo "CHYBA: chybí wallpaper $WALL_PATH" >&2
    exit 1
  }
}

export_preview_env() {
  export XDG_CONFIG_HOME="$PREVIEW_CONFIG"
  export XDG_DATA_HOME="$PREVIEW_DATA"
  export XDG_CACHE_HOME="$PREVIEW_CACHE"
  export XDG_STATE_HOME="$PREVIEW_STATE"

  # Keep host user applications, icons and system data discoverable while
  # retaining a completely separate user theme + dconf database.
  export XDG_DATA_DIRS="$ORIGINAL_XDG_DATA_HOME:$ORIGINAL_XDG_DATA_DIRS"

  export NOVA_PREVIEW_THEME="$THEME"
  export NOVA_PREVIEW_WALL="$WALL_PATH"
  export NOVA_PREVIEW_ACCENT="$ACCENT"
  export NOVA_PREVIEW_EXTENSIONS="$ENABLED"
  export NOVA_PREVIEW_ICON_THEME="Tela-circle"
  export NOVA_PREVIEW_DOCK_COLOR="$DOCK_COLOR"
  export NOVA_PREVIEW_DOCK_OPACITY="$DOCK_OPACITY"
  export NOVA_PREVIEW_DOCK_SIZE="$DOCK_SIZE"
}

print_banner() {
  echo
  echo "Fedora Nova Shell Preview"
  echo "========================="
  echo "Profil:      $PROFILE"
  echo "Shell theme: $THEME"
  echo "Wallpaper:   $WALLPAPER"
  echo "Izolace:     $PREVIEW_ROOT"
  if [[ $WATCH -eq 1 ]]; then
    echo "Live:        zapnuto"
  fi
  echo
  echo "Zavřením okna Mutter Development Kit ukončíš preview."
  echo
}

SESSION_SCRIPT='
set -e

gsettings set org.gnome.desktop.interface color-scheme "prefer-dark" || true
gsettings set org.gnome.desktop.interface accent-color "$NOVA_PREVIEW_ACCENT" || true
gsettings set org.gnome.desktop.interface icon-theme "$NOVA_PREVIEW_ICON_THEME" || true
gsettings set org.gnome.desktop.background picture-uri "file://$NOVA_PREVIEW_WALL" || true
gsettings set org.gnome.desktop.background picture-uri-dark "file://$NOVA_PREVIEW_WALL" || true
gsettings set org.gnome.desktop.background picture-options "zoom" || true
if gsettings writable org.gnome.shell welcome-dialog-last-shown-version >/dev/null 2>&1; then
  shell_version="$(gnome-shell --version 2>/dev/null | awk "{print \$NF}")"
  gsettings set org.gnome.shell welcome-dialog-last-shown-version "${shell_version:-999.0}" || true
fi

gsettings set org.gnome.shell enabled-extensions "$NOVA_PREVIEW_EXTENSIONS"
gsettings set org.gnome.shell.extensions.user-theme name "$NOVA_PREVIEW_THEME"
gsettings set org.gnome.mutter center-new-windows true || true
gsettings set org.gnome.mutter dynamic-workspaces true || true
gsettings set org.gnome.mutter edge-tiling true || true
gsettings set org.gnome.mutter workspaces-only-on-primary false || true

if gsettings writable org.gnome.shell.extensions.dash-to-dock dock-position >/dev/null 2>&1; then
  gsettings set org.gnome.shell.extensions.dash-to-dock dock-position "BOTTOM" || true
  gsettings set org.gnome.shell.extensions.dash-to-dock extend-height false || true
  gsettings set org.gnome.shell.extensions.dash-to-dock dash-max-icon-size "$NOVA_PREVIEW_DOCK_SIZE" || true
  gsettings set org.gnome.shell.extensions.dash-to-dock transparency-mode "FIXED" || true
  gsettings set org.gnome.shell.extensions.dash-to-dock custom-background-color true || true
  gsettings set org.gnome.shell.extensions.dash-to-dock background-color "$NOVA_PREVIEW_DOCK_COLOR" || true
  gsettings set org.gnome.shell.extensions.dash-to-dock background-opacity "$NOVA_PREVIEW_DOCK_OPACITY" || true
fi

exec gnome-shell --devkit --wayland
'

start_shell() {
  load_profile
  prepare_preview_root
  export_preview_env
  print_banner
  setsid dbus-run-session -- bash -lc "$SESSION_SCRIPT" &
  SHELL_PID=$!
}

stop_shell() {
  if [[ -n "${SHELL_PID:-}" ]] && kill -0 "-$SHELL_PID" 2>/dev/null; then
    kill -TERM -- "-$SHELL_PID" 2>/dev/null || true
    for _ in {1..40}; do
      kill -0 "-$SHELL_PID" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "-$SHELL_PID" 2>/dev/null; then
      kill -KILL -- "-$SHELL_PID" 2>/dev/null || true
    fi
    wait "$SHELL_PID" 2>/dev/null || true
  fi
  SHELL_PID=""
}

snapshot_state() {
  find "$CORE" \
    -type f -printf '%T@ %p\n' 2>/dev/null |
    sort |
    sha256sum
}

start_watcher() {
  if command -v inotifywait >/dev/null 2>&1; then
    inotifywait -q -r \
      -e close_write,create,delete,move \
      "$CORE" >/dev/null &
    WATCH_PID=$!
    return
  fi

  (
    previous="$(snapshot_state)"
    while sleep 2; do
      current="$(snapshot_state)"
      [[ "$current" != "$previous" ]] && exit 0
    done
  ) &
  WATCH_PID=$!
}

cleanup() {
  if [[ -n "${WATCH_PID:-}" ]] && kill -0 "$WATCH_PID" 2>/dev/null; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi
  stop_shell
  release_live_lock
}

if [[ $WATCH -ne 1 ]]; then
  load_profile
  prepare_preview_root
  export_preview_env
  print_banner
  exec dbus-run-session -- bash -lc "$SESSION_SCRIPT"
fi

acquire_live_lock
trap cleanup INT TERM EXIT
while true; do
  start_shell
  start_watcher

  wait -n "$SHELL_PID" "$WATCH_PID" 2>/dev/null || true

  if ! kill -0 "$SHELL_PID" 2>/dev/null; then
    stop_shell
    exit 0
  fi

  if kill -0 "$WATCH_PID" 2>/dev/null; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi

  wait "$WATCH_PID" 2>/dev/null || true
  echo
  echo "Změna ve zdrojích, restartuji Shell Preview..."
  stop_shell
  sleep 0.5
done
