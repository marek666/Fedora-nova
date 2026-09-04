#!/usr/bin/env bash
set -o pipefail

NOVA_NAME="Fedora Nova"
NOVA_VERSION="0.6.4"
NOVA_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
NOVA_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
NOVA_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
NOVA_APP_DIR="${FEDORA_NOVA_APP_DIR:-$NOVA_DATA_HOME/fedora-nova}"
NOVA_CONFIG_DIR="$NOVA_CONFIG_HOME/fedora-nova"
NOVA_STATE_DIR="$NOVA_STATE_HOME/fedora-nova"
NOVA_CUSTOM_DIR="$NOVA_CONFIG_DIR/custom-profiles"
NOVA_THEMES_DIR="$NOVA_DATA_HOME/themes"
NOVA_WALLPAPER_DIR="$NOVA_DATA_HOME/backgrounds/fedora-nova"
NOVA_PTYXIS_DIR="$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes"
NOVA_AUTOSTART_DIR="$NOVA_CONFIG_HOME/autostart"
NOVA_SESSION_AUTOSTART="$NOVA_AUTOSTART_DIR/fedora-nova-session.desktop"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

schema_exists() {
  command_exists gsettings || return 1
  gsettings list-schemas 2>/dev/null | grep -Fxq "$1"
}

key_exists() {
  local schema="$1" key="$2"
  schema_exists "$schema" || return 1
  gsettings list-keys "$schema" 2>/dev/null | grep -Fxq "$key"
}

try_set() {
  local schema="$1" key="$2" value="$3"
  if ! key_exists "$schema" "$key"; then
    warn "Přeskakuji neznámé nastavení: $schema $key"
    return 0
  fi
  if gsettings set "$schema" "$key" "$value" 2>/dev/null; then
    printf '  set %-57s %s\n' "$schema::$key" "$value"
  else
    warn "Nepodařilo se nastavit $schema $key na $value"
  fi
}

update_enabled_extensions() {
  local mode="$1"
  shift
  schema_exists org.gnome.shell || return 0
  command_exists python3 || return 0
  (($#)) || return 0

  python3 - "$mode" "$@" <<'PY' | xargs -0 -r gsettings set org.gnome.shell enabled-extensions || true
import ast
import subprocess
import sys

mode = sys.argv[1]
uuids = sys.argv[2:]

try:
    raw = subprocess.check_output(
        ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
        text=True,
    ).strip()
    values = ast.literal_eval(raw)
    if not isinstance(values, list):
        values = []
except Exception:
    values = []

values = [str(item) for item in values]
if mode == "add":
    for uuid in uuids:
        if uuid not in values:
            values.append(uuid)
elif mode == "remove":
    values = [uuid for uuid in values if uuid not in uuids]

output = "[" + ", ".join(repr(uuid) for uuid in values) + "]"
sys.stdout.buffer.write(output.encode() + b"\0")
PY
}

enable_extension() {
  local uuid="$1"
  command_exists gnome-extensions || { warn "gnome-extensions není dostupné"; return 0; }
  if gnome-extensions info "$uuid" >/dev/null 2>&1; then
    if gnome-extensions enable "$uuid" >/dev/null 2>&1; then
      printf '  enabled %s\n' "$uuid"
    else
      warn "Rozšíření $uuid se nepodařilo zapnout. Může být nutný relogin."
    fi
    update_enabled_extensions add "$uuid"
  else
    warn "Rozšíření $uuid aktuální GNOME Shell nevidí."
  fi
}

disable_extension() {
  local uuid="$1"
  if command_exists gnome-extensions && gnome-extensions info "$uuid" >/dev/null 2>&1; then
    gnome-extensions disable "$uuid" >/dev/null 2>&1 || true
    printf '  disabled %s\n' "$uuid"
  fi
  update_enabled_extensions remove "$uuid"
}

current_profile() {
  local file="$NOVA_CONFIG_DIR/current-profile"
  if [[ -s "$file" ]]; then cat "$file"; else printf 'tech\n'; fi
}

ensure_gnome_session() {
  command_exists gsettings || die "gsettings není dostupné. Spusť příkaz uvnitř GNOME sezení."
}

current_curve() {
  local file="$NOVA_CONFIG_DIR/current-curve"
  if [[ -s "$file" ]]; then cat "$file"; else printf 'squircle\n'; fi
}

current_icons() {
  local file="$NOVA_CONFIG_DIR/current-icons"
  if [[ -s "$file" ]]; then cat "$file"; else printf 'tela-dark\n'; fi
}

current_hover() {
  local file="$NOVA_CONFIG_DIR/current-hover"
  if [[ -s "$file" ]]; then cat "$file"; else printf 'circle\n'; fi
}

current_gtk() {
  local file="$NOVA_CONFIG_DIR/current-gtk"
  if [[ -s "$file" ]]; then cat "$file"; else printf 'on\n'; fi
}
