#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

PRESET="${1:-list}"
SCHEMA=org.gnome.shell.extensions.dash-to-dock

case "$PRESET" in
  list)
    printf '%-12s %s\n' reduced 'minimum animací; nejlepší diagnostický režim'
    printf '%-12s %s\n' balanced 'výchozí svižné animace'
    printf '%-12s %s\n' smooth 'delší, ale stále bez blur efektu'
    exit 0 ;;
  reduced) ENABLE=false; ANIMATION=0.10; SHOW=0.03; HIDE=0.10 ;;
  balanced) ENABLE=true; ANIMATION=0.18; SHOW=0.08; HIDE=0.16 ;;
  smooth) ENABLE=true; ANIMATION=0.28; SHOW=0.12; HIDE=0.22 ;;
  *) die "Použij: $0 {list|reduced|balanced|smooth}" ;;
esac

ensure_gnome_session
disable_extension blur-my-shell@aunetx
try_set org.gnome.desktop.interface enable-animations "$ENABLE"
try_set "$SCHEMA" animation-time "$ANIMATION"
try_set "$SCHEMA" show-delay "$SHOW"
try_set "$SCHEMA" hide-delay "$HIDE"

mkdir -p "$NOVA_CONFIG_DIR"
printf '%s\n' "$PRESET" > "$NOVA_CONFIG_DIR/current-motion"
log "Pohybový preset: $PRESET (bez blur)"
