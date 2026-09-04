#!/usr/bin/env bash
set -euo pipefail

ORIGINAL_ARGS=("$@")
SCRIPT_INVOKED_AS="${BASH_SOURCE[0]}"
ENV_BIN="/usr/bin/env"
[[ -x "$ENV_BIN" ]] || ENV_BIN="/bin/env"

sanitize_shell_startup_env() {
  local entry key needs_exec=0
  local -a clean_env=()

  if [[ ! -r "/proc/$$/environ" ]]; then
    unset BASH_ENV ENV || true
    return 0
  fi

  while IFS= read -r -d '' entry; do
    key="${entry%%=*}"
    case "$key" in
      BASH_ENV|ENV)
        needs_exec=1
        continue
        ;;
    esac
    clean_env+=("$entry")
  done < "/proc/$$/environ"

  unset BASH_ENV ENV || true
  if [[ "$needs_exec" -ne 1 ]]; then
    return 0
  fi

  if [[ ! -x "$ENV_BIN" ]]; then
    echo "CHYBA: chybí env." >&2
    exit 1
  fi

  exec "$ENV_BIN" -i "${clean_env[@]}" "$SCRIPT_INVOKED_AS" "${ORIGINAL_ARGS[@]}"
}

sanitize_shell_startup_env

SCRIPT_PATH="$(readlink -f -- "$SCRIPT_INVOKED_AS")"
ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd)"
CORE="$ROOT/core"
PROFILE="tech"
WATCH=0
STOP=0

ORIGINAL_HOME="${HOME:?}"
ORIGINAL_HOME_REAL="$(readlink -m -- "$ORIGINAL_HOME")"
ORIGINAL_PATH="${PATH:-/usr/local/bin:/usr/bin:/bin}"
ORIGINAL_XDG_DATA_HOME="${XDG_DATA_HOME:-$ORIGINAL_HOME/.local/share}"
ORIGINAL_XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

PREVIEW_ROOT="${XDG_CACHE_HOME:-$ORIGINAL_HOME/.cache}/fedora-nova-shell-preview"
PREVIEW_HOME="$PREVIEW_ROOT/home"
PREVIEW_CONFIG="$PREVIEW_ROOT/config"
PREVIEW_DATA="$PREVIEW_ROOT/data"
PREVIEW_CACHE="$PREVIEW_ROOT/cache"
PREVIEW_STATE="$PREVIEW_ROOT/state"
PREVIEW_HOST_EXPORT="$PREVIEW_ROOT/host-export"
PREVIEW_FLATPAK_EXPORT="$PREVIEW_ROOT/flatpak-export"
RUNTIME_DIR="$PREVIEW_ROOT/runtime"
LIVE_LOCK_DIR="$PREVIEW_ROOT/live.lock"
SUPERVISOR_PID_FILE="$RUNTIME_DIR/supervisor.pid"
SESSION_PID_FILE="$RUNTIME_DIR/session.pid"
SESSION_PGID_FILE="$RUNTIME_DIR/session.pgid"
SHELL_CHILD_PID_FILE="$RUNTIME_DIR/shell.pid"
SESSION_META_FILE="$RUNTIME_DIR/session.env"
TOKEN_FILE="$RUNTIME_DIR/preview.token"

PREVIEW_XDG_DATA_DIRS=""
SHELL_PID=""
SHELL_PGID=""
SHELL_CHILD_PID=""
WATCH_PID=""
CLEANUP_DONE=0

is_bootstrap_fd() {
  local fd="${1:-}"
  [[ "$fd" =~ ^[0-9]+$ ]] || return 1
  ((fd >= 10))
}

close_bootstrap_fd() {
  local fd="${1:-}"
  is_bootstrap_fd "$fd" || return 0
  exec {fd}<&- 2>/dev/null || true
}

bootstrap_proof_valid() {
  local fd="${NOVA_PREVIEW_TOKEN_BOOTSTRAP_FD:-}"
  local proof="" proof_pid="" proof_token=""

  is_bootstrap_fd "$fd" || return 1
  [[ -e "/proc/$$/fd/$fd" ]] || return 1
  if ! IFS= read -r -t 1 -u "$fd" proof 2>/dev/null; then
    return 1
  fi

  proof_pid="${proof%%:*}"
  proof_token="${proof#*:}"
  [[ "$proof_pid" == "$$" ]] || return 1
  [[ "$proof_token" == "${NOVA_PREVIEW_TOKEN:-}" ]] || return 1
  [[ "$proof_token" =~ ^[0-9a-fA-F]{32}$ ]]
}

