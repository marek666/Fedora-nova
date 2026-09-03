#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE="$ROOT/core"
PROFILE="tech"
WATCH=0
STOP=0

PREVIEW_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/fedora-nova-shell-preview"
PREVIEW_CONFIG="$PREVIEW_ROOT/config"
PREVIEW_DATA="$PREVIEW_ROOT/data"
PREVIEW_CACHE="$PREVIEW_ROOT/cache"
PREVIEW_STATE="$PREVIEW_ROOT/state"
RUNTIME_DIR="$PREVIEW_ROOT/runtime"
LIVE_LOCK_DIR="$PREVIEW_ROOT/live.lock"
SUPERVISOR_PID_FILE="$RUNTIME_DIR/supervisor.pid"
SESSION_PID_FILE="$RUNTIME_DIR/session.pid"
SESSION_PGID_FILE="$RUNTIME_DIR/session.pgid"
SESSION_META_FILE="$RUNTIME_DIR/session.env"

SHELL_PID=""
SHELL_PGID=""
WATCH_PID=""

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

The preview runs in an isolated XDG + D-Bus session. In --watch mode the
nested GNOME Shell is restarted when anything under core/ changes.
The host GNOME session is untouched.
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

is_pid() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

read_pid_file() {
  local path="$1"
  local value=""
  [[ -s "$path" ]] && value="$(<"$path")"
  is_pid "$value" && printf '%s\n' "$value"
  return 0
}

