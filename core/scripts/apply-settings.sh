#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

PROFILE="$(current_profile)"
SESSION_RESTORE=0
if [[ $# -gt 0 && "${1:-}" != --* ]]; then
  PROFILE="$1"
  shift
fi
while (($#)); do
  case "$1" in
    --session-restore) SESSION_RESTORE=1 ;;
    *) die "Použij: $0 [PROFILE] [--session-restore]" ;;
  esac
  shift
done

if [[ "$PROFILE" == system ]]; then
  log "Aktivní je systémový profil; Fedora Nova session restore přeskakuji."
  exit 0
fi

ensure_gnome_session

log "Aplikuji základní vzhled"
try_set org.gnome.desktop.interface color-scheme "'prefer-dark'"
try_set org.gnome.desktop.interface font-name "'Inter 11'"
try_set org.gnome.desktop.interface document-font-name "'Inter 11'"
try_set org.gnome.desktop.interface monospace-font-name "'JetBrains Mono 11'"
ICON_PRESET="$(current_icons)"
"$SCRIPT_DIR/apply-icons.sh" "$ICON_PRESET"
try_set org.gnome.desktop.interface cursor-theme "'Adwaita'"
try_set org.gnome.desktop.interface enable-animations true
try_set org.gnome.desktop.interface clock-show-weekday true
try_set org.gnome.desktop.interface clock-show-seconds false

log "Aplikuji Mutter a chování oken"
try_set org.gnome.mutter center-new-windows true
try_set org.gnome.mutter dynamic-workspaces true
try_set org.gnome.mutter edge-tiling true
try_set org.gnome.mutter workspaces-only-on-primary false
try_set org.gnome.desktop.wm.preferences button-layout "'appmenu:minimize,maximize,close'"
try_set org.gnome.desktop.wm.preferences focus-mode "'click'"
try_set org.gnome.desktop.wm.preferences resize-with-right-button true
try_set org.gnome.desktop.wm.preferences action-right-click-titlebar "'menu'"

try_set org.gnome.desktop.background picture-options "'zoom'"
try_set org.gnome.desktop.background primary-color "'#08111F'"
try_set org.gnome.desktop.background color-shading-type "'solid'"
try_set org.gnome.desktop.screensaver picture-options "'zoom'"

CURVE="$(current_curve)"
"$SCRIPT_DIR/apply-curve.sh" "$CURVE" --no-reload
HOVER="$(current_hover)"
"$SCRIPT_DIR/apply-hover.sh" "$HOVER"
"$SCRIPT_DIR/apply-profile.sh" "$PROFILE"
DOCK_PRESET="$(cat "$NOVA_CONFIG_DIR/current-dock" 2>/dev/null || echo profile-default)"
if [[ "$DOCK_PRESET" != profile-default ]]; then
  "$SCRIPT_DIR/apply-dock.sh" "$DOCK_PRESET"
fi
"$SCRIPT_DIR/gtk-theme.sh" "$(current_gtk)"
"$SCRIPT_DIR/monitor-panel.sh" on
"$SCRIPT_DIR/disable-welcome.sh" off
if [[ $SESSION_RESTORE -eq 1 ]]; then
  log "Session restore dokončen."
else
  log "Hotovo. Profil synchronizuje plochu, rozšíření i zamykací obrazovku."
fi