bootstrap_preview_token() {
  local preview_uuid="" proof_fd=""

  if [[ ! -r /proc/sys/kernel/random/uuid ]]; then
    echo "CHYBA: nelze vytvořit bezpečný identifikátor Shell Preview." >&2
    exit 1
  fi

  preview_uuid="$(</proc/sys/kernel/random/uuid)"
  export NOVA_PREVIEW_TOKEN="${preview_uuid//-/}"
  exec {proof_fd}<<<"$$:$NOVA_PREVIEW_TOKEN"
  export NOVA_PREVIEW_TOKEN_BOOTSTRAP_FD="$proof_fd"
  exec "$SCRIPT_PATH" "${ORIGINAL_ARGS[@]}"
}

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

The preview runs in an isolated HOME, XDG and D-Bus session. In --watch mode
the nested GNOME Shell is restarted when anything under core/ changes.
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

unset BASH_ENV ENV || true

# Bootstrap a token we generated ourselves. The inherited FD carries a one-shot
# proof bound to the exec-preserved PID, so a plain environment variable is not
# enough to skip token generation.
if [[ $STOP -ne 1 ]]; then
  unset NOVA_PREVIEW_TOKEN_BOOTSTRAP_PID || true
  bootstrap_fd="${NOVA_PREVIEW_TOKEN_BOOTSTRAP_FD:-}"
  if bootstrap_proof_valid; then
    close_bootstrap_fd "$bootstrap_fd"
    unset NOVA_PREVIEW_TOKEN_BOOTSTRAP_FD
  else
    close_bootstrap_fd "$bootstrap_fd"
    bootstrap_preview_token
  fi

  if [[ ! "${NOVA_PREVIEW_TOKEN:-}" =~ ^[0-9a-fA-F]{32}$ ]]; then
    echo "CHYBA: interní token Shell Preview je neplatný." >&2
    exit 1
  fi
fi

is_pid() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

pid_alive() {
  local pid="$1"
  is_pid "$pid" && kill -0 "$pid" 2>/dev/null
}

read_pid_file() {
  local path="$1"
  local value=""
  [[ -s "$path" ]] && value="$(<"$path")"
  is_pid "$value" && printf '%s\n' "$value"
  return 0
}

read_token_file() {
  local value=""
  [[ -s "$TOKEN_FILE" ]] && value="$(<"$TOKEN_FILE")"
  [[ "$value" =~ ^[0-9a-fA-F]{32}$ ]] && printf '%s\n' "$value"
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
  pid_alive "$pid" || return 1
  process_cmdline "$pid" 2>/dev/null | grep -Fq -- "$pattern"
}

process_has_token() {
  local pid="$1"
  local token="$2"
  pid_alive "$pid" || return 1
  [[ "$token" =~ ^[0-9a-fA-F]{32}$ ]] || return 1
  [[ -r "/proc/$pid/environ" ]] || return 1
  tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null |
    grep -Fxq -- "NOVA_PREVIEW_TOKEN=$token"
}

supervisor_matches_token() {
  local pid="$1"
  local token="$2"
  process_has_token "$pid" "$token"
}

session_matches_token() {
  local pid="$1"
  local token="$2"
  process_matches "$pid" "dbus-run-session" && process_has_token "$pid" "$token"
}

pid_pgid() {
  local pid="$1"
  is_pid "$pid" || return 1
  ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' '
}

group_has_token() {
  local pgid="$1"
  local token="$2"
  local candidate candidate_pgid
  is_pid "$pgid" || return 1
  [[ "$token" =~ ^[0-9a-fA-F]{32}$ ]] || return 1

  while read -r candidate candidate_pgid; do
    [[ "$candidate_pgid" == "$pgid" ]] || continue
    if process_has_token "$candidate" "$token"; then
      return 0
    fi
  done < <(ps -eo pid=,pgid= 2>/dev/null)
  return 1
}

