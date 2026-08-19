#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
PRESET="${1:-list}"
SCHEMA=org.gnome.shell.extensions.dash-to-dock

case "$PRESET" in
  list)
    printf '%-12s %s\n' compact '36 px, opacity 0.66, rychlý autohide'
    printf '%-12s %s\n' balanced '42 px, opacity 0.78'
    printf '%-12s %s\n' showcase '48 px, opacity 0.88'
    printf '%-12s %s\n' hidden 'dock se ukáže až u spodní hrany'
    exit 0 ;;
  compact) SIZE=36; OPACITY=0.66; DELAY=0.04 ;;
  balanced) SIZE=42; OPACITY=0.78; DELAY=0.08 ;;
  showcase) SIZE=48; OPACITY=0.88; DELAY=0.10 ;;
  hidden) SIZE=40; OPACITY=0.72; DELAY=0.18 ;;
  *) die "Použij: $0 {list|compact|balanced|showcase|hidden}" ;;
esac

ensure_gnome_session
enable_extension dash-to-dock@micxgx.gmail.com
try_set "$SCHEMA" dash-max-icon-size "$SIZE"
try_set "$SCHEMA" background-opacity "$OPACITY"
try_set "$SCHEMA" show-delay "$DELAY"
try_set "$SCHEMA" autohide true
try_set "$SCHEMA" intellihide true
if [[ "$PRESET" == hidden ]]; then
  try_set "$SCHEMA" require-pressure-to-show true
else
  try_set "$SCHEMA" require-pressure-to-show false
fi
mkdir -p "$NOVA_CONFIG_DIR"
printf '%s\n' "$PRESET" > "$NOVA_CONFIG_DIR/current-dock"
log "Dock preset: $PRESET"