process_cmdline() {
  local pid="$1"
  [[ -r "/proc/$pid/cmdline" ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline"
}

process_matches() {
  local pid="$1"
  local pattern="$2"
  is_pid "$pid" || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  process_cmdline "$pid" 2>/dev/null | grep -Fq -- "$pattern"
}

current_pgid() {
  ps -o pgid= -p "$$" 2>/dev/null | tr -d ' '
}

safe_kill_group() {
  local pgid="$1"
  local signal="${2:-TERM}"
  local own_pgid=""

  is_pid "$pgid" || return 1
  own_pgid="$(current_pgid)"
  if [[ -n "$own_pgid" && "$pgid" == "$own_pgid" ]]; then
    echo "CHYBA: odmítám ukončit vlastní process group $pgid." >&2
    return 1
  fi

  kill -s "$signal" -- "-$pgid" 2>/dev/null || true
}

clear_session_metadata() {
  rm -f "$SESSION_PID_FILE" "$SESSION_PGID_FILE" "$SESSION_META_FILE"
}

stop_recorded_session() {
  local pid pgid actual_pgid
  pid="$(read_pid_file "$SESSION_PID_FILE")"
  pgid="$(read_pid_file "$SESSION_PGID_FILE")"

  if [[ -z "$pid" || -z "$pgid" ]]; then
    clear_session_metadata
    return 0
  fi

  # Avoid killing an unrelated process if a stale PID has been recycled.
  if ! process_matches "$pid" "dbus-run-session"; then
    clear_session_metadata
    return 0
  fi

  actual_pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  if [[ -z "$actual_pgid" || "$actual_pgid" != "$pgid" ]]; then
    clear_session_metadata
    return 0
  fi

  safe_kill_group "$pgid" TERM
  for _ in {1..40}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then
    safe_kill_group "$pgid" KILL
  fi

  clear_session_metadata
}

stop_external_preview() {
  local supervisor
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"

  if [[ -n "$supervisor" ]] && process_matches "$supervisor" "dev-shell-preview.sh"; then
    kill -TERM "$supervisor" 2>/dev/null || true
    for _ in {1..40}; do
      kill -0 "$supervisor" 2>/dev/null || break
      sleep 0.1
    done
  fi

  # If the supervisor was killed abruptly, clean up its nested session too.
  stop_recorded_session
  rm -rf "$LIVE_LOCK_DIR"
  rm -f "$SUPERVISOR_PID_FILE"
  echo "Shell Preview zastaveno."
}

if [[ $STOP -eq 1 ]]; then
  stop_external_preview
  exit 0
fi

command -v gnome-shell >/dev/null 2>&1 || {
  echo "CHYBA: gnome-shell není dostupný." >&2
  exit 1
}

if [[ ! -x /usr/libexec/mutter-devkit ]]; then
  cat >&2 <<'ERR'
CHYBA: Mutter Development Kit není nainstalovaný.

Na Fedoře:
  sudo dnf install mutter-devkit
ERR
  exit 1
fi

for command_name in dbus-run-session setsid ps grep tr python3; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "CHYBA: chybí $command_name." >&2
    exit 1
  }
done

if ! command -v inotifywait >/dev/null 2>&1; then
  for command_name in find sort sha256sum; do
    command -v "$command_name" >/dev/null 2>&1 || {
      echo "CHYBA: bez inotifywait chybí fallback nástroj $command_name." >&2
      exit 1
    }
  done
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

acquire_live_lock() {
  mkdir -p "$PREVIEW_ROOT" "$RUNTIME_DIR"

  if mkdir "$LIVE_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$SUPERVISOR_PID_FILE"
    return 0
  fi

  local supervisor
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"
  if [[ -n "$supervisor" ]] && process_matches "$supervisor" "dev-shell-preview.sh"; then
    echo "Shell Preview už běží. Zavři jeho okno nebo spusť ./dev-shell-preview.sh --stop." >&2
    exit 2
  fi

  # Stale lock after a crash. Clean only a session that still matches our
  # recorded dbus-run-session PID/PGID pair.
  stop_recorded_session
  rm -rf "$LIVE_LOCK_DIR"
  mkdir "$LIVE_LOCK_DIR"
  printf '%s\n' "$$" > "$SUPERVISOR_PID_FILE"
}

release_live_lock() {
  local supervisor
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"
  if [[ "$supervisor" == "$$" ]]; then
    rm -rf "$LIVE_LOCK_DIR"
    rm -f "$SUPERVISOR_PID_FILE"
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
  # Runtime metadata lives outside these generated/session directories so a
  # restart cannot erase the information needed to stop a stale session.
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
    "$PREVIEW_STATE" \
    "$RUNTIME_DIR"

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
    org.fedoraproject.Welcome.desktop \
    liveinst-setup.desktop; do
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

  # Host applications remain discoverable for now. Extension isolation will
  # be tightened separately so that this lifecycle change stays low-risk.
  export XDG_DATA_DIRS="$ORIGINAL_XDG_DATA_HOME:$ORIGINAL_XDG_DATA_DIRS"

  # The nested development session does not need accessibility bridging by
  # default. Set NOVA_PREVIEW_A11Y=1 to test accessibility explicitly.
  if [[ "${NOVA_PREVIEW_A11Y:-0}" != "1" ]]; then
    export NO_AT_BRIDGE=1
    export GTK_A11Y=none
  else
    unset NO_AT_BRIDGE GTK_A11Y || true
  fi

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
  if [[ "${NOVA_PREVIEW_A11Y:-0}" == "1" ]]; then
    echo "A11y bridge: zapnutý"
  else
    echo "A11y bridge: vypnutý (dev preview)"
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

record_session_metadata() {
  local started_at
  started_at="$(date --iso-8601=seconds 2>/dev/null || date)"
  printf '%s\n' "$SHELL_PID" > "$SESSION_PID_FILE"
  printf '%s\n' "$SHELL_PGID" > "$SESSION_PGID_FILE"
  cat > "$SESSION_META_FILE" <<EOF
supervisor_pid=$$
session_pid=$SHELL_PID
process_group_id=$SHELL_PGID
profile=$PROFILE
started_at=$started_at
EOF
}

start_shell() {
  load_profile
  prepare_preview_root
  export_preview_env
  print_banner

  setsid dbus-run-session -- bash -lc "$SESSION_SCRIPT" &
  SHELL_PID=$!

  SHELL_PGID=""
  for _ in {1..20}; do
    SHELL_PGID="$(ps -o pgid= -p "$SHELL_PID" 2>/dev/null | tr -d ' ')"
    [[ -n "$SHELL_PGID" ]] && break
    sleep 0.05
  done
  if ! is_pid "$SHELL_PGID"; then
    echo "CHYBA: nepodařilo se zjistit process group Shell Preview." >&2
    kill "$SHELL_PID" 2>/dev/null || true
    wait "$SHELL_PID" 2>/dev/null || true
    return 1
  fi

  record_session_metadata
}

stop_shell() {
  local pid="${SHELL_PID:-}"
  local pgid="${SHELL_PGID:-}"

  if ! is_pid "$pid"; then
    pid="$(read_pid_file "$SESSION_PID_FILE")"
  fi
  if ! is_pid "$pgid"; then
    pgid="$(read_pid_file "$SESSION_PGID_FILE")"
  fi

  if [[ -n "$pid" && -n "$pgid" ]] && process_matches "$pid" "dbus-run-session"; then
    safe_kill_group "$pgid" TERM
    for _ in {1..40}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
      safe_kill_group "$pgid" KILL
    fi
    wait "$pid" 2>/dev/null || true
  fi

  SHELL_PID=""
  SHELL_PGID=""
  clear_session_metadata
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
  WATCH_PID=""
  stop_shell
  release_live_lock
}

acquire_live_lock
trap cleanup INT TERM EXIT

if [[ $WATCH -ne 1 ]]; then
  start_shell
  wait "$SHELL_PID" 2>/dev/null || true
  exit 0
fi

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
  WATCH_PID=""
  echo
  echo "Změna ve zdrojích, restartuji Shell Preview..."
  stop_shell
  sleep 0.5
done