resolve_token_group() {
  local session_pid="$1"
  local shell_pid="$2"
  local stored_pgid="$3"
  local token="$4"
  local actual=""

  if session_matches_token "$session_pid" "$token"; then
    actual="$(pid_pgid "$session_pid")"
    if is_pid "$actual"; then
      printf '%s\n' "$actual"
      return 0
    fi
  fi

  if process_has_token "$shell_pid" "$token"; then
    actual="$(pid_pgid "$shell_pid")"
    if is_pid "$actual"; then
      printf '%s\n' "$actual"
      return 0
    fi
  fi

  if is_pid "$stored_pgid" && group_has_token "$stored_pgid" "$token"; then
    printf '%s\n' "$stored_pgid"
    return 0
  fi

  return 1
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

atomic_write_file() {
  local path="$1"
  local mode="${2:-600}"
  local tmp="${path}.tmp.$$"

  mkdir -p "$(dirname -- "$path")"
  rm -f "$tmp"
  (
    umask 077
    cat > "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$path"
    chmod "$mode" "$path"
  )
}

write_pid_file() {
  local path="$1"
  local pid="$2"
  printf '%s\n' "$pid" | atomic_write_file "$path" 600
}

write_runtime_token() {
  mkdir -p "$RUNTIME_DIR"
  chmod 700 "$RUNTIME_DIR"
  printf '%s\n' "$NOVA_PREVIEW_TOKEN" | atomic_write_file "$TOKEN_FILE" 600
}

clear_session_metadata() {
  rm -f "$SESSION_PID_FILE" "$SESSION_PGID_FILE" "$SHELL_CHILD_PID_FILE" "$SESSION_META_FILE"
}

stop_recorded_session() {
  local session_pid stored_pgid shell_pid token pgid
  session_pid="$(read_pid_file "$SESSION_PID_FILE")"
  stored_pgid="$(read_pid_file "$SESSION_PGID_FILE")"
  shell_pid="$(read_pid_file "$SHELL_CHILD_PID_FILE")"
  token="$(read_token_file)"

  if [[ -z "$session_pid" && -z "$shell_pid" ]]; then
    clear_session_metadata
    return 0
  fi

  if [[ -z "$token" ]]; then
    if pid_alive "$session_pid" || pid_alive "$shell_pid"; then
      echo "CHYBA: preview.token chybí nebo je poškozený; běžící preview nelze bezpečně ověřit." >&2
      return 2
    fi
    clear_session_metadata
    return 0
  fi

  pgid="$(resolve_token_group "$session_pid" "$shell_pid" "$stored_pgid" "$token")" || true
  if is_pid "$pgid"; then
    if ! safe_kill_group "$pgid" TERM; then
      echo "CHYBA: ověřenou process group nelze bezpečně ukončit; metadata ponechávám." >&2
      return 2
    fi
    for _ in {1..40}; do
      group_has_token "$pgid" "$token" || break
      sleep 0.1
    done
    if group_has_token "$pgid" "$token"; then
      if ! safe_kill_group "$pgid" KILL; then
        echo "CHYBA: ověřenou process group nelze bezpečně dorazit; metadata ponechávám." >&2
        return 2
      fi
    fi
    if group_has_token "$pgid" "$token"; then
      echo "CHYBA: ověřená process group po cleanupu stále běží; metadata ponechávám." >&2
      return 2
    fi
    clear_session_metadata
    return 0
  fi

  if pid_alive "$session_pid" || pid_alive "$shell_pid"; then
    echo "CHYBA: token Shell Preview neodpovídá běžící session; nic jsem neukončil." >&2
    return 2
  fi

  clear_session_metadata
  return 0
}

stop_external_preview() {
  local supervisor token stop_rc=0
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"
  token="$(read_token_file)"

  if pid_alive "$supervisor"; then
    if [[ -n "$token" ]] && supervisor_matches_token "$supervisor" "$token"; then
      kill -TERM "$supervisor" 2>/dev/null || true
      for _ in {1..40}; do
        pid_alive "$supervisor" || break
        sleep 0.1
      done
      if pid_alive "$supervisor" && supervisor_matches_token "$supervisor" "$token"; then
        kill -KILL "$supervisor" 2>/dev/null || true
      fi
    else
      echo "CHYBA: supervisor běží, ale runtime token/metadata mu neodpovídají; nic nemažu." >&2
      return 2
    fi
  fi

  if stop_recorded_session; then
    :
  else
    stop_rc=$?
    echo "CHYBA: Shell Preview nebylo možné bezpečně zastavit; runtime metadata zůstávají zachována." >&2
    return "$stop_rc"
  fi

  rm -rf "$LIVE_LOCK_DIR"
  rm -f "$SUPERVISOR_PID_FILE" "$TOKEN_FILE"
  echo "Shell Preview zastaveno."
}

if [[ $STOP -eq 1 ]]; then
  stop_external_preview
  exit $?
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

for command_name in dbus-run-session env setsid ps grep tr python3 readlink; do
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

canonical_data_dir() {
  local candidate="$1"
  [[ -n "$candidate" && -d "$candidate" ]] || return 1
  readlink -m -- "$candidate"
}

append_preview_data_dir() {
  local candidate="$1"
  local canonical=""
  canonical="$(canonical_data_dir "$candidate")" || return 0
  case ":$PREVIEW_XDG_DATA_DIRS:" in
    *":$canonical:"*) return 0 ;;
  esac
  if [[ -n "$PREVIEW_XDG_DATA_DIRS" ]]; then
    PREVIEW_XDG_DATA_DIRS+=":"
  fi
  PREVIEW_XDG_DATA_DIRS+="$canonical"
}

build_preview_data_dirs() {
  local candidate canonical
  local -a host_dirs=()

  PREVIEW_XDG_DATA_DIRS=""
  append_preview_data_dir "$PREVIEW_HOST_EXPORT"
  append_preview_data_dir "$PREVIEW_FLATPAK_EXPORT"

  IFS=':' read -r -a host_dirs <<< "$ORIGINAL_XDG_DATA_DIRS"
  for candidate in "${host_dirs[@]}"; do
    [[ -n "$candidate" ]] || continue
    canonical="$(canonical_data_dir "$candidate")" || continue
    case "$canonical" in
      "$ORIGINAL_HOME_REAL"|"$ORIGINAL_HOME_REAL"/*) continue ;;
    esac
    append_preview_data_dir "$canonical"
  done

  append_preview_data_dir "/var/lib/flatpak/exports/share"
  append_preview_data_dir "/usr/local/share"
  append_preview_data_dir "/usr/share"
}

prepare_export_view() {
  local source="$1"
  local target="$2"
  local item

  rm -rf "$target"
  mkdir -p "$target"
  [[ -d "$source" ]] || return 0

  for item in applications icons mime metainfo; do
    if [[ -e "$source/$item" ]]; then
      ln -s "$source/$item" "$target/$item"
    fi
  done
}

prepare_host_exports() {
  local user_flatpak_share="$ORIGINAL_HOME/.local/share/flatpak/exports/share"
  prepare_export_view "$ORIGINAL_XDG_DATA_HOME" "$PREVIEW_HOST_EXPORT"
  prepare_export_view "$user_flatpak_share" "$PREVIEW_FLATPAK_EXPORT"
  build_preview_data_dirs
}

acquire_live_lock() {
  mkdir -p "$PREVIEW_ROOT" "$RUNTIME_DIR"
  chmod 700 "$RUNTIME_DIR"

  if mkdir "$LIVE_LOCK_DIR" 2>/dev/null; then
    chmod 700 "$LIVE_LOCK_DIR"
    write_pid_file "$SUPERVISOR_PID_FILE" "$$"
    write_runtime_token
    return 0
  fi

  local supervisor recorded_token
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"
  recorded_token="$(read_token_file)"

  if pid_alive "$supervisor"; then
    if [[ -n "$recorded_token" ]] && supervisor_matches_token "$supervisor" "$recorded_token"; then
      echo "Shell Preview už běží. Zavři jeho okno nebo spusť ./dev-shell-preview.sh --stop." >&2
      exit 2
    fi
    echo "CHYBA: existuje live lock s běžícím, ale neověřitelným supervisorem; nic nemažu." >&2
    exit 2
  fi

  if ! stop_recorded_session; then
    echo "CHYBA: stale preview nelze bezpečně uklidit; live lock zachovávám." >&2
    exit 2
  fi

  rm -rf "$LIVE_LOCK_DIR"
  mkdir "$LIVE_LOCK_DIR"
  chmod 700 "$LIVE_LOCK_DIR"
  write_pid_file "$SUPERVISOR_PID_FILE" "$$"
  write_runtime_token
}

release_live_lock() {
  local supervisor token
  supervisor="$(read_pid_file "$SUPERVISOR_PID_FILE")"
  token="$(read_token_file)"
  if [[ ! -d "$LIVE_LOCK_DIR" && -z "$supervisor" && -z "$token" ]]; then
    return 0
  fi
  if [[ "$supervisor" == "$$" && -n "$token" && "$token" == "${NOVA_PREVIEW_TOKEN:-}" ]]; then
    rm -rf "$LIVE_LOCK_DIR"
    rm -f "$SUPERVISOR_PID_FILE" "$TOKEN_FILE"
    return 0
  fi
  echo "CHYBA: live lock nepatří tomuto ověřenému preview procesu; diagnostiku ponechávám." >&2
  return 2
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
    "$PREVIEW_HOME" \
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
  chmod 700 "$PREVIEW_HOME" "$RUNTIME_DIR"

  prepare_host_exports

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

  local tela_install_log="$PREVIEW_STATE/tela-install.log"
  if ! XDG_DATA_HOME="$PREVIEW_DATA" \
    XDG_CACHE_HOME="$PREVIEW_CACHE" \
    FEDORA_NOVA_APP_DIR="$CORE" \
    "$CORE/scripts/install-tela-icons.sh" >"$tela_install_log" 2>&1; then
    echo "CHYBA: nepodařilo se připravit Tela Circle pro Shell Preview." >&2
    tail -n 80 "$tela_install_log" >&2 || true
    return 1
  fi
  if [[ ! -f "$PREVIEW_DATA/icons/Tela-circle-dark/index.theme" ]]; then
    echo "CHYBA: Tela-circle-dark se po instalaci v preview nenachází." >&2
    return 1
  fi
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
  export HOME="$PREVIEW_HOME"
  export PATH="$ORIGINAL_PATH"
  export XDG_CONFIG_HOME="$PREVIEW_CONFIG"
  export XDG_DATA_HOME="$PREVIEW_DATA"
  export XDG_CACHE_HOME="$PREVIEW_CACHE"
  export XDG_STATE_HOME="$PREVIEW_STATE"
  export XDG_DATA_DIRS="$PREVIEW_XDG_DATA_DIRS"

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
  export NOVA_PREVIEW_ICON_THEME="Tela-circle-dark"
  export NOVA_PREVIEW_DOCK_COLOR="$DOCK_COLOR"
  export NOVA_PREVIEW_DOCK_OPACITY="$DOCK_OPACITY"
  export NOVA_PREVIEW_DOCK_SIZE="$DOCK_SIZE"
  export NOVA_PREVIEW_SHELL_PID_FILE="$SHELL_CHILD_PID_FILE"
}

print_banner() {
  echo
  echo "Fedora Nova Shell Preview"
  echo "========================="
  echo "Profil:      $PROFILE"
  echo "Shell theme: $THEME"
  echo "Wallpaper:   $WALLPAPER"
  echo "Izolace:     $PREVIEW_ROOT"
  echo "Home:        izolovaný"
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

rm -f "$NOVA_PREVIEW_SHELL_PID_FILE"
(
  umask 077
  printf "%s\n" "$$" > "$NOVA_PREVIEW_SHELL_PID_FILE"
  chmod 600 "$NOVA_PREVIEW_SHELL_PID_FILE"
)

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
  local started_at mode
  started_at="$(date --iso-8601=seconds 2>/dev/null || date)"
  mode="once"
  [[ $WATCH -eq 1 ]] && mode="watch"

  write_pid_file "$SESSION_PID_FILE" "$SHELL_PID"
  write_pid_file "$SESSION_PGID_FILE" "$SHELL_PGID"
  write_pid_file "$SHELL_CHILD_PID_FILE" "$SHELL_CHILD_PID"

  {
    printf 'format_version=5\n'
    printf 'preview_token=%q\n' "$NOVA_PREVIEW_TOKEN"
    printf 'supervisor_pid=%q\n' "$$"
    printf 'session_pid=%q\n' "$SHELL_PID"
    printf 'shell_pid=%q\n' "$SHELL_CHILD_PID"
    printf 'process_group_id=%q\n' "$SHELL_PGID"
    printf 'profile=%q\n' "$PROFILE"
    printf 'mode=%q\n' "$mode"
    printf 'repo_root=%q\n' "$ROOT"
    printf 'preview_root=%q\n' "$PREVIEW_ROOT"
    printf 'preview_home=%q\n' "$PREVIEW_HOME"
    printf 'path=%q\n' "$ORIGINAL_PATH"
    printf 'xdg_data_dirs=%q\n' "$PREVIEW_XDG_DATA_DIRS"
    printf 'started_at=%q\n' "$started_at"
  } | atomic_write_file "$SESSION_META_FILE" 600
}

start_shell() {
  load_profile
  prepare_preview_root
  export_preview_env
  print_banner

  rm -f "$SHELL_CHILD_PID_FILE"
  # A non-login shell preserves the explicitly prepared preview environment.
  # We intentionally do not source /etc/profile or files from PREVIEW_HOME.
  setsid dbus-run-session -- env -u BASH_ENV -u ENV bash -c "$SESSION_SCRIPT" &
  SHELL_PID=$!

  SHELL_PGID=""
  for _ in {1..20}; do
    SHELL_PGID="$(pid_pgid "$SHELL_PID")"
    is_pid "$SHELL_PGID" && break
    sleep 0.05
  done
  if ! is_pid "$SHELL_PGID"; then
    echo "CHYBA: nepodařilo se zjistit process group Shell Preview." >&2
    kill "$SHELL_PID" 2>/dev/null || true
    wait "$SHELL_PID" 2>/dev/null || true
    return 1
  fi

  SHELL_CHILD_PID=""
  for _ in {1..40}; do
    SHELL_CHILD_PID="$(read_pid_file "$SHELL_CHILD_PID_FILE")"
    if is_pid "$SHELL_CHILD_PID" && process_has_token "$SHELL_CHILD_PID" "$NOVA_PREVIEW_TOKEN"; then
      break
    fi
    SHELL_CHILD_PID=""
    sleep 0.05
  done
  if ! is_pid "$SHELL_CHILD_PID"; then
    echo "CHYBA: nested Shell nezapsal ověřitelný shell PID." >&2
    safe_kill_group "$SHELL_PGID" TERM
    wait "$SHELL_PID" 2>/dev/null || true
    return 1
  fi

  record_session_metadata
}

stop_shell() {
  local wait_pid="${SHELL_PID:-}"
  local rc=0

  if stop_recorded_session; then
    if is_pid "$wait_pid"; then
      wait "$wait_pid" 2>/dev/null || true
    fi
    SHELL_PID=""
    SHELL_PGID=""
    SHELL_CHILD_PID=""
    return 0
  else
    rc=$?
    return "$rc"
  fi
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
  local rc=0
  if [[ -n "${WATCH_PID:-}" ]] && kill -0 "$WATCH_PID" 2>/dev/null; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi
  WATCH_PID=""

  if stop_shell; then
    if release_live_lock; then
      return 0
    else
      rc=$?
      echo "VAROVÁNÍ: live lock nebyl bezpečně uvolněn; runtime metadata ponechávám." >&2
      return "$rc"
    fi
  else
    rc=$?
    echo "VAROVÁNÍ: preview session nebyla bezpečně uklizena; runtime metadata ponechávám." >&2
    return "$rc"
  fi
}

run_cleanup_once() {
  if [[ "$CLEANUP_DONE" -eq 1 ]]; then
    return 0
  fi
  CLEANUP_DONE=1
  cleanup
}

exit_with_cleanup() {
  local main_rc="$1"
  local cleanup_rc=0

  trap - EXIT INT TERM
  if run_cleanup_once; then
    cleanup_rc=0
  else
    cleanup_rc=$?
  fi

  if [[ "$main_rc" -ne 0 ]]; then
    exit "$main_rc"
  fi
  exit "$cleanup_rc"
}

handle_exit() {
  local main_rc=$?
  exit_with_cleanup "$main_rc"
}

handle_int() {
  exit_with_cleanup 130
}

handle_term() {
  exit_with_cleanup 143
}

acquire_live_lock
trap handle_exit EXIT
trap handle_int INT
trap handle_term TERM

if [[ $WATCH -ne 1 ]]; then
  if start_shell; then
    :
  else
    rc=$?
    exit_with_cleanup "$rc"
  fi
  wait "$SHELL_PID" 2>/dev/null || true
  exit_with_cleanup 0
fi

while true; do
  if start_shell; then
    :
  else
    rc=$?
    exit_with_cleanup "$rc"
  fi
  start_watcher

  wait -n "$SHELL_PID" "$WATCH_PID" 2>/dev/null || true

  if ! kill -0 "$SHELL_PID" 2>/dev/null; then
    if stop_shell; then
      exit_with_cleanup 0
    else
      rc=$?
      exit_with_cleanup "$rc"
    fi
  fi

  if kill -0 "$WATCH_PID" 2>/dev/null; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi

  wait "$WATCH_PID" 2>/dev/null || true
  WATCH_PID=""
  echo
  echo "Změna ve zdrojích, restartuji Shell Preview..."
  if stop_shell; then
    :
  else
    rc=$?
    exit_with_cleanup "$rc"
  fi
  sleep 0.5
done
